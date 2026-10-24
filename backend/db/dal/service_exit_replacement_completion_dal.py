"""Terminal transitions, retained holds and retries of the same replacement execution."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.service_exit_replacement import ReplacementStopEvidence
from config.service_periods import as_utc
from db.dal.service_exit_replacement_dal import (
    ReplacementState,
    _audit,
    _check_accounting,
    _live,
    _previous_audit,
    _save_progress,
    _version,
)
from db.dal.user_services_dal import ServiceConflict
from db.service_models import DedicatedExit, DedicatedExitAudit, ServiceOrder


def finish_replacement(state: ReplacementState, *, enabled: bool, reasons: list[str]) -> None:
    _live(state)
    if state.progress.stage != "restoring" or state.progress.pending_action is not None:
        raise ServiceConflict("exit_replacement_stage_changed")
    if not state.progress.binding_audit_id or state.new_exit.service_id != state.service.id:
        raise ServiceConflict("exit_replacement_state_invalid")
    _save_progress(
        state,
        stage="completed",
        restore_result="enabled" if enabled else "restricted",
        restore_block_reasons=reasons,
    )
    state.execution.status = "succeeded"
    state.execution.error_code = None
    state.execution.completed_at = datetime.now(UTC)
    state.connection.replacement_order_id = None
    state.connection.sync_pending = False
    state.connection.sync_error = None
    state.connection.sync_confirmed_at = datetime.now(UTC)


def request_replacement_close(state: ReplacementState) -> None:
    _live(state)
    if state.progress.pending_action is not None:
        raise ServiceConflict("exit_replacement_write_unknown")
    if state.progress.stage in {"completed", "closed"}:
        raise ServiceConflict("exit_replacement_stage_changed")
    if state.service.desired_status not in {"paused", "cancelled"}:
        raise ServiceConflict("exit_replacement_pause_required")
    if state.progress.stage != "closing":
        _save_progress(
            state,
            stage="closing",
            restore_result="interrupted",
            restore_block_reasons=[
                "service_cancelled"
                if state.service.desired_status == "cancelled"
                else "service_paused"
            ],
        )
        state.execution.status = "pending"
        state.execution.error_code = None


async def accept_replacement_close(
    session: AsyncSession,
    state: ReplacementState,
    *,
    actor_id: int,
    expected_version: int,
    idempotency_key: str,
    evidence: ReplacementStopEvidence,
) -> tuple[DedicatedExitAudit, bool]:
    values = evidence.model_dump(mode="json") | {"operation_id": state.execution.id}
    previous = await _previous_audit(
        session,
        state,
        exit_id=state.new_exit.id,
        action="replace_close_stop",
        key=idempotency_key,
        evidence=values,
    )
    if previous:
        return previous, True
    _version(state, expected_version)
    if (
        state.progress.stage != "closing"
        or state.progress.pending_action is not None
        or state.service.desired_status not in {"paused", "cancelled"}
    ):
        raise ServiceConflict("exit_replacement_stage_changed")
    if evidence.stopped_at < as_utc(state.execution.attempted_at or state.order.created_at):
        raise ServiceConflict("exit_replacement_evidence_invalid")
    _check_accounting(
        state,
        total=evidence.usage_total_bytes,
        raw=evidence.usage_raw_bytes,
        offset=evidence.usage_lifetime_offset,
        observed_at=evidence.usage_observed_at,
    )
    row = _audit(
        session,
        state,
        exit_id=state.new_exit.id,
        actor_id=actor_id,
        action="replace_close_stop",
        key=idempotency_key,
        evidence=values,
    )
    _save_progress(state, stage="closed", restore_result="interrupted")
    state.execution.status = "superseded"
    state.execution.completed_at = datetime.now(UTC)
    state.execution.error_code = "exit_replacement_interrupted"
    state.connection.replacement_order_id = None
    state.connection.sync_pending = True
    state.connection.sync_error = "exit_replacement_interrupted"
    await session.flush()
    return row, False


async def reclaim_replacement_hold(
    session: AsyncSession,
    state: ReplacementState,
    *,
    resource: DedicatedExit,
    actor_id: int,
    expected_version: int,
    expected_revision: int,
    idempotency_key: str,
    checked_at: datetime,
    scope_fingerprint: str,
    report_digest: str,
) -> tuple[DedicatedExitAudit, bool]:
    values: dict[str, object] = {
        "operation_id": state.execution.id,
        "scope_fingerprint": scope_fingerprint,
        "checked_at": checked_at.isoformat(),
        "report_digest": report_digest,
        "provenance": "administrator",
        "connections_stopped": True,
        "old_config_rejected": True,
    }
    previous = await _previous_audit(
        session,
        state,
        exit_id=resource.id,
        action="replace_reclaim",
        key=idempotency_key,
        evidence=values,
    )
    if previous:
        return previous, True
    _version(state, expected_version)
    if (
        state.progress.pending_action is not None
        or state.connection.replacement_order_id is not None
    ):
        raise ServiceConflict("exit_replacement_write_unknown")
    if state.progress.stage not in {"completed", "closed"}:
        raise ServiceConflict("exit_replacement_stage_changed")
    if resource.hold_order_id != state.order.id or resource.service_id is not None:
        raise ServiceConflict("exit_replacement_hold_changed")
    if resource.revision != expected_revision:
        raise ServiceConflict("exit_revision_changed")
    if checked_at < as_utc(state.execution.completed_at or state.order.created_at):
        raise ServiceConflict("exit_replacement_evidence_invalid")
    resource.hold_order_id = None
    resource.verified_at = None
    resource.revision += 1
    row = _audit(
        session,
        state,
        exit_id=resource.id,
        actor_id=actor_id,
        action="replace_reclaim",
        key=idempotency_key,
        evidence=values,
    )
    _save_progress(state)
    await session.flush()
    return row, False


async def retry_replacement(
    session: AsyncSession,
    state: ReplacementState,
    *,
    actor_id: int,
    expected_revision: int,
    idempotency_key: str,
) -> tuple[ServiceOrder, bool]:
    _live(state)
    command: dict[str, object] = {
        "service_id": state.service.id,
        "operation_id": state.execution.id,
        "expected_revision": expected_revision,
    }
    previous = await session.scalar(
        select(ServiceOrder).where(
            ServiceOrder.request_owner_id == state.service.user_id,
            ServiceOrder.idempotency_key == idempotency_key,
        )
    )
    if previous:
        if previous.kind != "retry" or previous.request != command:
            raise ServiceConflict("idempotency_conflict")
        return previous, True
    if state.progress.pending_action is not None:
        raise ServiceConflict("exit_replacement_write_unknown")
    if state.progress.stage in {"completed", "closed"}:
        raise ServiceConflict("operation_not_retryable")
    if state.service.revision != expected_revision:
        raise ServiceConflict("service_revision_changed")
    assert state.service.user_id is not None
    row = ServiceOrder(
        id=uuid4().hex,
        user_id=state.service.user_id,
        request_owner_id=state.service.user_id,
        service_id=state.service.id,
        actor_id=actor_id,
        kind="retry",
        idempotency_key=idempotency_key,
        request=command,
        snapshot={
            "operation_id": state.execution.id,
            "phase": "exit_replace",
            "revision": state.service.revision,
        },
        created_at=datetime.now(UTC),
    )
    session.add(row)
    state.execution.status = "pending"
    state.execution.error_code = None
    _save_progress(state)
    await session.flush()
    return row, False


def discard_undispatched_write(
    state: ReplacementState, *, previous_attempted_at: datetime | None, reason: str
) -> None:
    """Only the dispatching process knows that its prepared request was never sent."""
    _live(state)
    if state.progress.pending_action is None or state.execution.status != "unknown":
        raise ServiceConflict("exit_replacement_write_unknown")
    _audit(
        state.session,
        state,
        exit_id=state.new_exit.id,
        actor_id=state.order.actor_id,
        action="replace_dispatch_skip",
        key=str(state.progress.version),
        evidence={
            "operation_id": state.execution.id,
            "action": state.progress.pending_action,
            "dispatched": False,
            "reason": reason,
        },
    )
    _save_progress(
        state,
        pending_action=None,
        restore_result="pending"
        if state.progress.pending_action == "restore"
        else state.progress.restore_result,
    )
    state.execution.attempt_count -= 1
    state.execution.attempted_at = previous_attempted_at
    state.execution.status = "failed"
    state.execution.error_code = reason
    state.execution.first_failed_at = state.execution.first_failed_at or datetime.now(UTC)
