"""Explicit administrator evidence, never inferred from inventory or panel success."""

from datetime import UTC, datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Literal

from pydantic import ConfigDict, Field, field_validator

from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from config.service_periods import as_utc
from db.service_models import DedicatedExitAudit


class ExitEvidenceBody(HttpBodyModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: int = Field(gt=0, strict=True)
    service_id: str | None = Field(pattern=r"^[a-f0-9]{32}$")
    idempotency_key: str = Field(min_length=1, max_length=128)
    checked_at: datetime
    evidence: str = Field(min_length=10, max_length=2000)

    @field_validator("checked_at")
    @classmethod
    def valid_observation_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value > datetime.now(UTC):
            raise ValueError("observation must have a timezone and cannot be in the future")
        return as_utc(value)


class ExitVerifyBody(ExitEvidenceBody):
    observed_ip: IPv4Address | IPv6Address
    fixed: Literal[True]
    exclusive: Literal[True]

    @field_validator("observed_ip")
    @classmethod
    def normalize_ip(cls, value: IPv4Address | IPv6Address) -> IPv4Address | IPv6Address:
        return value.ipv4_mapped or value if isinstance(value, IPv6Address) else value


class ExitReclaimBody(ExitEvidenceBody):
    service_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    connections_stopped: Literal[True]
    old_config_rejected: Literal[True]


class ServiceDeliverBody(HttpBodyModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    user_id: int = Field(ge=-(2**53 - 1), le=2**53 - 1, strict=True)
    expected_revision: int = Field(gt=0, strict=True)
    idempotency_key: str = Field(min_length=1, max_length=128)


class ServiceRevokeBody(ServiceDeliverBody):
    reason: str = Field(min_length=3, max_length=1000)


class ExitAuditOut(HttpResponseModel):
    id: str
    exit_id: str
    service_id: str | None
    actor_id: int
    action: str
    evidence: dict[str, object]
    created_at: datetime

    @classmethod
    def from_orm_audit(cls, row: DedicatedExitAudit) -> "ExitAuditOut":
        return cls(
            id=row.id,
            exit_id=row.exit_id,
            service_id=row.service_id,
            actor_id=row.actor_id,
            action=row.action,
            evidence=row.evidence,
            created_at=as_utc(row.created_at),
        )


class ServiceSubscriptionOut(HttpResponseModel):
    service_id: str
    subscription_url: str
