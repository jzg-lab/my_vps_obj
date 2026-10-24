"""SQLite regressions for restrictions after ACTIVE but before replacement finish."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import patch

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.app.web.admin_console_exit_replacement_schemas import ConsoleExitReplacementEvidenceBody
from bot.services.account_access_sync import synchronize_account_access
from bot.services.panel_api_service import PanelApiService
from bot.services.service_change_sync import ServiceChangeWorker
from bot.services.service_exit_replacement import current_state
from bot.services.service_exit_replacement_commands import accept_evidence
from bot.services.service_exit_replacement_panel import ReplacementPatch
from config.service_changes import ServiceChange
from db.dal.account_access_dal import enqueue_access_sync
from db.dal.service_changes_dal import change_service
from db.dal.service_exit_replacement_dal import ReplacementState
from db.models import User
from db.service_models import DedicatedExitAudit, ServiceOperationExecution
from tests.unit.test_service_exit_replacement import DIGEST
from tests.unit.test_service_exit_replacement_runner import RunnerDatabaseTestCase


class ExitReplacementRestoreRestrictionTests(RunnerDatabaseTestCase):
    async def restored_then_restricted(self, *, banned: bool) -> None:
        await self.tick()
        await self.attest()
        await self.confirm()
        for _ in range(3):
            await self.tick()
        assert self.remote["status"] == "ACTIVE"
        async with self.sessions.begin() as session:
            state = await self.state(session)
            assert state.progress.stage == "restoring" and state.progress.binding_audit_id
            assert state.progress.pending_action is None
            assert state.connection.replacement_order_id == state.order.id
            if banned:
                # Seed committed ban intent; PostgreSQL role-lock authorization is not under test.
                user = await session.get(User, 1)
                assert user
                await session.execute(update(User).where(User.user_id == 1).values(is_banned=True))
                await enqueue_access_sync(session, 1)
            else:
                await change_service(
                    session,
                    service_id=state.service.id,
                    user_id=1,
                    actor_id=1,
                    expected_revision=state.service.revision,
                    idempotency_key="pause-after-active",
                    change=ServiceChange(action="pause"),
                )

    async def unknown_disable(self) -> None:
        async def unapplied(_panel: PanelApiService, command: ReplacementPatch) -> None:
            assert command.payload["status"] == "DISABLED"
            async with self.sessions() as session:
                state = await self.state(session)
                assert state.execution.status == "unknown" and state.execution.attempted_at
                assert state.progress.pending_action == "restore"
            self.writes.append(command.payload)

        dispatch = self.dispatch.side_effect
        self.dispatch.side_effect = unapplied
        try:
            await self.tick()
        finally:
            self.dispatch.side_effect = dispatch
        assert self.remote["status"] == "ACTIVE"
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.execution.status == "unknown"
            assert state.progress.pending_action == "restore"

    async def poll_workers(self) -> None:
        worker = ServiceChangeWorker(cast(sessionmaker, self.sessions), self.panel)
        for _ in range(3):
            await self.sync(self.service, self.panel)
            async with self.sessions() as session:
                await synchronize_account_access(session, 1, self.panel)
            await worker.tick()

    async def assert_restricted(self, *, banned: bool, writes_before: int) -> None:
        async with self.sessions() as session:
            state = await current_state(
                session, self.service.id, self.operation.id, allow_terminal=True
            )
            user = await session.get(User, 1)
            assert user and user.is_banned is banned
            assert state.service.desired_status == ("active" if banned else "paused")
            assert state.new_exit.service_id == state.service.id
            assert state.new_exit.hold_order_id is None
            assert state.old_exit.service_id is None
            assert state.old_exit.hold_order_id == state.order.id
            assert state.progress.binding_audit_id and state.progress.pending_action is None
            assert self.remote["status"] == "DISABLED", {
                "stage": state.progress.stage,
                "execution": state.execution.status,
                "error": state.execution.error_code,
                "remote": self.remote["status"],
                "later_writes": len(self.writes) - writes_before,
                "gate_active": state.connection.replacement_order_id == state.order.id,
            }
        assert len(self.writes) > writes_before
        assert all(write["status"] == "DISABLED" for write in self.writes[writes_before:])

    async def test_known_unapplied_disable_after_pause_is_retried(self) -> None:
        await self.check_known_unapplied(banned=False)

    async def test_known_unapplied_disable_after_ban_is_retried(self) -> None:
        await self.check_known_unapplied(banned=True)

    async def check_known_unapplied(self, *, banned: bool) -> None:
        await self.restored_then_restricted(banned=banned)
        await self.unknown_disable()
        assert self.fingerprint
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
                    action="restore",
                    attempt=state.execution.attempt_count,
                    result="not_applied",
                    idempotency_key="disable-not-applied",
                ),
            )
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.execution.status == "failed"
            assert state.execution.error_code == "exit_replacement_write_failed"
            assert state.progress.stage == "restoring" and state.progress.pending_action is None
        writes_before = len(self.writes)
        await self.poll_workers()
        await self.assert_restricted(banned=banned, writes_before=writes_before)

    async def test_revision_change_before_pause_disable_dispatch_is_retried(self) -> None:
        await self.check_revision_change(banned=False)

    async def test_revision_change_before_ban_disable_dispatch_is_retried(self) -> None:
        await self.check_revision_change(banned=True)

    async def check_revision_change(self, *, banned: bool) -> None:
        await self.restored_then_restricted(banned=banned)
        writes_before = len(self.writes)
        async with self.sessions() as session:
            state = await self.state(session)
            attempts, attempted_at = state.execution.attempt_count, state.execution.attempted_at
        injected = False

        async def renew_after_marker(
            session: AsyncSession,
            service_id: str,
            operation_id: str | None = None,
            *,
            allow_terminal: bool = False,
        ) -> ReplacementState:
            nonlocal injected
            if operation_id is not None and not injected:
                async with self.sessions.begin() as change:
                    execution = await change.get(ServiceOperationExecution, operation_id)
                    assert execution and execution.status == "unknown"
                    assert execution.replacement_progress
                    assert execution.replacement_progress["pending_action"] == "restore"
                    assert execution.attempt_count == attempts + 1
                    assert len(self.writes) == writes_before
                    current = await self.state(change)
                    revision = current.service.revision
                    await change_service(
                        change,
                        service_id=service_id,
                        user_id=1,
                        actor_id=1,
                        expected_revision=revision,
                        idempotency_key="renew-after-disable-marker",
                        change=ServiceChange(
                            action="renew", days=1, price=Decimal("0.00"), currency="CNY"
                        ),
                    )
                    assert current.service.revision == revision + 1
                injected = True
            return await current_state(
                session, service_id, operation_id, allow_terminal=allow_terminal
            )

        with patch("bot.services.service_exit_replacement.current_state", renew_after_marker):
            await self.tick()
        assert injected and len(self.writes) == writes_before
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.execution.status == "failed"
            assert state.execution.error_code == "service_revision_changed"
            assert state.progress.stage == "restoring" and state.progress.pending_action is None
            assert (state.execution.attempt_count, state.execution.attempted_at) == (
                attempts,
                attempted_at,
            )
            audit = await session.scalar(
                select(DedicatedExitAudit).where(
                    DedicatedExitAudit.action == "replace_dispatch_skip"
                )
            )
            assert audit and audit.evidence["dispatched"] is False
            assert audit.evidence["action"] == "restore"
            assert audit.evidence["reason"] == "service_revision_changed"
        await self.poll_workers()
        await self.assert_restricted(banned=banned, writes_before=writes_before)

    async def test_unknown_pause_disable_is_not_replayed(self) -> None:
        await self.check_unknown_disable(banned=False)

    async def test_unknown_ban_disable_is_not_replayed(self) -> None:
        await self.check_unknown_disable(banned=True)

    async def check_unknown_disable(self, *, banned: bool) -> None:
        await self.restored_then_restricted(banned=banned)
        await self.unknown_disable()
        async with self.sessions() as session:
            state = await self.state(session)
            attempts, attempted_at = state.execution.attempt_count, state.execution.attempted_at
            progress = state.progress
        writes_before = len(self.writes)
        status_calls = self.panel.update_user_status_on_panel.call_count
        details_calls = self.panel.update_user_details_on_panel.call_count
        await self.poll_workers()
        assert len(self.writes) == writes_before and self.remote["status"] == "ACTIVE"
        assert self.panel.update_user_status_on_panel.call_count == status_calls
        assert self.panel.update_user_details_on_panel.call_count == details_calls
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.execution.status == "unknown" and state.progress == progress
            assert state.progress.pending_action == "restore"
            assert (state.execution.attempt_count, state.execution.attempted_at) == (
                attempts,
                attempted_at,
            )
            assert state.connection.replacement_order_id == state.order.id
            assert state.new_exit.service_id == state.service.id
            assert state.old_exit.hold_order_id == state.order.id
