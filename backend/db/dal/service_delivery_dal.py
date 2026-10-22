"""Serialize resource evidence and terminal revocation with account lifecycle changes."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.user_service_access import service_ready_for_delivery
from config.service_periods import as_utc
from db.dal.user_dal import lock_user_by_id
from db.dal.user_services_dal import ServiceConflict, get_service_resource
from db.service_models import (
    DedicatedExit,
    DedicatedExitAudit,
    ServiceConnection,
    ServiceOrder,
    UserService,
)


async def record_exit_evidence(
    session: AsyncSession,
    *,
    exit_id: str,
    actor_id: int,
    action: str,
    command: dict[str, object],
) -> tuple[DedicatedExit, DedicatedExitAudit, bool]:
    service_id = command["service_id"]
    # Same lock order as activation, bans and deletion: account, then resource.
    if service_id is not None:
        owner = await session.scalar(
            select(UserService.user_id).where(UserService.id == service_id)
        )
        if owner is not None:
            await lock_user_by_id(session, owner)
    resource = await session.scalar(
        select(DedicatedExit)
        .where(DedicatedExit.id == exit_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if resource is None:
        raise ServiceConflict("exit_not_found", 404)
    key = str(command["idempotency_key"])
    previous = await session.scalar(
        select(DedicatedExitAudit).where(
            DedicatedExitAudit.exit_id == exit_id, DedicatedExitAudit.idempotency_key == key
        )
    )
    if previous is not None:
        if previous.action != action or previous.evidence != command:
            raise ServiceConflict("idempotency_conflict")
        return resource, previous, True
    if resource.revision != command["expected_revision"] or resource.service_id != service_id:
        raise ServiceConflict("exit_revision_changed")
    now = datetime.now(UTC)
    checked = datetime.fromisoformat(str(command["checked_at"]).replace("Z", "+00:00"))
    if checked.tzinfo is None or checked > now:
        raise ServiceConflict("exit_evidence_invalid", 400)
    if action == "verify":
        if command.get("observed_ip") != resource.ip_address or not resource.enabled:
            raise ServiceConflict("exit_evidence_mismatch")
        if command.get("fixed") is not True or command.get("exclusive") is not True:
            raise ServiceConflict("exit_evidence_invalid", 400)
        resource.verified_at = checked
    elif action == "reclaim":
        connection = await session.get(ServiceConnection, str(service_id), populate_existing=True)
        if (
            connection is None
            or connection.state != "revoked"
            or connection.revoked_at is None
            or checked < as_utc(connection.revoked_at)
            or command.get("connections_stopped") is not True
            or command.get("old_config_rejected") is not True
        ):
            raise ServiceConflict("exit_stop_unconfirmed")
        resource.service_id = None
        # The next allocation needs its own check; an old tenant's proof is not transferable.
        resource.verified_at = None
    else:
        raise ServiceConflict("exit_evidence_invalid", 400)
    resource.revision += 1
    audit = DedicatedExitAudit(
        id=uuid4().hex,
        exit_id=exit_id,
        service_id=str(service_id) if service_id is not None else None,
        actor_id=actor_id,
        action=action,
        idempotency_key=key,
        evidence=command,
        created_at=now,
    )
    session.add(audit)
    await session.flush()
    return resource, audit, False


async def list_exit_audit(
    session: AsyncSession, exit_id: str, *, limit: int, offset: int
) -> tuple[list[DedicatedExitAudit], int]:
    filters = [DedicatedExitAudit.exit_id == exit_id]
    total = int(
        await session.scalar(select(func.count()).select_from(DedicatedExitAudit).where(*filters))
        or 0
    )
    rows = await session.scalars(
        select(DedicatedExitAudit)
        .where(*filters)
        .order_by(DedicatedExitAudit.created_at.desc(), DedicatedExitAudit.id)
        .limit(limit)
        .offset(offset)
    )
    return list(rows), total


async def request_service_revocation(
    session: AsyncSession,
    *,
    service_id: str,
    user_id: int,
    actor_id: int,
    expected_revision: int,
    idempotency_key: str,
    reason: str,
) -> tuple[UserService, ServiceOrder, bool]:
    user = await lock_user_by_id(session, user_id)
    service = await session.get(UserService, service_id, populate_existing=True)
    if user is None or service is None or service.user_id != user_id:
        raise ServiceConflict("service_not_found", 404)
    command: dict[str, object] = {
        "service_id": service_id,
        "expected_revision": expected_revision,
        "reason": reason,
    }
    previous = await session.scalar(
        select(ServiceOrder).where(
            ServiceOrder.request_owner_id == user_id,
            ServiceOrder.idempotency_key == idempotency_key,
        )
    )
    if previous is not None:
        if previous.kind != "revoke" or previous.request != command:
            raise ServiceConflict("idempotency_conflict")
        return service, previous, True
    connection = await session.get(ServiceConnection, service_id, populate_existing=True)
    if service.revision != expected_revision:
        raise ServiceConflict("service_revision_changed")
    if connection is None or service.desired_status == "cancelled":
        raise ServiceConflict("service_not_editable")
    now = datetime.now(UTC)
    service.desired_status = "cancelled"
    service.revision += 1
    connection.revoke_requested_at = now
    connection.sync_pending = True
    connection.sync_error = "service_revoke_pending"
    order = ServiceOrder(
        id=uuid4().hex,
        user_id=user_id,
        request_owner_id=user_id,
        service_id=service_id,
        actor_id=actor_id,
        kind="revoke",
        idempotency_key=idempotency_key,
        request=command,
        snapshot={
            "reason": reason,
            "terms": service.terms,
            "desired_status": "cancelled",
            "plan_revision": service.plan_revision,
            "quota_bytes": service.quota_bytes,
            "starts_at": as_utc(service.starts_at).isoformat(),
            "expires_at": as_utc(service.expires_at).isoformat(),
        },
        created_at=now,
    )
    session.add(order)
    await session.flush()
    return service, order, False


async def request_service_delivery(
    session: AsyncSession,
    *,
    service_id: str,
    user_id: int,
    actor_id: int,
    expected_revision: int,
    idempotency_key: str,
) -> tuple[UserService, ServiceOrder, bool]:
    user = await lock_user_by_id(session, user_id)
    service = await session.get(UserService, service_id, populate_existing=True)
    if user is None or service is None or service.user_id != user_id:
        raise ServiceConflict("service_not_found", 404)
    command: dict[str, object] = {"service_id": service_id, "expected_revision": expected_revision}
    previous = await session.scalar(
        select(ServiceOrder).where(
            ServiceOrder.request_owner_id == user_id,
            ServiceOrder.idempotency_key == idempotency_key,
        )
    )
    if previous is not None:
        if previous.kind != "deliver" or previous.request != command:
            raise ServiceConflict("idempotency_conflict")
        return service, previous, True
    if service.revision != expected_revision:
        raise ServiceConflict("service_revision_changed")
    connection, resource = await get_service_resource(session, service_id)
    if (
        connection is None
        or connection.state != "pending"
        or not service_ready_for_delivery(
            service, connection, resource, banned=bool(user.is_banned)
        )
    ):
        raise ServiceConflict("service_not_deliverable")
    service.revision += 1
    connection.sync_pending = True
    connection.sync_error = "service_delivery_pending"
    order = ServiceOrder(
        id=uuid4().hex,
        user_id=user_id,
        request_owner_id=user_id,
        service_id=service_id,
        actor_id=actor_id,
        kind="deliver",
        idempotency_key=idempotency_key,
        request=command,
        snapshot={
            "terms": service.terms,
            "plan_revision": service.plan_revision,
            "quota_bytes": service.quota_bytes,
            "starts_at": as_utc(service.starts_at).isoformat(),
            "expires_at": as_utc(service.expires_at).isoformat(),
        },
        created_at=datetime.now(UTC),
    )
    session.add(order)
    await session.flush()
    return service, order, False
