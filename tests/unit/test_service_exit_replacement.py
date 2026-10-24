"""Offline transaction tests; SQLite does not prove PostgreSQL row-lock exclusion."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.app.web.admin_console_operations_schemas import ConsoleServiceOperationOut
from bot.app.web.service_schemas import DedicatedExitOut, UserServiceOut
from bot.services.account_access_sync import set_account_ban, synchronize_account_access
from bot.services.service_change_sync import synchronize_service_entitlement_locked
from bot.services.service_delivery import deliver_service_identity, service_subscription
from bot.services.service_panel_state import service_squads
from bot.services.service_provisioning import ServiceProvisioningWorker, provision_service_identity
from bot.services.service_revocation import revoke_service_identity
from bot.services.service_usage_sync import record_service_usage
from config.service_exit_replacement import (
    ReplacementBindingObservation,
    ReplacementCandidateEvidence,
    ReplacementProgress,
    ReplacementRequest,
    ReplacementStopEvidence,
    ReplacementWriteResolution,
)
from config.service_periods import as_utc
from db.dal.admin_console_services_dal import business_status, service_query
from db.dal.service_accounts_dal import deletion_connections, merge_history
from db.dal.service_delivery_dal import record_exit_evidence, request_service_revocation
from db.dal.service_exit_replacement_dal import (
    ReplacementState,
    accept_replacement_stop,
    begin_replacement_action,
    bind_replacement_exit,
    confirm_exit_replacement,
    lock_replacement,
    reserve_exit_replacement,
    resolve_replacement_write,
    verify_replacement_candidate,
)
from db.dal.service_operations_dal import retry_block_reason, supersede_executions
from db.dal.user_merge_dal import UserMergeConflictError, merge_users
from db.dal.user_services_dal import ServiceConflict, activate_service, save_plan
from db.models import User
from db.service_models import (
    DedicatedExit,
    DedicatedExitAudit,
)
from tests.unit.test_service_changes import ServiceChangeTestCase
from tests.unit.test_user_services import sample_terms

DIGEST = "a" * 64


@pytest.mark.parametrize(
    "changes",
    [
        {"stage": "switching"},
        {"stage": "restoring"},
        {"pending_action": "set_target_group"},
        {"version": True},
        {"version": 0},
        {"schema_version": 1},
        {"verification_audit_id": "b" * 32},
    ],
)
def test_progress_rejects_invented_or_inconsistent_state(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ReplacementProgress.model_validate(changes)


def test_evidence_requires_explicit_boolean_and_real_ip() -> None:
    values = {
        "resource_fingerprint": DIGEST,
        "checked_at": datetime.now(UTC),
        "observed_ip": "::ffff:192.0.2.2",
        "provenance": "administrator",
        "report_digest": DIGEST,
        "fixed": True,
        "exclusive": True,
    }
    assert ReplacementCandidateEvidence.model_validate(values).observed_ip == "192.0.2.2"
    for changes in (
        {"fixed": 1},
        {"exclusive": "true"},
        {"observed_ip": "guess"},
        {"provenance": "stable_counts"},
        {"checked_at": datetime(2020, 1, 1, tzinfo=UTC).replace(tzinfo=None)},
    ):
        with pytest.raises(ValidationError):
            ReplacementCandidateEvidence.model_validate(values | changes)


class ReplacementDatabaseTestCase(ServiceChangeTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.old_id, self.new_id = uuid4().hex, uuid4().hex
        async with self.sessions.begin() as session:
            self.plan = await save_plan(
                session,
                terms=sample_terms(
                    resource_type="dedicated", squad_uuids=[], resource_pool="private"
                ),
                enabled=True,
                actor_id=1,
            )
            for index, exit_id in enumerate((self.old_id, self.new_id), 1):
                session.add(
                    DedicatedExit(
                        id=exit_id,
                        label=f"Exit {index}",
                        ip_address=f"192.0.2.{index}",
                        resource_pool="private",
                        squad_uuid=str(UUID(int=index)),
                        enabled=True,
                        verified_at=datetime.now(UTC),
                        created_at=datetime.now(UTC),
                    )
                )
        async with self.sessions.begin() as session:
            self.service, _, _ = await activate_service(
                session,
                user_id=1,
                actor_id=1,
                plan_id=self.plan.id,
                expected_revision=1,
                idempotency_key="open",
                exit_id=self.old_id,
            )
        self.panel, self.remote = await self.prepare(self.service, ready=True)
        await self.sync(self.service, self.panel)
        async with self.sessions.begin() as session:
            old = await session.get(DedicatedExit, self.old_id)
            new = await session.get(DedicatedExit, self.new_id)
            assert old and new
            self.request = ReplacementRequest(
                expected_revision=self.service.revision,
                old_exit_id=old.id,
                new_exit_id=new.id,
                expected_old_exit_revision=old.revision,
                expected_new_exit_revision=new.revision,
                resource_fingerprint=DIGEST,
                reason="Verified replacement",
            )
            self.operation, _ = await reserve_exit_replacement(
                session,
                service_id=self.service.id,
                user_id=1,
                actor_id=1,
                idempotency_key="replace",
                request=self.request,
            )
        self.panel.reset_mock()

    async def state(self, session: AsyncSession) -> ReplacementState:
        return await lock_replacement(
            session, service_id=self.service.id, user_id=1, operation_id=self.operation.id
        )

    def sample(self, state: ReplacementState) -> datetime:
        record_service_usage(state.service, state.connection, self.remote)
        assert state.service.last_usage_sync_at is not None
        observed = state.service.last_usage_sync_at
        assert isinstance(observed, datetime)
        return observed.replace(tzinfo=UTC) if observed.tzinfo is None else observed.astimezone(UTC)

    def stop_evidence(self, state: ReplacementState) -> ReplacementStopEvidence:
        observed = self.sample(state)
        return ReplacementStopEvidence(
            resource_fingerprint=DIGEST,
            stopped_at=observed,
            usage_observed_at=observed,
            stop_provenance="administrator",
            usage_provenance="administrator",
            stop_report_digest=DIGEST,
            usage_report_digest=DIGEST,
            authorization_removed=True,
            connections_stopped=True,
            old_config_rejected=True,
            usage_total_bytes=state.connection.usage_total_bytes or 0,
            usage_raw_bytes=state.connection.usage_raw_bytes or 0,
            usage_lifetime_offset=state.connection.usage_lifetime_offset or 0,
        )

    async def confirmed(self, session: AsyncSession) -> ReplacementState:
        state = await self.state(session)
        await accept_replacement_stop(
            session,
            state,
            actor_id=1,
            expected_version=1,
            idempotency_key="stop",
            evidence=self.stop_evidence(state),
        )
        await verify_replacement_candidate(
            session,
            state,
            actor_id=1,
            expected_version=2,
            idempotency_key="verify",
            evidence=ReplacementCandidateEvidence(
                resource_fingerprint=DIGEST,
                checked_at=datetime.now(UTC),
                observed_ip="192.0.2.2",
                provenance="administrator",
                report_digest=DIGEST,
                fixed=True,
                exclusive=True,
            ),
        )
        await confirm_exit_replacement(
            session,
            state,
            actor_id=1,
            expected_version=3,
            expected_service_revision=state.service.revision,
            resource_fingerprint=DIGEST,
            idempotency_key="confirm",
        )
        return state

    def observation(self, state: ReplacementState) -> ReplacementBindingObservation:
        self.remote["activeInternalSquads"] = [{"uuid": state.new_exit.squad_uuid}]
        self.remote["status"] = "DISABLED"
        observed = self.sample(state)
        assert state.connection.panel_user_uuid
        return ReplacementBindingObservation(
            resource_fingerprint=DIGEST,
            panel_user_uuid=state.connection.panel_user_uuid,
            username=state.connection.username,
            description=f"my_vps_obj:service:{state.service.id}",
            group_ids=[state.new_exit.squad_uuid],
            status="DISABLED",
            observed_at=observed,
            report_digest=DIGEST,
            usage_total_bytes=state.connection.usage_total_bytes or 0,
            usage_raw_bytes=state.connection.usage_raw_bytes or 0,
            usage_lifetime_offset=state.connection.usage_lifetime_offset or 0,
        )


class ExitReplacementTests(ReplacementDatabaseTestCase):
    async def test_reservation_replays_without_freeing_or_rewriting_rights(self) -> None:
        async with self.sessions.begin() as session:
            execution, duplicate = await reserve_exit_replacement(
                session,
                service_id=self.service.id,
                user_id=1,
                actor_id=1,
                idempotency_key="replace",
                request=self.request,
            )
            state = await self.state(session)
            assert duplicate and execution.id == self.operation.id
            assert (
                state.old_exit.service_id == state.service.id
                and state.old_exit.hold_order_id is None
            )
            assert (
                state.new_exit.service_id is None and state.new_exit.hold_order_id == state.order.id
            )
            assert state.service.terms == self.service.terms
            assert as_utc(state.service.expires_at) == as_utc(self.service.expires_at)
            assert state.connection.state == "ready" and state.connection.panel_user_uuid
            with pytest.raises(ServiceConflict, match="idempotency_conflict"):
                await reserve_exit_replacement(
                    session,
                    service_id=self.service.id,
                    user_id=1,
                    actor_id=1,
                    idempotency_key="replace",
                    request=self.request.model_copy(update={"reason": "Different reason"}),
                )
            with pytest.raises(ServiceConflict, match="exit_unavailable"):
                await activate_service(
                    session,
                    user_id=2,
                    actor_id=1,
                    plan_id=self.plan.id,
                    expected_revision=1,
                    idempotency_key="race",
                    exit_id=self.new_id,
                )
        assert not self.panel.mock_calls

    async def test_unknown_write_requires_explicit_idempotent_receipt(self) -> None:
        async with self.sessions.begin() as session:
            state = await self.state(session)
            await begin_replacement_action(session, state, action="stop_old", expected_version=1)
        async with self.sessions.begin() as session:
            state = await self.state(session)
            assert state.progress.version == 2 and state.execution.status == "unknown"
            with pytest.raises(ServiceConflict, match="write_unknown"):
                await accept_replacement_stop(
                    session,
                    state,
                    actor_id=1,
                    expected_version=2,
                    idempotency_key="stop",
                    evidence=self.stop_evidence(state),
                )
            receipt = ReplacementWriteResolution(
                action="stop_old",
                attempt=1,
                provenance="operator_reconciliation",
                report_digest=DIGEST,
                completed_at=datetime.now(UTC),
                result="applied",
            )
            await resolve_replacement_write(
                session, state, actor_id=1, expected_version=2, resolution=receipt
            )
            await resolve_replacement_write(
                session, state, actor_id=1, expected_version=2, resolution=receipt
            )
            assert state.progress.version == 3 and state.execution.status == "pending"
            with pytest.raises(ServiceConflict, match="version_changed"):
                await begin_replacement_action(
                    session, state, action="stop_old", expected_version=2
                )
            with pytest.raises(ServiceConflict, match="idempotency_conflict"):
                await resolve_replacement_write(
                    session,
                    state,
                    actor_id=1,
                    expected_version=2,
                    resolution=receipt.model_copy(update={"result": "not_applied"}),
                )

    async def test_state_cannot_cross_transaction_without_relocking(self) -> None:
        async with self.sessions() as session:
            state = await self.state(session)
            await session.commit()
            with pytest.raises(ServiceConflict, match="lock_required"):
                await begin_replacement_action(
                    session, state, action="stop_old", expected_version=1
                )

    async def test_manual_provenance_and_binding_keep_identity_usage_and_old_hold(self) -> None:
        async with self.sessions.begin() as session:
            state = await self.confirmed(session)
            identity = state.connection.panel_user_uuid
            usage = state.connection.usage_total_bytes
            assert state.progress.version == 4
            evidence = self.observation(state)
            audit, duplicate = await bind_replacement_exit(
                session,
                state,
                actor_id=1,
                expected_version=4,
                idempotency_key="bind",
                observation=evidence,
            )
            same, duplicate = await bind_replacement_exit(
                session,
                state,
                actor_id=1,
                expected_version=4,
                idempotency_key="bind",
                observation=evidence,
            )
            assert duplicate and same.id == audit.id
            assert state.progress.stage == "restoring" and state.execution.status != "succeeded"
            assert (
                state.old_exit.service_id is None and state.old_exit.hold_order_id == state.order.id
            )
            assert (
                state.new_exit.service_id == state.service.id
                and state.new_exit.hold_order_id is None
            )
            assert (
                state.connection.panel_user_uuid == identity
                and state.connection.usage_total_bytes == usage
            )
            assert (
                state.service.terms == self.service.terms
                and state.service.desired_status == "active"
            )
            stop = await session.get(DedicatedExitAudit, state.progress.stop_audit_id)
            assert stop and stop.evidence["stop_provenance"] == "administrator"
            assert stop.evidence["usage_provenance"] == "administrator"
            assert state.connection.replacement_order_id == state.order.id
        await self.sync(self.service, self.panel)
        assert self.remote["status"] == "DISABLED"
        self.panel.update_user_details_on_panel.assert_not_awaited()

    async def test_binding_rollback_preserves_both_original_allocations(self) -> None:
        async with self.sessions.begin() as session:
            await self.confirmed(session)
        async with self.sessions() as session:
            state = await self.state(session)
            await bind_replacement_exit(
                session,
                state,
                actor_id=1,
                expected_version=4,
                idempotency_key="bind",
                observation=self.observation(state),
            )
            await session.rollback()
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.progress.stage == "switching"
            assert state.old_exit.service_id == state.service.id
            assert (
                state.new_exit.hold_order_id == state.order.id and state.new_exit.service_id is None
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(DedicatedExitAudit)
                    .where(DedicatedExitAudit.action == "replace_bind")
                )
                == 0
            )

    async def test_scope_corruption_and_forged_audit_fail_closed(self) -> None:
        async with self.sessions.begin() as session:
            state = await self.state(session)
            state.execution.replacement_progress = ReplacementProgress(
                stage="awaiting_confirmation", stop_audit_id="b" * 32
            ).model_dump(mode="json")
        async with self.sessions() as session:
            with pytest.raises(ServiceConflict, match="evidence_invalid"):
                await self.state(session)

    async def test_changed_accounting_blocks_stop_without_releasing_resources(self) -> None:
        async with self.sessions.begin() as session:
            state = await self.state(session)
            evidence = self.stop_evidence(state)
            state.connection.usage_error = "panel_usage_reset"
            with pytest.raises(ServiceConflict, match="usage_unconfirmed"):
                await accept_replacement_stop(
                    session,
                    state,
                    actor_id=1,
                    expected_version=1,
                    idempotency_key="stop",
                    evidence=evidence,
                )
            assert state.progress.stage == "stopping_old" and state.new_exit.hold_order_id

    async def test_durable_gate_blocks_direct_sync_even_when_pending_flag_lost(self) -> None:
        async with self.sessions.begin() as session:
            state = await self.state(session)
            state.connection.sync_pending = False
            user = await session.get(User, 1)
            assert user
            self.remote["userTraffic"] = {"usedTrafficBytes": 123, "lifetimeUsedTrafficBytes": 123}
            confirmed = await synchronize_service_entitlement_locked(
                session, user, state.service, state.connection, self.panel
            )
            assert not confirmed and state.connection.sync_pending
            assert state.connection.usage_total_bytes == 123 and state.service.used_bytes == 123
            assert state.connection.replacement_order_id == state.order.id
            assert await service_squads(session, state.service) is None
            assert (
                UserServiceOut.from_orm_service(
                    state.service, state.connection, state.old_exit
                ).status
                == "pending"
            )
            sql_status = await session.scalar(
                service_query()
                .with_only_columns(business_status(datetime.now(UTC)))
                .where(type(state.service).id == state.service.id)
            )
            assert sql_status == "pending"
        assert self.remote["status"] == "ACTIVE"
        self.panel.update_user_status_on_panel.assert_not_awaited()
        self.panel.update_user_details_on_panel.assert_not_awaited()

    async def test_provision_delivery_and_subscription_cannot_bypass_gate(self) -> None:
        async with self.sessions.begin() as session:
            state = await self.state(session)
            state.connection.state = "error"
        await provision_service_identity(
            cast(sessionmaker, self.sessions), self.service.id, self.panel
        )
        await deliver_service_identity(
            cast(sessionmaker, self.sessions), self.service.id, self.panel
        )
        await ServiceProvisioningWorker(cast(sessionmaker, self.sessions), self.panel).tick()
        async with self.sessions() as session:
            with pytest.raises(ServiceConflict, match="replacement_in_progress"):
                await service_subscription(
                    session, user_id=1, service_id=self.service.id, panel=self.panel
                )
        assert not self.panel.mock_calls

    async def test_cancel_queues_restriction_without_bypassing_replacement_runner(self) -> None:
        async with self.sessions.begin() as session:
            state = await self.state(session)
            await request_service_revocation(
                session,
                service_id=self.service.id,
                user_id=1,
                actor_id=1,
                expected_revision=state.service.revision,
                idempotency_key="cancel",
                reason="Cancel during replacement",
            )
        await revoke_service_identity(
            cast(sessionmaker, self.sessions), self.service.id, self.panel
        )
        self.panel.delete_user_from_panel.assert_not_awaited()
        self.panel.update_user_status_on_panel.assert_not_awaited()
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.connection.state != "revoked" and state.connection.panel_user_uuid
            assert state.new_exit.hold_order_id and state.old_exit.service_id
            assert state.execution.status == "pending"

    async def test_unban_cannot_resume_during_replacement(self) -> None:
        self.remote["status"] = "DISABLED"
        async with self.sessions.begin() as session:
            await set_account_ban(session, user_id=1, actor_id=1, banned=False)
        async with self.sessions() as session:
            await synchronize_account_access(session, 1, self.panel)
        assert self.remote["status"] == "DISABLED"
        assert all(
            call.args[1] is False for call in self.panel.update_user_status_on_panel.await_args_list
        )

    async def test_delete_merge_and_generic_evidence_reject_live_hold(self) -> None:
        async with self.sessions.begin() as session:
            state = await self.state(session)
            with pytest.raises(ServiceConflict):
                await deletion_connections(session, 1)
            with pytest.raises(ServiceConflict, match="replacement_in_progress"):
                await merge_history(session, 1, 2)
            with pytest.raises(UserMergeConflictError):
                await merge_users(session, source_user_id=2, target_user_id=1)
            for resource in (state.old_exit, state.new_exit):
                with pytest.raises(ServiceConflict, match="replacement_in_progress"):
                    await record_exit_evidence(
                        session,
                        exit_id=resource.id,
                        actor_id=1,
                        action="verify",
                        command={"service_id": resource.service_id},
                    )

    async def test_replacement_is_not_superseded_and_offers_scoped_retry(self) -> None:
        async with self.sessions.begin() as session:
            state = await self.state(session)
            state.service.revision += 1
            await supersede_executions(session, state.service)
            assert state.execution.status == "pending"
            user = await session.get(User, 1)
            reason = retry_block_reason(state.service, state.connection, user, state.execution)
            assert reason is None
            out = ConsoleServiceOperationOut.from_record(
                state.order, state.execution, blocked=reason
            )
            assert out.replacement_progress and out.retryable and out.phase == "exit_replace"
            assert DedicatedExitOut.from_orm_exit(state.new_exit).hold_order_id == state.order.id

    async def test_database_rejects_bound_and_held_exit(self) -> None:
        async with self.sessions() as session:
            state = await self.state(session)
            state.old_exit.hold_order_id = state.order.id
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

    async def test_database_rejects_missing_replacement_progress(self) -> None:
        async with self.sessions() as session:
            state = await self.state(session)
            state.execution.replacement_progress = None
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()
