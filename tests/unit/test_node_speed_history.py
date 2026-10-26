from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from bot.services.node_speed_history import RETENTION, NodeSpeedHistoryWorker, parse_speed_rows
from bot.services.panel_api_contracts import PanelApiOperation
from bot.services.panel_api_service import PanelApiService
from db.node_speed_models import NodeSpeedSample
from tests.unit.test_user_services import ServiceDatabaseTestCase


def test_parse_speed_rows_keeps_missing_direction_as_unknown() -> None:
    rows = parse_speed_rows(
        {"nodes": [{"uuid": "node-1", "stats": {"interface": {"rxBytesPerSec": 12}}}]},
        datetime(2026, 10, 26, tzinfo=UTC),
    )
    assert len(rows) == 1
    assert rows[0].rx_bytes_per_second == 12
    assert rows[0].tx_bytes_per_second is None


def test_retention_is_exactly_one_day() -> None:
    assert timedelta(hours=24) == RETENTION


class NodeSpeedHistoryTests(ServiceDatabaseTestCase):
    async def test_duplicate_minute_keeps_first_sample_and_saves_new_nodes(self) -> None:
        now = datetime(2026, 10, 27, 10, 0, 15, tzinfo=UTC)
        minute = now.replace(second=0)
        panel = AsyncMock(spec=PanelApiService)
        panel._request.return_value = {
            "response": [
                {"uuid": "node-1", "system": {"stats": {"interface": {"rxBytesPerSec": 12}}}}
            ]
        }
        worker = NodeSpeedHistoryWorker(self.sessions, panel)
        with patch("bot.services.node_speed_history.datetime", wraps=datetime) as clock:
            clock.now.return_value = now
            await worker.tick()
            panel._request.assert_awaited_once_with(
                "GET", "/nodes", operation=PanelApiOperation.NODES_LIST, log_full_response=False
            )
            async with self.sessions.begin() as session:
                session.add_all(
                    [
                        NodeSpeedSample(
                            node_id="expired", sampled_at=minute - RETENTION - timedelta(minutes=1)
                        ),
                        NodeSpeedSample(node_id="boundary", sampled_at=minute - RETENTION),
                    ]
                )
            panel._request.return_value = {
                "response": [
                    {"uuid": "node-1", "interface": {"rxBytesPerSec": 99}},
                    {"uuid": "node-2", "interface": {"txBytesPerSec": 34}},
                    {"uuid": "node-2", "interface": {"txBytesPerSec": 55}},
                ]
            }
            await worker.tick()
        async with self.sessions() as session:
            rows = {row.node_id: row for row in await session.scalars(select(NodeSpeedSample))}
        assert set(rows) == {"node-1", "node-2", "boundary"}
        assert rows["node-1"].rx_bytes_per_second == 12
        assert rows["node-1"].tx_bytes_per_second is None
        assert rows["node-2"].rx_bytes_per_second is None
        assert rows["node-2"].tx_bytes_per_second == 34

    async def test_empty_batch_still_cleans_expired_samples(self) -> None:
        async with self.sessions.begin() as session:
            session.add(
                NodeSpeedSample(
                    node_id="expired",
                    sampled_at=datetime.now(UTC) - RETENTION - timedelta(minutes=1),
                )
            )
        panel = AsyncMock(spec=PanelApiService)
        panel._request.return_value = {"response": []}
        await NodeSpeedHistoryWorker(self.sessions, panel).tick()
        async with self.sessions() as session:
            assert list(await session.scalars(select(NodeSpeedSample))) == []


def test_parse_real_node_inventory_keeps_direction_and_rejects_nonfinite() -> None:
    rows = parse_speed_rows(
        [
            {
                "uuid": "node-1",
                "system": {
                    "stats": {"interface": {"rxBytesPerSec": 123, "txBytesPerSec": float("inf")}}
                },
            }
        ],
        datetime(2026, 10, 27, tzinfo=UTC),
    )
    assert len(rows) == 1
    assert rows[0].rx_bytes_per_second == 123
    assert rows[0].tx_bytes_per_second is None
