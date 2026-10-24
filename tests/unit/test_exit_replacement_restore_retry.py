"""Failed restoration may enforce restrictions, but never retry an ACTIVE grant."""

from datetime import UTC, datetime
from unittest.mock import patch

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.admin_console_exit_replacement_schemas import ConsoleExitReplacementEvidenceBody
from bot.services.panel_api_service import PanelApiService
from bot.services.service_exit_replacement import current_state
from bot.services.service_exit_replacement_commands import accept_evidence
from bot.services.service_exit_replacement_panel import ReplacementPatch
from config.service_plans import ServicePlanTerms
from db.dal.service_exit_replacement_dal import ReplacementState
from db.dal.service_quota_dal import apply_latest_quota
from db.dal.user_services_dal import save_plan
from db.models import User
from db.service_models import ServicePlan
from tests.unit.test_service_exit_replacement import DIGEST
from tests.unit.test_service_exit_replacement_runner import RunnerDatabaseTestCase


class FailedRestoreRetryTests(RunnerDatabaseTestCase):
    async def reach_restoring(self, *, active: bool) -> None:
        await self.tick()
        await self.attest()
        await self.confirm()
        for _ in range(3 if active else 2):
            await self.tick()
        assert (await self.progress()).stage == "restoring"
        assert self.remote["status"] == ("ACTIVE" if active else "DISABLED")

    async def reject_restore(self, *, status: str) -> None:
        async def unapplied(_panel: PanelApiService, command: ReplacementPatch) -> None:
            assert command.payload["status"] == status
            self.writes.append(command.payload)

        dispatch = self.dispatch.side_effect
        self.dispatch.side_effect = unapplied
        try:
            await self.tick()
        finally:
            self.dispatch.side_effect = dispatch
        async with self.sessions.begin() as session:
            state = await self.state(session)
            assert state.progress.pending_action == "restore"
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
                    idempotency_key="restore-not-applied",
                ),
            )
            assert state.execution.status == "failed"

    async def test_failed_active_grant_needs_explicit_retry(self) -> None:
        await self.reach_restoring(active=False)
        await self.reject_restore(status="ACTIVE")
        before = len(self.writes)
        async with self.sessions() as session:
            state = await self.state(session)
            attempts, attempted_at = state.execution.attempt_count, state.execution.attempted_at
        for _ in range(3):
            await self.tick()
        assert len(self.writes) == before and self.remote["status"] == "DISABLED"
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.execution.status == "failed" and state.progress.pending_action is None
            assert (state.execution.attempt_count, state.execution.attempted_at) == (
                attempts,
                attempted_at,
            )
            assert state.connection.replacement_order_id == state.order.id
            assert state.old_exit.hold_order_id == state.order.id

    async def test_lifted_ban_discards_restriction_before_dispatch_without_active_retry(
        self,
    ) -> None:
        await self.reach_restoring(active=True)
        async with self.sessions.begin() as session:
            user = await session.get(User, 1)
            assert user
            await session.execute(update(User).where(User.user_id == 1).values(is_banned=True))
        await self.reject_restore(status="DISABLED")
        before = len(self.writes)
        async with self.sessions() as session:
            state = await self.state(session)
            attempts, attempted_at = state.execution.attempt_count, state.execution.attempted_at

        async def lift_ban_after_marker(
            session: AsyncSession,
            service_id: str,
            operation_id: str | None = None,
            *,
            allow_terminal: bool = False,
        ) -> ReplacementState:
            if operation_id is not None:
                async with self.sessions.begin() as change:
                    pending = await self.state(change)
                    assert pending.progress.pending_action == "restore"
                    assert pending.execution.status == "unknown"
                    user = await change.get(User, 1)
                    assert user
                    await change.execute(
                        update(User).where(User.user_id == 1).values(is_banned=False)
                    )
            return await current_state(
                session, service_id, operation_id, allow_terminal=allow_terminal
            )

        with patch("bot.services.service_exit_replacement.current_state", lift_ban_after_marker):
            await self.tick()
        for _ in range(2):
            await self.tick()
        assert len(self.writes) == before and self.remote["status"] == "ACTIVE"
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.execution.status == "failed" and state.progress.pending_action is None
            assert state.execution.error_code == "service_not_deliverable"
            assert (state.execution.attempt_count, state.execution.attempted_at) == (
                attempts,
                attempted_at,
            )
            assert state.connection.replacement_order_id == state.order.id
            assert state.old_exit.hold_order_id == state.order.id

    async def test_relaxed_quota_does_not_retry_failed_active_grant(self) -> None:
        await self.reach_restoring(active=False)
        await self.reject_restore(status="ACTIVE")
        self.remote["userTraffic"] = {"usedTrafficBytes": 5000, "lifetimeUsedTrafficBytes": 5000}
        async with self.sessions.begin() as session:
            state = await self.state(session)
            self.sample(state)
            plan = await session.get(ServicePlan, self.plan.id)
            assert plan
            for quota in (1000, 10000):
                await save_plan(
                    session,
                    plan_id=plan.id,
                    expected_revision=plan.revision,
                    terms=ServicePlanTerms.model_validate(plan.terms | {"quota_bytes": quota}),
                    enabled=True,
                    actor_id=1,
                    quota_change_reason="Verified quota adjustment",
                )
                if quota == 1000:
                    await apply_latest_quota(session, state.service, state.connection)
            assert state.service.quota_bytes == 1000 and state.service.used_bytes == 5000
            attempts = state.execution.attempt_count
        before = len(self.writes)
        for _ in range(3):
            await self.tick()
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.service.quota_bytes == 10000 and state.service.used_bytes == 5000
            assert state.execution.status == "failed" and state.progress.pending_action is None
            assert state.execution.attempt_count == attempts
        assert len(self.writes) == before and self.remote["status"] == "DISABLED"
