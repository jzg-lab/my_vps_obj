"""Calendar-month boundaries retain the original activation day and Beijing time."""

from calendar import monthrange
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

SERVICE_TIMEZONE = ZoneInfo("Asia/Shanghai")


def as_utc(value: datetime) -> datetime:
    # SQLite test databases discard tzinfo; production columns are TIMESTAMPTZ.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def month_boundary(anchor: datetime, offset: int) -> datetime:
    local = as_utc(anchor).astimezone(SERVICE_TIMEZONE)
    year, month = divmod(local.year * 12 + local.month - 1 + offset, 12)
    month += 1
    return local.replace(
        year=year, month=month, day=min(local.day, monthrange(year, month)[1])
    ).astimezone(UTC)


def monthly_period(anchor: datetime, instant: datetime) -> tuple[datetime, datetime]:
    local_anchor = as_utc(anchor).astimezone(SERVICE_TIMEZONE)
    local_now = as_utc(instant).astimezone(SERVICE_TIMEZONE)
    index = max(0, (local_now.year - local_anchor.year) * 12 + local_now.month - local_anchor.month)
    if index > 0 and month_boundary(anchor, index) > as_utc(instant):
        index -= 1
    return month_boundary(anchor, index), month_boundary(anchor, index + 1)
