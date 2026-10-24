"""Aggregate persisted business records without remote reads or entitlement writes."""

from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from config.service_periods import as_utc
from db.dal.admin_console_services_dal import business_status, cycle_pending, service_query
from db.models import User
from db.service_models import AccountAccessSync, DedicatedExit, ServiceConnection, UserService


async def read_console_summary(session: AsyncSession, *, now: datetime) -> dict[str, object]:
    customers = (
        await session.execute(
            select(
                func.count(User.user_id),
                func.count(User.user_id).filter(
                    select(UserService.id).where(UserService.user_id == User.user_id).exists()
                ),
                func.count(User.user_id).filter(User.is_banned.is_(True)),
            )
        )
    ).one()
    state = business_status(now)
    grouped = (
        await session.execute(
            service_query().with_only_columns(state, func.count(UserService.id)).group_by(state)
        )
    ).all()
    by_status = {str(status): int(count) for status, count in grouped}
    total = sum(by_status.values())
    archived = int(
        await session.scalar(
            select(func.count(UserService.id)).where(UserService.user_id.is_(None))
        )
        or 0
    )
    entitlement = and_(
        UserService.desired_status == "active",
        User.is_banned.is_(False),
        UserService.starts_at <= now,
        UserService.expires_at > now,
        UserService.used_bytes < UserService.quota_bytes,
    )
    valid = int(
        await session.scalar(
            service_query().with_only_columns(func.count(UserService.id)).where(entitlement)
        )
        or 0
    )
    delivery_ready = int(
        await session.scalar(
            service_query()
            .with_only_columns(func.count(UserService.id))
            .where(
                state == "active",
                ServiceConnection.panel_user_uuid.is_not(None),
                ServiceConnection.last_error.is_(None),
                ServiceConnection.usage_total_bytes.is_not(None),
                ServiceConnection.usage_error.is_(None),
                UserService.last_usage_sync_at.is_not(None),
                ServiceConnection.sync_pending.is_(False),
                ServiceConnection.sync_error.is_(None),
            )
        )
        or 0
    )
    usage = (
        await session.execute(
            service_query().with_only_columns(
                func.count(UserService.id).filter(UserService.last_usage_sync_at.is_not(None)),
                func.count(UserService.id).filter(ServiceConnection.usage_error.is_not(None)),
                func.sum(UserService.used_bytes).filter(
                    UserService.last_usage_sync_at.is_not(None)
                ),
                func.min(UserService.last_usage_sync_at),
                func.max(UserService.last_usage_sync_at),
            )
        )
    ).one()
    sampled, errors = int(usage[0]), int(usage[1])
    availability = "available"
    if total and not sampled:
        availability = "unknown"
    elif sampled < total or errors:
        availability = "partial"
    # Health includes archived services: remote revocation may still need work.
    health = (
        await session.execute(
            select(
                func.count(UserService.id).filter(
                    or_(
                        ServiceConnection.service_id.is_(None), ServiceConnection.state == "pending"
                    )
                ),
                func.count(UserService.id).filter(
                    or_(
                        ServiceConnection.state == "error",
                        ServiceConnection.last_error.is_not(None),
                    )
                ),
                func.count(UserService.id).filter(ServiceConnection.sync_pending.is_(True)),
                func.count(UserService.id).filter(ServiceConnection.sync_error.is_not(None)),
                func.count(UserService.id).filter(ServiceConnection.usage_error.is_not(None)),
                func.count(UserService.id).filter(UserService.last_usage_sync_at.is_(None)),
                func.count(UserService.id).filter(cycle_pending(now)),
                func.max(ServiceConnection.sync_confirmed_at),
                func.max(ServiceConnection.attempted_at),
                func.max(ServiceConnection.sync_attempted_at),
                func.max(ServiceConnection.usage_attempted_at),
            )
            .select_from(UserService)
            .outerjoin(ServiceConnection, ServiceConnection.service_id == UserService.id)
        )
    ).one()
    access = (
        await session.execute(
            select(
                func.count(AccountAccessSync.user_id).filter(AccountAccessSync.pending.is_(True)),
                func.count(AccountAccessSync.user_id).filter(
                    AccountAccessSync.last_error.is_not(None)
                ),
                func.max(AccountAccessSync.attempted_at),
            )
        )
    ).one()
    attempts = [as_utc(value) for value in (*health[8:11], access[2]) if value is not None]
    # A bound exit remains occupied until explicit reclaim, even after expiry.
    reclaim = and_(
        DedicatedExit.service_id.is_not(None),
        or_(
            UserService.user_id.is_(None),
            UserService.desired_status == "cancelled",
            UserService.expires_at <= now,
        ),
    )
    exits = (
        await session.execute(
            select(
                func.count(DedicatedExit.id),
                func.count(DedicatedExit.id).filter(
                    and_(
                        DedicatedExit.enabled.is_(True),
                        DedicatedExit.service_id.is_(None),
                        DedicatedExit.hold_order_id.is_(None),
                        DedicatedExit.verified_at.is_not(None),
                    )
                ),
                func.count(DedicatedExit.id).filter(DedicatedExit.service_id.is_not(None)),
                func.count(DedicatedExit.id).filter(
                    and_(
                        DedicatedExit.enabled.is_(True),
                        DedicatedExit.service_id.is_(None),
                        DedicatedExit.hold_order_id.is_(None),
                        DedicatedExit.verified_at.is_(None),
                    )
                ),
                func.count(DedicatedExit.id).filter(reclaim),
                func.count(DedicatedExit.id).filter(DedicatedExit.enabled.is_(False)),
                func.count(DedicatedExit.id).filter(DedicatedExit.verified_at.is_(None)),
            )
            .select_from(DedicatedExit)
            .outerjoin(UserService, UserService.id == DedicatedExit.service_id)
        )
    ).one()
    return {
        "observed_at": now,
        "customers": dict(
            zip(("total", "with_services", "banned"), map(int, customers), strict=True)
        ),
        "services": {
            "total": total,
            "by_status": by_status,
            "entitlement_valid": valid,
            "delivery_ready": delivery_ready,
            "archived": archived,
        },
        "usage": {
            "confirmed_used_bytes": int(usage[2])
            if usage[2] is not None
            else (0 if total == 0 else None),
            "services_total": total,
            "services_sampled": sampled,
            "services_with_errors": errors,
            "oldest_sample_at": as_utc(usage[3]) if usage[3] is not None else None,
            "latest_sample_at": as_utc(usage[4]) if usage[4] is not None else None,
            "availability": availability,
        },
        "health": {
            **dict(
                zip(
                    (
                        "delivery_pending",
                        "delivery_failed",
                        "sync_pending",
                        "sync_failed",
                        "usage_failed",
                        "usage_unobserved",
                        "cycle_pending",
                    ),
                    map(int, health[:7]),
                    strict=True,
                )
            ),
            "account_sync_pending": int(access[0]),
            "account_sync_failed": int(access[1]),
            "latest_success_at": as_utc(health[7]) if health[7] is not None else None,
            "latest_attempt_at": max(attempts) if attempts else None,
        },
        "exits": dict(
            zip(
                (
                    "total",
                    "available",
                    "occupied",
                    "pending_verification",
                    "pending_reclaim",
                    "disabled",
                    "unverified_total",
                ),
                map(int, exits),
                strict=True,
            )
        ),
    }
