"""Local-only node records. Name/address are deliberately not remote identities."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.node_asset_models import NodeAsset


async def list_assets(
    session: AsyncSession, *, page: int, page_size: int
) -> tuple[list[NodeAsset], int]:
    count = await session.execute(select(func.count()).select_from(NodeAsset))
    total = int(count.scalar_one())
    rows = await session.scalars(
        select(NodeAsset)
        .order_by(NodeAsset.created_at.desc(), NodeAsset.id.desc())
        .offset(page * page_size)
        .limit(page_size)
    )
    return list(rows.all()), total


async def get_asset(session: AsyncSession, asset_id: str) -> NodeAsset | None:
    return await session.get(NodeAsset, asset_id)


async def create_asset(session: AsyncSession, *, name: str, address: str, notes: str) -> NodeAsset:
    now = datetime.now(UTC)
    row = NodeAsset(
        id=uuid4().hex,
        name=name,
        address=address,
        notes=notes,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()
    return row


async def update_asset(
    session: AsyncSession, asset_id: str, *, name: str, address: str, notes: str
) -> NodeAsset | None:
    result = await session.execute(
        update(NodeAsset)
        .where(NodeAsset.id == asset_id)
        .values(name=name, address=address, notes=notes, updated_at=datetime.now(UTC))
        .returning(NodeAsset)
    )
    return result.scalar_one_or_none()


async def delete_asset(session: AsyncSession, asset_id: str) -> bool:
    result = await session.execute(
        delete(NodeAsset).where(NodeAsset.id == asset_id).returning(NodeAsset.id)
    )
    return result.scalar_one_or_none() is not None
