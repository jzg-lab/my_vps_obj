"""UC-04/05：只读预检、脱敏诊断和既有意图执行结果。"""

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field, ValidationError

from bot.app.web.admin_console_nodes_schemas import (
    ConsoleHostOut,
    ConsoleNodeOut,
    ConsoleNodeSourceOut,
)
from bot.app.web.http_contracts import HttpBodyModel, HttpResponseModel
from bot.services.service_operation_errors import safe_service_error
from config.service_exit_replacement import ReplacementProgress
from config.service_periods import as_utc
from config.service_plans import ServicePlanTerms
from db.service_models import ServiceOperationExecution, ServiceOrder


class ConsoleServicePreflightBody(HttpBodyModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: int = Field(ge=-(2**53 - 1), le=2**53 - 1, strict=True)
    plan_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    expected_revision: int = Field(ge=1, strict=True)
    exit_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")


class ConsolePreflightCheckOut(HttpResponseModel):
    code: str
    status: Literal["passed", "blocked", "unknown"]
    reason: str | None = None


class ConsoleServicePreflightOut(HttpResponseModel):
    user_id: int
    plan_id: str
    plan_revision: int | None
    exit_id: str | None
    exit_revision: int | None
    terms: ServicePlanTerms | None
    allow_pending_creation: bool = Field(description="本地开通条件；提交时仍须事务内重核。")
    resource_readiness: Literal["ready", "blocked", "unknown"]
    ready_for_delivery: Literal[False] = Field(
        default=False, description="预检没有已准备身份与计量证据，不能作为交付完成证明。"
    )
    checks: list[ConsolePreflightCheckOut]
    configured_group_ids: list[str]
    nodes: list[ConsoleNodeOut]
    hosts: list[ConsoleHostOut]
    sources: list[ConsoleNodeSourceOut]
    local_observed_at: datetime


class ConsoleServiceRemoteObservationOut(HttpResponseModel):
    availability: Literal[
        "available",
        "unavailable",
        "unconfigured",
        "not_prepared",
        "unconfirmed",
        "not_found",
        "conflict",
    ]
    attempted_at: datetime | None = None
    observed_at: datetime | None = None
    identity_matches: bool | None = None
    terms_match: bool | None = None
    status: Literal["ACTIVE", "DISABLED", "EXPIRED", "LIMITED"] | None = None
    usage_readable: bool | None = None
    raw_used_bytes: int | None = None
    error: str | None = None


class ConsoleServiceDiagnosticsOut(HttpResponseModel):
    service_id: str
    user_id: int | None
    service_revision: int
    status: str
    desired_status: str
    target_access: Literal["enabled", "disabled", "unknown"]
    connection_state: str | None
    sync_pending: bool | None
    errors: dict[str, str | None]
    last_usage_sync_at: datetime | None
    sync_confirmed_at: datetime | None
    local_observed_at: datetime
    remote: ConsoleServiceRemoteObservationOut
    next_steps: list[str]
    data_plane_verified: Literal[False] = Field(
        default=False, description="面板读取不能验证客户端连接或旧连接已停止。"
    )


class ConsoleServiceRetryBody(HttpBodyModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: int = Field(ge=-(2**53 - 1), le=2**53 - 1, strict=True)
    expected_revision: int = Field(ge=1, strict=True)
    idempotency_key: str = Field(min_length=1, max_length=128)


class ConsoleServiceOperationOut(HttpResponseModel):
    id: str
    service_id: str
    order_id: str | None
    kind: str
    phase: (
        Literal["prepare", "delivery", "entitlement", "revocation", "usage", "exit_replace"] | None
    )
    replacement_progress: ReplacementProgress | None = None
    target_revision: int | None
    source: Literal["administrator", "worker", "unknown"]
    actor_id: int | None
    status: Literal["pending", "unknown", "failed", "succeeded", "superseded"]
    attempt_count: int | None
    created_at: datetime
    attempted_at: datetime | None
    first_failed_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    retryable: bool
    retry_block_reason: str | None

    @classmethod
    def from_record(
        cls,
        order: ServiceOrder | None,
        execution: ServiceOperationExecution | None,
        *,
        blocked: str | None,
    ) -> "ConsoleServiceOperationOut":
        if execution is None:
            assert order is not None
            return cls(
                id=order.id,
                service_id=order.service_id,
                order_id=order.id,
                kind=order.kind,
                phase=None,
                target_revision=None,
                source="unknown",
                actor_id=order.actor_id,
                status="unknown",
                attempt_count=None,
                created_at=as_utc(order.created_at),
                attempted_at=None,
                first_failed_at=None,
                completed_at=None,
                error_code=None,
                retryable=False,
                retry_block_reason="historical_result_unknown",
            )
        progress = None
        error = safe_service_error(execution.error_code)
        if execution.phase == "exit_replace":
            try:
                progress = ReplacementProgress.model_validate(execution.replacement_progress)
            except ValidationError:
                error = "exit_replacement_state_invalid"
        return cls.model_validate(
            {
                "id": execution.id,
                "service_id": execution.service_id,
                "order_id": execution.order_id,
                "kind": order.kind if order else execution.phase,
                "phase": execution.phase,
                "target_revision": execution.target_revision,
                "source": execution.source,
                "actor_id": execution.actor_id,
                "status": execution.status,
                "attempt_count": execution.attempt_count,
                "created_at": as_utc(execution.created_at),
                "attempted_at": as_utc(execution.attempted_at) if execution.attempted_at else None,
                "first_failed_at": as_utc(execution.first_failed_at)
                if execution.first_failed_at
                else None,
                "completed_at": as_utc(execution.completed_at) if execution.completed_at else None,
                "error_code": error,
                "replacement_progress": progress,
                "retryable": blocked is None,
                "retry_block_reason": blocked,
            }
        )


class ConsoleServiceOperationsOut(HttpResponseModel):
    service_id: str
    service_revision: int
    operations: list[ConsoleServiceOperationOut]
    total: int
    limit: int
    offset: int


class ConsoleServiceRetryOut(HttpResponseModel):
    operation: ConsoleServiceOperationOut
    retry_order_id: str
    duplicate: bool
    accepted: Literal[True] = Field(
        default=True, description="已保存重试意图，不代表远端已经生效。"
    )
