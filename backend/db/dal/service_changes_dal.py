"""Save service intent and immutable operation records in one account-locked transaction."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.service_changes import ServiceChange
from config.service_periods import as_utc
from db.dal.resource_operations_dal import coordinate_resources, require_resource_authorization
from db.dal.service_operations_dal import enqueue_execution
from db.dal.user_dal import lock_user_by_id
from db.dal.user_services_dal import ServiceConflict
from db.service_models import ServiceConnection, ServiceOrder, UserService


async def change_service(
    session: AsyncSession,
    *,
    service_id: str,
    user_id: int,
    actor_id: int,
    expected_revision: int,
    idempotency_key: str,
    change: ServiceChange,
    now: datetime | None = None,
    usage_observation: tuple[int, int] | None = None,
) -> tuple[UserService, ServiceOrder, bool]:
    await coordinate_resources(session)
    now = as_utc(now or datetime.now(UTC))
    user = await lock_user_by_id(session, user_id)
    if user is None:
        raise ServiceConflict("user_not_found", 404)
    command: dict[str, object] = {
        "service_id": service_id,
        "expected_revision": expected_revision,
        "change": change.request_values(),
    }
    previous = await session.scalar(
        select(ServiceOrder).where(
            ServiceOrder.request_owner_id == user_id,
            ServiceOrder.idempotency_key == idempotency_key,
        )
    )
    service = await session.get(UserService, service_id, populate_existing=True)
    if previous is not None:
        if previous.kind != change.action or previous.request != command:
            raise ServiceConflict("idempotency_conflict")
        if service is None or service.user_id != user_id:
            raise ServiceConflict("idempotency_owner_changed")
        return service, previous, True
    if service is None or service.user_id != user_id:
        raise ServiceConflict("service_not_found", 404)
    connection = await session.get(ServiceConnection, service_id, populate_existing=True)
    if (
        connection is None
        or connection.state == "revoked"
        or (service.desired_status == "cancelled" and change.action != "reconcile_usage")
    ):
        raise ServiceConflict("service_not_editable")
    if service.revision != expected_revision:
        raise ServiceConflict("service_revision_changed")
    if change.action not in {"pause", "reconcile_usage"}:
        await require_resource_authorization(session)
    before: dict[str, object] = {
        "desired_status": service.desired_status,
        "expires_at": as_utc(service.expires_at).isoformat(),
        "revision": service.revision,
    }
    if change.action == "reconcile_usage":
        if service.desired_status not in {"paused", "cancelled"}:
            raise ServiceConflict("usage_reconciliation_pause_required")
        if usage_observation is None or connection.usage_error not in {
            "panel_usage_reset",
            "panel_usage_regressed",
        }:
            raise ServiceConflict("usage_reconciliation_unavailable")
        raw, lifetime = usage_observation
        verified = change.verified_total_bytes
        previous = connection.usage_total_bytes
        previous = service.used_bytes if previous is None else previous
        if verified is None or verified < previous or raw != change.expected_raw_bytes:
            raise ServiceConflict("usage_reconciliation_changed")
        before.update(
            {
                "used_bytes": service.used_bytes,
                "usage_total_bytes": connection.usage_total_bytes,
                "usage_raw_bytes": connection.usage_raw_bytes,
                "usage_error": connection.usage_error,
            }
        )
        if connection.cycle_cutover_bytes is None:
            service.used_bytes += verified - previous
        connection.usage_total_bytes = verified
        connection.usage_raw_bytes = raw
        connection.usage_lifetime_offset = lifetime - raw
        connection.usage_error = None
        service.last_usage_sync_at = now
    elif change.action == "renew":
        assert change.days is not None
        try:
            service.expires_at = max(as_utc(service.expires_at), now) + timedelta(days=change.days)
        except OverflowError:
            raise ServiceConflict("invalid_renewal_date", 400) from None
    else:
        target = "paused" if change.action == "pause" else "active"
        if target == "active" and user.is_banned:
            raise ServiceConflict("account_banned", 403)
        if service.desired_status == target:
            raise ServiceConflict("service_state_unchanged")
        service.desired_status = target
    service.revision += 1
    connection.sync_pending = True
    connection.sync_error = None
    order = ServiceOrder(
        id=uuid4().hex,
        user_id=user_id,
        request_owner_id=user_id,
        service_id=service.id,
        actor_id=actor_id,
        kind=change.action,
        idempotency_key=idempotency_key,
        request=command,
        snapshot={
            "terms": dict(service.terms),
            "plan_id": service.plan_id,
            "plan_revision": service.plan_revision,
            "starts_at": as_utc(service.starts_at).isoformat(),
            "expires_at": as_utc(service.expires_at).isoformat(),
            "quota_bytes": service.quota_bytes,
            "used_bytes": service.used_bytes,
            "usage_total_bytes": connection.usage_total_bytes,
            "usage_raw_bytes": connection.usage_raw_bytes,
            "usage_lifetime_offset": connection.usage_lifetime_offset,
            "before": before,
            "desired_status": service.desired_status,
            "revision": service.revision,
            "change": change.request_values(),
            "fulfillment": "manual",
        },
        created_at=now,
    )
    session.add(order)
    await enqueue_execution(session, service, "entitlement", order=order, source="administrator")
    await session.flush()
    return service, order, False
