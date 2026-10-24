"""Strict, service-scoped replacement intent and evidence; no remote execution."""

from datetime import UTC, datetime
from ipaddress import IPv6Address, ip_address
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ReplacementId = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
ReplacementDigest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
ReplacementCount = Annotated[int, Field(strict=True, ge=0, le=2**53 - 1)]
ReplacementAction = Literal["stop_old", "set_target_group", "restore", "close_access"]
ReplacementRestoreBlock = Literal[
    "account_banned",
    "service_expired",
    "service_exhausted",
    "service_paused",
    "service_cancelled",
    "service_not_started",
    "service_not_deliverable",
    "exit_unavailable",
]


class ReplacementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    expected_revision: int = Field(gt=0)
    old_exit_id: ReplacementId
    new_exit_id: ReplacementId
    expected_old_exit_revision: int = Field(gt=0)
    expected_new_exit_revision: int = Field(gt=0)
    resource_fingerprint: ReplacementDigest
    reason: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def different_resources(self) -> Self:
        if self.old_exit_id == self.new_exit_id:
            raise ValueError("replacement_requires_different_exit")
        return self


class ReplacementProgress(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    version: int = Field(default=1, gt=0)
    stage: Literal[
        "stopping_old",
        "awaiting_confirmation",
        "switching",
        "restoring",
        "closing",
        "completed",
        "closed",
    ] = "stopping_old"
    pending_action: ReplacementAction | None = None
    stop_audit_id: ReplacementId | None = None
    verification_audit_id: ReplacementId | None = None
    confirmation_audit_id: ReplacementId | None = None
    binding_audit_id: ReplacementId | None = None
    restore_result: Literal[
        "not_requested", "pending", "enabled", "restricted", "unknown", "interrupted"
    ] = "not_requested"
    restore_block_reasons: list[ReplacementRestoreBlock] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_stage(self) -> Self:
        if self.stage == "stopping_old" and any(
            (self.stop_audit_id, self.verification_audit_id, self.confirmation_audit_id)
        ):
            raise ValueError("replacement_evidence_stage_mismatch")
        if self.stage == "awaiting_confirmation" and self.confirmation_audit_id is not None:
            raise ValueError("replacement_evidence_stage_mismatch")
        if (
            self.stage in {"awaiting_confirmation", "switching", "restoring", "completed"}
            and self.stop_audit_id is None
        ):
            raise ValueError("replacement_stop_evidence_required")
        if self.stage in {"switching", "restoring", "completed"} and (
            self.verification_audit_id is None or self.confirmation_audit_id is None
        ):
            raise ValueError("replacement_confirmation_required")
        if (self.stage in {"restoring", "completed"} and self.binding_audit_id is None) or (
            self.binding_audit_id is not None
            and self.stage not in {"restoring", "completed", "closing", "closed"}
        ):
            raise ValueError("replacement_binding_evidence_invalid")
        if self.pending_action is not None and (
            (
                self.pending_action == "stop_old"
                and self.stage not in {"stopping_old", "awaiting_confirmation"}
            )
            or (self.pending_action == "set_target_group" and self.stage != "switching")
            or (self.pending_action == "restore" and self.stage != "restoring")
            or (self.pending_action == "close_access" and self.stage != "closing")
        ):
            raise ValueError("replacement_action_stage_mismatch")
        if self.stage in {"completed", "closed"} and self.pending_action is not None:
            raise ValueError("replacement_write_unknown")
        return self


class ReplacementStopEvidence(BaseModel):
    """An explicit attestation, never inferred from disabled status or stable counters.

    A future HTTP adapter may accept administrator evidence only. Machine provenance
    must be constructed by a verified server-side observer, not copied from a body.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    resource_fingerprint: ReplacementDigest
    stopped_at: datetime
    usage_observed_at: datetime
    stop_provenance: Literal["administrator", "machine"]
    usage_provenance: Literal["administrator", "machine"]
    stop_report_digest: ReplacementDigest
    usage_report_digest: ReplacementDigest
    authorization_removed: Literal[True]
    connections_stopped: Literal[True]
    old_config_rejected: Literal[True]
    usage_total_bytes: ReplacementCount
    usage_raw_bytes: ReplacementCount
    usage_lifetime_offset: ReplacementCount

    @field_validator(
        "authorization_removed", "connections_stopped", "old_config_rejected", mode="before"
    )
    @staticmethod
    def explicit_true(value: object) -> bool:
        if value is not True:
            raise ValueError("replacement_explicit_evidence_required")
        return True

    @field_validator("stopped_at", "usage_observed_at")
    @staticmethod
    def observed_time(value: datetime) -> datetime:
        if value.tzinfo is None or value > datetime.now(UTC):
            raise ValueError("replacement_evidence_time_invalid")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def usage_follows_stop(self) -> Self:
        if self.usage_observed_at < self.stopped_at:
            raise ValueError("replacement_usage_precedes_stop")
        return self


class ReplacementCandidateEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    resource_fingerprint: ReplacementDigest
    checked_at: datetime
    observed_ip: str = Field(min_length=1, max_length=45)
    provenance: Literal["administrator", "machine"]
    report_digest: ReplacementDigest
    fixed: Literal[True]
    exclusive: Literal[True]

    _observed_time = field_validator("checked_at")(ReplacementStopEvidence.observed_time)
    _explicit_true = field_validator("fixed", "exclusive", mode="before")(
        ReplacementStopEvidence.explicit_true
    )

    @field_validator("observed_ip")
    @classmethod
    def normalize_ip(cls, value: str) -> str:
        address = ip_address(value)
        return (
            str(address.ipv4_mapped or address)
            if isinstance(address, IPv6Address)
            else str(address)
        )


class ReplacementWriteResolution(BaseModel):
    """Evidence resolving one dispatched action, not an invented upstream fence."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    action: ReplacementAction
    attempt: int = Field(gt=0)
    provenance: Literal["panel_response", "operator_reconciliation"]
    report_digest: ReplacementDigest
    completed_at: datetime
    result: Literal["applied", "not_applied"]

    _observed_time = field_validator("completed_at")(ReplacementStopEvidence.observed_time)


class ReplacementBindingObservation(BaseModel):
    """Normalized identity read-back supplied by the future runner, never an HTTP body."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    resource_fingerprint: ReplacementDigest
    panel_user_uuid: str = Field(min_length=1, max_length=36)
    username: str = Field(min_length=1, max_length=64)
    description: str
    group_ids: list[str]
    status: Literal["DISABLED", "EXPIRED", "LIMITED"]
    observed_at: datetime
    report_digest: ReplacementDigest
    usage_total_bytes: ReplacementCount
    usage_raw_bytes: ReplacementCount
    usage_lifetime_offset: ReplacementCount

    _observed_time = field_validator("observed_at")(ReplacementStopEvidence.observed_time)
