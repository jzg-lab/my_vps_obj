"""Offline window parsing, cache, UUID joins and route validation. No database/API."""

import asyncio
import json
import time
from datetime import UTC, date, datetime, timedelta, timezone
from typing import cast
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from bot.app.web import admin_console_nodes_routes as routes
from bot.app.web.admin_console_nodes_panel import NodeInventoryReader
from bot.app.web.admin_console_nodes_schemas import ConsoleNodeOut, ConsoleNodeTrafficPreset
from bot.app.web.admin_console_nodes_traffic import NodeTrafficReader, _parse_traffic, traffic_dates
from bot.services.panel_api_service import PanelApiService
from tests.unit.test_admin_console_nodes import NODE, OTHER_NODE, panel_fixture, panel_responses

NOW = datetime(2026, 10, 24, 0, 10, tzinfo=UTC)


def payload(
    preset: ConsoleNodeTrafficPreset, rows: list[object], now: datetime = NOW
) -> dict[str, object]:
    start, end = traffic_dates(preset, now)
    return {
        "categories": [
            (start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)
        ],
        "series": rows,
        # Deliberately inconsistent: this auxiliary ranking must never be consumed.
        "topNodes": [{"uuid": str(UUID(int=999)), "name": "Same name", "total": 99999}],
        "sparklineData": [],
    }


async def inventory_nodes() -> list[ConsoleNodeOut]:
    panel, _ = panel_fixture(panel_responses())
    inventory = await NodeInventoryReader().read(panel, ttl_seconds=0)
    return [inventory.node_out(node) for node in inventory.nodes.rows]


class NodeTrafficTests(IsolatedAsyncioTestCase):
    async def test_utc_calendar_dates_including_today_not_rolling_hours(self) -> None:
        beijing = datetime(2026, 10, 24, 3, 15, tzinfo=timezone(timedelta(hours=8)))
        assert traffic_dates("today", beijing) == (date(2026, 10, 23), date(2026, 10, 23))
        assert traffic_dates("7d", NOW) == (date(2026, 10, 18), date(2026, 10, 24))
        assert traffic_dates("30d", datetime(2024, 3, 1, tzinfo=UTC)) == (
            date(2024, 2, 1),
            date(2024, 3, 1),
        )

    async def test_uuid_join_keeps_inventory_unknown_and_real_zero(self) -> None:
        nodes = await inventory_nodes()
        panel = Mock(spec=PanelApiService)
        panel.get_nodes_bandwidth_usage = AsyncMock(
            return_value=payload("7d", [{"uuid": OTHER_NODE, "total": 0}])
        )
        result = await NodeTrafficReader().read(
            panel, preset="7d", nodes=nodes, inventory_complete=True, ttl_seconds=15, now=NOW
        )
        assert [node.id for node in nodes] == [NODE, OTHER_NODE]
        assert nodes[0].window_traffic_bytes is None
        assert nodes[0].window_traffic_quality == "missing"
        assert nodes[1].window_traffic_bytes == 0
        assert nodes[1].window_traffic_quality == "reported"
        assert nodes[0].traffic_used_bytes == 0
        assert result.availability == "partial" and result.matched_nodes == 1
        assert result.inventory_nodes == 2
        assert result.timezone == "UTC" and result.boundaries == "inclusive_start_and_end"
        assert result.start_at == datetime(2026, 10, 18, tzinfo=UTC)
        assert result.end_at == datetime(2026, 10, 24, 23, 59, 59, 999000, tzinfo=UTC)
        assert result.history_completeness == "unknown_not_service_billing"
        panel.get_nodes_bandwidth_usage.assert_awaited_once_with(
            start="2026-10-18", end="2026-10-24", top_nodes_limit=1
        )

    async def test_empty_history_is_missing_not_zero_and_empty_inventory_is_known(self) -> None:
        panel = Mock(spec=PanelApiService)
        panel.get_nodes_bandwidth_usage = AsyncMock(return_value=payload("today", []))
        reader = NodeTrafficReader()
        for complete, expected_count in ((True, 2), (False, None)):
            nodes = await inventory_nodes()
            result = await reader.read(
                panel,
                preset="today",
                nodes=nodes,
                inventory_complete=complete,
                ttl_seconds=15,
                now=NOW,
            )
            assert result.inventory_nodes == expected_count
            assert result.availability == "partial"
            assert all(node.window_traffic_bytes is None for node in nodes)
        result = await reader.read(
            panel, preset="today", nodes=[], inventory_complete=True, ttl_seconds=15, now=NOW
        )
        assert result.availability == "available" and result.inventory_nodes == 0

    async def test_invalid_or_duplicate_values_never_claim_exact_bytes(self) -> None:
        start, end = traffic_dates("today", NOW)
        for value in (-1, True, "0", 1.5, 2**53, float("nan"), None):
            result = _parse_traffic(payload("today", [{"uuid": NODE, "total": value}]), start, end)
            assert result.partial and result.totals == {} and result.invalid_ids == {NODE}
        result = _parse_traffic(
            payload(
                "today",
                [
                    {"uuid": NODE, "total": 123},
                    {"uuid": NODE.upper(), "total": 456},
                    {"uuid": OTHER_NODE, "total": 12},
                    {"uuid": "invalid", "total": 3},
                    None,
                ],
            ),
            start,
            end,
        )
        assert result.totals == {OTHER_NODE: 12} and result.invalid_ids == {NODE}
        assert result.partial
        for data in (
            {},
            {"categories": ["wrong"], "series": []},
            {"categories": ["2026-10-24"], "series": None},
        ):
            with self.assertRaisesRegex(ValueError, "invalid_response"):
                _parse_traffic(data, start, end)

    async def test_singleflight_cache_separates_windows_and_utc_rollover(self) -> None:
        panel = Mock(spec=PanelApiService)

        async def read(*, start: str, end: str, top_nodes_limit: int) -> dict[str, object]:
            count = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
            preset: ConsoleNodeTrafficPreset = (
                "today" if count == 1 else "7d" if count == 7 else "30d"
            )
            return payload(
                preset,
                [{"uuid": NODE, "total": count}],
                datetime.fromisoformat(end).replace(tzinfo=UTC),
            )

        panel.get_nodes_bandwidth_usage = AsyncMock(side_effect=read)
        reader = NodeTrafficReader()
        nodes = await inventory_nodes()
        await asyncio.gather(
            *(
                reader.read(
                    panel,
                    preset="today",
                    nodes=[node.model_copy() for node in nodes],
                    inventory_complete=True,
                    ttl_seconds=60,
                    now=NOW,
                )
                for _ in range(5)
            )
        )
        assert panel.get_nodes_bandwidth_usage.await_count == 1
        for preset in ("7d", "30d"):
            await reader.read(
                panel,
                preset=cast(ConsoleNodeTrafficPreset, preset),
                nodes=nodes,
                inventory_complete=True,
                ttl_seconds=60,
                now=NOW,
            )
        await reader.read(
            panel,
            preset="today",
            nodes=nodes,
            inventory_complete=True,
            ttl_seconds=60,
            now=NOW + timedelta(days=1),
        )
        assert panel.get_nodes_bandwidth_usage.await_count == 4
        assert nodes[0].window_traffic_bytes == 1

    async def test_failure_stale_bounded_and_never_borrows_another_window(self) -> None:
        panel = Mock(spec=PanelApiService)
        panel.get_nodes_bandwidth_usage = AsyncMock(
            return_value=payload("today", [{"uuid": NODE, "total": 5}])
        )
        reader = NodeTrafficReader()
        nodes = await inventory_nodes()
        first = await reader.read(
            panel, preset="today", nodes=nodes, inventory_complete=True, ttl_seconds=15, now=NOW
        )
        panel.get_nodes_bandwidth_usage.side_effect = TimeoutError("PRIVATE upstream message")
        with patch("bot.utils.ttl_cache.time.monotonic", return_value=time.monotonic() + 16):
            stale = await reader.read(
                panel, preset="today", nodes=nodes, inventory_complete=True, ttl_seconds=15, now=NOW
            )
        assert stale.availability == "stale" and stale.last_success_at == first.last_success_at
        assert nodes[0].window_traffic_bytes == 5 and stale.error == "request_failed"
        missing = await reader.read(
            panel, preset="7d", nodes=nodes, inventory_complete=True, ttl_seconds=15, now=NOW
        )
        assert missing.availability == "unavailable" and missing.last_success_at is None
        assert nodes[0].window_traffic_bytes is None
        assert "PRIVATE" not in missing.model_dump_json()
        with patch("bot.utils.ttl_cache.time.monotonic", return_value=time.monotonic() + 400):
            expired = await reader.read(
                panel, preset="today", nodes=nodes, inventory_complete=True, ttl_seconds=15, now=NOW
            )
        assert expired.availability == "unavailable" and nodes[0].window_traffic_bytes is None
        unconfigured = await reader.read(
            None, preset="today", nodes=nodes, inventory_complete=True, ttl_seconds=15, now=NOW
        )
        assert (
            unconfigured.availability == "unconfigured" and unconfigured.error == "not_configured"
        )


class NodeTrafficRouteTests(IsolatedAsyncioTestCase):
    async def test_denied_administrator_never_reaches_readers(self) -> None:
        for handler in (routes.admin_console_nodes_route, routes.admin_console_node_route):
            request = make_mocked_request("GET", f"/api/admin/console/nodes/{NODE}")
            with (
                patch.object(routes, "_require_admin_user_id", side_effect=web.HTTPForbidden()),
                patch.object(routes, "_inventory", new_callable=AsyncMock) as inventory,
                self.assertRaises(web.HTTPForbidden),
            ):
                await handler(request)
            inventory.assert_not_awaited()

    async def test_window_validation_before_any_upstream_read(self) -> None:
        app = web.Application()
        routes.setup_admin_console_nodes_routes(app)
        for handler, path in (
            (routes.admin_console_nodes_route, "/api/admin/console/nodes"),
            (routes.admin_console_node_route, f"/api/admin/console/nodes/{NODE}"),
        ):
            for query in (
                "traffic_window=custom",
                "traffic_window=",
                "traffic_window=TODAY",
                "traffic_window=7d&traffic_window=30d",
                "start=2026-01-01",
                "end=2026-11-01",
            ):
                request = make_mocked_request(
                    "GET", f"{path}?{query}", app=app, match_info={"node_id": NODE}
                )
                with (
                    patch.object(routes, "_require_admin_user_id"),
                    patch.object(routes, "_inventory", new_callable=AsyncMock) as inventory,
                ):
                    response = await handler(request)
                assert response.status == 400
                inventory.assert_not_awaited()

    async def test_list_total_and_paging_are_inventory_based_despite_partial_statistics(
        self,
    ) -> None:
        app = web.Application()
        routes.setup_admin_console_nodes_routes(app)
        panel, _ = panel_fixture(panel_responses())
        panel.get_nodes_bandwidth_usage = AsyncMock(
            return_value=payload("today", [{"uuid": OTHER_NODE, "total": 11}], datetime.now(UTC))
        )
        inventory = await NodeInventoryReader().read(panel, ttl_seconds=0)
        request = make_mocked_request(
            "GET", "/api/admin/console/nodes?traffic_window=today&page_size=1&page=1", app=app
        )
        with (
            patch.object(routes, "_require_admin_user_id"),
            patch.object(routes, "_inventory", AsyncMock(return_value=inventory)),
            patch.object(routes, "get_panel_service", return_value=panel),
            patch.object(
                routes, "get_settings", return_value=Mock(ADMIN_PANEL_STATS_CACHE_TTL_SECONDS=0)
            ),
        ):
            response = await routes.admin_console_nodes_route(request)
        body = json.loads(response.text or "{}")
        assert body["total"] == 2 and body["coverage"] == "complete"
        assert len(body["nodes"]) == 1 and body["nodes"][0]["id"] == OTHER_NODE
        assert body["nodes"][0]["window_traffic_bytes"] == 11
        assert body["traffic"]["inventory_nodes"] == 2 and body["traffic"]["matched_nodes"] == 1
        assert response.headers["Cache-Control"] == "private, no-store"

    async def test_detail_reads_same_window_and_failure_does_not_hide_node(self) -> None:
        app = web.Application()
        routes.setup_admin_console_nodes_routes(app)
        panel, _ = panel_fixture(panel_responses())
        panel.get_nodes_bandwidth_usage = AsyncMock(
            return_value=payload("30d", [{"uuid": NODE, "total": 25}], datetime.now(UTC))
        )
        inventory = await NodeInventoryReader().read(panel, ttl_seconds=0)
        session = AsyncMock()
        session_factory = Mock(return_value=session)
        for failed in (False, True):
            if failed:
                panel.get_nodes_bandwidth_usage.side_effect = RuntimeError("PRIVATE")
                app[routes._TRAFFIC_READER].cache.invalidate()
            request = make_mocked_request(
                "GET",
                f"/api/admin/console/nodes/{NODE}?traffic_window=30d",
                app=app,
                match_info={"node_id": NODE},
            )
            with (
                patch.object(routes, "_require_admin_user_id"),
                patch.object(routes, "_inventory", AsyncMock(return_value=inventory)),
                patch.object(routes, "get_panel_service", return_value=panel),
                patch.object(
                    routes, "get_settings", return_value=Mock(ADMIN_PANEL_STATS_CACHE_TTL_SECONDS=0)
                ),
                patch.object(routes, "get_session_factory", return_value=session_factory),
                patch.object(routes, "read_service_resources", AsyncMock(return_value=[])),
            ):
                response = await routes.admin_console_node_route(request)
            body = json.loads(response.text or "{}")
            assert body["node"]["id"] == NODE and body["coverage"] == "complete"
            assert body["node"]["window_traffic_bytes"] == (None if failed else 25)
            assert body["traffic"]["availability"] == ("unavailable" if failed else "partial")
            assert body["traffic"]["preset"] == "30d"
            assert "PRIVATE" not in (response.text or "")
            assert response.headers["Cache-Control"] == "private, no-store"
