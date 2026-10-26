"""Read the bounded local speed history for node cards and details."""

import inspect
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.app.web.admin_console_nodes_schemas import ConsoleNodeOut
from db.node_speed_models import NodeSpeedSample


class NodeSpeedHistoryReader:
    async def attach(
        self, session_factory: async_sessionmaker[AsyncSession], nodes: list[ConsoleNodeOut]
    ) -> None:
        if not nodes:
            return
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        async with session_factory() as session:
            result = await session.scalars(
                select(NodeSpeedSample)
                .where(
                    NodeSpeedSample.node_id.in_([node.id for node in nodes]),
                    NodeSpeedSample.sampled_at >= cutoff,
                )
                .order_by(NodeSpeedSample.sampled_at)
            )
            items = result.all()
            if inspect.isawaitable(items):
                items = await items
            rows = list(items)
        by_id: dict[str, list[NodeSpeedSample]] = {node.id: [] for node in nodes}
        for row in rows:
            by_id.setdefault(row.node_id, []).append(row)
        for node in nodes:
            node.speed_history = [
                {
                    "sampled_at": row.sampled_at,
                    "rx_bytes_per_second": row.rx_bytes_per_second,
                    "tx_bytes_per_second": row.tx_bytes_per_second,
                }
                for row in by_id.get(node.id, [])
            ]
