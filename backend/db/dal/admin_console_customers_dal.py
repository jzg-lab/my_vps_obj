"""One local aggregate query for the accounts on the current customer page."""

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from config.service_periods import as_utc
from db.dal.admin_console_services_dal import (
    business_status,
    cycle_pending,
    service_query,
    sync_error,
)
from db.service_models import ServiceConnection, UserService

_BUSINESS_STATES = (
    "active",
    "pending",
    "paused",
    "cancelled",
    "expired",
    "exhausted",
    "account_banned",
)
_COUNTERS = (
    "total",
    "sync_error",
    "sync_pending",
    "cycle_pending",
    "sync_unobserved",
    "usage_unobserved",
)
_TIMESTAMPS = (
    "oldest_sync_confirmed_at",
    "latest_sync_confirmed_at",
    "oldest_usage_sync_at",
    "latest_usage_sync_at",
)


async def summaries_for_customers(
    session: AsyncSession, user_ids: list[int], *, now: datetime
) -> dict[int, dict[str, object]]:
    if not user_ids:
        return {}
    user_ids = list(dict.fromkeys(user_ids))
    state = business_status(now)
    statement = (
        service_query()
        .with_only_columns(
            UserService.user_id,
            func.count(UserService.id).label("total"),
            *(
                func.count(UserService.id).filter(state == value).label(f"status_{value}")
                for value in _BUSINESS_STATES
            ),
            func.count(UserService.id).filter(sync_error()).label("sync_error"),
            func.count(UserService.id)
            .filter(ServiceConnection.sync_pending.is_(True))
            .label("sync_pending"),
            func.count(UserService.id).filter(cycle_pending(now)).label("cycle_pending"),
            func.count(UserService.id)
            .filter(ServiceConnection.sync_confirmed_at.is_(None))
            .label("sync_unobserved"),
            func.count(UserService.id)
            .filter(UserService.last_usage_sync_at.is_(None))
            .label("usage_unobserved"),
            func.min(ServiceConnection.sync_confirmed_at).label("oldest_sync_confirmed_at"),
            func.max(ServiceConnection.sync_confirmed_at).label("latest_sync_confirmed_at"),
            func.min(UserService.last_usage_sync_at).label("oldest_usage_sync_at"),
            func.max(UserService.last_usage_sync_at).label("latest_usage_sync_at"),
        )
        .where(UserService.user_id.in_(user_ids))
        .group_by(UserService.user_id)
    )
    rows = (await session.execute(statement)).mappings().all()
    summaries: dict[int, dict[str, object]] = {
        user_id: {
            **dict.fromkeys(_COUNTERS, 0),
            **dict.fromkeys(_TIMESTAMPS),
            "by_status": dict.fromkeys(_BUSINESS_STATES, 0),
            "observed_at": now,
        }
        for user_id in user_ids
    }
    for row in rows:
        summaries[int(row["user_id"])] = {
            **{key: int(row[key]) for key in _COUNTERS},
            **{key: as_utc(row[key]) if row[key] is not None else None for key in _TIMESTAMPS},
            "by_status": {value: int(row[f"status_{value}"]) for value in _BUSINESS_STATES},
            "observed_at": now,
        }
    return summaries
