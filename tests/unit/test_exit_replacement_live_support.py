"""Offline exit fixture guards; no sockets, live locks, Docker or PostgreSQL."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from bot.services.panel_api_service import PanelApiService
from tests.integration import test_exit_replacement_live_node as acceptance
from tests.support import exit_replacement_live_node as harness
from tests.support import service_operations_live_node as shared


def offline_node(directory: Path) -> harness.ExitNode:
    node = object.__new__(harness.ExitNode)
    node.directory = directory
    node.directory.mkdir()
    node.manifest = directory / "manifest.json"
    node.state = {
        "run_id": uuid4().hex,
        "context": shared.CONTEXT,
        "image": shared.IMAGE,
        "resources": [],
        "services": [],
        "containers": [],
        "baseline": {},
        "schema": None,
    }
    node.prefix = "uc2-" + str(node.state["run_id"])[:12]
    node.evidence = {"node_image_id": "sha256:offline", "state": "failed"}
    node.ports = []
    node.last_probe = {}
    node.panel = Mock(spec=PanelApiService)
    node.save()
    return node


def test_default_skip_precedes_every_environment_and_resource_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QA_SERVICE_OPERATIONS_LIVE_NODE", raising=False)
    forbidden = Mock(side_effect=AssertionError("Offline skip touched live infrastructure"))
    for name in ("require_exit_environment", "scenario", "_panel_service", "ExitNode"):
        monkeypatch.setattr(acceptance, name, forbidden)
    with pytest.raises(pytest.skip.Exception):
        acceptance.run_local_exit_replacement()
    forbidden.assert_not_called()
    monkeypatch.setattr(shared, "_read_env", forbidden)
    with pytest.raises(ValueError, match="Explicit QA_SERVICE_OPERATIONS_LIVE_NODE"):
        harness.require_exit_environment()
    forbidden.assert_not_called()


@pytest.mark.parametrize("directory", [None, "", "relative/artifacts"])
def test_adapter_is_mandatory_and_absolute(
    directory: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(harness, "require_environment", lambda: "offline-database")
    if directory is None:
        monkeypatch.delenv(harness.ADAPTER_ENV, raising=False)
    else:
        monkeypatch.setenv(harness.ADAPTER_ENV, directory)
    with pytest.raises(ValueError, match="explicit absolute r3"):
        harness.require_exit_environment()


def test_reviewed_artifacts_can_move_without_weakening_shared_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(harness, "require_environment", lambda: "offline-database")
    monkeypatch.setenv(harness.ADAPTER_ENV, str(tmp_path / "other-artifacts"))
    assert harness.require_exit_environment() == "offline-database"


def test_stale_imported_database_cannot_bypass_local_environment_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QA_SERVICE_OPERATIONS_LIVE_NODE", "1")
    monkeypatch.setattr(acceptance, "require_exit_environment", lambda: "validated-local-db")
    monkeypatch.setattr(acceptance, "SCENARIO_DATABASE_URL", "different-imported-db")
    forbidden = Mock(side_effect=AssertionError("No schema or panel should be touched"))
    monkeypatch.setattr(acceptance, "scenario", forbidden)
    monkeypatch.setattr(acceptance, "_panel_service", forbidden)
    with pytest.raises(ValueError, match="before importing tests"):
        acceptance.run_local_exit_replacement()
    forbidden.assert_not_called()


@pytest.mark.parametrize(
    "change",
    [
        {"closed": False},
        {"error": "TimeoutError"},
        {"peer": "172.19.0.3"},
        {"up": True},
        {"down": -1},
        {"up": 20},
    ],
)
def test_ledger_cannot_turn_unknown_or_wrong_exit_into_usage_evidence(
    change: dict[str, object],
) -> None:
    row = {"closed": True, "error": None, "peer": "172.19.0.2", "up": 21, "down": 16}
    with pytest.raises(AssertionError):
        harness.ledger_totals([row | change], expected_peer="172.19.0.2")


@pytest.mark.parametrize("operation", [b"P", b"U", b"D", b"H"])
def test_actual_origin_protocol_counts_both_directions_without_network(operation: bytes) -> None:
    async def run() -> None:
        namespace: dict[str, object] = {"__name__": "offline_origin"}
        exec(compile(harness.ORIGIN, "controlled-origin", "exec"), namespace)
        size = 128
        token = uuid4()
        reader = asyncio.StreamReader()
        reader.feed_data(operation + size.to_bytes(4, "big") + token.bytes)
        if operation == b"U":
            reader.feed_data(b"u" * size)
        reader.feed_eof()
        writer = Mock()
        writer.get_extra_info.return_value = ("172.19.0.2", 45000)
        writer.drain = AsyncMock()
        writer.wait_closed = AsyncMock()
        handler = namespace["handle"]
        assert callable(handler)
        await handler(reader, writer)
        values = namespace["rows"]
        assert isinstance(values, list) and len(values) == 1
        rows = [shared.object_dict(row) for row in values]
        assert rows[0]["token"] == token.hex
        assert harness.ledger_totals(rows, expected_peer="172.19.0.2") == (
            21 + (size if operation == b"U" else 0),
            16 if operation == b"P" else 1 if operation == b"U" else size,
        )
        writer.close.assert_called_once()

    asyncio.run(run())


def test_pair_manifests_have_separate_ownership_and_reject_foreign_recovery(tmp_path: Path) -> None:
    root = offline_node(tmp_path / "root")
    target = root.target()
    assert root.state["target_manifest"] == "target/manifest.json"
    assert target.state["parent_run_id"] == root.state["run_id"]
    assert root.prefix != target.prefix
    root.remember_service("a" * 32)
    assert target.rows("services") == []
    assert root.manifest.stat().st_mode & 0o777 == 0o600
    assert target.manifest.stat().st_mode & 0o777 == 0o600
    recovered = root.target(recover=True)
    assert recovered.state == target.state
    assert recovered.companion is root and root.companion is recovered
    recovered.state["parent_run_id"] = "b" * 32
    recovered.save()
    with pytest.raises(AssertionError):
        root.target(recover=True)


def test_target_profile_uses_run_unique_tag_and_preserves_scoped_routing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = offline_node(tmp_path / "root")
    root.origin_ip = "172.19.0.2"
    target = root.target()
    profile: dict[str, object] = {}

    async def capture_profile(endpoint: str, payload: dict[str, object]) -> str:
        assert endpoint == "/config-profiles"
        profile.update(payload)
        raise RuntimeError("Offline profile captured")

    monkeypatch.setattr(target, "create_resource", capture_profile)
    forbidden = AsyncMock(side_effect=AssertionError("Offline test touched infrastructure"))
    for name in ("api", "docker", "container", "wait_ready"):
        monkeypatch.setattr(target, name, forbidden)
    with pytest.raises(RuntimeError, match="Offline profile captured"):
        asyncio.run(target.setup_target())
    forbidden.assert_not_called()
    assert profile["name"] == target.prefix
    config = shared.object_dict(profile["config"])
    inbounds = config["inbounds"]
    assert isinstance(inbounds, list) and len(inbounds) == 1
    inbound = shared.object_dict(inbounds[0])
    tag = inbound["tag"]
    assert tag == "UC2_VLESS_" + str(target.state["run_id"])
    assert tag != "UC2_VLESS"
    rules = shared.object_dict(config["routing"])["rules"]
    assert isinstance(rules, list) and len(rules) == 2
    for rule in rules:
        assert shared.object_dict(rule)["inboundTag"] == [tag]
    # Normalizing only tags must leave the exact origin /32, port and deny rules intact.
    inbound["tag"] = "UC2_VLESS"
    for rule in rules:
        shared.object_dict(rule)["inboundTag"] = ["UC2_VLESS"]
    assert config == shared.node_config(root.origin_ip)


@pytest.mark.parametrize("service_index", [1, 2])
def test_retained_hash_covers_formal_service_port_and_identity_not_probe(
    tmp_path: Path, service_index: int
) -> None:
    node = offline_node(tmp_path / "root")
    node.ports = [19000 + index for index in range(service_index + 1)]
    service_identity = str(uuid4())
    for index in range(service_index + 1):
        config = {
            "outbounds": [
                {
                    "settings": {
                        "vnext": [
                            {
                                "address": node.prefix + "-node",
                                "port": 12080,
                                "users": [
                                    {
                                        "id": service_identity
                                        if index == service_index
                                        else str(uuid4())
                                    }
                                ],
                            }
                        ]
                    }
                }
            ]
        }
        path = node.directory / f"client-{index}.json"
        shared.private_json(path, config)
        node.state[f"client_{index}_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    proof = harness.retained_client(node, node.ports[service_index], service_identity)
    assert proof["client_index"] == service_index
    assert proof["socks_port"] == node.ports[service_index]
    assert service_identity not in json.dumps(proof)
    with pytest.raises(AssertionError, match="not the service credential"):
        harness.retained_client(node, node.ports[0], service_identity)
    path = node.directory / f"client-{service_index}.json"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(AssertionError):
        harness.retained_client(node, node.ports[service_index], service_identity)


@pytest.mark.parametrize("fail_once", [False, True])
def test_real_manifest_cleanup_orders_identities_before_groups_and_recovers_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail_once: bool
) -> None:
    async def run() -> None:
        root = offline_node(tmp_path / "root")
        env = tmp_path / "project.env"
        env.write_text("PANEL_WRITE_MODE=dry_run\n")
        monkeypatch.setattr(shared, "PROJECT_ENV", env)
        inventories: dict[str, list[dict[str, object]]] = {key: [] for key in shared.RESOURCE_KEYS}
        # Keep a foreign profile to prove neither half deletes or masks baseline resources.
        foreign_id = str(uuid4())
        inventories["/config-profiles"].append({"uuid": foreign_id, "name": "baseline-profile"})

        async def inventory(endpoint: str) -> list[dict[str, object]]:
            return list(inventories[endpoint])

        monkeypatch.setattr(root, "inventory", inventory)
        root.state["baseline"] = await root.baseline()
        root.state["env_sha256"] = hashlib.sha256(env.read_bytes()).hexdigest()
        root.save()
        target = root.target()
        identities = {"a" * 32, "b" * 32}
        root.remember_service("a" * 32)
        target.remember_service("a" * 32)
        target.remember_service("b" * 32)
        actions: list[str] = []

        async def lookup(*, username: str) -> list[dict[str, object]]:
            identity = username.removeprefix("svc_")
            return (
                [
                    {
                        "uuid": identity,
                        "username": username,
                        "description": "my_vps_obj:service:" + identity,
                    }
                ]
                if identity in identities
                else []
            )

        async def delete_user(reference: str) -> bool:
            actions.append("identity:" + reference)
            identities.remove(reference)
            return True

        monkeypatch.setattr(root.panel, "get_users_by_filter", lookup)
        monkeypatch.setattr(root.panel, "delete_user_from_panel", delete_user)
        should_fail = fail_once

        async def api(method: str, endpoint: str, payload: object = None) -> None:
            nonlocal should_fail
            assert method == "DELETE" and not identities, "Resources deleted before identities"
            path, reference = endpoint.rsplit("/", 1)
            assert reference != foreign_id
            actions.append(endpoint)
            if should_fail and path == "/internal-squads":
                should_fail = False
                raise OSError("offline cleanup failure")
            inventories[path] = [row for row in inventories[path] if row["uuid"] != reference]

        containers: dict[str, str] = {}

        async def docker(*args: str) -> str:
            if args[0] == "ps":
                name = args[-1].removeprefix("name=^/").removesuffix("$")
                return name if name in containers else ""
            if args[0] == "inspect":
                return containers[args[-1]]
            assert args[:2] == ("rm", "-f") and args[-1] in containers
            del containers[args[-1]]
            actions.append("container:" + args[-1])
            return ""

        for node in (root, target):
            monkeypatch.setattr(node, "api", api)
            monkeypatch.setattr(node, "docker", docker)
            resources: list[dict[str, object]] = []
            for endpoint in ("/config-profiles", "/internal-squads", "/nodes", "/hosts"):
                reference = str(uuid4())
                key = shared.RESOURCE_KEYS[endpoint][1]
                inventories[endpoint].append({"uuid": reference, key: node.prefix})
                resources.append({"endpoint": endpoint, "name": node.prefix, "uuid": reference})
            # Lost POST response: cleanup must recover exactly the matching run name/UUID.
            if node is target:
                resources[2]["uuid"] = None
            node.state["resources"] = resources
            name = node.prefix + "-node"
            node.state["containers"] = [{"name": name}]
            containers[name] = str(node.state["run_id"])
            (node.directory / "node.env").write_text("DO_NOT_REPORT_SECRET")
            node.save()
        if fail_once:
            with pytest.raises(AssertionError, match="retain both manifests"):
                await harness.cleanup_pair(root)
            assert root.manifest.exists() and target.manifest.exists()
            report = json.loads((root.directory / "report.json").read_text())
            assert report["state"] == "failed" and report["cleanup"] == "failed"
            recovered = root.target(recover=True)
            monkeypatch.setattr(recovered, "api", api)
            monkeypatch.setattr(recovered, "docker", docker)
        await harness.cleanup_pair(root)
        assert not identities and not containers
        assert inventories == {
            key: (
                [{"uuid": foreign_id, "name": "baseline-profile"}]
                if key == "/config-profiles"
                else []
            )
            for key in shared.RESOURCE_KEYS
        }
        assert actions[:2] == ["identity:" + "a" * 32, "identity:" + "b" * 32]
        for node in (root, target):
            assert node.manifest.exists()  # Only successful outer schema cleanup removes manifests.
            assert not (node.directory / "node.env").exists()
            assert "DO_NOT_REPORT_SECRET" not in (node.directory / "report.json").read_text()

    asyncio.run(run())


def test_cleanup_continues_to_other_half_after_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def run() -> None:
        root = offline_node(tmp_path / "root")
        target = root.target()
        first = AsyncMock(side_effect=OSError("private output must not leak"))
        second = AsyncMock()
        monkeypatch.setattr(target, "cleanup", first)
        monkeypatch.setattr(root, "cleanup", second)
        with pytest.raises(AssertionError, match="retain both manifests"):
            await harness.cleanup_pair(root)
        first.assert_awaited_once()
        second.assert_awaited_once()
        assert root.manifest.exists() and target.manifest.exists()
        report = (root.directory / "report.json").read_text()
        assert "private output" not in report and "OSError" in report

    asyncio.run(run())


@pytest.mark.parametrize("outcome", ["success", "failure", "cancelled"])
def test_recovery_entry_drops_only_recorded_schema_after_successful_pair_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    async def run() -> None:
        root = offline_node(tmp_path / "root")
        schema = "user_services_test_" + uuid4().hex
        root.state["schema"] = schema
        root.save()
        target = root.target()
        close = Mock()
        monkeypatch.setattr(root, "close_lock", close)
        monkeypatch.setattr(root, "require_local_docker", AsyncMock())
        monkeypatch.setattr(harness, "ExitNode", Mock(return_value=root))
        monkeypatch.setattr(harness, "_panel_service", lambda: root.panel)
        monkeypatch.setattr(harness, "require_exit_environment", lambda: "validated-local-db")
        cleanup = AsyncMock()
        if outcome == "failure":
            cleanup.side_effect = AssertionError("offline cleanup failure")
        elif outcome == "cancelled":
            cleanup.side_effect = asyncio.CancelledError()
        monkeypatch.setattr(harness, "cleanup_pair", cleanup)
        connection = Mock()
        connection.execute = AsyncMock()
        transaction = AsyncMock()
        transaction.__aenter__.return_value = connection
        engine = Mock()
        engine.begin.return_value = transaction
        engine.dispose = AsyncMock()
        engine_factory = Mock(return_value=engine)
        monkeypatch.setattr(harness, "create_async_engine", engine_factory)
        if outcome == "success":
            await harness.recover(root.manifest)
            engine_factory.assert_called_once_with("validated-local-db")
            connection.execute.assert_awaited_once()
            assert str(connection.execute.await_args.args[0]) == (
                f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'
            )
            engine.dispose.assert_awaited_once()
            assert not root.manifest.exists() and not target.manifest.exists()
        else:
            error = AssertionError if outcome == "failure" else asyncio.CancelledError
            with pytest.raises(error):
                await harness.recover(root.manifest)
            engine_factory.assert_not_called()
            assert root.manifest.exists() and target.manifest.exists()
        cleanup.assert_awaited_once_with(root)
        close.assert_called_once()
        root.panel.close_session.assert_awaited_once()

    asyncio.run(run())
