"""Account-locked replacement reservations and evidence; callers own the transaction.

No function here contacts a panel or enables access. The lifecycle gate remains set
after binding; restoration and manual reclaim belong to the next reviewed slice.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import SessionTransaction

from config.service_exit_replacement import (
    ReplacementAction,
    ReplacementBindingObservation,
    ReplacementCandidateEvidence,
    ReplacementProgress,
    ReplacementRequest,
    ReplacementStopEvidence,
    ReplacementWriteResolution,
)
from config.service_periods import as_utc
from db.dal.resource_operations_dal import coordinate_resources, require_resource_authorization
from db.dal.user_dal import lock_user_by_id
from db.dal.user_services_dal import ServiceConflict
from db.service_models import (
    DedicatedExit,
    DedicatedExitAudit,
    ServiceConnection,
    ServiceOperationExecution,
    ServiceOrder,
    UserService,
)


@dataclass(frozen=True)
class ReplacementState:
    session: AsyncSession
    transaction: SessionTransaction | None
    service: UserService
    connection: ServiceConnection
    order: ServiceOrder
    execution: ServiceOperationExecution
    request: ReplacementRequest
    old_exit: DedicatedExit
    new_exit: DedicatedExit

    @property
    def progress(self) -> ReplacementProgress:
        try:
            return ReplacementProgress.model_validate(self.execution.replacement_progress)
        except ValidationError:
            raise ServiceConflict("exit_replacement_state_invalid") from None


def _resource_values(resource: DedicatedExit) -> dict[str, object]:
    return {
        "id": resource.id,
        "ip_address": resource.ip_address,
        "resource_pool": resource.resource_pool,
        "squad_uuid": resource.squad_uuid,
    }


async def _lock_resources(
    session: AsyncSession, request: ReplacementRequest
) -> tuple[DedicatedExit, DedicatedExit]:
    rows = list(
        await session.scalars(
            select(DedicatedExit)
            .where(DedicatedExit.id.in_((request.old_exit_id, request.new_exit_id)))
            .order_by(DedicatedExit.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    resources = {row.id: row for row in rows}
    if len(resources) != 2:
        raise ServiceConflict("exit_not_found", 404)
    return resources[request.old_exit_id], resources[request.new_exit_id]


async def lock_replacement(
    session: AsyncSession,
    *,
    service_id: str,
    user_id: int,
    operation_id: str,
    allow_terminal: bool = False,
) -> ReplacementState:
    await coordinate_resources(session)
    if await lock_user_by_id(session, user_id) is None:
        raise ServiceConflict("user_not_found", 404)
    service = await session.get(UserService, service_id, populate_existing=True)
    connection = await session.get(ServiceConnection, service_id, populate_existing=True)
    if service is None or service.user_id != user_id or connection is None:
        raise ServiceConflict("service_not_found", 404)
    execution = await session.scalar(
        select(ServiceOperationExecution)
        .where(ServiceOperationExecution.id == operation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if execution is None or execution.service_id != service_id or execution.phase != "exit_replace":
        raise ServiceConflict("operation_not_found", 404)
    order = await session.get(ServiceOrder, execution.order_id) if execution.order_id else None
    if order is None or order.kind != "replace_exit" or order.service_id != service_id:
        raise ServiceConflict("exit_replacement_state_invalid")
    try:
        request = ReplacementRequest.model_validate(order.request.get("replacement"))
        progress = ReplacementProgress.model_validate(execution.replacement_progress)
    except ValidationError:
        raise ServiceConflict("exit_replacement_state_invalid") from None
    terminal = progress.stage in {"completed", "closed"}
    if terminal:
        if not allow_terminal or execution.status not in {"succeeded", "superseded"}:
            raise ServiceConflict("exit_replacement_stage_changed")
        if connection.replacement_order_id == order.id:
            raise ServiceConflict("exit_replacement_state_invalid")
    elif (
        order.request_owner_id != user_id
        or execution.request_owner_id != user_id
        or connection.replacement_order_id != order.id
    ):
        raise ServiceConflict("exit_replacement_state_invalid")
    old, new = await _lock_resources(session, request)
    if not terminal and (
        order.snapshot.get("old_exit") != _resource_values(old)
        or order.snapshot.get("new_exit") != _resource_values(new)
        or order.snapshot.get("panel_user_uuid") != connection.panel_user_uuid
        or order.snapshot.get("username") != connection.username
    ):
        raise ServiceConflict("exit_replacement_scope_changed")
    state = ReplacementState(
        session,
        session.sync_session.get_transaction(),
        service,
        connection,
        order,
        execution,
        request,
        old,
        new,
    )
    if terminal:
        await _evidence_chain(state)
        return state
    if state.progress.binding_audit_id is not None:
        valid_binding = (
            old.service_id is None
            and old.hold_order_id == order.id
            and new.service_id == service.id
            and new.hold_order_id is None
        )
    else:
        valid_binding = (
            old.service_id == service.id
            and old.hold_order_id is None
            and new.service_id is None
            and new.hold_order_id == order.id
        )
    if (
        not valid_binding
        or execution.status not in {"pending", "unknown", "failed"}
        or (state.progress.pending_action is not None) != (execution.status == "unknown")
    ):
        raise ServiceConflict("exit_replacement_state_invalid")
    await _evidence_chain(state)
    return state


def _live(state: ReplacementState) -> None:
    if (
        state.transaction is None
        or not state.transaction.is_active
        or state.session.sync_session.get_transaction() is not state.transaction
    ):
        raise ServiceConflict("exit_replacement_lock_required")
    if state.connection.replacement_order_id != state.order.id and state.progress.stage not in {
        "completed",
        "closed",
    }:
        raise ServiceConflict("exit_replacement_state_invalid")


async def _evidence_chain(state: ReplacementState) -> dict[str, DedicatedExitAudit]:
    audits: dict[str, DedicatedExitAudit] = {}
    for action, audit_id, exit_id in (
        ("replace_stop", state.progress.stop_audit_id, state.old_exit.id),
        ("replace_verify", state.progress.verification_audit_id, state.new_exit.id),
        ("replace_confirm", state.progress.confirmation_audit_id, state.new_exit.id),
        ("replace_bind", state.progress.binding_audit_id, state.new_exit.id),
    ):
        if audit_id is None:
            continue
        audit = await state.session.get(DedicatedExitAudit, audit_id)
        if (
            audit is None
            or audit.action != action
            or audit.exit_id != exit_id
            or audit.service_id != state.service.id
            or audit.evidence.get("operation_id") != state.execution.id
            or audit.evidence.get("resource_fingerprint") != state.request.resource_fingerprint
            or as_utc(audit.created_at) < as_utc(state.order.created_at)
        ):
            raise ServiceConflict("exit_replacement_evidence_invalid")
        evidence = {key: value for key, value in audit.evidence.items() if key != "operation_id"}
        try:
            if action == "replace_stop":
                ReplacementStopEvidence.model_validate_json(json.dumps(evidence))
            elif action == "replace_verify":
                verified = ReplacementCandidateEvidence.model_validate_json(json.dumps(evidence))
                if state.progress.stage not in {"completed", "closed"} and (
                    state.new_exit.verified_at is None
                    or as_utc(state.new_exit.verified_at) != verified.checked_at
                ):
                    raise ServiceConflict("exit_replacement_scope_changed")
            elif action == "replace_confirm" and (
                evidence.get("request_restore") is not True
                or evidence.get("stop_audit_id") != state.progress.stop_audit_id
                or evidence.get("verification_audit_id") != state.progress.verification_audit_id
            ):
                raise ServiceConflict("exit_replacement_evidence_invalid")
            elif action == "replace_bind":
                ReplacementBindingObservation.model_validate_json(json.dumps(evidence))
        except (ValidationError, TypeError):
            raise ServiceConflict("exit_replacement_evidence_invalid") from None
        audits[action] = audit
    return audits


def _before_binding(state: ReplacementState) -> None:
    if (
        state.service.user_id is None
        or state.service.desired_status == "cancelled"
        or state.connection.state == "revoked"
        or state.connection.revoke_requested_at is not None
        or state.old_exit.service_id != state.service.id
        or state.old_exit.hold_order_id is not None
        or state.new_exit.service_id is not None
        or state.new_exit.hold_order_id != state.order.id
        or not state.new_exit.enabled
    ):
        raise ServiceConflict("exit_replacement_not_switchable")


def _version(state: ReplacementState, expected_version: int) -> None:
    _live(state)
    if state.progress.version != expected_version:
        raise ServiceConflict("exit_replacement_version_changed")


def _save_progress(state: ReplacementState, **changes: object) -> None:
    values = state.progress.model_dump() | {"version": state.progress.version + 1} | changes
    progress = ReplacementProgress.model_validate(values)
    state.execution.replacement_progress = progress.model_dump(mode="json")


def _audit_key(operation_id: str, action: str, key: str) -> str:
    return hashlib.sha256(f"{operation_id}:{action}:{key}".encode()).hexdigest()


async def _previous_audit(
    session: AsyncSession,
    state: ReplacementState,
    *,
    exit_id: str,
    action: str,
    key: str,
    evidence: dict[str, object],
) -> DedicatedExitAudit | None:
    _live(state)
    if session is not state.session:
        raise ServiceConflict("exit_replacement_lock_required")
    previous = await session.scalar(
        select(DedicatedExitAudit).where(
            DedicatedExitAudit.exit_id == exit_id,
            DedicatedExitAudit.idempotency_key == _audit_key(state.execution.id, action, key),
        )
    )
    if previous and (previous.action != action or previous.evidence != evidence):
        raise ServiceConflict("idempotency_conflict")
    return previous


def _audit(
    session: AsyncSession,
    state: ReplacementState,
    *,
    exit_id: str,
    actor_id: int,
    action: str,
    key: str,
    evidence: dict[str, object],
) -> DedicatedExitAudit:
    row = DedicatedExitAudit(
        id=uuid4().hex,
        exit_id=exit_id,
        service_id=state.service.id,
        actor_id=actor_id,
        action=action,
        idempotency_key=_audit_key(state.execution.id, action, key),
        evidence=evidence,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    return row


async def reserve_exit_replacement(
    session: AsyncSession,
    *,
    service_id: str,
    user_id: int,
    actor_id: int,
    idempotency_key: str,
    request: ReplacementRequest,
) -> tuple[ServiceOperationExecution, bool]:
    """The future caller must supply a fresh resource fingerprint; this locks local facts."""
    if not 1 <= len(idempotency_key) <= 128:
        raise ServiceConflict("invalid_idempotency_key", 400)
    await coordinate_resources(session)
    if await lock_user_by_id(session, user_id) is None:
        raise ServiceConflict("user_not_found", 404)
    service = await session.get(UserService, service_id, populate_existing=True)
    connection = await session.get(ServiceConnection, service_id, populate_existing=True)
    if service is None or service.user_id != user_id or connection is None:
        raise ServiceConflict("service_not_found", 404)
    command: dict[str, object] = {
        "service_id": service_id,
        "replacement": request.model_dump(mode="json"),
    }
    previous = await session.scalar(
        select(ServiceOrder).where(
            ServiceOrder.request_owner_id == user_id,
            ServiceOrder.idempotency_key == idempotency_key,
        )
    )
    if previous is not None:
        if previous.kind != "replace_exit" or previous.request != command:
            raise ServiceConflict("idempotency_conflict")
        execution = await session.scalar(
            select(ServiceOperationExecution).where(
                ServiceOperationExecution.order_id == previous.id
            )
        )
        if execution is None:
            raise ServiceConflict("exit_replacement_state_invalid")
        return execution, True
    await require_resource_authorization(session)
    if connection.replacement_order_id is not None:
        raise ServiceConflict("exit_replacement_in_progress")
    if await session.scalar(
        select(ServiceOperationExecution.id)
        .where(
            ServiceOperationExecution.service_id == service_id,
            ServiceOperationExecution.phase.in_(("prepare", "delivery", "entitlement")),
            ServiceOperationExecution.status == "unknown",
        )
        .limit(1)
    ):
        raise ServiceConflict("exit_replacement_prior_write_unknown")
    if service.revision != request.expected_revision:
        raise ServiceConflict("service_revision_changed")
    if (
        service.terms.get("resource_type") != "dedicated"
        or service.desired_status == "cancelled"
        or connection.state not in {"pending", "ready"}
        or connection.panel_user_uuid is None
        or connection.revoke_requested_at is not None
    ):
        raise ServiceConflict("exit_replacement_not_available")
    old, new = await _lock_resources(session, request)
    if (old.revision, new.revision) != (
        request.expected_old_exit_revision,
        request.expected_new_exit_revision,
    ):
        raise ServiceConflict("exit_revision_changed")
    if (
        old.service_id != service.id
        or old.hold_order_id is not None
        or new.service_id is not None
        or new.hold_order_id is not None
        or not new.enabled
        or new.resource_pool != service.terms.get("resource_pool")
        or old.resource_pool != service.terms.get("resource_pool")
    ):
        raise ServiceConflict("exit_unavailable")
    order = ServiceOrder(
        id=uuid4().hex,
        user_id=user_id,
        request_owner_id=user_id,
        service_id=service.id,
        actor_id=actor_id,
        kind="replace_exit",
        idempotency_key=idempotency_key,
        request=command,
        snapshot={
            "old_exit": _resource_values(old),
            "new_exit": _resource_values(new),
            "terms": dict(service.terms),
            "starts_at": as_utc(service.starts_at).isoformat(),
            "expires_at": as_utc(service.expires_at).isoformat(),
            "used_bytes": service.used_bytes,
            "usage_total_bytes": connection.usage_total_bytes,
            "panel_user_uuid": connection.panel_user_uuid,
            "username": connection.username,
        },
        created_at=datetime.now(UTC),
    )
    session.add(order)
    await session.flush()
    new.hold_order_id = order.id
    new.revision += 1
    connection.replacement_order_id = order.id
    connection.sync_pending = True
    connection.sync_error = "exit_replacement_in_progress"
    service.revision += 1
    # Create with progress before flushing; the database rejects a bare replacement phase.
    execution = ServiceOperationExecution(
        id=uuid4().hex,
        service_id=service.id,
        order_id=order.id,
        request_owner_id=user_id,
        phase="exit_replace",
        target_revision=service.revision,
        source="administrator",
        actor_id=actor_id,
        status="pending",
        attempt_count=0,
        created_at=datetime.now(UTC),
        replacement_progress=ReplacementProgress().model_dump(mode="json"),
    )
    session.add(execution)
    await session.flush()
    state = ReplacementState(
        session,
        session.sync_session.get_transaction(),
        service,
        connection,
        order,
        execution,
        request,
        old,
        new,
    )
    _audit(
        session,
        state,
        exit_id=new.id,
        actor_id=actor_id,
        action="replace_reserve",
        key=idempotency_key,
        evidence={
            "operation_id": execution.id,
            "resource_fingerprint": request.resource_fingerprint,
            "old_exit_id": old.id,
            "new_exit_id": new.id,
        },
    )
    await session.flush()
    return execution, False


async def begin_replacement_action(
    session: AsyncSession,
    state: ReplacementState,
    *,
    action: ReplacementAction,
    expected_version: int,
) -> None:
    """Commit this marker before dispatch; no caller in this checkpoint dispatches it."""
    _version(state, expected_version)
    if action == "set_target_group":
        _before_binding(state)
    if state.progress.stage in {"completed", "closed"}:
        raise ServiceConflict("exit_replacement_stage_changed")
    if state.progress.pending_action is not None:
        raise ServiceConflict("exit_replacement_write_unknown")
    _save_progress(state, pending_action=action)
    state.execution.attempt_count += 1
    state.execution.attempted_at = datetime.now(UTC)
    state.execution.status = "unknown"
    state.execution.error_code = "exit_replacement_write_unknown"
    if action == "restore":
        _save_progress(state, restore_result="unknown")
    await session.flush()


async def resolve_replacement_write(
    session: AsyncSession,
    state: ReplacementState,
    *,
    actor_id: int,
    expected_version: int,
    resolution: ReplacementWriteResolution,
) -> None:
    """Record an explicit completion receipt; stable reads/timeouts are not receipts."""
    exit_id = state.old_exit.id if resolution.action == "stop_old" else state.new_exit.id
    evidence = resolution.model_dump(mode="json") | {"operation_id": state.execution.id}
    if await _previous_audit(
        session,
        state,
        exit_id=exit_id,
        action="replace_write_result",
        key=str(resolution.attempt),
        evidence=evidence,
    ):
        return
    _version(state, expected_version)
    if (
        state.progress.pending_action != resolution.action
        or state.execution.attempt_count != resolution.attempt
        or state.execution.attempted_at is None
        or resolution.completed_at < as_utc(state.execution.attempted_at)
    ):
        raise ServiceConflict("exit_replacement_write_unknown")
    _audit(
        session,
        state,
        exit_id=exit_id,
        actor_id=actor_id,
        action="replace_write_result",
        key=str(resolution.attempt),
        evidence=evidence,
    )
    _save_progress(state, pending_action=None)
    state.execution.status = "pending" if resolution.result == "applied" else "failed"
    state.execution.error_code = (
        None if resolution.result == "applied" else "exit_replacement_write_failed"
    )
    if resolution.result == "not_applied" and state.execution.first_failed_at is None:
        state.execution.first_failed_at = datetime.now(UTC)
    await session.flush()


def matches_stop_usage(
    stop: DedicatedExitAudit, *, total: int | None, raw: int | None, offset: int
) -> bool:
    return (
        stop.evidence.get("usage_total_bytes"),
        stop.evidence.get("usage_raw_bytes"),
        stop.evidence.get("usage_lifetime_offset"),
    ) == (total, raw, offset)


def _check_accounting(
    state: ReplacementState, *, total: int, raw: int, offset: int, observed_at: datetime
) -> None:
    connection = state.connection
    if (
        connection.usage_error is not None
        or connection.cycle_cutover_bytes is not None
        or state.service.last_usage_sync_at is None
        or as_utc(state.service.last_usage_sync_at) < observed_at
        or (
            connection.usage_total_bytes,
            connection.usage_raw_bytes,
            connection.usage_lifetime_offset or 0,
        )
        != (total, raw, offset)
    ):
        raise ServiceConflict("exit_replacement_usage_unconfirmed")


async def accept_replacement_stop(
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
        exit_id=state.old_exit.id,
        action="replace_stop",
        key=idempotency_key,
        evidence=values,
    )
    if previous:
        return previous, True
    _version(state, expected_version)
    if state.service.desired_status == "cancelled":
        raise ServiceConflict("exit_replacement_not_switchable")
    if (
        state.progress.stage not in {"stopping_old", "awaiting_confirmation", "switching"}
        or state.progress.pending_action is not None
    ):
        raise ServiceConflict("exit_replacement_write_unknown")
    if (
        evidence.resource_fingerprint != state.request.resource_fingerprint
        or evidence.stopped_at < as_utc(state.order.created_at)
    ):
        raise ServiceConflict("exit_replacement_scope_changed")
    _check_accounting(
        state,
        total=evidence.usage_total_bytes,
        raw=evidence.usage_raw_bytes,
        offset=evidence.usage_lifetime_offset,
        observed_at=evidence.usage_observed_at,
    )
    audit = _audit(
        session,
        state,
        exit_id=state.old_exit.id,
        actor_id=actor_id,
        action="replace_stop",
        key=idempotency_key,
        evidence=values,
    )
    _save_progress(
        state,
        stage="awaiting_confirmation",
        stop_audit_id=audit.id,
        verification_audit_id=None,
        confirmation_audit_id=None,
        restore_result="not_requested",
    )
    state.execution.status = "pending"
    state.execution.error_code = None
    await session.flush()
    return audit, False


async def verify_replacement_candidate(
    session: AsyncSession,
    state: ReplacementState,
    *,
    actor_id: int,
    expected_version: int,
    idempotency_key: str,
    evidence: ReplacementCandidateEvidence,
) -> tuple[DedicatedExitAudit, bool]:
    values = evidence.model_dump(mode="json") | {"operation_id": state.execution.id}
    previous = await _previous_audit(
        session,
        state,
        exit_id=state.new_exit.id,
        action="replace_verify",
        key=idempotency_key,
        evidence=values,
    )
    if previous:
        return previous, True
    _version(state, expected_version)
    _before_binding(state)
    if state.progress.stage != "awaiting_confirmation" or state.progress.pending_action is not None:
        raise ServiceConflict("exit_replacement_stage_changed")
    if (
        evidence.resource_fingerprint != state.request.resource_fingerprint
        or evidence.observed_ip != state.new_exit.ip_address
        or evidence.checked_at < as_utc(state.order.created_at)
    ):
        raise ServiceConflict("exit_replacement_scope_changed")
    audit = _audit(
        session,
        state,
        exit_id=state.new_exit.id,
        actor_id=actor_id,
        action="replace_verify",
        key=idempotency_key,
        evidence=values,
    )
    state.new_exit.verified_at = evidence.checked_at
    state.new_exit.revision += 1
    _save_progress(state, verification_audit_id=audit.id)
    state.execution.status = "pending"
    state.execution.error_code = None
    await session.flush()
    return audit, False


async def confirm_exit_replacement(
    session: AsyncSession,
    state: ReplacementState,
    *,
    actor_id: int,
    expected_version: int,
    expected_service_revision: int,
    resource_fingerprint: str,
    idempotency_key: str,
) -> tuple[DedicatedExitAudit, bool]:
    values: dict[str, object] = {
        "operation_id": state.execution.id,
        "resource_fingerprint": resource_fingerprint,
        "expected_service_revision": expected_service_revision,
        "stop_audit_id": state.progress.stop_audit_id,
        "verification_audit_id": state.progress.verification_audit_id,
        "request_restore": True,
    }
    previous = await _previous_audit(
        session,
        state,
        exit_id=state.new_exit.id,
        action="replace_confirm",
        key=idempotency_key,
        evidence=values,
    )
    if previous:
        return previous, True
    _version(state, expected_version)
    _before_binding(state)
    if state.service.revision != expected_service_revision:
        raise ServiceConflict("service_revision_changed")
    if resource_fingerprint != state.request.resource_fingerprint:
        raise ServiceConflict("exit_replacement_scope_changed")
    audits = await _evidence_chain(state)
    stop = audits.get("replace_stop")
    if stop is None or not matches_stop_usage(
        stop,
        total=state.connection.usage_total_bytes,
        raw=state.connection.usage_raw_bytes,
        offset=state.connection.usage_lifetime_offset or 0,
    ):
        raise ServiceConflict("exit_replacement_usage_unconfirmed")
    if (
        state.progress.stage != "awaiting_confirmation"
        or state.progress.verification_audit_id is None
        or state.progress.pending_action is not None
    ):
        raise ServiceConflict("exit_replacement_confirmation_required")
    audit = _audit(
        session,
        state,
        exit_id=state.new_exit.id,
        actor_id=actor_id,
        action="replace_confirm",
        key=idempotency_key,
        evidence=values,
    )
    _save_progress(
        state, stage="switching", confirmation_audit_id=audit.id, restore_result="pending"
    )
    state.execution.status = "pending"
    state.execution.error_code = None
    await session.flush()
    return audit, False


async def bind_replacement_exit(
    session: AsyncSession,
    state: ReplacementState,
    *,
    actor_id: int,
    expected_version: int,
    idempotency_key: str,
    observation: ReplacementBindingObservation,
) -> tuple[DedicatedExitAudit, bool]:
    values = observation.model_dump(mode="json") | {"operation_id": state.execution.id}
    previous = await _previous_audit(
        session,
        state,
        exit_id=state.new_exit.id,
        action="replace_bind",
        key=idempotency_key,
        evidence=values,
    )
    if previous:
        return previous, True
    _version(state, expected_version)
    _before_binding(state)
    if state.progress.stage != "switching" or state.progress.pending_action is not None:
        raise ServiceConflict("exit_replacement_write_unknown")
    audits = await _evidence_chain(state)
    stop = audits["replace_stop"]
    if not matches_stop_usage(
        stop,
        total=observation.usage_total_bytes,
        raw=observation.usage_raw_bytes,
        offset=observation.usage_lifetime_offset,
    ):
        raise ServiceConflict("exit_replacement_usage_unconfirmed")
    if observation.observed_at < as_utc(audits["replace_confirm"].created_at) or (
        state.execution.attempted_at is not None
        and observation.observed_at < as_utc(state.execution.attempted_at)
    ):
        raise ServiceConflict("exit_replacement_evidence_invalid")
    if (
        observation.resource_fingerprint != state.request.resource_fingerprint
        or observation.panel_user_uuid != state.connection.panel_user_uuid
        or observation.username != state.connection.username
        or observation.description != f"my_vps_obj:service:{state.service.id}"
        or observation.group_ids != [state.new_exit.squad_uuid]
        or state.new_exit.verified_at is None
    ):
        raise ServiceConflict("exit_replacement_scope_changed")
    _check_accounting(
        state,
        total=observation.usage_total_bytes,
        raw=observation.usage_raw_bytes,
        offset=observation.usage_lifetime_offset,
        observed_at=observation.observed_at,
    )
    # Flush the old unique binding first; both updates still commit or roll back together.
    state.old_exit.service_id = None
    state.old_exit.hold_order_id = state.order.id
    state.old_exit.revision += 1
    await session.flush()
    state.new_exit.hold_order_id = None
    state.new_exit.service_id = state.service.id
    state.new_exit.revision += 1
    state.service.revision += 1
    audit = _audit(
        session,
        state,
        exit_id=state.new_exit.id,
        actor_id=actor_id,
        action="replace_bind",
        key=idempotency_key,
        evidence=values,
    )
    _save_progress(state, stage="restoring", binding_audit_id=audit.id)
    state.connection.sync_pending = True
    state.connection.sync_error = "exit_replacement_in_progress"
    await session.flush()
    return audit, False
