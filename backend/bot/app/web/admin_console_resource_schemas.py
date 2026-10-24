"""UC-06 read-only change proposals and fresh impact comparisons."""

import re
from datetime import datetime
from ipaddress import ip_address
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    ConfigDict,
    Field,
    StrictBool,
    field_serializer,
    field_validator,
    model_validator,
)

from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel


class ResourceBody(HttpBodyModel):
    model_config = ConfigDict(extra="forbid")


class ResourceGroupChange(ResourceBody):
    operation: Literal["group_inbounds"]
    target_id: UUID
    inbound_ids: list[UUID]

    @field_validator("inbound_ids")
    @classmethod
    def unique_inbounds(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("duplicate_resource_id")
        return sorted(value)


class ResourceHostPatch(ResourceBody):
    profile_id: UUID | None = None
    inbound_id: UUID | None = None
    node_ids: list[UUID] | None = None
    is_disabled: StrictBool | None = None
    is_hidden: StrictBool | None = None
    group_mode: Literal["EXCLUDE", "ALLOW_ONLY"] | None = None
    group_ids: list[UUID] | None = None
    address: str | None = Field(default=None, min_length=1, max_length=253)
    port: int | None = Field(default=None, strict=True, ge=1, le=65535)

    @field_validator("node_ids", "group_ids")
    @classmethod
    def unique_ids(cls, value: list[UUID] | None) -> list[UUID] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("duplicate_resource_id")
        return sorted(value) if value is not None else None

    @field_validator("address")
    @classmethod
    def public_endpoint(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            ip_address(value)
        except ValueError:
            if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", value):
                raise ValueError("invalid_host_address") from None
        return value

    @model_validator(mode="after")
    def explicit_patch(self) -> Self:
        fields = self.model_fields_set
        if not fields or any(getattr(self, field) is None for field in fields):
            raise ValueError("empty_or_null_host_patch")
        for left, right in (("profile_id", "inbound_id"), ("group_mode", "group_ids")):
            if (left in fields) != (right in fields):
                raise ValueError("paired_host_fields_required")
        if self.group_mode == "ALLOW_ONLY" and not self.group_ids:
            raise ValueError("allow_only_requires_groups")
        return self


class ResourceHostChange(ResourceBody):
    operation: Literal["host_update"]
    target_id: UUID
    patch: ResourceHostPatch

    @field_serializer("patch")
    def explicit_fields(self, patch: ResourceHostPatch) -> dict[str, object]:
        return patch.model_dump(mode="json", exclude_unset=True)


class ResourceNodeChange(ResourceBody):
    operation: Literal["node_enable", "node_disable", "node_restart"]
    target_id: UUID
    force_restart: StrictBool = False

    @model_validator(mode="after")
    def restart_flag(self) -> Self:
        if self.operation != "node_restart" and self.force_restart:
            raise ValueError("restart_flag_requires_restart")
        return self


class ResourceGroupCreate(ResourceBody):
    operation: Literal["group_create"]
    name: str = Field(min_length=2, max_length=30, pattern=r"^[A-Za-z0-9_\s-]+$")
    inbound_ids: list[UUID]

    @model_validator(mode="after")
    def checked_group(self) -> Self:
        if self.name == "Default-Squad" or len(set(self.inbound_ids)) != len(self.inbound_ids):
            raise ValueError("invalid_group_create")
        self.inbound_ids = sorted(self.inbound_ids)
        return self


class ResourceNodeCreate(ResourceBody):
    operation: Literal["node_create"]
    name: str = Field(min_length=3, max_length=30)
    address: str = Field(min_length=2, max_length=253)
    port: int = Field(strict=True, ge=1, le=65535)
    profile_id: UUID
    inbound_ids: list[UUID] = Field(min_length=1)

    @model_validator(mode="after")
    def checked_node(self) -> Self:
        ResourceHostPatch.public_endpoint(self.address)
        if len(set(self.inbound_ids)) != len(self.inbound_ids):
            raise ValueError("duplicate_resource_id")
        self.inbound_ids = sorted(self.inbound_ids)
        return self


class ResourceHostCreate(ResourceBody):
    operation: Literal["host_create"]
    name: str = Field(min_length=1, max_length=100)
    profile_id: UUID
    inbound_id: UUID
    address: str = Field(min_length=1, max_length=253)
    port: int = Field(strict=True, ge=1, le=65535)
    node_ids: list[UUID]
    group_mode: Literal["EXCLUDE", "ALLOW_ONLY"]
    group_ids: list[UUID]
    is_disabled: StrictBool
    is_hidden: StrictBool

    @model_validator(mode="after")
    def checked_host(self) -> Self:
        ResourceHostPatch.model_validate(self.model_dump(exclude={"operation", "name"}))
        self.node_ids = sorted(self.node_ids)
        self.group_ids = sorted(self.group_ids)
        return self


type ResourceChange = Annotated[
    ResourceGroupChange
    | ResourceHostChange
    | ResourceNodeChange
    | ResourceGroupCreate
    | ResourceHostCreate
    | ResourceNodeCreate,
    Field(discriminator="operation"),
]


class ConsoleResourcePreviewBody(ResourceBody):
    change: ResourceChange


class ConsoleResourceRevalidateBody(ConsoleResourcePreviewBody):
    expected_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class ResourceValuesOut(HttpResponseModel):
    kind: Literal["group", "host", "node"]
    id: str | None
    name: str
    inbound_ids: list[str]
    profile_id: str | None = None
    node_ids: list[str] = Field(default_factory=list)
    is_disabled: bool | None = None
    is_hidden: bool | None = None
    group_mode: Literal["EXCLUDE", "ALLOW_ONLY"] | None = None
    group_ids: list[str] = Field(default_factory=list)
    address: str | None = None
    port: int | None = None
    force_restart: bool | None = None


class ResourceImpactServiceOut(HttpResponseModel):
    service_id: str
    customer_id: int
    name: str
    group_ids: list[str]
    configured_group_ids: list[str]
    observed_group_ids: list[str]
    connection_state: str | None


class ResourceImpactOut(HttpResponseModel):
    group_ids: list[str]
    node_ids: list[str]
    profile_ids: list[str]
    services: list[ResourceImpactServiceOut]
    customer_ids: list[int]
    service_total: int
    customer_total: int


class ResourceSourceOut(HttpResponseModel):
    source: Literal[
        "metadata", "nodes", "hosts", "groups", "profiles", "services", "authorizations"
    ]
    availability: Literal["available", "unavailable", "invalid", "unsupported"]
    observed_at: datetime


class ResourceCatalogInboundOut(HttpResponseModel):
    id: str
    profile_id: str
    tag: str = Field(description="Remnawave 返回的入站标签，不是推断出的名称。")


class ResourceCatalogProfileOut(HttpResponseModel):
    id: str
    name: str
    inbounds: list[ResourceCatalogInboundOut]
    node_ids: list[str]
    config_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class ConsoleResourceCatalogOut(HttpResponseModel):
    """仅用于生成草稿的资源目录，不包含服务影响确认或执行授权。"""

    groups: list[ResourceValuesOut]
    profiles: list[ResourceCatalogProfileOut]
    nodes: list[ResourceValuesOut]
    hosts: list[ResourceValuesOut]
    sources: list[ResourceSourceOut]
    coverage: Literal["complete", "partial"]
    blockers: list[str]
    draft_available: bool = Field(
        description="目录完整时才允许生成草稿；预览和重核仍会重新读取资源。"
    )
    reviewed_panel_version: Literal["3.4.5"] = "3.4.5"
    observed_panel_version: str | None
    observed_at: datetime
    execution_available: bool = False


class ConsoleResourcePreviewOut(HttpResponseModel):
    change: ResourceChange
    current: ResourceValuesOut | None
    proposed: ResourceValuesOut | None
    direct: ResourceImpactOut
    possible_reload: ResourceImpactOut
    affected_service_ids: list[str]
    affected_customer_ids: list[int]
    coverage: Literal["complete", "partial"]
    blockers: list[str]
    sources: list[ResourceSourceOut]
    fingerprint: str | None
    reviewed_panel_version: Literal["3.4.5"] = "3.4.5"
    observed_panel_version: str | None
    observed_at: datetime
    association_basis: Literal["configured_and_observed_scope_not_live_connections"] = (
        "configured_and_observed_scope_not_live_connections"
    )
    remote_authorization_verified: bool
    execution_available: bool = False
    recovery: Literal[
        "restore_previous_inbounds_and_recheck_profile_nodes",
        "restore_previous_host_and_refresh_subscription",
        "inverse_node_action_requires_fresh_preview",
        "restart_has_no_automatic_rollback",
        "creation_requires_explicit_reconciliation_no_automatic_delete",
    ]


class ConsoleResourceRevalidateOut(HttpResponseModel):
    valid: bool
    reason: Literal["unchanged", "changed", "incomplete"]
    preview: ConsoleResourcePreviewOut
