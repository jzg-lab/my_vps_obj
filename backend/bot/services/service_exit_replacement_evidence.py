"""Scoped use of the existing dedicated-exit verify/reclaim actions."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.admin_console_exit_replacement_schemas import (
    ExitReplacementReclaimBody,
    ExitReplacementVerifyBody,
)
from bot.services.panel_api_service import PanelApiService
from bot.services.service_exit_replacement import current_state, observe_identity, observed_groups
from bot.services.service_exit_replacement_view import stable_topology
from config.service_exit_replacement import ReplacementCandidateEvidence
from config.service_periods import as_utc
from db.dal.service_exit_replacement_completion_dal import (
    reclaim_replacement_hold,
    request_replacement_close,
)
from db.dal.service_exit_replacement_dal import (
    _audit,
    _audit_key,
    _previous_audit,
    _version,
    verify_replacement_candidate,
)
from db.dal.user_services_dal import ServiceConflict
from db.service_models import DedicatedExit, DedicatedExitAudit


async def scoped_exit_evidence(
    session: AsyncSession,
    panel: PanelApiService | None,
    *,
    exit_id: str,
    actor_id: int,
    body: ExitReplacementVerifyBody | ExitReplacementReclaimBody,
) -> tuple[DedicatedExit, DedicatedExitAudit, bool]:
    state = await current_state(
        session, body.service_id, body.replacement_operation_id, allow_terminal=True
    )
    if exit_id not in {state.old_exit.id, state.new_exit.id}:
        raise ServiceConflict("exit_replacement_scope_changed")
    resource = state.old_exit if exit_id == state.old_exit.id else state.new_exit
    if isinstance(body, ExitReplacementVerifyBody):
        if exit_id != state.new_exit.id:
            raise ServiceConflict("exit_replacement_scope_changed")
        evidence = ReplacementCandidateEvidence(
            resource_fingerprint=state.request.resource_fingerprint,
            checked_at=body.checked_at,
            observed_ip=body.observed_ip,
            provenance="administrator",
            report_digest=body.evidence_digest,
            fixed=True,
            exclusive=True,
        )
        previous = await _previous_audit(
            session,
            state,
            exit_id=exit_id,
            action="replace_verify",
            key=body.idempotency_key,
            evidence=evidence.model_dump(mode="json") | {"operation_id": state.execution.id},
        )
        if previous:
            return resource, previous, True
        topology = await stable_topology(session, panel, state)
        topology.require(state.request.resource_fingerprint)
        if topology.new_scope != body.scope_fingerprint:
            raise ServiceConflict("exit_replacement_scope_changed")
        if resource.revision != body.expected_revision:
            raise ServiceConflict("exit_revision_changed")
        audit, duplicate = await verify_replacement_candidate(
            session,
            state,
            actor_id=actor_id,
            expected_version=body.expected_operation_version,
            idempotency_key=body.idempotency_key,
            evidence=evidence,
        )
        return resource, audit, duplicate
    if (body.reclaim_purpose == "retained_old") != (exit_id == state.old_exit.id):
        raise ServiceConflict("exit_replacement_scope_changed")
    values = body.model_dump(mode="json") | {"operation_id": state.execution.id}
    prior_cleanup = await _previous_audit(
        session,
        state,
        exit_id=exit_id,
        action="replace_cleanup",
        key=body.idempotency_key,
        evidence=values,
    )
    if prior_cleanup:
        return resource, prior_cleanup, True
    prior_reclaim = await session.scalar(
        select(DedicatedExitAudit).where(
            DedicatedExitAudit.exit_id == exit_id,
            DedicatedExitAudit.idempotency_key
            == _audit_key(state.execution.id, "replace_reclaim", body.idempotency_key),
        )
    )
    if prior_reclaim is not None:
        # DAL checks the full immutable command before returning an historical duplicate.
        audit, duplicate = await reclaim_replacement_hold(
            session,
            state,
            resource=resource,
            actor_id=actor_id,
            expected_version=body.expected_operation_version,
            expected_revision=body.expected_revision,
            idempotency_key=body.idempotency_key,
            checked_at=body.checked_at,
            scope_fingerprint=body.scope_fingerprint,
            report_digest=body.evidence_digest,
        )
        return resource, audit, duplicate
    topology = await stable_topology(session, panel, state, candidate_required=False)
    scope = topology.old_scope if exit_id == state.old_exit.id else topology.new_scope
    if scope is None:
        raise ServiceConflict("exit_replacement_sources_incomplete")
    if scope != body.scope_fingerprint:
        raise ServiceConflict("exit_replacement_scope_changed")
    _version(state, body.expected_operation_version)
    if resource.revision != body.expected_revision:
        raise ServiceConflict("exit_revision_changed")
    if body.checked_at < as_utc(state.order.created_at):
        raise ServiceConflict("exit_replacement_evidence_invalid")
    if state.progress.stage not in {"completed", "closed"}:
        if (
            body.reclaim_purpose != "candidate_cleanup"
            or state.progress.binding_audit_id is not None
        ):
            raise ServiceConflict("exit_replacement_stage_changed")
        request_replacement_close(state)
        audit = _audit(
            session,
            state,
            exit_id=exit_id,
            actor_id=actor_id,
            action="replace_cleanup",
            key=body.idempotency_key,
            evidence=values,
        )
        await session.flush()
        return resource, audit, False
    if panel is None:
        raise ServiceConflict("exit_replacement_sources_incomplete")
    # Reclaimed resources can never be inferred from a completed swap alone.
    if state.connection.state == "revoked" and state.connection.revoked_at is not None:
        if body.checked_at < as_utc(state.connection.revoked_at):
            raise ServiceConflict("exit_replacement_evidence_invalid")
    else:
        remote = await observe_identity(panel, state)
        if resource.squad_uuid in observed_groups(remote):
            raise ServiceConflict("exit_replacement_stop_unconfirmed")
    if (
        state.connection.usage_error is not None
        or state.connection.cycle_cutover_bytes is not None
        or state.connection.usage_total_bytes is None
    ):
        raise ServiceConflict("exit_replacement_usage_unconfirmed")
    audit, duplicate = await reclaim_replacement_hold(
        session,
        state,
        resource=resource,
        actor_id=actor_id,
        expected_version=body.expected_operation_version,
        expected_revision=body.expected_revision,
        idempotency_key=body.idempotency_key,
        checked_at=body.checked_at,
        scope_fingerprint=body.scope_fingerprint,
        report_digest=body.evidence_digest,
    )
    return resource, audit, duplicate
