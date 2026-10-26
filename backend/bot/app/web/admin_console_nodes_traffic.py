"""UTC calendar-window totals, separate from inventory and tracking counters."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import cast
from uuid import UUID

from bot.app.web.admin_console_nodes_schemas import (
    ConsoleNodeOut,
    ConsoleNodeTrafficPreset,
    ConsoleNodeTrafficWindowOut,
    ConsoleTrafficDayOut,
)
from bot.services.panel_api_service import PanelApiService
from bot.utils.ttl_cache import AsyncTTLCache


def traffic_dates(preset: ConsoleNodeTrafficPreset, now: datetime) -> tuple[date, date]:
    end = now.astimezone(UTC).date()
    return end - timedelta(days={"today": 1, "7d": 7, "30d": 30}[preset] - 1), end


@dataclass
class _Traffic:
    totals: dict[str, int]
    daily: dict[str, list[ConsoleTrafficDayOut]]
    invalid_ids: set[str]
    partial: bool
    observed_at: datetime


def _parse_traffic(data: object, start: date, end: date) -> _Traffic:
    dates = [
        (start + timedelta(days=offset)).isoformat() for offset in range((end - start).days + 1)
    ]
    if not isinstance(data, dict) or data.get("categories") != dates:
        raise ValueError("invalid_response")
    rows = data.get("series")
    if not isinstance(rows, list):
        raise ValueError("invalid_response")
    totals: dict[str, int] = {}
    daily: dict[str, list[ConsoleTrafficDayOut]] = {}
    seen: set[str] = set()
    invalid_ids: set[str] = set()
    partial = False
    for row in rows:
        try:
            if not isinstance(row, dict) or not isinstance(row.get("uuid"), str):
                raise ValueError("invalid_response")
            identity = str(UUID(row["uuid"]))
        except ValueError:
            partial = True
            continue
        total = row.get("total")
        # Upstream converts bigint to JS Number; unsafe integers cannot claim exact bytes.
        if identity in seen or type(total) is not int or not 0 <= total <= 2**53 - 1:
            invalid_ids.add(identity)
            totals.pop(identity, None)
            daily.pop(identity, None)
            partial = True
        elif identity not in invalid_ids:
            totals[identity] = total
            daily[identity] = traffic_days(row.get("data"), start, end)
        seen.add(identity)
    return _Traffic(totals, daily, invalid_ids, partial, datetime.now(UTC))


def traffic_days(values: object, start: date, end: date) -> list[ConsoleTrafficDayOut]:
    count = (end - start).days + 1
    if not isinstance(values, list) or len(values) != count:
        return []
    return [
        ConsoleTrafficDayOut(
            date=start + timedelta(days=index),
            bytes=value if type(value) is int and 0 <= value <= 2**53 - 1 else None,
        )
        for index, value in enumerate(values)
    ]


class NodeTrafficReader:
    def __init__(self) -> None:
        self.cache = AsyncTTLCache(ttl_seconds=15, max_entries=6)

    async def _load(self, panel: PanelApiService, start: date, end: date) -> _Traffic:
        # 3.4.5 series is unbounded by topNodesLimit; never use the ranking as inventory.
        data = await panel.get_nodes_bandwidth_usage(
            start=start.isoformat(), end=end.isoformat(), top_nodes_limit=1
        )
        if data is None:
            raise RuntimeError("request_failed")
        return _parse_traffic(data, start, end)

    async def read(
        self,
        panel: PanelApiService | None,
        *,
        preset: ConsoleNodeTrafficPreset,
        nodes: list[ConsoleNodeOut],
        inventory_complete: bool,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> ConsoleNodeTrafficWindowOut:
        now = now or datetime.now(UTC)
        for node in nodes:
            node.window_traffic_bytes = None
            node.window_traffic_quality = "missing"
            node.daily_traffic = []
        start, end = traffic_dates(preset, now)
        key = f"{preset}:{start.isoformat()}:{end.isoformat()}:UTC"
        self.cache.ttl_seconds = max(0, ttl_seconds)
        result = ConsoleNodeTrafficWindowOut(
            preset=preset,
            start_date=start,
            end_date=end,
            start_at=datetime.combine(start, time.min, UTC),
            end_at=datetime.combine(end, time(23, 59, 59, 999000), UTC),
            availability="unavailable",
            attempted_at=now,
            last_success_at=None,
            inventory_nodes=len(nodes) if inventory_complete else None,
            matched_nodes=0,
            cache_ttl_seconds=max(0, ttl_seconds),
        )
        if panel is None:
            result.availability = "unconfigured"
            result.error = "not_configured"
            return result
        data: _Traffic | None
        try:
            data = cast(
                _Traffic, await self.cache.get_or_load(key, lambda: self._load(panel, start, end))
            )
            result.availability = "available"
        except Exception as exc:
            result.error = "invalid_response" if isinstance(exc, ValueError) else "request_failed"
            data = cast(_Traffic | None, self.cache.get_stale(key))
            if data is None:
                return result
            result.availability = "stale"
        result.last_success_at = data.observed_at
        if result.availability != "stale":
            result.attempted_at = data.observed_at
        known_ids = {node.id for node in nodes}
        for node in nodes:
            node.window_traffic_bytes = data.totals.get(node.id)
            node.daily_traffic = data.daily.get(node.id, [])
            node.window_traffic_quality = (
                "invalid"
                if node.id in data.invalid_ids
                else "reported"
                if node.id in data.totals
                else "missing"
            )
        result.matched_nodes = len(known_ids & data.totals.keys())
        if result.availability != "stale" and (
            data.partial
            or not inventory_complete
            or result.matched_nodes != len(nodes)
            or bool(data.totals.keys() - known_ids)
        ):
            result.availability = "partial"
        if data.partial and result.error is None:
            result.error = "invalid_response"
        return result
