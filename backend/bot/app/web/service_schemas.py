"""Typed contracts for the project's unified plans and independent services."""

from datetime import UTC, datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StrictBool, field_validator

from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from config.service_periods import as_utc
from config.service_plans import ServicePlanTerms
from db.service_models import (
    DedicatedExit,
    ServiceConnection,
    ServiceOrder,
    ServicePlan,
    UserService,
)


class ServicePlanBody(HttpBodyModel):
    model_config = ConfigDict(extra="forbid")
    terms: ServicePlanTerms
    enabled: StrictBool


class ServicePlanUpdateBody(ServicePlanBody):
    expected_revision: int = Field(gt=0, strict=True)


class ServiceActivationBody(HttpBodyModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    user_id: int = Field(ge=-(2**53 - 1), le=2**53 - 1, strict=True)
    plan_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    expected_revision: int = Field(gt=0, strict=True)
    idempotency_key: str = Field(min_length=1, max_length=128)
    exit_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class DedicatedExitBody(HttpBodyModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    label: str = Field(min_length=1, max_length=160)
    ip_address: IPv4Address | IPv6Address
    resource_pool: str = Field(min_length=1, max_length=120)
    squad_uuid: UUID

    @field_validator("ip_address")
    @classmethod
    def normalize_ip(cls, value: IPv4Address | IPv6Address) -> IPv4Address | IPv6Address:
        if isinstance(value, IPv6Address) and value.ipv4_mapped is not None:
            return value.ipv4_mapped
        return value


class ServicePlanOut(HttpResponseModel):
    id: str
    revision: int
    terms: ServicePlanTerms
    enabled: bool
    updated_at: datetime

    @classmethod
    def from_orm_plan(cls, plan: ServicePlan) -> "ServicePlanOut":
        return cls(
            id=plan.id,
            revision=plan.revision,
            terms=ServicePlanTerms.model_validate(plan.terms),
            enabled=plan.enabled,
            updated_at=as_utc(plan.updated_at),
        )


class UserServiceOut(HttpResponseModel):
    id: str
    user_id: int
    plan_id: str
    plan_revision: int
    name: str
    description: str
    resource_type: Literal["shared", "dedicated"]
    traffic_rule: Literal["total", "monthly"]
    quota_bytes: int
    used_bytes: int
    starts_at: datetime
    expires_at: datetime
    cycle_started_at: datetime | None
    cycle_ends_at: datetime | None
    last_usage_sync_at: datetime | None
    status: str
    connection_state: str
    exit_ip: str | None
    exit_verified: bool

    @classmethod
    def from_orm_service(
        cls,
        service: UserService,
        connection: ServiceConnection | None,
        resource: DedicatedExit | None,
        *,
        banned: bool = False,
    ) -> "UserServiceOut":
        terms = ServicePlanTerms.model_validate(service.terms)
        state = connection.state if connection is not None else "pending"
        if banned:
            status = "account_banned"
        elif service.desired_status != "active":
            status = service.desired_status
        elif as_utc(service.expires_at) <= datetime.now(UTC):
            status = "expired"
        elif service.used_bytes >= service.quota_bytes:
            status = "exhausted"
        elif state != "ready" or (
            terms.resource_type == "dedicated"
            and (resource is None or resource.verified_at is None or not resource.enabled)
        ):
            status = "pending"
        else:
            status = "active"
        return cls(
            id=service.id,
            user_id=service.user_id,
            plan_id=service.plan_id,
            plan_revision=service.plan_revision,
            name=terms.name,
            description=terms.description,
            resource_type=terms.resource_type,
            traffic_rule=terms.traffic_rule,
            quota_bytes=service.quota_bytes,
            used_bytes=service.used_bytes,
            starts_at=as_utc(service.starts_at),
            expires_at=as_utc(service.expires_at),
            cycle_started_at=as_utc(service.cycle_started_at) if service.cycle_started_at else None,
            cycle_ends_at=as_utc(service.cycle_ends_at) if service.cycle_ends_at else None,
            last_usage_sync_at=(
                as_utc(service.last_usage_sync_at) if service.last_usage_sync_at else None
            ),
            status=status,
            connection_state=state,
            exit_ip=resource.ip_address if resource else None,
            exit_verified=resource is not None and resource.verified_at is not None,
        )


class ServiceOrderOut(HttpResponseModel):
    id: str
    user_id: int
    service_id: str
    actor_id: int
    kind: str
    snapshot: dict[str, object]
    created_at: datetime

    @classmethod
    def from_orm_order(cls, order: ServiceOrder) -> "ServiceOrderOut":
        return cls(
            id=order.id,
            user_id=order.user_id,
            service_id=order.service_id,
            actor_id=order.actor_id,
            kind=order.kind,
            snapshot=order.snapshot,
            created_at=as_utc(order.created_at),
        )


class DedicatedExitOut(HttpResponseModel):
    id: str
    label: str
    ip_address: str
    resource_pool: str
    squad_uuid: str
    service_id: str | None
    verified_at: datetime | None
    enabled: bool

    @classmethod
    def from_orm_exit(cls, resource: DedicatedExit) -> "DedicatedExitOut":
        return cls(
            id=resource.id,
            label=resource.label,
            ip_address=resource.ip_address,
            resource_pool=resource.resource_pool,
            squad_uuid=resource.squad_uuid,
            service_id=resource.service_id,
            verified_at=as_utc(resource.verified_at) if resource.verified_at else None,
            enabled=resource.enabled,
        )
