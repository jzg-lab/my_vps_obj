"""SQLite lifecycle races with the real runner/DAL and the existing offline Panel."""

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Literal, Self
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.admin_console_exit_replacement_schemas import ExitReplacementReclaimBody
from bot.services.service_exit_replacement import current_state
from bot.services.service_exit_replacement_evidence import scoped_exit_evidence
from bot.services.service_exit_replacement_topology import read_replacement_topology
from config.service_changes import ServiceChange
from config.service_periods import as_utc
from config.service_plans import ServicePlanTerms
from db.dal.service_changes_dal import change_service
from db.dal.service_exit_replacement_dal import ReplacementState
from db.dal.service_operations_dal import retry_execution
from db.dal.service_periods_dal import prepare_period
from db.dal.user_services_dal import ServiceConflict, save_plan
from db.service_models import (
    ServiceOperationExecution,
    ServicePlan,
    ServicePlanQuotaChange,
    ServiceUsagePeriod,
    UserService,
)
from tests.unit.test_service_exit_replacement import DIGEST
from tests.unit.test_service_exit_replacement_runner import RunnerDatabaseTestCase
from tests.unit.test_user_services import sample_terms

Stage = Literal["stopping_old", "awaiting_confirmation", "switching", "restoring", "closing"]


@contextmanager
def at_time(now: datetime) -> Iterator[None]:
    """Advance execution and evidence-validation clocks together, without sleeps."""

    class Clock(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Self:
            return cls.fromtimestamp(now.timestamp(), tz=tz)

    with ExitStack() as stack:
        for module in (
            "bot.services.service_exit_replacement",
            "bot.services.service_exit_replacement_entitlements",
            "bot.services.service_operations",
            "bot.services.service_usage_sync",
            "config.service_exit_replacement",
            "db.dal.service_exit_replacement_dal",
            "db.dal.service_exit_replacement_completion_dal",
        ):
            stack.enter_context(patch(f"{module}.datetime", Clock))
        yield


class LifecycleRaceTestCase(RunnerDatabaseTestCase):
    async def pause_service(self, *, key: str = "race-pause") -> None:
        async with self.sessions.begin() as session:
            service = await session.get(UserService, self.service.id)
            assert service
            await change_service(
                session,
                service_id=service.id,
                user_id=1,
                actor_id=1,
                expected_revision=service.revision,
                idempotency_key=key,
                change=ServiceChange(action="pause"),
            )

    async def reach_stage(self, stage: Stage) -> None:
        if stage != "stopping_old":
            await self.tick()
            if stage == "closing":
                await self.pause_service()
                async with self.sessions.begin() as session:
                    state = await self.state(session)
                    topology = await read_replacement_topology(
                        session,
                        self.panel,
                        state.old_exit,
                        state.new_exit,
                        service_id=state.service.id,
                    )
                    assert topology.new_scope
                    await scoped_exit_evidence(
                        session,
                        self.panel,
                        exit_id=self.new_id,
                        actor_id=1,
                        body=ExitReplacementReclaimBody(
                            replacement_operation_id=self.operation.id,
                            service_id=self.service.id,
                            reclaim_purpose="candidate_cleanup",
                            expected_revision=state.new_exit.revision,
                            expected_operation_version=state.progress.version,
                            scope_fingerprint=topology.new_scope,
                            checked_at=datetime.now(UTC),
                            connections_stopped=True,
                            old_config_rejected=True,
                            evidence_digest=DIGEST,
                            idempotency_key="race-cleanup",
                        ),
                    )
            else:
                await self.attest()
                if stage in {"switching", "restoring"}:
                    await self.confirm()
                if stage == "restoring":
                    await self.tick()
                    await self.tick()
        assert (await self.progress()).stage == stage


class ExitReplacementLifecycleRaceTests(LifecycleRaceTestCase):
    async def test_pause_after_stop_marker_eventually_disables_old_identity(self) -> None:
        injected = False

        async def pause_after_marker(
            session: AsyncSession,
            service_id: str,
            operation_id: str | None = None,
            *,
            allow_terminal: bool = False,
        ) -> ReplacementState:
            nonlocal injected
            if operation_id is not None and not injected:
                async with self.sessions() as check:
                    execution = await check.get(ServiceOperationExecution, operation_id)
                    assert execution and execution.status == "unknown"
                    assert execution.replacement_progress is not None
                    assert execution.replacement_progress["pending_action"] == "stop_old"
                assert not self.writes
                await self.pause_service()
                injected = True
            return await current_state(
                session, service_id, operation_id, allow_terminal=allow_terminal
            )

        with patch("bot.services.service_exit_replacement.current_state", pause_after_marker):
            await self.tick()
        assert injected
        for _ in range(2):
            await self.sync(self.service, self.panel)
            await self.tick()
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.service.desired_status == "paused"
            assert state.progress.pending_action is None
            assert state.old_exit.service_id == self.service.id
            assert state.new_exit.hold_order_id == state.order.id
            assert state.connection.replacement_order_id == state.order.id
            assert self.remote["status"] == "DISABLED", {
                "remote": self.remote["status"],
                "execution": state.execution.status,
                "error": state.execution.error_code,
                "attempts": state.execution.attempt_count,
                "writes": self.writes,
            }
        assert self.writes and all(write["status"] == "DISABLED" for write in self.writes)

    async def test_quota_reduction_after_restore_marker_never_enables_exhausted_service(
        self,
    ) -> None:
        self.remote["userTraffic"] = {"usedTrafficBytes": 5000, "lifetimeUsedTrafficBytes": 5000}
        await self.reach_stage("restoring")
        assert self.remote["status"] == "DISABLED"
        injected = False

        async def lower_quota_after_marker(
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
                    assert execution.replacement_progress is not None
                    assert execution.replacement_progress["pending_action"] == "restore"
                    plan = await change.get(ServicePlan, self.plan.id)
                    assert plan
                    await save_plan(
                        change,
                        plan_id=plan.id,
                        expected_revision=plan.revision,
                        terms=ServicePlanTerms.model_validate(plan.terms | {"quota_bytes": 1000}),
                        enabled=True,
                        actor_id=1,
                        quota_change_reason="Reduce quota below confirmed usage",
                    )
                injected = True
            return await current_state(
                session, service_id, operation_id, allow_terminal=allow_terminal
            )

        before = len(self.writes)
        with patch("bot.services.service_exit_replacement.current_state", lower_quota_after_marker):
            await self.tick()
        assert injected
        async with self.sessions() as session:
            change = await session.scalar(
                select(ServicePlanQuotaChange).where(ServicePlanQuotaChange.plan_id == self.plan.id)
            )
            assert change and change.quota_bytes == 1000
        assert not any(write["status"] == "ACTIVE" for write in self.writes[before:]), self.writes[
            before:
        ]
        for _ in range(2):
            await self.tick()
        async with self.sessions() as session:
            state = await current_state(
                session, self.service.id, self.operation.id, allow_terminal=True
            )
            assert state.service.quota_bytes == 1000 and state.service.used_bytes == 5000
            assert state.connection.usage_total_bytes == 5000
            assert state.new_exit.service_id == self.service.id
            assert state.old_exit.hold_order_id == state.order.id
            assert as_utc(state.service.expires_at) == as_utc(self.service.expires_at)
        assert self.remote["status"] == "DISABLED"
        assert not any(write["status"] == "ACTIVE" for write in self.writes[before:])

    async def test_unknown_stop_remains_unresolved_after_pause(self) -> None:
        await self.check_unknown_after_pause("stopping_old")

    async def test_unknown_restore_remains_unresolved_after_pause(self) -> None:
        await self.check_unknown_after_pause("restoring")

    async def check_unknown_after_pause(self, stage: Stage) -> None:
        await self.reach_stage(stage)
        self.unknown = True
        await self.tick()
        async with self.sessions() as session:
            state = await self.state(session)
            action = state.progress.pending_action
            assert action == ("stop_old" if stage == "stopping_old" else "restore")
            attempts, attempted_at = state.execution.attempt_count, state.execution.attempted_at
            holds = (state.old_exit.hold_order_id, state.new_exit.hold_order_id)
        before = len(self.writes)
        await self.pause_service()
        for _ in range(2):
            await self.sync(self.service, self.panel)
            await self.tick()
        assert len(self.writes) == before
        async with self.sessions.begin() as session:
            state = await self.state(session)
            assert state.service.desired_status == "paused"
            assert state.execution.status == "unknown" and state.progress.pending_action == action
            assert (state.execution.attempt_count, state.execution.attempted_at) == (
                attempts,
                attempted_at,
            )
            assert (state.old_exit.hold_order_id, state.new_exit.hold_order_id) == holds
            assert state.connection.replacement_order_id == state.order.id
            with pytest.raises(ServiceConflict, match="exit_replacement_write_unknown"):
                await retry_execution(
                    session,
                    service_id=self.service.id,
                    operation_id=self.operation.id,
                    user_id=1,
                    actor_id=1,
                    expected_revision=state.service.revision,
                    idempotency_key="unknown-race-retry",
                )


class ExitReplacementMonthlyRaceTests(LifecycleRaceTestCase):
    async def asyncSetUp(self) -> None:
        def monthly_terms(**changes: object) -> ServicePlanTerms:
            return sample_terms(**(changes | {"traffic_rule": "monthly"}))

        with patch("tests.unit.test_service_exit_replacement.sample_terms", monthly_terms):
            await super().asyncSetUp()
        self.remote["userTraffic"] = {"usedTrafficBytes": 5000, "lifetimeUsedTrafficBytes": 5000}

    async def test_month_boundary_while_awaiting_confirmation_settles_without_internal_failure(
        self,
    ) -> None:
        await self.reach_stage("awaiting_confirmation")
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.service.cycle_ends_at
            boundary = as_utc(state.service.cycle_ends_at) + timedelta(seconds=1)
            assert boundary < as_utc(state.service.expires_at)
        before = len(self.writes)
        with at_time(boundary):
            for _ in range(3):
                await self.tick()
                async with self.sessions() as session:
                    state = await self.state(session)
                    assert state.execution.status != "failed", state.execution.error_code
                    assert state.progress.stage == "awaiting_confirmation"
            async with self.sessions() as session:
                state = await self.state(session)
                periods = list(await session.scalars(select(ServiceUsagePeriod)))
                assert len(periods) == 1 and periods[0].confirmed_at is not None
                assert periods[0].used_bytes == 5000 and periods[0].cutover_bytes == 5000
                assert state.connection.cycle_cutover_bytes is None
                assert state.connection.usage_total_bytes == 5000 and state.service.used_bytes == 0
                assert state.progress.confirmation_audit_id is None
                assert state.progress.binding_audit_id is None
                assert state.old_exit.service_id == self.service.id
                assert state.new_exit.hold_order_id == state.order.id
                assert state.connection.replacement_order_id == state.order.id
        assert self.remote["trafficLimitBytes"] == 15000
        assert self.remote["status"] == "DISABLED" and self.remote["activeInternalSquads"] == []
        assert self.writes[before:] and all(
            write["status"] == "DISABLED" for write in self.writes[before:]
        )

    async def test_expired_cutover_in_stopping_old_keeps_usage_and_cap(self) -> None:
        await self.check_expired_cutover("stopping_old")

    async def test_expired_cutover_in_awaiting_confirmation_keeps_usage_and_cap(self) -> None:
        await self.check_expired_cutover("awaiting_confirmation")

    async def test_expired_cutover_in_switching_keeps_usage_and_cap(self) -> None:
        await self.check_expired_cutover("switching")

    async def test_expired_cutover_in_restoring_keeps_usage_and_cap(self) -> None:
        await self.check_expired_cutover("restoring")

    async def test_expired_cutover_in_paused_closing_keeps_usage_and_cap(self) -> None:
        await self.check_expired_cutover("closing")

    async def check_expired_cutover(self, stage: Stage) -> None:
        await self.reach_stage(stage)
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.service.cycle_ends_at
            boundary = as_utc(state.service.cycle_ends_at) + timedelta(seconds=1)
            expired = as_utc(state.service.expires_at) + timedelta(seconds=1)
            original_cycle = state.service.cycle_started_at
            assert boundary < as_utc(state.service.expires_at)
        with at_time(boundary):
            async with self.sessions.begin() as session:
                state = await self.state(session)
                self.sample(state)
                await prepare_period(session, state.service, state.connection, boundary)
                assert state.connection.cycle_cutover_bytes == 5000
                assert state.service.used_bytes == 5000
                holds = (state.old_exit.hold_order_id, state.new_exit.hold_order_id)
        before = len(self.writes)
        with at_time(expired):
            for _ in range(4):
                await self.tick()
            async with self.sessions() as session:
                state = await current_state(
                    session, self.service.id, self.operation.id, allow_terminal=True
                )
                periods = list(await session.scalars(select(ServiceUsagePeriod)))
                assert len(periods) == 1 and periods[0].cutover_bytes == 5000
                actual = {
                    "stage": stage,
                    "used": state.service.used_bytes,
                    "cutover": state.connection.cycle_cutover_bytes,
                    "confirmed": periods[0].confirmed_at,
                    "cap": self.remote["trafficLimitBytes"],
                    "error": state.execution.error_code,
                }
                assert state.execution.error_code != "exit_replacement_sources_incomplete", actual
                assert periods[0].confirmed_at is None, actual
                assert state.connection.cycle_cutover_bytes == 5000, actual
                assert state.service.used_bytes == 5000, actual
                assert state.service.cycle_started_at == original_cycle
                assert state.connection.usage_total_bytes == 5000
                assert (state.old_exit.hold_order_id, state.new_exit.hold_order_id) == holds
                assert state.connection.replacement_order_id == state.order.id
        assert self.remote["status"] == "DISABLED"
        assert self.remote["trafficLimitBytes"] == 10000
        assert all(
            write["status"] == "DISABLED" and write.get("trafficLimitBytes", 10000) == 10000
            for write in self.writes[before:]
        )
