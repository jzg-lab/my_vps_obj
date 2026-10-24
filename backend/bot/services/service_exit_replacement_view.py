"""Safe replacement projections for both service and inventory consumers."""

from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.admin_console_exit_replacement_schemas import (
    ConsoleExitReplacementDraftOut,
    ConsoleExitReplacementOut,
    ConsoleExitReplacementQuery,
    ConsoleExitReplacementStateOut,
    ReplacementAccountingOut,
    ReplacementEvidenceOut,
)
from bot.app.web.admin_console_operations_schemas import ConsoleServiceOperationOut
from bot.services.panel_api_service import PanelApiService
from bot.services.service_exit_replacement import current_state
from bot.services.service_exit_replacement_topology import (
    ReplacementTopology,
    exit_output,
    read_replacement_topology,
)
from bot.services.service_operation_errors import safe_service_error
from config.service_periods import as_utc
from db.dal.service_exit_replacement_dal import ReplacementState, matches_stop_usage
from db.dal.user_services_dal import ServiceConflict
from db.service_models import (
    DedicatedExit,
    DedicatedExitAudit,
    ServiceConnection,
    ServiceOperationExecution,
    UserService,
)


async def stable_topology(
    session: AsyncSession,
    panel: PanelApiService | None,
    state: ReplacementState,
    *,
    candidate_required: bool = True,
) -> ReplacementTopology:
    first = await read_replacement_topology(
        session,
        panel,
        state.old_exit,
        state.new_exit,
        service_id=state.service.id,
        candidate_required=candidate_required,
    )
    second = await read_replacement_topology(
        session,
        panel,
        state.old_exit,
        state.new_exit,
        service_id=state.service.id,
        candidate_required=candidate_required,
    )
    if (first.old_scope, first.new_scope) != (second.old_scope, second.new_scope):
        raise ServiceConflict("exit_replacement_scope_changed")
    return second


async def operation_output(
    session: AsyncSession,
    state: ReplacementState,
    topology: ReplacementTopology,
) -> ConsoleExitReplacementOut:
    progress = state.progress
    gate = state.connection.replacement_order_id == state.order.id
    valid = topology.public.resource_fingerprint == state.request.resource_fingerprint

    async def evidence(
        audit_id: str | None, observed_field: Literal["stopped_at", "checked_at"]
    ) -> ReplacementEvidenceOut | None:
        row = await session.get(DedicatedExitAudit, audit_id) if audit_id else None
        if row is None:
            return None
        observed = row.evidence.get(observed_field)
        if not isinstance(observed, str):
            raise ServiceConflict("exit_replacement_evidence_invalid")
        try:
            observed_at = datetime.fromisoformat(observed)
        except ValueError:
            raise ServiceConflict("exit_replacement_evidence_invalid") from None
        if observed_at.tzinfo is None:
            raise ServiceConflict("exit_replacement_evidence_invalid")
        evidence_valid = valid
        if observed_field == "stopped_at" and progress.binding_audit_id is None:
            evidence_valid = valid and matches_stop_usage(
                row,
                total=state.connection.usage_total_bytes,
                raw=state.connection.usage_raw_bytes,
                offset=state.connection.usage_lifetime_offset or 0,
            )
        return ReplacementEvidenceOut(
            audit_id=row.id,
            observed_at=as_utc(observed_at),
            provenance="machine"
            if row.evidence.get("provenance", row.evidence.get("stop_provenance")) == "machine"
            else "administrator",
            valid=evidence_valid,
        )

    blocked = (
        "exit_replacement_write_unknown"
        if progress.pending_action
        else "operation_not_retryable"
        if not gate
        else None
    )
    actions = []
    if progress.pending_action:
        actions.append("resolve_write")
    elif gate:
        actions.append("retry")
        if progress.stage in {"stopping_old", "awaiting_confirmation", "switching"}:
            actions.append("stop_evidence")
        if progress.stage == "awaiting_confirmation":
            actions.append("verify")
            if progress.verification_audit_id:
                actions.append("confirm")
        if progress.stage == "closing":
            actions.append("close_evidence")
        if not progress.binding_audit_id and state.service.desired_status in {
            "paused",
            "cancelled",
        }:
            actions.append("candidate_cleanup")
    if not gate and (
        state.old_exit.hold_order_id == state.order.id
        or state.new_exit.hold_order_id == state.order.id
    ):
        actions.append("reclaim")
    connection = state.connection
    return ConsoleExitReplacementOut.model_validate(
        topology.public.model_dump()
        | {
            "operation": ConsoleServiceOperationOut.from_record(
                state.order, state.execution, blocked=blocked
            ),
            "progress": progress,
            "gate_active": gate,
            "requested_resource_fingerprint": state.request.resource_fingerprint,
            "old_exit": exit_output(state.old_exit, topology.old_scope),
            "candidate_exit": exit_output(state.new_exit, topology.new_scope),
            "current_exit_id": await session.scalar(
                select(DedicatedExit.id).where(DedicatedExit.service_id == state.service.id)
            ),
            "switch_result": "confirmed"
            if progress.binding_audit_id
            else "unknown"
            if progress.pending_action
            else "interrupted"
            if progress.stage in {"closing", "closed"}
            else "pending"
            if gate
            else "not_started",
            "restore_requested": progress.confirmation_audit_id is not None,
            "old_resource_state": "held"
            if state.old_exit.hold_order_id == state.order.id
            else "current"
            if state.old_exit.service_id == state.service.id
            else "released",
            "old_stop": await evidence(progress.stop_audit_id, "stopped_at"),
            "candidate_verification": await evidence(progress.verification_audit_id, "checked_at"),
            "accounting": ReplacementAccountingOut(
                usage_total_bytes=connection.usage_total_bytes,
                usage_raw_bytes=connection.usage_raw_bytes,
                usage_lifetime_offset=connection.usage_lifetime_offset or 0,
                observed_at=as_utc(state.service.last_usage_sync_at)
                if state.service.last_usage_sync_at
                else None,
                error_code=safe_service_error(connection.usage_error),
                cycle_pending=connection.cycle_cutover_bytes is not None,
            ),
            "allowed_actions": actions,
        }
    )


async def replacement_view(
    session: AsyncSession,
    panel: PanelApiService | None,
    service_id: str,
    query: ConsoleExitReplacementQuery,
) -> ConsoleExitReplacementStateOut:
    service = await session.get(UserService, service_id)
    connection = await session.get(ServiceConnection, service_id)
    if service is None:
        raise ServiceConflict("service_not_found", 404)
    result = ConsoleExitReplacementStateOut(
        service_id=service.id, service_revision=service.revision, observed_at=datetime.now(UTC)
    )
    if query.candidate_exit_id:
        old = await session.scalar(
            select(DedicatedExit).where(DedicatedExit.service_id == service.id)
        )
        new = await session.get(DedicatedExit, query.candidate_exit_id)
        if old is None or new is None or old.id == new.id:
            raise ServiceConflict("exit_unavailable")
        topology = await read_replacement_topology(session, panel, old, new, service_id=service.id)
        allowed = bool(
            connection
            and service.user_id is not None
            and service.desired_status != "cancelled"
            and connection.replacement_order_id is None
            and connection.panel_user_uuid
            and connection.state in {"ready", "pending"}
            and connection.revoke_requested_at is None
            and not new.service_id
            and not new.hold_order_id
            and new.enabled
            and new.resource_pool == service.terms.get("resource_pool")
            and topology.public.coverage == "complete"
        )
        result.draft = ConsoleExitReplacementDraftOut(
            **topology.public.model_dump(),
            old_exit=exit_output(old, topology.old_scope),
            candidate_exit=exit_output(new, topology.new_scope),
            allowed_to_start=allowed,
        )
        return result
    operation_id = query.operation_id
    if not operation_id:
        statement = select(ServiceOperationExecution.id).where(
            ServiceOperationExecution.service_id == service_id,
            ServiceOperationExecution.phase == "exit_replace",
        )
        if connection and connection.replacement_order_id:
            statement = statement.where(
                ServiceOperationExecution.order_id == connection.replacement_order_id
            )
        operation_id = await session.scalar(
            statement.order_by(ServiceOperationExecution.created_at.desc()).limit(1)
        )
    if operation_id:
        state = await current_state(session, service_id, operation_id, allow_terminal=True)
        topology = await read_replacement_topology(
            session,
            panel,
            state.old_exit,
            state.new_exit,
            service_id=service_id,
            candidate_required=state.progress.stage not in {"closing", "closed", "completed"},
        )
        result.replacement = await operation_output(session, state, topology)
    return result
