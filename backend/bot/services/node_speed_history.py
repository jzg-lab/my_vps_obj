"""Collect ten minute node speed samples and retain one day on the main worker."""

import asyncio
import logging
import math
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from bot.services.panel_api_contracts import PanelApiOperation
from bot.services.panel_api_service import PanelApiService
from db.node_speed_models import NodeSpeedSample

logger = logging.getLogger(__name__)
SAMPLE_INTERVAL_SECONDS = 600
RETENTION = timedelta(hours=24)


def _rows(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("nodes", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _number(value: object) -> float | None:
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    ):
        return float(value)
    return None


def parse_speed_rows(payload: object, sampled_at: datetime) -> list[NodeSpeedSample]:
    result: list[NodeSpeedSample] = []
    for row in _rows(payload):
        node_id = row.get("uuid") or row.get("nodeUuid") or row.get("node_id") or row.get("id")
        if not isinstance(node_id, str) or not node_id.strip():
            continue
        system = row.get("system")
        metrics = system if isinstance(system, dict) else row
        interface = metrics.get("interface")
        if not isinstance(interface, dict):
            stats = metrics.get("stats")
            interface = stats.get("interface") if isinstance(stats, dict) else None
        result.append(
            NodeSpeedSample(
                node_id=node_id.strip().lower(),
                sampled_at=sampled_at,
                rx_bytes_per_second=(
                    _number(interface.get("rxBytesPerSec")) if isinstance(interface, dict) else None
                ),
                tx_bytes_per_second=(
                    _number(interface.get("txBytesPerSec")) if isinstance(interface, dict) else None
                ),
            )
        )
    return result


class NodeSpeedHistoryWorker:
    def __init__(self, session_factory: Any, panel: PanelApiService) -> None:
        self.session_factory = session_factory
        self.panel = panel

    async def tick(self) -> None:
        sampled_at = datetime.now(UTC).replace(second=0, microsecond=0)
        payload = await self.panel._request(
            "GET", "/nodes", operation=PanelApiOperation.NODES_LIST, log_full_response=False
        )
        samples = parse_speed_rows(
            payload.get("response") if payload and not payload.get("error") else None, sampled_at
        )
        cutoff = sampled_at - RETENTION
        async with self.session_factory() as session:
            await session.execute(
                delete(NodeSpeedSample).where(NodeSpeedSample.sampled_at < cutoff)
            )
            if samples:
                await session.execute(
                    insert(NodeSpeedSample)
                    .values(
                        [
                            {
                                "node_id": sample.node_id,
                                "sampled_at": sample.sampled_at,
                                "rx_bytes_per_second": sample.rx_bytes_per_second,
                                "tx_bytes_per_second": sample.tx_bytes_per_second,
                            }
                            for sample in samples
                        ]
                    )
                    .on_conflict_do_nothing(
                        index_elements=[NodeSpeedSample.node_id, NodeSpeedSample.sampled_at]
                    )
                )
            await session.commit()

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("Node speed history sample failed")
            await asyncio.sleep(SAMPLE_INTERVAL_SECONDS)
