"""Persist monthly checkpoints and terminal usage without issuing panel allowances."""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.services.service_panel_state import ServiceEntitlementPanel, locked_service, owns_identity
from bot.services.service_usage_sync import record_service_usage
from config.service_periods import as_utc
from db.dal.service_operations_dal import enqueue_execution, finish_execution
from db.dal.service_periods_dal import cycle_due, prepare_period
from db.service_models import ServiceConnection, ServiceOrder, ServiceUsagePeriod, UserService

logger = logging.getLogger(__name__)


async def settle_cancelled_service_period(
    session: AsyncSession,
    service: UserService,
    connection: ServiceConnection,
    remote: dict[str, Any],
    *,
    actor_id: int,
    now: datetime | None = None,
) -> bool:
    """Caller holds the account lock and supplies a fresh stopped-identity read.

    True accepts this observation; it does not complete revocation or prove traffic stopped.
    Calls after the cutover marker is cleared still accept new counter deltas. Commit each
    accepted observation before DELETE, including a newer read after reacquiring the lock.
    The first settlement audit stays an immutable observation, not evidence of no later bytes.
    Errors block deletion pending reconciliation. This never confirms an allowance.
    """
    if (
        service.desired_status != "cancelled"
        or service.user_id is None
        or connection.service_id != service.id
        or connection.state == "revoked"
        or connection.panel_user_uuid is None
        or not owns_identity(remote, connection)
        or remote.get("status") not in {"DISABLED", "LIMITED", "EXPIRED"}
        or connection.usage_error is not None
    ):
        return False
    cutover = connection.cycle_cutover_bytes
    period = None
    if cutover is not None:
        if service.cycle_started_at is None:
            return False
        period = await session.get(ServiceUsagePeriod, (service.id, service.cycle_started_at))
        if period is None or period.confirmed_at is not None or period.cutover_bytes != cutover:
            return False
    record_service_usage(service, connection, remote)
    total = connection.usage_total_bytes
    if connection.usage_error is not None or total is None:
        return False
    if cutover is None:
        return True
    if total < cutover:
        return False
    assert period is not None
    now = as_utc(now or datetime.now(UTC))
    before = {
        "desired_status": service.desired_status,
        "expires_at": as_utc(service.expires_at).isoformat(),
        "used_bytes": service.used_bytes,
        "cycle_started_at": as_utc(period.cycle_started_at).isoformat(),
        "cycle_ends_at": as_utc(period.cycle_ends_at).isoformat(),
    }
    service.used_bytes = total - cutover
    service.last_usage_sync_at = now
    service.cycle_started_at = period.next_started_at
    service.cycle_ends_at = period.next_ends_at
    connection.cycle_cutover_bytes = None
    order = ServiceOrder(
        id=uuid4().hex,
        user_id=service.user_id,
        request_owner_id=service.user_id,
        service_id=service.id,
        actor_id=actor_id,
        kind="settle_usage",
        idempotency_key=f"settle:{service.id}:{before['cycle_started_at']}",
        request={"service_id": service.id, "cycle_started_at": before["cycle_started_at"]},
        snapshot={
            "terms": dict(service.terms),
            "plan_id": service.plan_id,
            "plan_revision": service.plan_revision,
            "starts_at": as_utc(service.starts_at).isoformat(),
            "expires_at": as_utc(service.expires_at).isoformat(),
            "quota_bytes": service.quota_bytes,
            "desired_status": service.desired_status,
            "before": before,
            "change": {"action": "settle_usage"},
            "used_bytes": service.used_bytes,
            "usage_total_bytes": total,
            "usage_raw_bytes": connection.usage_raw_bytes,
            "usage_lifetime_offset": connection.usage_lifetime_offset,
            "cutover_bytes": cutover,
            "cycle_started_at": as_utc(service.cycle_started_at).isoformat(),
            "cycle_ends_at": as_utc(service.cycle_ends_at).isoformat(),
            "panel_user_uuid": connection.panel_user_uuid,
            "panel_status": remote["status"],
            "allowance_confirmed": False,
            "observed_at": now.isoformat(),
        },
        created_at=now,
    )
    session.add(order)
    await enqueue_execution(session, service, "usage", order=order)
    await finish_execution(session, service, "usage", success=True)
    await session.flush()
    return True


async def prepare_service_cycle(
    session_factory: sessionmaker, service_id: str, panel: ServiceEntitlementPanel
) -> None:
    async with session_factory() as session:
        locked = await locked_service(session, service_id)
        if locked is None:
            return
        _user, service, connection = locked
        if (
            connection.panel_user_uuid is None
            or connection.cycle_cutover_bytes is not None
            or not cycle_due(service, datetime.now(UTC))
        ):
            return
        try:
            lookup = await panel.get_user_by_uuid_lookup(connection.panel_user_uuid)
            remote = lookup.get("user") if lookup.get("ok") is True else None
            if not isinstance(remote, dict) or not owns_identity(remote, connection):
                return
            record_service_usage(service, connection, remote)
            await prepare_period(session, service, connection, datetime.now(UTC))
            # No panel mutation precedes this commit; a crash cannot lose its cutover.
            await session.commit()
        except Exception:
            logger.exception("Monthly checkpoint needs retry for %s", service_id)
            await session.rollback()
