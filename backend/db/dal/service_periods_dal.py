"""Monthly checkpoints are committed before the corresponding absolute panel cap."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from config.service_periods import as_utc, monthly_period
from db.service_models import ServiceConnection, ServiceUsagePeriod, UserService


def cycle_due(service: UserService, now: datetime) -> bool:
    return (
        service.terms.get("traffic_rule") == "monthly"
        and service.cycle_ends_at is not None
        and as_utc(service.cycle_ends_at) <= as_utc(now) < as_utc(service.expires_at)
        and service.desired_status != "cancelled"
    )


async def prepare_period(
    session: AsyncSession, service: UserService, connection: ServiceConnection, now: datetime
) -> None:
    if connection.cycle_cutover_bytes is not None or not cycle_due(service, now):
        return
    total = connection.usage_total_bytes
    if total is None or connection.usage_error is not None or service.cycle_started_at is None:
        return
    if total + service.quota_bytes > 2**53 - 1:
        connection.sync_error = "panel_limit_invalid"
        return
    assert service.cycle_ends_at is not None
    start, end = monthly_period(service.starts_at, now)
    period = ServiceUsagePeriod(
        service_id=service.id,
        cycle_started_at=service.cycle_started_at,
        cycle_ends_at=service.cycle_ends_at,
        used_bytes=service.used_bytes,
        quota_bytes=service.quota_bytes,
        cutover_bytes=total,
        next_started_at=start,
        next_ends_at=end,
        created_at=now,
    )
    session.add(period)
    connection.cycle_cutover_bytes = total
    connection.sync_pending = True
    connection.sync_error = "panel_cycle_unconfirmed"
    await session.flush()


async def confirm_period(
    session: AsyncSession, service: UserService, connection: ServiceConnection, now: datetime
) -> bool:
    cutover = connection.cycle_cutover_bytes
    total = connection.usage_total_bytes
    if cutover is None or total is None or service.cycle_started_at is None:
        return False
    period = await session.get(ServiceUsagePeriod, (service.id, service.cycle_started_at))
    if period is None or period.confirmed_at is not None or period.cutover_bytes != cutover:
        connection.sync_error = "panel_cycle_conflict"
        return False
    if total < cutover or connection.usage_error is not None:
        return False
    service.used_bytes = total - cutover
    service.last_usage_sync_at = now
    service.cycle_started_at = period.next_started_at
    service.cycle_ends_at = period.next_ends_at
    period.confirmed_at = now
    connection.cycle_cutover_bytes = None
    return True
