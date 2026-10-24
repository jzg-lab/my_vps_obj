"""Node metric failures must not become zeros or remove inventory rows."""

from datetime import UTC, datetime
from typing import cast
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock

import pytest

from bot.app.web.admin_console_node_metrics import parse_node_system
from bot.app.web.admin_console_nodes_panel import NodeInventoryReader
from bot.services.panel_api_service import PanelApiService


def system_sample() -> dict[str, object]:
    return {
        "info": {"cpus": 4, "cpuModel": "Example CPU", "memoryTotal": 4096},
        "stats": {
            "memoryFree": 4096,
            "memoryUsed": 0,
            "loadAvg": [0, 0.5, 1.25],
            "uptime": 0,
            "interface": {
                "interface": "eth0",
                "rxBytesPerSec": 0,
                "txBytesPerSec": 512.5,
                "rxTotal": 0,
                "txTotal": 1024,
            },
        },
    }


def test_known_values_units_and_sample_time_are_preserved() -> None:
    result = parse_node_system(system_sample())
    assert result.cpu_cores == 4 and result.cpu_model == "Example CPU"
    assert (result.memory_total_bytes, result.memory_free_bytes, result.memory_used_bytes) == (
        4096,
        4096,
        0,
    )
    assert (result.load_1m, result.load_5m, result.load_15m) == (0, 0.5, 1.25)
    assert result.uptime_seconds == 0 and result.interface_name == "eth0"
    assert (result.rx_bytes_per_second, result.tx_bytes_per_second) == (0, 512.5)
    assert (result.rx_total_bytes, result.tx_total_bytes) == (0, 1024)
    assert result.invalid_fields == [] and result.sampled_at is None


@pytest.mark.parametrize("raw", [None, {}, {"info": None, "stats": None}])
def test_missing_is_not_invalid_or_zero(raw: object) -> None:
    result = parse_node_system(raw)
    assert result.invalid_fields == []
    assert all(
        value is None for key, value in result.model_dump().items() if key != "invalid_fields"
    )


@pytest.mark.parametrize("raw", [True, "0", 0, [], [1, 2, 3]])
def test_invalid_system_never_raises_or_becomes_empty_success(raw: object) -> None:
    result = parse_node_system(raw)
    assert len(result.invalid_fields) == 14
    assert result.memory_used_bytes is None and result.sampled_at is None


@pytest.mark.parametrize(
    "bad", [True, False, "0", -1, float("nan"), float("inf"), -float("inf"), [], {}, 10**1000]
)
def test_bad_leaf_is_isolated_and_json_remains_finite(bad: object) -> None:
    raw = system_sample()
    stats = cast(dict[str, object], raw["stats"])
    stats["memoryUsed"] = bad
    result = parse_node_system(raw)
    assert result.memory_used_bytes is None
    assert result.invalid_fields == ["memory_used_bytes"]
    assert result.memory_free_bytes == 4096 and result.rx_bytes_per_second == 0
    assert "NaN" not in result.model_dump_json() and "Infinity" not in result.model_dump_json()


def test_partial_load_and_invalid_network_do_not_hide_other_metrics() -> None:
    result = parse_node_system(
        {
            "info": {"cpus": True, "cpuModel": [], "memoryTotal": None},
            "stats": {"memoryUsed": 0, "loadAvg": [0, "1", 2], "interface": False},
        }
    )
    assert result.cpu_cores is None and result.cpu_model is None
    assert result.memory_total_bytes is None and "memory_total_bytes" not in result.invalid_fields
    assert (result.load_1m, result.load_5m, result.load_15m) == (0, None, 2)
    assert "load_5m" in result.invalid_fields and "load_1m" not in result.invalid_fields
    assert (
        "interface_name" in result.invalid_fields and "rx_bytes_per_second" in result.invalid_fields
    )
    assert result.memory_used_bytes == 0


@pytest.mark.parametrize("bad", [[], [1, 2], [1, 2, 3, 4], "1,2,3", {"0": 1}])
def test_load_requires_three_ordered_windows(bad: object) -> None:
    result = parse_node_system({"stats": {"loadAvg": bad}})
    assert result.invalid_fields == ["load_1m", "load_5m", "load_15m"]


@pytest.mark.parametrize("bad", [True, 0, -1, 1.5, "4", 2**53])
def test_core_count_is_a_positive_safe_integer(bad: object) -> None:
    result = parse_node_system({"info": {"cpus": bad}})
    assert result.cpu_cores is None and result.invalid_fields == ["cpu_cores"]


@pytest.mark.parametrize("bad", [False, "", "  ", "x" * 257, []])
def test_text_metrics_are_bounded_nonempty_strings(bad: object) -> None:
    result = parse_node_system({"info": {"cpuModel": bad}})
    assert result.cpu_model is None and result.invalid_fields == ["cpu_model"]


def test_extra_payload_and_fabricated_sample_time_are_not_exposed() -> None:
    result = parse_node_system(
        {
            "info": {"cpuModel": " Example CPU ", "hostname": "SECRET_HOST"},
            "sampled_at": "2026-10-24T00:00:00Z",
            "cpuPercent": 99,
            "stats": {"memoryFree": 0, "rawConfig": "SECRET_CONFIG"},
        }
    )
    assert result.cpu_model == "Example CPU" and result.sampled_at is None
    assert "SECRET" not in result.model_dump_json() and "cpuPercent" not in result.model_dump_json()


def test_node_placeholder_model_is_missing_not_hardware_information() -> None:
    result = parse_node_system({"info": {"cpuModel": "unknown"}})
    assert result.cpu_model is None and result.invalid_fields == []


class NodeMetricsInventoryTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.node: dict[str, object] = {
            "uuid": "00000000-0000-0000-0000-000000000001",
            "name": "Node",
            "isConnected": True,
            "usersOnline": 0,
            "system": system_sample(),
            "configProfile": {"activeInbounds": []},
        }
        self.fail_requests = False

        async def read(method: str, endpoint: str, **kwargs: object) -> dict[str, object]:
            assert method == "GET" and kwargs["log_full_response"] is False
            assert endpoint in {"/nodes", "/hosts", "/internal-squads"}
            if self.fail_requests:
                raise RuntimeError("SECRET_UPSTREAM_ERROR")
            return {"response": [self.node] if endpoint == "/nodes" else []}

        panel = Mock(spec=PanelApiService)
        self.request = AsyncMock(side_effect=read)
        panel._request = self.request
        self.panel = cast(PanelApiService, panel)
        self.reader = NodeInventoryReader()

    async def test_invalid_metrics_keep_inventory_without_verifying_zero_identities(self) -> None:
        self.node["system"] = {"stats": {"memoryUsed": "bad", "memoryFree": 0}}
        inventory = await self.reader.read(self.panel, ttl_seconds=60)
        assert inventory.coverage == "complete" and len(inventory.nodes.rows) == 1
        node = inventory.node_out(inventory.nodes.rows[0])
        assert node.users_online is None and node.users_online_quality == "unverified_zero"
        assert node.system.memory_free_bytes == 0
        assert node.system.invalid_fields == ["memory_used_bytes"]

    async def test_zero_is_unverified_even_when_system_cache_is_healthy(self) -> None:
        for raw in (None, False, {}, system_sample()):
            with self.subTest(raw=raw):
                self.node["system"] = raw
                inventory = await self.reader.read(self.panel, ttl_seconds=0)
                node = inventory.node_out(inventory.nodes.rows[0])
                assert node.users_online is None and node.users_online_quality == "unverified_zero"
                assert node.status == "online"
        self.node["usersOnline"] = 7
        inventory = await self.reader.read(self.panel, ttl_seconds=0)
        node = inventory.node_out(inventory.nodes.rows[0])
        assert node.users_online == 7 and node.users_online_quality == "reported"

    async def test_missing_or_invalid_identities_do_not_become_zero(self) -> None:
        for raw in (None, True, -1, "0", 1.5):
            with self.subTest(raw=raw):
                self.node["usersOnline"] = raw
                inventory = await self.reader.read(self.panel, ttl_seconds=0)
                node = inventory.node_out(inventory.nodes.rows[0])
                assert node.users_online is None and node.users_online_quality == "missing"
                assert node.system.cpu_cores == 4

    async def test_cached_read_preserves_read_time_without_inventing_sample_time(self) -> None:
        first = await self.reader.read(self.panel, ttl_seconds=60)
        original = first.node_out(first.nodes.rows[0])
        cached = await self.reader.read(self.panel, ttl_seconds=60)
        repeated = cached.node_out(cached.nodes.rows[0])
        assert self.request.await_count == 3
        assert original.observed_at == repeated.observed_at
        assert original.observed_at is not None and original.observed_at <= datetime.now(UTC)
        assert repeated.system.sampled_at is None

    async def test_failure_and_stale_cache_are_distinct_from_missing_metrics(self) -> None:
        self.node["usersOnline"] = 7
        first = await self.reader.read(self.panel, ttl_seconds=0)
        original = first.node_out(first.nodes.rows[0])
        self.fail_requests = True
        stale = await self.reader.read(self.panel, ttl_seconds=0)
        node = stale.node_out(stale.nodes.rows[0])
        assert stale.nodes.source.availability == "stale"
        assert stale.nodes.source.error == "request_failed" and node.status == "unknown"
        assert node.system.memory_used_bytes == 0 and node.observed_at == original.observed_at
        assert node.users_online == 7 and node.users_online_quality == "reported"
        assert stale.nodes.source.last_success_at is not None
        assert stale.nodes.source.attempted_at >= stale.nodes.source.last_success_at
        assert node.system.sampled_at is None
        failed = await NodeInventoryReader().read(self.panel, ttl_seconds=0)
        assert failed.nodes.source.availability == "unavailable" and failed.nodes.rows == []
        assert failed.nodes.source.last_success_at is None
        assert "SECRET" not in failed.nodes.source.model_dump_json()
        self.fail_requests = False
        recovered = await self.reader.read(self.panel, ttl_seconds=0)
        assert recovered.nodes.source.availability == "available"
        assert recovered.nodes.source.error is None
        assert recovered.node_out(recovered.nodes.rows[0]).status == "online"
