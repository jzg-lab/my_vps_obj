"""Typed administrator intent and attestation acceptance; never dispatch panel mutations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.admin_console_exit_replacement_schemas import (
    ConsoleExitReplacementAcceptedOut,
    ConsoleExitReplacementConfirmBody,
    ConsoleExitReplacementEvidenceBody,
    ConsoleExitReplacementStartBody,
)
from bot.services.panel_api_service import PanelApiService
from bot.services.service_exit_replacement import (
    current_state,
    observe_identity,
    observed_groups,
    require_stopped,
)
from bot.services.service_exit_replacement_topology import read_replacement_topology
from bot.services.service_exit_replacement_view import operation_output, stable_topology
from config.service_exit_replacement import (
    ReplacementRequest,
    ReplacementStopEvidence,
    ReplacementWriteResolution,
)
from db.dal.resource_operations_dal import coordinate_resources
from db.dal.service_exit_replacement_completion_dal import accept_replacement_close
from db.dal.service_exit_replacement_dal import (
    accept_replacement_stop,
    confirm_exit_replacement,
    reserve_exit_replacement,
    resolve_replacement_write,
)
from db.dal.user_dal import lock_user_by_id
from db.dal.user_services_dal import ServiceConflict
from db.service_models import DedicatedExit, ServiceOrder, UserService


async def start_replacement(
    session: AsyncSession,
    panel: PanelApiService | None,
    *,
    service_id: str,
    actor_id: int,
    body: ConsoleExitReplacementStartBody,
) -> ConsoleExitReplacementAcceptedOut:
    await coordinate_resources(session)
    await lock_user_by_id(session, body.user_id)
    service = await session.get(UserService, service_id, populate_existing=True)
    if service is None or service.user_id != body.user_id:
        raise ServiceConflict("service_not_found", 404)
    old, new = (
        await session.get(DedicatedExit, body.old_exit_id),
        await session.get(DedicatedExit, body.new_exit_id),
    )
    if old is None or new is None:
        raise ServiceConflict("exit_not_found", 404)
    previous = await session.scalar(
        select(ServiceOrder.id).where(
            ServiceOrder.request_owner_id == body.user_id,
            ServiceOrder.idempotency_key == body.idempotency_key,
        )
    )
    if previous is None:
        first = await read_replacement_topology(session, panel, old, new, service_id=service_id)
        first.require(body.expected_resource_fingerprint)
        second = await read_replacement_topology(session, panel, old, new, service_id=service_id)
        second.require(body.expected_resource_fingerprint)
    operation, duplicate = await reserve_exit_replacement(
        session,
        service_id=service_id,
        user_id=body.user_id,
        actor_id=actor_id,
        idempotency_key=body.idempotency_key,
        request=ReplacementRequest(
            **body.model_dump(
                exclude={"user_id", "idempotency_key", "expected_resource_fingerprint"}
            ),
            resource_fingerprint=body.expected_resource_fingerprint,
        ),
    )
    state = await current_state(session, service_id, operation.id, allow_terminal=True)
    topology = await read_replacement_topology(
        session, panel, state.old_exit, state.new_exit, service_id=service_id
    )
    return ConsoleExitReplacementAcceptedOut(
        duplicate=duplicate, replacement=await operation_output(session, state, topology)
    )


async def confirm_replacement(
    session: AsyncSession,
    panel: PanelApiService | None,
    *,
    service_id: str,
    actor_id: int,
    body: ConsoleExitReplacementConfirmBody,
) -> ConsoleExitReplacementAcceptedOut:
    state = await current_state(session, service_id, body.operation_id, allow_terminal=True)
    if state.service.user_id != body.user_id:
        raise ServiceConflict("service_not_found", 404)
    topology = await stable_topology(session, panel, state)
    topology.require(body.expected_resource_fingerprint)
    if (
        body.old_stop_audit_id != state.progress.stop_audit_id
        or body.candidate_verify_audit_id != state.progress.verification_audit_id
    ):
        raise ServiceConflict("exit_replacement_evidence_invalid")
    if state.progress.stage == "awaiting_confirmation":
        if (state.old_exit.revision, state.new_exit.revision) != (
            body.expected_old_exit_revision,
            body.expected_new_exit_revision,
        ):
            raise ServiceConflict("exit_revision_changed")
        if panel is None:
            raise ServiceConflict("exit_replacement_sources_incomplete")
        remote = await observe_identity(panel, state)
        groups = observed_groups(remote)
        require_stopped(remote, group=state.new_exit.squad_uuid if groups else None)
    _, duplicate = await confirm_exit_replacement(
        session,
        state,
        actor_id=actor_id,
        expected_version=body.expected_operation_version,
        expected_service_revision=body.expected_revision,
        resource_fingerprint=body.expected_resource_fingerprint,
        idempotency_key=body.idempotency_key,
    )
    return ConsoleExitReplacementAcceptedOut(
        duplicate=duplicate, replacement=await operation_output(session, state, topology)
    )


async def accept_evidence(
    session: AsyncSession,
    panel: PanelApiService | None,
    *,
    service_id: str,
    actor_id: int,
    body: ConsoleExitReplacementEvidenceBody,
) -> ConsoleExitReplacementAcceptedOut:
    state = await current_state(session, service_id, body.operation_id, allow_terminal=True)
    if body.purpose == "resolve_write":
        if body.resource_fingerprint != state.request.resource_fingerprint:
            raise ServiceConflict("exit_replacement_scope_changed")
        assert body.action and body.attempt and body.result
        before = state.progress.version
        await resolve_replacement_write(
            session,
            state,
            actor_id=actor_id,
            expected_version=body.expected_operation_version,
            resolution=ReplacementWriteResolution(
                action=body.action,
                attempt=body.attempt,
                provenance="operator_reconciliation",
                report_digest=body.evidence_digest,
                completed_at=body.checked_at,
                result=body.result,
            ),
        )
        duplicate = before == state.progress.version
        topology = await read_replacement_topology(
            session,
            panel,
            state.old_exit,
            state.new_exit,
            service_id=service_id,
            candidate_required=False,
        )
    else:
        topology = await stable_topology(
            session, panel, state, candidate_required=body.purpose != "close"
        )
        topology.require(body.resource_fingerprint)
        if panel is None:
            raise ServiceConflict("exit_replacement_sources_incomplete")
        remote = await observe_identity(panel, state)
        groups = observed_groups(remote)
        require_stopped(
            remote, group=state.new_exit.squad_uuid if body.purpose == "stop" and groups else None
        )
        evidence = ReplacementStopEvidence.model_validate(
            {
                "resource_fingerprint": body.resource_fingerprint,
                "stopped_at": body.checked_at,
                "usage_observed_at": body.usage_observed_at,
                "stop_provenance": "administrator",
                "usage_provenance": "administrator",
                "stop_report_digest": body.evidence_digest,
                "usage_report_digest": body.usage_evidence_digest,
                "authorization_removed": True,
                "connections_stopped": True,
                "old_config_rejected": True,
                "usage_total_bytes": body.usage_total_bytes,
                "usage_raw_bytes": body.usage_raw_bytes,
                "usage_lifetime_offset": body.usage_lifetime_offset,
            }
        )
        accept = accept_replacement_stop if body.purpose == "stop" else accept_replacement_close
        _, duplicate = await accept(
            session,
            state,
            actor_id=actor_id,
            expected_version=body.expected_operation_version,
            idempotency_key=body.idempotency_key,
            evidence=evidence,
        )
    return ConsoleExitReplacementAcceptedOut(
        duplicate=duplicate, replacement=await operation_output(session, state, topology)
    )
