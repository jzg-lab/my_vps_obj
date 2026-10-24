"""Offline runner transactions and fake transport; no PostgreSQL lock-concurrency claim."""

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.app.web.admin_console_exit_replacement_schemas import (
    ConsoleExitReplacementConfirmBody,
    ConsoleExitReplacementEvidenceBody,
    ExitReplacementReclaimBody,
    ExitReplacementVerifyBody,
)
from bot.services.panel_api_compat import PanelApiCompatibility
from bot.services.panel_api_service import PanelApiService
from bot.services.resource_preview_panel import digest
from bot.services.service_change_sync import synchronize_service_entitlement_locked
from bot.services.service_exit_replacement import _decision, current_state, run_exit_replacement
from bot.services.service_exit_replacement_commands import accept_evidence, confirm_replacement
from bot.services.service_exit_replacement_evidence import scoped_exit_evidence
from bot.services.service_exit_replacement_panel import ReplacementPatch
from bot.services.service_exit_replacement_topology import read_replacement_topology
from bot.services.service_exit_replacement_view import operation_output
from config.service_changes import ServiceChange
from config.service_exit_replacement import ReplacementProgress
from config.service_periods import as_utc, monthly_period
from db.dal.service_changes_dal import change_service
from db.dal.service_exit_replacement_dal import ReplacementState
from db.dal.service_operations_dal import retry_execution
from db.dal.service_periods_dal import prepare_period
from db.dal.user_services_dal import ServiceConflict, activate_service
from db.models import User
from db.service_models import (
    DedicatedExitAudit,
    ServiceOperationExecution,
    ServiceUsagePeriod,
    UserService,
)
from tests.unit.test_admin_console_resource_preview import (
    H1,
    I2,
    N2,
    P1,
    inventory_fixture,
    panel_fixture,
    uid,
)
from tests.unit.test_service_exit_replacement import DIGEST, ReplacementDatabaseTestCase


class RunnerDatabaseTestCase(ReplacementDatabaseTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.payloads = inventory_fixture()
        hosts = self.payloads["/hosts"]
        assert isinstance(hosts, list)
        hosts.append(
            {
                **hosts[0],
                "uuid": uid(402),
                "address": "192.0.2.2",
                "inbound": {"configProfileUuid": P1, "configProfileInboundUuid": I2},
                "nodes": [N2],
            }
        )
        inventory_panel, request = panel_fixture(self.payloads)
        self.panel._request.side_effect = request.side_effect
        self.panel.base_url = "https://panel.invalid/api"
        self.panel.get_panel_api_compatibility.return_value = PanelApiCompatibility.from_metadata(
            {"response": {"version": "3.4.5"}}
        )
        self.panel.panel_mutation_allowed.return_value = True
        self.panel.resolve_panel_user_reference.side_effect = lambda value, *_args, **_kwargs: value
        self.panel.get_user_by_uuid_lookup.side_effect = lambda _reference, **_kwargs: {
            "ok": True,
            "user": self.remote,
        }
        self.extra_remote_users: list[dict[str, object]] = []
        self.panel._get_all_panel_users_uncached.side_effect = lambda **_kwargs: [
            self.remote,
            *self.extra_remote_users,
        ]
        await inventory_panel.close()
        async with self.sessions.begin() as session:
            state = await self.state(session)
            topology = await read_replacement_topology(
                session, self.panel, state.old_exit, state.new_exit, service_id=state.service.id
            )
            assert topology.public.coverage == "complete", topology.public.block_reasons
            fingerprint = topology.public.resource_fingerprint
            assert fingerprint
            self.fingerprint = fingerprint
            self.request = self.request.model_copy(
                update={"resource_fingerprint": self.fingerprint}
            )
            state.order.request = {
                "service_id": self.service.id,
                "replacement": self.request.model_dump(mode="json"),
            }
            audit = await session.scalar(
                select(DedicatedExitAudit).where(DedicatedExitAudit.action == "replace_reserve")
            )
            assert audit
            audit.evidence = audit.evidence | {"resource_fingerprint": self.fingerprint}
        self.writes: list[dict[str, object]] = []
        self.unknown = False

        async def dispatch(_panel: PanelApiService, command: ReplacementPatch) -> str | None:
            async with self.sessions() as session:
                execution = await session.get(ServiceOperationExecution, self.operation.id)
                assert execution and execution.status == "unknown" and execution.attempted_at
            self.writes.append(command.payload)
            self.remote.update(
                {key: value for key, value in command.payload.items() if key != "id"}
            )
            return None if self.unknown else digest(command.payload)

        self.dispatch = AsyncMock(side_effect=dispatch)
        patcher = patch("bot.services.service_exit_replacement.dispatch_patch", self.dispatch)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def tick(self) -> None:
        await run_exit_replacement(cast(sessionmaker, self.sessions), self.service.id, self.panel)

    async def progress(self) -> ReplacementProgress:
        async with self.sessions() as session:
            state = await current_state(
                session, self.service.id, self.operation.id, allow_terminal=True
            )
            return state.progress

    async def attest(self, purpose: str = "stop", *, key: str | None = None) -> None:
        async with self.sessions.begin() as session:
            state = await current_state(
                session, self.service.id, self.operation.id, allow_terminal=True
            )
            topology = await read_replacement_topology(
                session,
                self.panel,
                state.old_exit,
                state.new_exit,
                service_id=state.service.id,
                candidate_required=purpose != "close",
            )
            now = datetime.now(UTC)
            body = ConsoleExitReplacementEvidenceBody.model_validate(
                {
                    "operation_id": self.operation.id,
                    "expected_operation_version": state.progress.version,
                    "resource_fingerprint": topology.public.resource_fingerprint,
                    "checked_at": now,
                    "evidence_digest": DIGEST,
                    "purpose": purpose,
                    "authorization_removed": True,
                    "connections_stopped": True,
                    "old_config_rejected": True,
                    "usage_observed_at": now,
                    "usage_total_bytes": state.connection.usage_total_bytes,
                    "usage_raw_bytes": state.connection.usage_raw_bytes,
                    "usage_lifetime_offset": state.connection.usage_lifetime_offset or 0,
                    "usage_evidence_digest": DIGEST,
                    "idempotency_key": key or f"attest:{purpose}",
                }
            )
            await accept_evidence(
                session, self.panel, service_id=self.service.id, actor_id=1, body=body
            )

    async def confirm(self, *, key_suffix: str = "") -> None:
        async with self.sessions.begin() as session:
            state = await self.state(session)
            topology = await read_replacement_topology(
                session, self.panel, state.old_exit, state.new_exit, service_id=state.service.id
            )
            assert topology.new_scope
            await scoped_exit_evidence(
                session,
                self.panel,
                exit_id=self.new_id,
                actor_id=1,
                body=ExitReplacementVerifyBody(
                    replacement_operation_id=self.operation.id,
                    service_id=self.service.id,
                    expected_revision=state.new_exit.revision,
                    expected_operation_version=state.progress.version,
                    scope_fingerprint=topology.new_scope,
                    checked_at=datetime.now(UTC),
                    observed_ip="192.0.2.2",
                    fixed=True,
                    exclusive=True,
                    evidence_digest=DIGEST,
                    idempotency_key="verify" + key_suffix,
                ),
            )
        async with self.sessions.begin() as session:
            state = await self.state(session)
            assert state.progress.stop_audit_id and state.progress.verification_audit_id
            await confirm_replacement(
                session,
                self.panel,
                service_id=self.service.id,
                actor_id=1,
                body=ConsoleExitReplacementConfirmBody(
                    user_id=1,
                    operation_id=self.operation.id,
                    expected_revision=state.service.revision,
                    expected_operation_version=state.progress.version,
                    expected_old_exit_revision=state.old_exit.revision,
                    expected_new_exit_revision=state.new_exit.revision,
                    expected_resource_fingerprint=self.fingerprint,
                    old_stop_audit_id=state.progress.stop_audit_id,
                    candidate_verify_audit_id=state.progress.verification_audit_id,
                    confirm_replace_and_request_restore=True,
                    idempotency_key="confirm" + key_suffix,
                ),
            )


class ExitReplacementRunnerTests(RunnerDatabaseTestCase):
    async def test_known_unapplied_stop_does_not_block_later_pause(self) -> None:
        await self.check_known_unapplied_stop_restriction(banned=False)

    async def test_known_unapplied_stop_does_not_block_later_ban(self) -> None:
        await self.check_known_unapplied_stop_restriction(banned=True)

    async def check_known_unapplied_stop_restriction(self, *, banned: bool) -> None:
        async def unapplied(_panel: PanelApiService, command: ReplacementPatch) -> None:
            self.writes.append(command.payload)

        dispatch = self.dispatch.side_effect
        self.dispatch.side_effect = unapplied
        await self.tick()
        self.dispatch.side_effect = dispatch
        assert self.remote["status"] == "ACTIVE"
        async with self.sessions.begin() as session:
            state = await self.state(session)
            await accept_evidence(
                session,
                self.panel,
                service_id=self.service.id,
                actor_id=1,
                body=ConsoleExitReplacementEvidenceBody(
                    operation_id=self.operation.id,
                    expected_operation_version=state.progress.version,
                    resource_fingerprint=self.fingerprint,
                    checked_at=datetime.now(UTC),
                    evidence_digest=DIGEST,
                    purpose="resolve_write",
                    action="stop_old",
                    attempt=1,
                    result="not_applied",
                    idempotency_key="stop-not-applied",
                ),
            )
            assert state.execution.status == "failed" and state.progress.pending_action is None
        # A failed replacement still needs explicit retry while no new restriction exists.
        await self.tick()
        assert len(self.writes) == 1
        async with self.sessions.begin() as session:
            state = await self.state(session)
            if banned:
                user = await session.get(User, 1)
                assert user
                await session.execute(update(User).where(User.user_id == 1).values(is_banned=True))
            else:
                await change_service(
                    session,
                    service_id=self.service.id,
                    user_id=1,
                    actor_id=1,
                    expected_revision=state.service.revision,
                    idempotency_key="pause-after-failed-stop",
                    change=ServiceChange(action="pause"),
                )
        for _ in range(2):
            await self.sync(self.service, self.panel)
            await self.tick()
        assert self.remote["status"] == "DISABLED"
        assert len(self.writes) == 2 and self.writes[-1]["status"] == "DISABLED"
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.progress.pending_action is None
            assert state.execution.attempt_count == 2
            assert state.old_exit.service_id == self.service.id
            assert state.new_exit.hold_order_id == state.order.id
            assert state.connection.replacement_order_id == state.order.id

    async def test_restore_rechecks_original_entitlements_and_does_not_override_metering(
        self,
    ) -> None:
        await self.tick()
        await self.attest()
        await self.confirm()
        await self.tick()
        await self.tick()
        assert (await self.progress()).stage == "restoring"
        for reason in (
            "service_paused",
            "service_expired",
            "service_exhausted",
            "service_not_started",
            "service_not_deliverable",
        ):
            with self.subTest(reason=reason):
                async with self.sessions() as session:
                    state = await self.state(session)
                    if reason == "service_paused":
                        state.service.desired_status = "paused"
                    elif reason == "service_expired":
                        state.service.starts_at = datetime.now(UTC) - timedelta(days=2)
                        state.service.expires_at = datetime.now(UTC) - timedelta(days=1)
                        self.remote["expireAt"] = state.service.expires_at.isoformat()
                    elif reason == "service_exhausted":
                        state.service.used_bytes = state.service.quota_bytes
                    elif reason == "service_not_started":
                        state.service.starts_at = datetime.now(UTC) + timedelta(days=1)
                    else:
                        state.connection.last_error = "service_delivery_pending"
                    decision = await _decision(session, self.panel, state)
                    if decision is not None:
                        assert decision[0] == "restore" and decision[1]["status"] == "DISABLED"
                    else:
                        assert state.progress.restore_result == "restricted"
                        assert reason in state.progress.restore_block_reasons
                self.remote["expireAt"] = self.service.expires_at.isoformat()
        self.remote["userTraffic"] = {"usedTrafficBytes": True, "lifetimeUsedTrafficBytes": 0}
        async with self.sessions() as session:
            state = await self.state(session)
            with pytest.raises(ServiceConflict, match="usage_unconfirmed"):
                await _decision(session, self.panel, state)
            assert state.connection.replacement_order_id == state.order.id
        assert not any(write["status"] == "ACTIVE" for write in self.writes)

    async def test_ban_after_durable_marker_prevents_dispatch_without_counting_an_attempt(
        self,
    ) -> None:
        await self.tick()
        await self.attest()
        await self.confirm()
        await self.tick()
        await self.tick()
        assert (await self.progress()).stage == "restoring"
        async with self.sessions() as session:
            state = await self.state(session)
            attempts, attempted_at = state.execution.attempt_count, state.execution.attempted_at
        writes = len(self.writes)

        async def ban_between_transactions(
            session: AsyncSession,
            service_id: str,
            operation_id: str | None = None,
            *,
            allow_terminal: bool = False,
        ) -> ReplacementState:
            if operation_id is not None:
                async with self.sessions.begin() as change:
                    user = await change.get(User, 1)
                    assert user
                    await change.execute(
                        update(User).where(User.user_id == 1).values(is_banned=True)
                    )
            return await current_state(
                session, service_id, operation_id, allow_terminal=allow_terminal
            )

        with patch("bot.services.service_exit_replacement.current_state", ban_between_transactions):
            await self.tick()
        assert len(self.writes) == writes
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.execution.status == "failed"
            assert state.execution.error_code == "service_not_deliverable"
            assert state.execution.attempt_count == attempts
            assert state.execution.attempted_at == attempted_at
            assert state.progress.pending_action is None
            assert state.old_exit.hold_order_id == state.order.id
            audit = await session.scalar(
                select(DedicatedExitAudit).where(
                    DedicatedExitAudit.action == "replace_dispatch_skip"
                )
            )
            assert audit and audit.evidence["dispatched"] is False
        for _ in range(2):
            await self.tick()
        assert len(self.writes) == writes

    async def test_expiry_after_monthly_marker_discards_unsent_allowance(self) -> None:
        self.remote["userTraffic"] = {"usedTrafficBytes": 5000, "lifetimeUsedTrafficBytes": 5000}
        await self.tick()
        await self.attest()
        await self.confirm()
        await self.tick()
        await self.tick()
        async with self.sessions.begin() as session:
            state = await self.state(session)
            assert state.progress.stage == "restoring"
            state.service.terms = state.service.terms | {"traffic_rule": "monthly"}
            state.service.cycle_started_at, state.service.cycle_ends_at = monthly_period(
                state.service.starts_at, state.service.starts_at
            )
            boundary = as_utc(state.service.cycle_ends_at) + timedelta(seconds=1)
            await prepare_period(session, state.service, state.connection, boundary)
            assert state.connection.cycle_cutover_bytes == 5000
            expires = as_utc(state.service.expires_at)
            attempts = state.execution.attempt_count
        writes = len(self.writes)
        with patch(
            "bot.services.service_exit_replacement_entitlements.datetime", wraps=datetime
        ) as clock:
            clock.now.return_value = expires - timedelta(seconds=1)

            async def expire_after_marker(
                session: AsyncSession,
                service_id: str,
                operation_id: str | None = None,
                *,
                allow_terminal: bool = False,
            ) -> ReplacementState:
                if operation_id is not None:
                    clock.now.return_value = expires + timedelta(seconds=1)
                return await current_state(
                    session, service_id, operation_id, allow_terminal=allow_terminal
                )

            with patch("bot.services.service_exit_replacement.current_state", expire_after_marker):
                await self.tick()
        assert len(self.writes) == writes
        assert self.remote["status"] == "DISABLED" and self.remote["trafficLimitBytes"] == 10000
        async with self.sessions() as session:
            state = await self.state(session)
            period = await session.scalar(select(ServiceUsagePeriod))
            assert period and period.confirmed_at is None
            assert state.execution.error_code == "panel_cycle_unconfirmed"
            assert state.execution.attempt_count == attempts
            assert state.progress.pending_action is None
            assert state.service.used_bytes == state.connection.cycle_cutover_bytes == 5000
            assert state.old_exit.hold_order_id == state.order.id
            assert state.new_exit.service_id == state.service.id
            assert state.connection.replacement_order_id == state.order.id

    async def test_remote_success_with_local_receipt_failure_remains_unknown_without_replay(
        self,
    ) -> None:
        with patch(
            "bot.services.service_exit_replacement.resolve_replacement_write",
            AsyncMock(side_effect=RuntimeError("FAKE_PRIVATE_RECEIPT")),
        ):
            await self.tick()
        assert self.remote["activeInternalSquads"] == []
        assert len(self.writes) == 1
        await self.tick()
        assert len(self.writes) == 1
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.execution.status == "unknown" and state.execution.attempt_count == 1
            assert state.progress.pending_action == "stop_old"
            assert state.old_exit.service_id == state.service.id
            assert state.new_exit.hold_order_id == state.order.id
            assert "FAKE_PRIVATE_RECEIPT" not in str(state.execution.error_code)

    async def test_preflight_exception_is_visible_and_retry_uses_same_operation(self) -> None:
        lookup = self.panel.get_user_by_uuid_lookup.side_effect
        self.panel.get_user_by_uuid_lookup.side_effect = RuntimeError("FAKE_PRIVATE_SOURCE")
        await self.tick()
        self.panel.get_user_by_uuid_lookup.side_effect = lookup
        async with self.sessions.begin() as session:
            state = await self.state(session)
            assert state.execution.status == "failed"
            assert state.execution.error_code == "exit_replacement_sources_incomplete"
            assert state.execution.attempt_count == 0 and state.execution.attempted_at is None
            _, order, duplicate = await retry_execution(
                session,
                service_id=self.service.id,
                operation_id=self.operation.id,
                user_id=1,
                actor_id=1,
                expected_revision=state.service.revision,
                idempotency_key="retry-source",
            )
            assert not duplicate and order.snapshot["operation_id"] == self.operation.id
        await self.tick()
        assert len(self.writes) == 1
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.execution.id == self.operation.id and state.execution.attempt_count == 1

    async def test_late_usage_blocks_binding_until_new_stop_and_confirmation(self) -> None:
        await self.tick()
        await self.attest()
        await self.confirm()
        self.remote["userTraffic"] = {"usedTrafficBytes": 1, "lifetimeUsedTrafficBytes": 1}
        await self.tick()
        await self.tick()
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.execution.status == "failed"
            assert state.execution.error_code == "exit_replacement_usage_unconfirmed"
            assert state.old_exit.service_id == state.service.id
            assert state.new_exit.hold_order_id == state.order.id
            assert state.service.used_bytes == 1
        await self.attest(key="stop-refreshed")
        assert (await self.progress()).confirmation_audit_id is None
        await self.confirm(key_suffix="-refreshed")
        for _ in range(3):
            await self.tick()
        assert (await self.progress()).stage == "completed"
        async with self.sessions() as session:
            state = await current_state(
                session, self.service.id, self.operation.id, allow_terminal=True
            )
            assert state.service.used_bytes == 1 and state.connection.usage_total_bytes == 1

    async def test_cancelled_archive_without_connection_blocks_real_source_query(self) -> None:
        async with self.sessions.begin() as session:
            session.add(
                UserService(
                    id="f" * 32,
                    user_id=None,
                    plan_id=self.plan.id,
                    plan_revision=self.service.plan_revision,
                    terms=self.service.terms,
                    quota_bytes=self.service.quota_bytes,
                    starts_at=self.service.starts_at,
                    expires_at=self.service.expires_at,
                    desired_status="cancelled",
                    created_at=datetime.now(UTC),
                )
            )
        async with self.sessions() as session:
            state = await self.state(session)
            topology = await read_replacement_topology(
                session, self.panel, state.old_exit, state.new_exit, service_id=state.service.id
            )
            assert topology.public.coverage == "partial"
            assert "exit_replacement_archived_scope_unconfirmed" in topology.public.block_reasons
            assert topology.public.resource_fingerprint is None
        await self.tick()
        assert not self.writes

    async def test_evidence_projection_keeps_observation_time_before_recording(self) -> None:
        await self.tick()
        await self.attest()
        await self.confirm()
        recorded_at = datetime.now(UTC)
        async with self.sessions.begin() as session:
            state = await self.state(session)
            stop = await session.get(DedicatedExitAudit, state.progress.stop_audit_id)
            verify = await session.get(DedicatedExitAudit, state.progress.verification_audit_id)
            assert stop and verify
            stop_time, verify_time = stop.evidence["stopped_at"], verify.evidence["checked_at"]
            assert isinstance(stop_time, str) and isinstance(verify_time, str)
            stopped_at = datetime.fromisoformat(stop_time)
            checked_at = datetime.fromisoformat(verify_time)
            assert stopped_at < recorded_at and checked_at < recorded_at
            stop.created_at = verify.created_at = recorded_at
            topology = await read_replacement_topology(
                session, self.panel, state.old_exit, state.new_exit, service_id=state.service.id
            )
            output = await operation_output(session, state, topology)
            assert output.old_stop and output.candidate_verification
            assert output.old_stop.observed_at == stopped_at
            assert output.candidate_verification.observed_at == checked_at
            assert output.old_stop.provenance == "administrator"
            assert output.candidate_verification.provenance == "administrator"

    async def test_full_loop_preserves_rights_identity_and_retains_old_until_explicit_reclaim(
        self,
    ) -> None:
        original = {
            key: self.remote[key] for key in ("uuid", "username", "description", "expireAt")
        }
        await self.tick()
        assert len(self.writes) == 1 and self.remote["activeInternalSquads"] == []
        await self.tick()
        assert len(self.writes) == 1
        await self.attest()
        await self.confirm()
        assert (await self.progress()).restore_result == "pending"
        for _ in range(4):
            await self.tick()
        progress = await self.progress()
        assert progress.stage == "completed" and progress.restore_result == "enabled"
        assert len(self.writes) == 3
        assert all(
            self.remote[key] == value for key, value in original.items() if key != "expireAt"
        )
        async with self.sessions.begin() as session:
            state = await current_state(
                session, self.service.id, self.operation.id, allow_terminal=True
            )
            assert state.connection.replacement_order_id is None
            assert (
                state.old_exit.hold_order_id == state.order.id
                and state.new_exit.service_id == self.service.id
            )
            assert (
                state.service.terms == self.service.terms
                and state.service.used_bytes == self.service.used_bytes
            )
            topology = await read_replacement_topology(
                session, self.panel, state.old_exit, state.new_exit, service_id=state.service.id
            )
            assert topology.old_scope
            command = ExitReplacementReclaimBody(
                replacement_operation_id=self.operation.id,
                service_id=self.service.id,
                reclaim_purpose="retained_old",
                expected_revision=state.old_exit.revision,
                expected_operation_version=state.progress.version,
                scope_fingerprint=topology.old_scope,
                checked_at=datetime.now(UTC),
                connections_stopped=True,
                old_config_rejected=True,
                evidence_digest=DIGEST,
                idempotency_key="reclaim",
            )
            _, audit, duplicate = await scoped_exit_evidence(
                session, self.panel, exit_id=self.old_id, actor_id=1, body=command
            )
            assert (
                not duplicate
                and audit.action == "replace_reclaim"
                and state.old_exit.hold_order_id is None
            )
        # Duplicate after allocation cannot release the subsequent customer's binding.
        async with self.sessions.begin() as session:
            second, _, _ = await activate_service(
                session,
                user_id=2,
                actor_id=1,
                plan_id=self.plan.id,
                expected_revision=1,
                idempotency_key="reuse",
                exit_id=self.old_id,
            )
        async with self.sessions.begin() as session:
            resource, _, duplicate = await scoped_exit_evidence(
                session, self.panel, exit_id=self.old_id, actor_id=1, body=command
            )
            assert duplicate and resource.service_id == second.id

    async def test_unknown_write_cannot_be_resolved_by_readback_retry_pause_or_ordinary_sync(
        self,
    ) -> None:
        self.unknown = True
        await self.tick()
        assert (await self.progress()).pending_action == "stop_old"
        async with self.sessions.begin() as session:
            state = await self.state(session)
            state.service.desired_status = "paused"
            user = await session.get(User, 1)
            assert user
            await synchronize_service_entitlement_locked(
                session, user, state.service, state.connection, self.panel
            )
            with pytest.raises(ServiceConflict, match="write_unknown"):
                await retry_execution(
                    session,
                    service_id=self.service.id,
                    operation_id=self.operation.id,
                    user_id=1,
                    actor_id=1,
                    expected_revision=state.service.revision,
                    idempotency_key="retry",
                )
        await self.tick()
        assert len(self.writes) == 1
        self.panel.update_user_status_on_panel.assert_not_awaited()
        async with self.sessions.begin() as session:
            state = await self.state(session)
            await accept_evidence(
                session,
                self.panel,
                service_id=self.service.id,
                actor_id=1,
                body=ConsoleExitReplacementEvidenceBody(
                    operation_id=self.operation.id,
                    expected_operation_version=state.progress.version,
                    resource_fingerprint=self.fingerprint,
                    checked_at=datetime.now(UTC),
                    evidence_digest=DIGEST,
                    purpose="resolve_write",
                    action="stop_old",
                    attempt=1,
                    result="applied",
                    idempotency_key="receipt",
                ),
            )
        assert (await self.progress()).pending_action is None

    async def test_bad_candidate_cleanup_requires_pause_then_stop_evidence_then_explicit_release(
        self,
    ) -> None:
        await self.tick()
        async with self.sessions.begin() as session:
            state = await self.state(session)
            topology = await read_replacement_topology(
                session, self.panel, state.old_exit, state.new_exit, service_id=state.service.id
            )
            assert topology.new_scope
            values = {
                "replacement_operation_id": self.operation.id,
                "service_id": self.service.id,
                "reclaim_purpose": "candidate_cleanup",
                "expected_revision": state.new_exit.revision,
                "expected_operation_version": state.progress.version,
                "scope_fingerprint": topology.new_scope,
                "checked_at": datetime.now(UTC),
                "connections_stopped": True,
                "old_config_rejected": True,
                "evidence_digest": DIGEST,
                "idempotency_key": "cleanup",
            }
            with pytest.raises(ServiceConflict, match="pause_required"):
                await scoped_exit_evidence(
                    session,
                    self.panel,
                    exit_id=self.new_id,
                    actor_id=1,
                    body=ExitReplacementReclaimBody.model_validate(values),
                )
            state.service.desired_status = "paused"
            await session.flush()
            await scoped_exit_evidence(
                session,
                self.panel,
                exit_id=self.new_id,
                actor_id=1,
                body=ExitReplacementReclaimBody.model_validate(values),
            )
            assert state.new_exit.hold_order_id == state.order.id
        await self.tick()
        await self.attest("close")
        async with self.sessions.begin() as session:
            state = await current_state(
                session, self.service.id, self.operation.id, allow_terminal=True
            )
            assert state.progress.stage == "closed" and state.old_exit.service_id == self.service.id
            assert (
                state.connection.state == "ready" and state.new_exit.hold_order_id == state.order.id
            )
            values.update(
                expected_operation_version=state.progress.version,
                idempotency_key="release",
                checked_at=datetime.now(UTC),
            )
            await scoped_exit_evidence(
                session,
                self.panel,
                exit_id=self.new_id,
                actor_id=1,
                body=ExitReplacementReclaimBody.model_validate(values),
            )
            assert state.new_exit.hold_order_id is None and state.service.desired_status == "paused"

    async def test_ban_before_restore_completes_switch_but_remains_restricted(self) -> None:
        await self.tick()
        await self.attest()
        await self.confirm()
        async with self.sessions.begin() as session:
            user = await session.get(User, 1)
            assert user
            await session.execute(update(User).where(User.user_id == 1).values(is_banned=True))
        for _ in range(4):
            await self.tick()
        progress = await self.progress()
        assert progress.stage == "completed" and progress.restore_result == "restricted"
        assert progress.restore_block_reasons == ["account_banned"]
        assert not any(write["status"] == "ACTIVE" for write in self.writes)

    async def test_disabled_old_path_is_complete_but_disabled_candidate_is_not(self) -> None:
        nodes = self.payloads["/nodes"]
        assert isinstance(nodes, list)
        nodes[0]["isDisabled"] = True
        hosts = self.payloads["/hosts"]
        assert isinstance(hosts, list) and hosts[0]["uuid"] == H1
        hosts[0]["isDisabled"] = True
        async with self.sessions() as session:
            state = await self.state(session)
            scope = await read_replacement_topology(
                session, self.panel, state.old_exit, state.new_exit, service_id=state.service.id
            )
            assert scope.public.coverage == "complete" and scope.old_scope
            nodes[1]["isDisabled"] = True
            blocked = await read_replacement_topology(
                session, self.panel, state.old_exit, state.new_exit, service_id=state.service.id
            )
            assert (
                blocked.public.coverage == "partial"
                and blocked.old_scope
                and blocked.new_scope is None
            )

    async def test_other_remote_identity_conflict_blocks_without_exporting_secrets(self) -> None:
        self.extra_remote_users.append(
            {"uuid": "other", "activeInternalSquads": [uid(2)], "password": "PRIVATE_PASSWORD"}
        )
        async with self.sessions() as session:
            state = await self.state(session)
            scope = await read_replacement_topology(
                session, self.panel, state.old_exit, state.new_exit, service_id=state.service.id
            )
            assert "exit_replacement_authorization_conflict" in scope.public.block_reasons
            result = await operation_output(session, state, scope)
            assert "PRIVATE_PASSWORD" not in result.model_dump_json()
        await self.tick()
        assert not self.writes

    async def test_other_group_on_same_profile_is_possible_reload_and_changes_fingerprint(
        self,
    ) -> None:
        group_id, inbound_id = uid(4), uid(104)
        groups = self.payloads["/internal-squads"]
        profiles = self.payloads["/config-profiles"]
        assert isinstance(groups, dict) and isinstance(profiles, dict)
        groups["total"] += 1
        groups["internalSquads"].append(
            {"uuid": group_id, "name": "Other scope", "inbounds": [{"uuid": inbound_id}]}
        )
        profiles["configProfiles"][0]["inbounds"].append(
            {"uuid": inbound_id, "profileUuid": P1, "tag": "other"}
        )
        self.extra_remote_users.append(
            {"uuid": "other", "activeInternalSquads": [group_id], "password": "PRIVATE_PASSWORD"}
        )
        async with self.sessions() as session:
            state = await self.state(session)
            topology = await read_replacement_topology(
                session, self.panel, state.old_exit, state.new_exit, service_id=state.service.id
            )
            assert topology.public.coverage == "complete"
            assert any(
                impact.kind == "possible_reload"
                and impact.service_id is None
                and impact.group_ids == [group_id]
                for impact in topology.public.impacts
            )
            assert "PRIVATE_PASSWORD" not in topology.public.model_dump_json()
            self.extra_remote_users.clear()
            refreshed = await read_replacement_topology(
                session, self.panel, state.old_exit, state.new_exit, service_id=state.service.id
            )
            assert topology.public.resource_fingerprint != refreshed.public.resource_fingerprint
