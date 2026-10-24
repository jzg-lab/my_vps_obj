"""Service-scoped replacement commands; HTTP accepts administrator attestations only."""

from datetime import datetime
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from bot.app.web.admin_console_operations_schemas import ConsoleServiceOperationOut
from bot.app.web.admin_console_resource_schemas import ResourceSourceOut
from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from config.service_exit_replacement import (
    ReplacementAction,
    ReplacementCandidateEvidence,
    ReplacementCount,
    ReplacementDigest,
    ReplacementId,
    ReplacementProgress,
    ReplacementStopEvidence,
)


class ReplacementCommand(HttpBodyModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    idempotency_key: str = Field(min_length=1, max_length=128)


class ConsoleExitReplacementStartBody(ReplacementCommand):
    user_id: int = Field(strict=True, ge=-(2**53 - 1), le=2**53 - 1)
    expected_revision: int = Field(strict=True, gt=0)
    old_exit_id: ReplacementId
    new_exit_id: ReplacementId
    expected_old_exit_revision: int = Field(strict=True, gt=0)
    expected_new_exit_revision: int = Field(strict=True, gt=0)
    expected_resource_fingerprint: ReplacementDigest
    reason: str = Field(min_length=3, max_length=1000)


class ConsoleExitReplacementConfirmBody(ReplacementCommand):
    user_id: int = Field(strict=True, ge=-(2**53 - 1), le=2**53 - 1)
    operation_id: ReplacementId
    expected_revision: int = Field(strict=True, gt=0)
    expected_operation_version: int = Field(strict=True, gt=0)
    expected_old_exit_revision: int = Field(strict=True, gt=0)
    expected_new_exit_revision: int = Field(strict=True, gt=0)
    expected_resource_fingerprint: ReplacementDigest
    old_stop_audit_id: ReplacementId
    candidate_verify_audit_id: ReplacementId
    confirm_replace_and_request_restore: Literal[True]

    _explicit = field_validator("confirm_replace_and_request_restore", mode="before")(
        ReplacementStopEvidence.explicit_true
    )


class ConsoleExitReplacementEvidenceBody(ReplacementCommand):
    operation_id: ReplacementId
    expected_operation_version: int = Field(strict=True, gt=0)
    resource_fingerprint: ReplacementDigest
    checked_at: datetime
    evidence_digest: ReplacementDigest
    purpose: Literal["stop", "close", "resolve_write"]
    authorization_removed: Literal[True] | None = None
    connections_stopped: Literal[True] | None = None
    old_config_rejected: Literal[True] | None = None
    usage_observed_at: datetime | None = None
    usage_total_bytes: ReplacementCount | None = None
    usage_raw_bytes: ReplacementCount | None = None
    usage_lifetime_offset: ReplacementCount | None = None
    usage_evidence_digest: ReplacementDigest | None = None
    action: ReplacementAction | None = None
    attempt: int | None = Field(default=None, strict=True, gt=0)
    result: Literal["applied", "not_applied"] | None = None

    _time = field_validator("checked_at")(ReplacementStopEvidence.observed_time)

    @model_validator(mode="after")
    def evidence_scope(self) -> Self:
        stop = (
            self.authorization_removed,
            self.connections_stopped,
            self.old_config_rejected,
            self.usage_observed_at,
            self.usage_total_bytes,
            self.usage_raw_bytes,
            self.usage_lifetime_offset,
            self.usage_evidence_digest,
        )
        receipt = (self.action, self.attempt, self.result)
        if self.purpose == "resolve_write":
            if any(value is not None for value in stop) or any(value is None for value in receipt):
                raise ValueError("invalid_write_receipt")
        elif any(value is None for value in stop) or any(value is not None for value in receipt):
            raise ValueError("invalid_stop_attestation")
        return self

    @field_validator(
        "authorization_removed", "connections_stopped", "old_config_rejected", mode="before"
    )
    @classmethod
    def explicit_or_absent(cls, value: object) -> bool | None:
        return None if value is None else ReplacementStopEvidence.explicit_true(value)


class ExitReplacementVerifyBody(ReplacementCommand):
    replacement_operation_id: ReplacementId
    service_id: ReplacementId
    expected_revision: int = Field(strict=True, gt=0)
    expected_operation_version: int = Field(strict=True, gt=0)
    scope_fingerprint: ReplacementDigest
    checked_at: datetime
    observed_ip: str
    fixed: Literal[True]
    exclusive: Literal[True]
    evidence_digest: ReplacementDigest

    _time = field_validator("checked_at")(ReplacementStopEvidence.observed_time)
    _true = field_validator("fixed", "exclusive", mode="before")(
        ReplacementStopEvidence.explicit_true
    )

    @field_validator("observed_ip")
    @classmethod
    def normalize_ip(cls, value: str) -> str:
        return ReplacementCandidateEvidence.normalize_ip(value)


class ExitReplacementReclaimBody(ReplacementCommand):
    replacement_operation_id: ReplacementId
    service_id: ReplacementId
    reclaim_purpose: Literal["retained_old", "candidate_cleanup"]
    expected_revision: int = Field(strict=True, gt=0)
    expected_operation_version: int = Field(strict=True, gt=0)
    scope_fingerprint: ReplacementDigest
    checked_at: datetime
    connections_stopped: Literal[True]
    old_config_rejected: Literal[True]
    evidence_digest: ReplacementDigest

    _time = field_validator("checked_at")(ReplacementStopEvidence.observed_time)
    _true = field_validator("connections_stopped", "old_config_rejected", mode="before")(
        ReplacementStopEvidence.explicit_true
    )


class ConsoleExitReplacementQuery(HttpBodyModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: ReplacementId | None = None
    candidate_exit_id: ReplacementId | None = None

    @model_validator(mode="after")
    def one_scope(self) -> Self:
        if self.operation_id and self.candidate_exit_id:
            raise ValueError("invalid_replacement_query")
        return self


class ReplacementExitOut(HttpResponseModel):
    id: str
    revision: int
    label: str
    ip_address: str
    resource_pool: str
    squad_uuid: str
    service_id: str | None
    hold_order_id: str | None
    enabled: bool
    verified_at: datetime | None
    scope_fingerprint: str | None


class ReplacementImpactOut(HttpResponseModel):
    service_id: str | None
    customer_id: int | None = None
    service_name: str | None = None
    group_ids: list[str]
    kind: Literal["direct_authorization", "possible_reload"]


class ReplacementTopologyOut(HttpResponseModel):
    resource_fingerprint: str | None
    sources: list[ResourceSourceOut]
    coverage: Literal["complete", "partial"]
    observed_at: datetime
    block_reasons: list[str]
    impacts: list[ReplacementImpactOut] = Field(default_factory=list)


class ConsoleExitReplacementDraftOut(ReplacementTopologyOut):
    old_exit: ReplacementExitOut
    candidate_exit: ReplacementExitOut
    allowed_to_start: bool


class ReplacementEvidenceOut(HttpResponseModel):
    audit_id: str
    observed_at: datetime
    provenance: Literal["administrator", "machine"]
    valid: bool


class ReplacementAccountingOut(HttpResponseModel):
    usage_total_bytes: int | None
    usage_raw_bytes: int | None
    usage_lifetime_offset: int
    observed_at: datetime | None
    error_code: str | None
    cycle_pending: bool


class ConsoleExitReplacementOut(ReplacementTopologyOut):
    operation: ConsoleServiceOperationOut
    progress: ReplacementProgress
    gate_active: bool
    requested_resource_fingerprint: str
    old_exit: ReplacementExitOut
    candidate_exit: ReplacementExitOut
    current_exit_id: str | None
    switch_result: Literal["not_started", "pending", "confirmed", "unknown", "interrupted"]
    restore_requested: bool
    old_resource_state: Literal["current", "held", "released"]
    old_stop: ReplacementEvidenceOut | None
    candidate_verification: ReplacementEvidenceOut | None
    accounting: ReplacementAccountingOut
    allowed_actions: list[
        Literal[
            "stop_evidence",
            "resolve_write",
            "verify",
            "confirm",
            "retry",
            "reclaim",
            "candidate_cleanup",
            "close_evidence",
        ]
    ]


class ConsoleExitReplacementStateOut(HttpResponseModel):
    service_id: str
    service_revision: int
    observed_at: datetime
    draft: ConsoleExitReplacementDraftOut | None = None
    replacement: ConsoleExitReplacementOut | None = None


class ConsoleExitReplacementAcceptedOut(HttpResponseModel):
    accepted: Literal[True] = True
    duplicate: bool
    replacement: ConsoleExitReplacementOut
