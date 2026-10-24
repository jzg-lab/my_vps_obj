"""Fresh, fail-closed projections of the pinned Remnawave 3.4.5 inventory."""

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, StrictBool, ValidationError

from bot.app.web.admin_console_resource_schemas import ResourceSourceOut
from bot.services.panel_api_contracts import PanelApiOperation
from bot.services.panel_api_service import PanelApiService


class ResourceRef(BaseModel):
    uuid: UUID


class PreviewNodeProfile(BaseModel):
    activeConfigProfileUuid: UUID | None
    activeInbounds: list[ResourceRef]


class PreviewNode(ResourceRef):
    name: str
    isDisabled: StrictBool
    configProfile: PreviewNodeProfile
    address: str | None = None
    port: int | None = Field(default=None, strict=True, ge=1, le=65535)
    note: str | None = None


class PreviewGroup(ResourceRef):
    name: str
    inbounds: list[ResourceRef]


class PreviewHostInbound(BaseModel):
    configProfileUuid: UUID | None
    configProfileInboundUuid: UUID | None


class PreviewHostGroups(BaseModel):
    mode: Literal["EXCLUDE", "ALLOW_ONLY"]
    squads: list[UUID]


class PreviewHost(ResourceRef):
    remark: str
    address: str
    port: int = Field(strict=True, ge=1, le=65535)
    inbound: PreviewHostInbound
    nodes: list[UUID]
    isDisabled: StrictBool
    isHidden: StrictBool
    internalSquads: PreviewHostGroups
    tags: list[str] = Field(default_factory=list)


class PreviewInbound(ResourceRef):
    profileUuid: UUID
    tag: str


class PreviewProfile(ResourceRef):
    name: str
    inbounds: list[PreviewInbound]
    nodes: list[ResourceRef]
    # Retained only for an internal digest; never serialized to HTTP or logs.
    config: dict[str, object]


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


@dataclass
class PreviewSource[T: ResourceRef]:
    rows: list[T]
    source: ResourceSourceOut
    fingerprint: str


@dataclass
class PreviewInventory:
    nodes: PreviewSource[PreviewNode]
    hosts: PreviewSource[PreviewHost]
    groups: PreviewSource[PreviewGroup]
    profiles: PreviewSource[PreviewProfile]
    metadata: ResourceSourceOut
    version: str | None

    @property
    def sources(self) -> list[ResourceSourceOut]:
        return [
            self.metadata,
            self.nodes.source,
            self.hosts.source,
            self.groups.source,
            self.profiles.source,
        ]

    @property
    def fingerprint(self) -> str:
        return digest(
            [
                self.version,
                self.nodes.fingerprint,
                self.hosts.fingerprint,
                self.groups.fingerprint,
                self.profiles.fingerprint,
            ]
        )


async def _source[T: ResourceRef](
    panel: PanelApiService | None,
    source: Literal["nodes", "hosts", "groups", "profiles"],
    endpoint: str,
    model: type[T],
    key: str | None,
    operation: PanelApiOperation | None = None,
) -> PreviewSource[T]:
    observed = datetime.now(UTC)
    unavailable = PreviewSource[T](
        [], ResourceSourceOut(source=source, availability="unavailable", observed_at=observed), ""
    )
    if panel is None:
        return unavailable
    try:
        response = await panel._request(
            "GET", endpoint, operation=operation, log_full_response=False
        )
        if not response or response.get("error"):
            return unavailable
        body: object = response.get("response")
        total: object = None
        if key is not None:
            if not isinstance(body, dict):
                raise ValueError("invalid_inventory")
            total = body.get("total")
            body = body.get(key)
            if type(total) is not int or total < 0:
                raise ValueError("invalid_inventory_total")
        if not isinstance(body, list):
            raise ValueError("invalid_inventory")
        rows = [model.model_validate(item) for item in body]
        if len({row.uuid for row in rows}) != len(rows) or (
            total is not None and total != len(rows)
        ):
            raise ValueError("partial_inventory")
        # Node telemetry changes continuously; only configuration belongs in the guard.
        raw = (
            [row.model_dump(mode="json") for row in sorted(rows, key=lambda row: row.uuid)]
            if source == "nodes"
            else sorted(body, key=lambda item: str(item["uuid"]))
        )
        return PreviewSource(
            rows,
            ResourceSourceOut(
                source=source, availability="available", observed_at=datetime.now(UTC)
            ),
            digest(raw),
        )
    except (ValidationError, ValueError, TypeError, KeyError):
        unavailable.source.availability = "invalid"
    except Exception:
        # Upstream exception text may contain credentials or raw configuration.
        pass
    return unavailable


async def _metadata(panel: PanelApiService | None) -> tuple[ResourceSourceOut, str | None]:
    source = ResourceSourceOut(
        source="metadata", availability="unavailable", observed_at=datetime.now(UTC)
    )
    if panel is None:
        return source, None
    try:
        data = await panel._request(
            "GET",
            "/system/metadata",
            operation=PanelApiOperation.SYSTEM_METADATA,
            log_full_response=False,
        )
        body: object = data.get("response") if data and not data.get("error") else None
        version = body.get("version") if isinstance(body, dict) else None
        if not isinstance(version, str):
            source.availability = "invalid"
            return source, None
        # Do not echo arbitrary upstream text in the version field.
        normalized = version.removeprefix("v")
        if normalized != "3.4.5":
            source.availability = "unsupported"
            return source, None
        source.availability = "available"
        source.observed_at = datetime.now(UTC)
        return source, normalized
    except Exception:
        return source, None


async def read_preview_inventory(panel: PanelApiService | None) -> PreviewInventory:
    """No shared cache or stale fallback is suitable for confirmation guards."""
    nodes, hosts, groups, profiles, metadata = await asyncio.gather(
        _source(panel, "nodes", "/nodes", PreviewNode, None, PanelApiOperation.NODES_LIST),
        _source(panel, "hosts", "/hosts", PreviewHost, None, PanelApiOperation.HOSTS_LIST),
        _source(
            panel,
            "groups",
            "/internal-squads",
            PreviewGroup,
            "internalSquads",
            PanelApiOperation.INTERNAL_SQUADS_LIST,
        ),
        _source(panel, "profiles", "/config-profiles", PreviewProfile, "configProfiles"),
        _metadata(panel),
    )
    return PreviewInventory(nodes, hosts, groups, profiles, metadata[0], metadata[1])
