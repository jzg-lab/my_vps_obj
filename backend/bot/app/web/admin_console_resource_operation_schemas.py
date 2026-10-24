"""Confirmed resource intentions and explicit reconciliation, without raw configuration."""

from datetime import UTC, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from bot.app.web.admin_console_resource_schemas import (
    ConsoleResourcePreviewOut,
    ResourceBody,
    ResourceChange,
    ResourceValuesOut,
)
from bot.app.web.http_contracts import HttpResponseModel

type ResourceOperationStatus = Literal["pending", "unknown", "failed", "succeeded", "superseded"]


class ConsoleResourceOperationStartBody(ResourceBody):
    change: ResourceChange
    expected_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=128)
    recovery_of: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class ConsoleResourceOperationRetryBody(ResourceBody):
    expected_version: int = Field(strict=True, gt=0)
    expected_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class ConsoleResourceOperationReconcileBody(ResourceBody):
    expected_version: int = Field(strict=True, gt=0)


class ConsoleResourceOperationEvidenceBody(ConsoleResourceOperationReconcileBody):
    attempt: int = Field(strict=True, gt=0)
    result: Literal["applied", "not_applied", "partial", "externally_removed"]
    target_id: UUID | None = None
    evidence_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    checked_at: datetime
    original_request_terminated: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def observed_time(self) -> Self:
        if self.checked_at.tzinfo is None or self.checked_at > datetime.now(UTC):
            raise ValueError("invalid_resource_evidence_time")
        if self.result == "externally_removed":
            if self.target_id is None or self.original_request_terminated is not True:
                raise ValueError("invalid_resource_removal_evidence")
        elif self.original_request_terminated is not None:
            raise ValueError("invalid_resource_removal_evidence")
        return self


class ResourceAttemptOut(HttpResponseModel):
    number: int
    started_at: datetime
    receipt: Literal["unknown", "accepted", "rejected"]


class ResourceEvidenceOut(HttpResponseModel):
    actor_id: int
    attempt: int
    result: Literal["applied", "not_applied", "partial", "externally_removed"]
    target_id: str | None
    evidence_digest: str
    observed_at: datetime
    recorded_at: datetime
    original_request_terminated: bool | None = Field(default=None, strict=True)
    provenance: Literal["administrator_attestation"] = "administrator_attestation"


class ResourceObservationOut(HttpResponseModel):
    observed_at: datetime
    values: ResourceValuesOut | None
    configuration: Literal["matched", "different", "missing", "unavailable"]
    runtime: Literal["unverified"] = "unverified"
    restart: Literal["not_requested", "accepted_unverified", "may_be_noop", "unknown"]
    correlation: Literal[
        "response_uuid", "creation_marker", "administrator_attestation", "known_uuid", "unresolved"
    ]


class ConsoleResourceOperationOut(HttpResponseModel):
    id: str
    actor_id: int
    status: ResourceOperationStatus
    version: int
    change: ResourceChange
    target_id: str | None
    recovery_of: str | None
    preview: ConsoleResourcePreviewOut
    attempts: list[ResourceAttemptOut]
    observation: ResourceObservationOut | None
    evidence: list[ResourceEvidenceOut]
    gate_active: bool
    error_code: str | None
    created_at: datetime
    completed_at: datetime | None
    can_retry: bool
    requires_manual_reconciliation: bool


class ConsoleResourceOperationAcceptedOut(HttpResponseModel):
    duplicate: bool
    operation: ConsoleResourceOperationOut


class ConsoleResourceOperationListOut(HttpResponseModel):
    items: list[ConsoleResourceOperationOut]
    total: int


class ConsoleResourceOperationQuery(ResourceBody):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=25, ge=1, le=100)


class ConsoleNodeDeploymentBody(ResourceBody):
    management_port: int = Field(strict=True, ge=1, le=65535)


class ConsoleNodeDeploymentOut(HttpResponseModel):
    panel_version: Literal["3.4.5"] = "3.4.5"
    recorded_node_version: Literal["3.4.2"] = "3.4.2"
    management_port: int
    secret_key: str
    credential_semantics: Literal["new_node_certificate_existing_panel_ca"] = (
        "new_node_certificate_existing_panel_ca"
    )
    installation_performed: Literal[False] = False
