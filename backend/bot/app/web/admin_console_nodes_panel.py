"""Safe projections of Remnawave's UUID-based inventory (2.8 / 3.x)."""

import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel, Field, StrictBool, ValidationError, field_validator

from bot.app.web.admin_console_node_metrics import parse_node_system
from bot.app.web.admin_console_nodes_schemas import (
    ConsoleHostOut,
    ConsoleNodeOut,
    ConsoleNodesCoverage,
    ConsoleNodeSourceOut,
    ConsoleResourceRefOut,
)
from bot.services.panel_api_contracts import PanelApiOperation
from bot.services.panel_api_service import PanelApiService
from bot.utils.ttl_cache import AsyncTTLCache
from db.dal.admin_console_nodes_dal import ServiceResourceRow, replacement_impacts


class _Resource(BaseModel):
    uuid: UUID


class _NodeProfile(BaseModel):
    activeConfigProfileUuid: UUID | None = None
    activeInbounds: list[_Resource]


class _Node(_Resource):
    name: str
    address: str | None = None
    countryCode: str | None = None
    isConnected: StrictBool | None = None
    isDisabled: StrictBool | None = None
    isConnecting: StrictBool | None = None
    lastStatusChange: datetime | None = None
    configProfile: _NodeProfile | None = None
    usersOnline: int | None = None
    system: object = None
    isTrafficTrackingActive: StrictBool | None = None
    trafficUsedBytes: int | None = None
    trafficResetDay: int | None = None

    @field_validator("usersOnline", "trafficUsedBytes", "trafficResetDay", mode="before")
    @classmethod
    def known_nonnegative_count(cls, value: object) -> int | None:
        return value if type(value) is int and value >= 0 else None

    @field_validator("lastStatusChange")
    @classmethod
    def dated_observation(cls, value: datetime | None) -> datetime | None:
        return value if value is not None and value.tzinfo is not None else None


class _Squad(_Resource):
    name: str
    inbounds: list[_Resource]


class _HostInbound(BaseModel):
    configProfileInboundUuid: UUID | None


class _HostSquads(BaseModel):
    mode: Literal["EXCLUDE", "ALLOW_ONLY"]
    squads: list[UUID]


class _Host(_Resource):
    remark: str
    inbound: _HostInbound
    nodes: list[UUID] = Field(default_factory=list)
    isDisabled: StrictBool | None = None
    isHidden: StrictBool | None = None
    internalSquads: _HostSquads | None = None
    excludedInternalSquads: list[UUID] | None = None

    def permits(self, groups: set[str]) -> bool | None:
        if self.internalSquads is not None:
            selected = {str(value) for value in self.internalSquads.squads}
            if self.internalSquads.mode == "ALLOW_ONLY":
                return bool(selected & groups)
            return bool(groups - selected)
        if self.excludedInternalSquads is not None:
            return bool(groups - {str(value) for value in self.excludedInternalSquads})
        return None


@dataclass
class _SourceData[T: _Resource]:
    rows: list[T]
    source: ConsoleNodeSourceOut


class _SourceUnavailable(Exception):
    def __init__(
        self, error: Literal["request_failed", "invalid_response", "not_supported"]
    ) -> None:
        self.error = error


@dataclass
class NodeInventory:
    nodes: _SourceData[_Node]
    hosts: _SourceData[_Host]
    squads: _SourceData[_Squad]

    @property
    def sources(self) -> list[ConsoleNodeSourceOut]:
        return [self.nodes.source, self.hosts.source, self.squads.source]

    @property
    def coverage(self) -> ConsoleNodesCoverage:
        states = {source.availability for source in self.sources}
        if self.nodes.source.availability in {"unavailable", "unsupported", "unconfigured"}:
            return "unavailable"
        if "stale" in states:
            return "stale"
        if states != {"available"} or any(node.configProfile is None for node in self.nodes.rows):
            return "partial"
        return "complete"

    def scope_coverage(self, rows: list[ServiceResourceRow]) -> ConsoleNodesCoverage:
        """Call before pagination: local hold uncertainty is separate from panel health."""
        if self.coverage == "complete" and replacement_impacts(rows):
            return "partial"
        return self.coverage

    def group_refs(self, ids: set[str]) -> list[ConsoleResourceRefOut]:
        labels = {str(squad.uuid): squad.name for squad in self.squads.rows}
        return [ConsoleResourceRefOut(id=value, name=labels.get(value)) for value in sorted(ids)]

    def node_groups(self, node: _Node) -> set[str]:
        inbounds = (
            {item.uuid for item in node.configProfile.activeInbounds}
            if node.configProfile
            else set()
        )
        return {
            str(squad.uuid)
            for squad in self.squads.rows
            if inbounds.intersection(item.uuid for item in squad.inbounds)
        }

    def node_out(self, node: _Node) -> ConsoleNodeOut:
        profile = node.configProfile
        status: Literal["online", "offline", "unknown"] = "unknown"
        if node.isDisabled is True or node.isConnected is False:
            status = "offline"
        elif node.isConnected is True:
            status = "online"
        # A stale positive observation cannot establish that a node is online now.
        if self.nodes.source.availability == "stale":
            status = "unknown"
        # Panel 3.4.5 also writes zero on user-stat failures, independently of system stats.
        unverified_zero = node.usersOnline == 0
        return ConsoleNodeOut(
            id=str(node.uuid),
            name=node.name,
            address=node.address,
            country_code=node.countryCode or None,
            status=status,
            is_disabled=node.isDisabled,
            is_connecting=node.isConnecting,
            last_status_change_at=node.lastStatusChange,
            observed_at=self.nodes.source.last_success_at,
            profile_id=str(profile.activeConfigProfileUuid)
            if profile and profile.activeConfigProfileUuid
            else None,
            inbound_ids=[str(item.uuid) for item in profile.activeInbounds] if profile else [],
            groups=self.group_refs(self.node_groups(node)),
            users_online=None if unverified_zero else node.usersOnline,
            users_online_quality=(
                "unverified_zero"
                if unverified_zero
                else "missing"
                if node.usersOnline is None
                else "reported"
            ),
            system=parse_node_system(node.system),
            traffic_used_bytes=node.trafficUsedBytes
            if node.isTrafficTrackingActive is True
            else None,
            traffic_tracking_enabled=node.isTrafficTrackingActive,
            traffic_reset_day=node.trafficResetDay,
        )

    def node_hosts(self, node: _Node, *, groups: set[str] | None = None) -> list[ConsoleHostOut]:
        inbounds = (
            {item.uuid for item in node.configProfile.activeInbounds}
            if node.configProfile
            else set()
        )
        result = []
        for host in self.hosts.rows:
            if host.inbound.configProfileInboundUuid not in inbounds or (
                host.nodes and node.uuid not in host.nodes
            ):
                continue
            if groups is not None:
                # Subscription visibility can be narrower than the inbound's group.
                allowed_groups = {
                    str(squad.uuid)
                    for squad in self.squads.rows
                    if str(squad.uuid) in groups
                    and any(
                        item.uuid == host.inbound.configProfileInboundUuid
                        for item in squad.inbounds
                    )
                }
                if (
                    host.isDisabled is True
                    or host.isHidden is True
                    or host.permits(allowed_groups) is not True
                ):
                    continue
                if not allowed_groups:
                    continue
            result.append(
                ConsoleHostOut(
                    id=str(host.uuid),
                    name=host.remark,
                    inbound_id=str(host.inbound.configProfileInboundUuid),
                    node_ids=[str(value) for value in host.nodes],
                    is_disabled=host.isDisabled,
                    is_hidden=host.isHidden,
                )
            )
        return result


class NodeInventoryReader:
    """One cache per application: single-flight reads, bounded stale fallback."""

    def __init__(self) -> None:
        self.cache = AsyncTTLCache(ttl_seconds=15, max_entries=3)
        self.last_success_at: dict[str, datetime] = {}

    async def read(self, panel: PanelApiService | None, *, ttl_seconds: int) -> NodeInventory:
        self.cache.ttl_seconds = max(0, ttl_seconds)
        nodes, hosts, squads = await asyncio.gather(
            self._read_source(
                panel, "nodes", "/nodes", PanelApiOperation.NODES_LIST, _Node, ("nodes", "items")
            ),
            self._read_source(
                panel, "hosts", "/hosts", PanelApiOperation.HOSTS_LIST, _Host, ("hosts", "items")
            ),
            self._read_source(
                panel,
                "internal_squads",
                "/internal-squads",
                PanelApiOperation.INTERNAL_SQUADS_LIST,
                _Squad,
                ("internalSquads", "squads", "items"),
            ),
        )
        return NodeInventory(nodes, hosts, squads)

    async def _read_source[T: _Resource](
        self,
        panel: PanelApiService | None,
        source: Literal["nodes", "hosts", "internal_squads"],
        endpoint: str,
        operation: PanelApiOperation,
        model: type[T],
        keys: tuple[str, ...],
    ) -> _SourceData[T]:
        now = datetime.now(UTC)
        if panel is None:
            return _SourceData(
                [],
                ConsoleNodeSourceOut(
                    source=source,
                    availability="unconfigured",
                    attempted_at=now,
                    error="not_configured",
                ),
            )
        try:
            loaded = await self.cache.get_or_load(
                source,
                lambda: self._load_source(panel, source, endpoint, operation, model, keys),
            )
            return cast(_SourceData[T], loaded)
        except Exception as exc:
            # Upstream errors can contain tokens or raw response bodies; never expose them.
            error = exc.error if isinstance(exc, _SourceUnavailable) else "request_failed"
            stale = cast(_SourceData[T] | None, self.cache.get_stale(source))
            if stale is not None:
                return replace(
                    stale,
                    source=stale.source.model_copy(
                        update={
                            "availability": "stale",
                            "attempted_at": now,
                            "error": error,
                        }
                    ),
                )
            return _SourceData(
                [],
                ConsoleNodeSourceOut(
                    source=source,
                    availability="unsupported" if error == "not_supported" else "unavailable",
                    attempted_at=now,
                    last_success_at=self.last_success_at.get(source),
                    error=error,
                ),
            )

    async def _load_source[T: _Resource](
        self,
        panel: PanelApiService,
        source: Literal["nodes", "hosts", "internal_squads"],
        endpoint: str,
        operation: PanelApiOperation,
        model: type[T],
        keys: tuple[str, ...],
    ) -> _SourceData[T]:
        data = await panel._request("GET", endpoint, operation=operation, log_full_response=False)
        if not data or data.get("error"):
            raise _SourceUnavailable(
                "not_supported"
                if data and data.get("status_code") in (404, 405)
                else "request_failed"
            )
        if "response" not in data:
            raise _SourceUnavailable("invalid_response")
        body: object = data["response"]
        expected_total: object = None
        if isinstance(body, dict):
            expected_total = body.get("total")
            body = next((body[key] for key in keys if isinstance(body.get(key), list)), None)
        if not isinstance(body, list):
            raise _SourceUnavailable("invalid_response")
        rows = []
        seen: set[str] = set()
        partial = False
        for item in body:
            try:
                row = model.model_validate(item)
                identity = str(row.uuid)
                if identity in seen:
                    partial = True
                    continue
                seen.add(identity)
                rows.append(row)
            except ValidationError:
                partial = True
        partial = partial or (type(expected_total) is int and expected_total != len(rows))
        observed_at = datetime.now(UTC)
        self.last_success_at[source] = observed_at
        return _SourceData(
            rows,
            ConsoleNodeSourceOut(
                source=source,
                availability="partial" if partial else "available",
                attempted_at=observed_at,
                last_success_at=observed_at,
                error="invalid_response" if partial else None,
            ),
        )
