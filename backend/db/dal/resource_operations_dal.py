"""Resource intentions and the short coordination lock shared with authorization writers."""

import asyncio
from datetime import UTC, datetime
from weakref import WeakKeyDictionary

from sqlalchemy import event, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

from db.resource_operation_models import ResourceOperation

PANEL_GATE = "primary"
RESOURCE_LOCK_ID = 817512404897421339


class _SQLiteResourceLock:
    """Model shared/exclusive compatibility without making shared sessions self-block."""

    def __init__(self) -> None:
        self.readers = 0
        self.writer = False
        self.changed = asyncio.Event()

    async def acquire(self, *, exclusive: bool) -> None:
        while self.writer or (exclusive and self.readers):
            await self.changed.wait()
        if exclusive:
            self.writer = True
        else:
            self.readers += 1

    def release(self, *, exclusive: bool) -> None:
        if exclusive:
            self.writer = False
        else:
            self.readers -= 1
        # SQLAlchemy's synchronous transaction-end hook cannot await a Condition.
        changed, self.changed = self.changed, asyncio.Event()
        changed.set()


_sqlite_locks: WeakKeyDictionary[Engine, _SQLiteResourceLock] = WeakKeyDictionary()
_sqlite_operation_locks: WeakKeyDictionary[Engine, dict[str, asyncio.Lock]] = WeakKeyDictionary()


@event.listens_for(Session, "after_transaction_end")
def _release_coordination(session: Session, transaction: SessionTransaction) -> None:
    if transaction.parent is None:
        lock = session.info.pop("resource_coordination_sqlite", None)
        if isinstance(lock, _SQLiteResourceLock):
            lock.release(exclusive=session.info.get("resource_coordination") == "exclusive")
        for operation_lock in session.info.pop("resource_operation_locks", {}).values():
            operation_lock.release()
        session.info.pop("resource_coordination", None)


async def coordinate_resources(session: AsyncSession, *, exclusive: bool = False) -> None:
    """Acquire before account/plan/execution/exit locks; no expiring remote-write lease."""
    if session.info.get("resource_coordination") is not None:
        if exclusive and session.info["resource_coordination"] != "exclusive":
            raise RuntimeError("resource_lock_order")
        return
    if not session.in_transaction():
        await session.begin()
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        function = "pg_advisory_xact_lock" if exclusive else "pg_advisory_xact_lock_shared"
        await session.execute(text(f"SELECT {function}(:key)"), {"key": RESOURCE_LOCK_ID})
    elif bind.dialect.name == "sqlite":
        engine = bind.engine
        lock = _sqlite_locks.setdefault(engine, _SQLiteResourceLock())
        await lock.acquire(exclusive=exclusive)
        session.info["resource_coordination_sqlite"] = lock
    else:
        raise RuntimeError("resource_coordination_backend_unsupported")
    session.info["resource_coordination"] = "exclusive" if exclusive else "shared"


async def resource_gate_active(session: AsyncSession) -> bool:
    return (
        await session.scalar(
            select(ResourceOperation.id).where(ResourceOperation.gate_key == PANEL_GATE).limit(1)
        )
        is not None
    )


async def require_resource_authorization(session: AsyncSession) -> None:
    from db.dal.user_services_dal import ServiceConflict

    await coordinate_resources(session)
    if await resource_gate_active(session):
        raise ServiceConflict("resource_operation_in_progress")


async def locked_resource_operation(session: AsyncSession, operation_id: str) -> ResourceOperation:
    from db.dal.user_services_dal import ServiceConflict

    # A persistent gate blocks grants. Only this operation row stays locked over IO;
    # bans and pauses must not queue behind the panel-wide coordination lock.
    bind = session.get_bind()
    if bind.dialect.name == "sqlite":
        if not session.in_transaction():
            await session.begin()
        held = session.info.setdefault("resource_operation_locks", {})
        if operation_id not in held:
            locks = _sqlite_operation_locks.setdefault(bind.engine, {})
            lock = locks.setdefault(operation_id, asyncio.Lock())
            await lock.acquire()
            held[operation_id] = lock
    row = await session.scalar(
        select(ResourceOperation)
        .where(ResourceOperation.id == operation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise ServiceConflict("resource_operation_not_found", 404)
    return row


def finish_resource_operation(
    row: ResourceOperation, *, success: bool, error: str | None = None
) -> None:
    row.status = "succeeded" if success else "failed"
    row.error_code = error
    row.gate_key = None
    row.completed_at = datetime.now(UTC)
    row.version += 1
