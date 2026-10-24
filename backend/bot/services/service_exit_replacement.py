"""One durable replacement step per worker tick; no HTTP handler dispatches remote writes."""

from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.services.panel_api_service import PanelApiService
from bot.services.resource_preview_panel import digest
from bot.services.service_exit_replacement_entitlements import (
    confirm_replacement_period,
    period_allowance_blocked,
    replacement_terms,
    restore_reasons,
)
from bot.services.service_exit_replacement_panel import (
    ReplacementPatch,
    dispatch_patch,
    prepare_patch,
)
from bot.services.service_exit_replacement_topology import read_replacement_topology
from bot.services.service_operations import enabling_block
from bot.services.service_panel_state import locked_service, matches_service_terms, owns_identity
from bot.services.service_period_sync import settle_cancelled_service_period
from bot.services.service_usage_sync import record_service_usage
from config.service_exit_replacement import (
    ReplacementAction,
    ReplacementBindingObservation,
    ReplacementWriteResolution,
)
from config.service_periods import as_utc
from db.dal.service_exit_replacement_completion_dal import (
    discard_undispatched_write,
    finish_replacement,
    request_replacement_close,
)
from db.dal.service_exit_replacement_dal import (
    ReplacementState,
    begin_replacement_action,
    bind_replacement_exit,
    lock_replacement,
    resolve_replacement_write,
)
from db.dal.service_periods_dal import prepare_period
from db.dal.service_quota_dal import apply_latest_quota
from db.dal.user_services_dal import ServiceConflict
from db.models import User
from db.service_models import ServiceConnection, ServiceOperationExecution, UserService

DISABLED = {"DISABLED", "EXPIRED", "LIMITED"}


async def observe_identity(panel: PanelApiService, state: ReplacementState) -> dict[str, object]:
    reference = state.connection.panel_user_uuid
    if reference is None:
        raise ServiceConflict("panel_identity_missing")
    lookup = await panel.get_user_by_uuid_lookup(reference, log_response=False)
    value = lookup.get("user") if lookup.get("ok") is True else None
    if not isinstance(value, dict) or not owns_identity(value, state.connection):
        raise ServiceConflict("panel_identity_conflict")
    remote: dict[str, object] = dict(value)
    record_service_usage(state.service, state.connection, remote)
    return remote


def observed_groups(remote: dict[str, object]) -> set[str]:
    values = remote.get("activeInternalSquads")
    if not isinstance(values, list):
        raise ServiceConflict("exit_replacement_authorizations_unavailable")
    groups = [value.get("uuid") if isinstance(value, dict) else value for value in values]
    if not all(isinstance(value, str) for value in groups) or len(set(groups)) != len(groups):
        raise ServiceConflict("exit_replacement_authorizations_unavailable")
    return {str(value) for value in groups}


def require_stopped(remote: dict[str, object], *, group: str | None = None) -> None:
    if remote.get("status") not in DISABLED or observed_groups(remote) != (
        {group} if group else set()
    ):
        raise ServiceConflict("exit_replacement_stop_unconfirmed")


async def current_state(
    session: AsyncSession,
    service_id: str,
    operation_id: str | None = None,
    *,
    allow_terminal: bool = False,
) -> ReplacementState:
    owner = await session.scalar(select(UserService.user_id).where(UserService.id == service_id))
    if owner is None:
        raise ServiceConflict("service_not_found", 404)
    if operation_id is None:
        operation_id = await session.scalar(
            select(ServiceOperationExecution.id)
            .join(
                ServiceConnection,
                ServiceConnection.replacement_order_id == ServiceOperationExecution.order_id,
            )
            .where(ServiceConnection.service_id == service_id)
        )
    if operation_id is None:
        raise ServiceConflict("operation_not_found", 404)
    return await lock_replacement(
        session,
        service_id=service_id,
        user_id=owner,
        operation_id=operation_id,
        allow_terminal=allow_terminal,
    )


async def _decision(
    session: AsyncSession,
    panel: PanelApiService,
    state: ReplacementState,
) -> tuple[ReplacementAction, dict[str, object]] | None:
    if state.progress.pending_action is not None:
        return None
    await apply_latest_quota(session, state.service, state.connection)
    if state.service.desired_status == "cancelled":
        request_replacement_close(state)
    if state.execution.status == "failed":
        # Known failures cannot prevent new restrictions; restoration still needs retry.
        user = await session.get(User, state.service.user_id)
        if (
            state.progress.stage not in {"stopping_old", "restoring", "closing"}
            or user is None
            or (
                state.service.desired_status == "active"
                and enabling_block(user, state.service) is None
            )
        ):
            return None
    remote = await observe_identity(panel, state)
    groups = observed_groups(remote)
    if groups - {state.old_exit.squad_uuid, state.new_exit.squad_uuid}:
        raise ServiceConflict("exit_replacement_scope_changed")
    stage = state.progress.stage
    topology = await read_replacement_topology(
        session,
        panel,
        state.old_exit,
        state.new_exit,
        service_id=state.service.id,
        candidate_required=stage not in {"closing", "stopping_old"},
    )
    if period_allowance_blocked(state) and state.service.desired_status != "cancelled":
        state.connection.sync_error = state.execution.error_code = "panel_cycle_unconfirmed"
        if remote.get("status") not in DISABLED:
            action: ReplacementAction
            payload: dict[str, object] = {"status": "DISABLED"}
            if stage in {"stopping_old", "awaiting_confirmation", "closing"}:
                action = "close_access" if stage == "closing" else "stop_old"
                payload["activeInternalSquads"] = []
            else:
                action = "set_target_group" if stage == "switching" else "restore"
            return action, payload
        return None
    if stage == "closing":
        # Closing removes only this identity's authorization, even if a candidate failed.
        if topology.old_scope is None or topology.new_scope is None:
            raise ServiceConflict("exit_replacement_sources_incomplete")
        if groups or remote.get("status") not in DISABLED:
            return "close_access", {"status": "DISABLED", "activeInternalSquads": []}
        if state.connection.cycle_cutover_bytes is not None:
            if state.service.desired_status == "cancelled":
                await settle_cancelled_service_period(
                    session, state.service, state.connection, remote, actor_id=state.order.actor_id
                )
            elif not matches_service_terms(remote, state.service, [], connection=state.connection):
                return "close_access", replacement_terms(state, [], enable=False)
            else:
                await confirm_replacement_period(session, state)
        state.execution.error_code = "exit_replacement_close_evidence_required"
        return None
    topology.require(state.request.resource_fingerprint)
    await prepare_period(session, state.service, state.connection, datetime.now(UTC))
    if stage in {"stopping_old", "awaiting_confirmation"}:
        if groups or remote.get("status") not in DISABLED:
            if stage != "stopping_old":
                raise ServiceConflict("exit_replacement_stop_unconfirmed")
            return "stop_old", {"status": "DISABLED", "activeInternalSquads": []}
        if state.connection.cycle_cutover_bytes is not None:
            if not matches_service_terms(remote, state.service, [], connection=state.connection):
                return "stop_old", replacement_terms(state, [], enable=False)
            await confirm_replacement_period(session, state)
        state.execution.error_code = (
            "exit_replacement_stop_evidence_required" if stage == "stopping_old" else None
        )
        return None
    if stage == "switching":
        if state.connection.usage_error is not None:
            raise ServiceConflict("exit_replacement_usage_unconfirmed")
        if remote.get("status") not in DISABLED:
            raise ServiceConflict("exit_replacement_stop_unconfirmed")
        target = [state.new_exit.squad_uuid]
        if not matches_service_terms(remote, state.service, target, connection=state.connection):
            return "set_target_group", replacement_terms(state, target, enable=False)
        if state.connection.cycle_cutover_bytes is not None:
            await confirm_replacement_period(session, state)
            return None
        assert state.connection.panel_user_uuid is not None
        assert state.connection.usage_total_bytes is not None
        assert state.connection.usage_raw_bytes is not None
        assert state.service.last_usage_sync_at is not None
        # This read verifies the binding only after the pending write was explicitly resolved.
        observation = ReplacementBindingObservation(
            resource_fingerprint=state.request.resource_fingerprint,
            panel_user_uuid=state.connection.panel_user_uuid,
            username=state.connection.username,
            description=f"my_vps_obj:service:{state.service.id}",
            group_ids=target,
            status=cast(Literal["DISABLED", "EXPIRED", "LIMITED"], remote["status"]),
            observed_at=as_utc(state.service.last_usage_sync_at),
            report_digest=digest(remote),
            usage_total_bytes=state.connection.usage_total_bytes,
            usage_raw_bytes=state.connection.usage_raw_bytes,
            usage_lifetime_offset=state.connection.usage_lifetime_offset or 0,
        )
        await bind_replacement_exit(
            session,
            state,
            actor_id=state.order.actor_id,
            expected_version=state.progress.version,
            idempotency_key="binding",
            observation=observation,
        )
        return None
    if stage == "restoring":
        reasons = await restore_reasons(session, state)
        if state.execution.status == "failed":
            if reasons and remote.get("status") not in DISABLED:
                return "restore", {"status": "DISABLED"}
            return None
        enable = not reasons and state.connection.cycle_cutover_bytes is None
        target = [state.new_exit.squad_uuid]
        desired = {"ACTIVE"} if enable else DISABLED
        if (
            not matches_service_terms(remote, state.service, target, connection=state.connection)
            or remote.get("status") not in desired
        ):
            return "restore", replacement_terms(state, target, enable=enable)
        if state.connection.cycle_cutover_bytes is not None:
            await confirm_replacement_period(session, state)
            return None
        # Recompute after network latency and the accepted usage sample.
        after = await restore_reasons(session, state)
        if not reasons and after:
            return "restore", replacement_terms(state, target, enable=False)
        finish_replacement(state, enabled=enable, reasons=after)
    return None


async def run_exit_replacement(
    session_factory: sessionmaker,
    service_id: str,
    panel: PanelApiService,
) -> None:
    patch: ReplacementPatch | None = None
    action: ReplacementAction | None = None
    operation_id: str | None = None
    attempt = 0
    checked_revision = 0
    restriction_only = False
    previous_attempted_at: datetime | None = None
    async with session_factory() as session:
        try:
            locked = await locked_service(session, service_id)
            if locked is None or locked[2].replacement_order_id is None:
                return
            # Polling must rotate even when evidence, an unknown write or sources block progress.
            locked[2].sync_attempted_at = datetime.now(UTC)
            await session.commit()
            state = await current_state(session, service_id)
            operation_id = state.execution.id
            decision = await _decision(session, panel, state)
            if decision is not None:
                action, payload = decision
                restriction_only = state.execution.status == "failed" and action == "restore"
                assert state.connection.panel_user_uuid is not None
                patch = await prepare_patch(panel, state.connection.panel_user_uuid, payload)
                checked_revision = state.service.revision
                previous_attempted_at = state.execution.attempted_at
                await begin_replacement_action(
                    session, state, action=action, expected_version=state.progress.version
                )
                attempt = state.execution.attempt_count
            await session.commit()
        except ServiceConflict as exc:
            if operation_id is not None:
                execution = await session.get(ServiceOperationExecution, operation_id)
                if execution and execution.status != "unknown":
                    execution.error_code = exc.code
                    execution.status = "failed"
                    execution.first_failed_at = execution.first_failed_at or datetime.now(UTC)
                    await session.commit()
            return
        except Exception:
            await session.rollback()
            if operation_id is not None:
                try:
                    state = await current_state(session, service_id, operation_id)
                    if state.progress.pending_action is None:
                        state.execution.status = "failed"
                        state.execution.error_code = "exit_replacement_sources_incomplete"
                        state.execution.first_failed_at = (
                            state.execution.first_failed_at or datetime.now(UTC)
                        )
                        await session.commit()
                except Exception:
                    await session.rollback()
            return
    if patch is None or action is None or operation_id is None:
        return
    # Hold the account/execution/resource locks over dispatch and receipt acceptance.
    # The committed marker survives timeout, cancellation and a failed local commit.
    async with session_factory() as session:
        try:
            state = await current_state(session, service_id, operation_id)
            if state.progress.pending_action != action or state.execution.attempt_count != attempt:
                return
            try:
                await apply_latest_quota(session, state.service, state.connection)
                if state.service.revision != checked_revision:
                    raise ServiceConflict("service_revision_changed")
                topology = await read_replacement_topology(
                    session,
                    panel,
                    state.old_exit,
                    state.new_exit,
                    service_id=service_id,
                    candidate_required=action in {"set_target_group", "restore"},
                )
                if action == "close_access":
                    if topology.old_scope is None or topology.new_scope is None:
                        raise ServiceConflict("exit_replacement_sources_incomplete")
                else:
                    topology.require(state.request.resource_fingerprint)
                remote = await observe_identity(panel, state)
                if observed_groups(remote) - {state.old_exit.squad_uuid, state.new_exit.squad_uuid}:
                    raise ServiceConflict("exit_replacement_scope_changed")
                if "trafficLimitBytes" in patch.payload:
                    groups = (
                        []
                        if action in {"stop_old", "close_access"}
                        else [state.new_exit.squad_uuid]
                    )
                    terms = replacement_terms(
                        state, groups, enable=patch.payload.get("status") == "ACTIVE"
                    )
                    if any(patch.payload.get(key) != value for key, value in terms.items()):
                        raise ServiceConflict("exit_replacement_usage_unconfirmed")
                if patch.payload.get("status") == "ACTIVE" and await restore_reasons(
                    session, state
                ):
                    raise ServiceConflict("service_not_deliverable")
                if restriction_only and not await restore_reasons(session, state):
                    raise ServiceConflict("service_not_deliverable")
            except ServiceConflict as exc:
                discard_undispatched_write(
                    state, previous_attempted_at=previous_attempted_at, reason=exc.code
                )
                await session.commit()
                return
            receipt = await dispatch_patch(panel, patch)
            if receipt is None:
                return
            await resolve_replacement_write(
                session,
                state,
                actor_id=state.order.actor_id,
                expected_version=state.progress.version,
                resolution=ReplacementWriteResolution(
                    action=action,
                    attempt=attempt,
                    provenance="panel_response",
                    report_digest=receipt,
                    completed_at=datetime.now(UTC),
                    result="applied",
                ),
            )
            await session.commit()
        except Exception:
            await session.rollback()
