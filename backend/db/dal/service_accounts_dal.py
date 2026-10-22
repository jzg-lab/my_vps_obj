"""Account lifecycle guards; callers hold the owner row lock before external work."""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.dal.account_access_dal import enqueue_access_sync
from db.dal.user_services_dal import ServiceConflict
from db.service_models import (
    AccountAccessSync,
    DedicatedExit,
    ServiceConnection,
    ServiceOrder,
    UserService,
)


async def deletion_connections(session: AsyncSession, user_id: int) -> list[ServiceConnection]:
    services = select(UserService.id).where(UserService.user_id == user_id)
    resource = await session.scalar(
        select(DedicatedExit.id).where(DedicatedExit.service_id.in_(services)).limit(1)
    )
    if resource is not None:
        raise ServiceConflict("dedicated_exit_reclaim_required")
    connections = list(
        await session.scalars(
            select(ServiceConnection).where(ServiceConnection.service_id.in_(services))
        )
    )
    # A failed provisioning attempt without an identity needs reconciliation first.
    if any(
        c.state not in {"pending", "revoked"} and c.panel_user_uuid is None for c in connections
    ):
        raise ServiceConflict("service_connection_unconfirmed")
    # Account deletion must not bypass the service's metering and revocation workflow.
    if any(c.state != "revoked" and c.panel_user_uuid is not None for c in connections):
        raise ServiceConflict("service_connection_revoke_required")
    return connections


async def detach_history(session: AsyncSession, user_id: int) -> None:
    connections = await deletion_connections(session, user_id)
    if any(c.state != "revoked" for c in connections):
        raise ServiceConflict("service_connection_revoke_required")
    await session.execute(
        update(UserService)
        .where(UserService.user_id == user_id)
        .values(user_id=None, desired_status="cancelled")
    )
    await session.execute(
        update(ServiceOrder).where(ServiceOrder.user_id == user_id).values(user_id=None)
    )


async def merge_history(session: AsyncSession, source_id: int, target_id: int) -> None:
    source_job = await session.get(AccountAccessSync, source_id)
    if source_job is not None and source_job.pending:
        await enqueue_access_sync(session, target_id)
    # Request scope, terms, dates, connection identities and resource bindings stay intact.
    for model in (UserService, ServiceOrder):
        await session.execute(
            update(model).where(model.user_id == source_id).values(user_id=target_id)
        )
