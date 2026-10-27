"""Persistence for local annotations on remote node identities."""

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.node_metadata_models import NodeMetadata


async def list_for_nodes(session: AsyncSession, node_ids: list[str]) -> dict[str, NodeMetadata]:
    if not node_ids:
        return {}
    rows = await session.scalars(select(NodeMetadata).where(NodeMetadata.node_id.in_(node_ids)))
    return {row.node_id: row for row in rows.all()}


async def save(
    session: AsyncSession,
    node_id: str,
    *,
    display_name: str | None,
    region: str | None,
    provider: str | None,
) -> NodeMetadata:
    row = await session.get(NodeMetadata, node_id)
    if row is None:
        row = NodeMetadata(node_id=node_id)
        session.add(row)
    row.display_name = display_name
    row.region = region
    row.provider = provider
    row.updated_at = datetime.now(UTC)
    await session.flush()
    return row


async def delete_for_node(session: AsyncSession, node_id: str) -> bool:
    result = await session.execute(
        delete(NodeMetadata).where(NodeMetadata.node_id == node_id).returning(NodeMetadata.node_id)
    )
    return result.scalar_one_or_none() is not None
