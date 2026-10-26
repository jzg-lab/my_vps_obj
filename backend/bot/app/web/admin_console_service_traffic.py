"""Read-only Panel history for one independent service identity, never a billing ledger."""

from datetime import UTC, date, datetime, timedelta
from typing import Literal, cast

from pydantic import Field

from bot.app.web.admin_console_nodes_schemas import ConsoleTrafficDayOut
from bot.app.web.admin_console_nodes_traffic import _parse_traffic, traffic_days
from bot.app.web.http_contracts import HttpResponseModel
from bot.services.panel_api_service import PanelApiService
from bot.utils.ttl_cache import AsyncTTLCache


class ConsoleServiceTrafficNodeOut(HttpResponseModel):
    node_id: str
    bytes: int = Field(ge=0)


class ConsoleServiceTrafficOut(HttpResponseModel):
    service_id: str
    start_date: date
    end_date: date
    timezone: Literal["UTC"] = "UTC"
    availability: Literal["available", "partial", "unavailable", "unconfigured"]
    observed_at: datetime | None = None
    days: list[ConsoleTrafficDayOut] = Field(default_factory=list)
    nodes: list[ConsoleServiceTrafficNodeOut] = Field(default_factory=list)
    source: Literal["panel_service_identity_raw_traffic_not_billing"] = (
        "panel_service_identity_raw_traffic_not_billing"
    )
    history_completeness: Literal["unknown"] = "unknown"


def parse_service_traffic(
    data: object, service_id: str, start: date, end: date
) -> ConsoleServiceTrafficOut:
    parsed = _parse_traffic(data, start, end)
    assert isinstance(data, dict)
    days = traffic_days(data.get("sparklineData"), start, end)
    complete = bool(days) and all(day.bytes is not None for day in days) and not parsed.partial
    return ConsoleServiceTrafficOut(
        service_id=service_id,
        start_date=start,
        end_date=end,
        availability="available" if complete else "partial",
        observed_at=parsed.observed_at,
        days=days,
        nodes=[
            ConsoleServiceTrafficNodeOut(node_id=identity, bytes=value)
            for identity, value in parsed.totals.items()
            if value > 0
        ],
    )


class ServiceTrafficReader:
    def __init__(self) -> None:
        self.cache = AsyncTTLCache(ttl_seconds=15, max_entries=128)

    async def read(
        self,
        panel: PanelApiService | None,
        service_id: str,
        identity: str | None,
        *,
        now: datetime | None = None,
    ) -> ConsoleServiceTrafficOut:
        end = (now or datetime.now(UTC)).astimezone(UTC).date()
        start = end - timedelta(days=6)
        missing = ConsoleServiceTrafficOut(
            service_id=service_id, start_date=start, end_date=end, availability="unconfigured"
        )
        if panel is None or not identity:
            return missing

        async def load() -> ConsoleServiceTrafficOut:
            data = await panel.get_user_bandwidth_stats(
                identity, start=start.isoformat(), end=end.isoformat(), top_nodes_limit=1
            )
            return parse_service_traffic(data, service_id, start, end)

        try:
            return cast(
                ConsoleServiceTrafficOut,
                await self.cache.get_or_load(f"{service_id}:{identity}:{start}:{end}", load),
            )
        except Exception:
            missing.availability = "unavailable"
            return missing
