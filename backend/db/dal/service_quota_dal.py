"""Apply a recorded template quota revision under the service owner's lock."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.service_periods import as_utc
from db.dal.service_operations_dal import enqueue_execution
from db.service_models import ServiceConnection, ServiceOrder, ServicePlanQuotaChange, UserService


async def apply_latest_quota(
    session: AsyncSession, service: UserService, connection: ServiceConnection
) -> None:
    if (
        service.user_id is None
        or service.desired_status == "cancelled"
        or connection.state == "revoked"
    ):
        return
    change = await session.scalar(
        select(ServicePlanQuotaChange)
        .where(
            ServicePlanQuotaChange.plan_id == service.plan_id,
            ServicePlanQuotaChange.revision > service.quota_revision,
        )
        .order_by(ServicePlanQuotaChange.revision.desc())
        .limit(1)
    )
    if change is None:
        return
    before = service.quota_bytes
    service.quota_bytes = change.quota_bytes
    service.quota_revision = change.revision
    service.revision += 1
    connection.sync_pending = True
    connection.sync_error = None
    order = ServiceOrder(
        id=uuid4().hex,
        user_id=service.user_id,
        request_owner_id=service.user_id,
        service_id=service.id,
        actor_id=change.actor_id,
        kind="quota",
        idempotency_key=f"quota:{service.id}:{change.revision}",
        request={"plan_id": change.plan_id, "quota_revision": change.revision},
        snapshot={
            "terms": dict(service.terms),
            "starts_at": as_utc(service.starts_at).isoformat(),
            "expires_at": as_utc(service.expires_at).isoformat(),
            "plan_revision": service.plan_revision,
            "before": {"quota_bytes": before},
            "quota_bytes": service.quota_bytes,
            "used_bytes": service.used_bytes,
            "reason": change.reason,
            "scope": "current_and_future_periods",
            "plan_id": service.plan_id,
            "quota_revision": change.revision,
        },
        created_at=datetime.now(UTC),
    )
    session.add(order)
    await enqueue_execution(session, service, "entitlement", order=order)
    await session.flush()
