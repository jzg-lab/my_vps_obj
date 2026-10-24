"""SQLite checks for failed replacement quota updates and retained period markers."""

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from bot.app.web.admin_console_exit_replacement_schemas import ConsoleExitReplacementEvidenceBody
from bot.services.panel_api_service import PanelApiService
from bot.services.service_change_sync import ServiceChangeWorker
from bot.services.service_exit_replacement_commands import accept_evidence
from bot.services.service_exit_replacement_panel import ReplacementPatch
from config.service_periods import as_utc
from config.service_plans import ServicePlanTerms
from db.dal.service_periods_dal import prepare_period
from db.dal.user_services_dal import save_plan
from db.service_models import ServicePlan, ServicePlanQuotaChange, ServiceUsagePeriod
from tests.unit.test_exit_replacement_lifecycle_races import at_time
from tests.unit.test_service_exit_replacement import DIGEST
from tests.unit.test_service_exit_replacement_runner import RunnerDatabaseTestCase
from tests.unit.test_user_services import sample_terms


class ExitReplacementFailedQuotaTests(RunnerDatabaseTestCase):
    async def start_unknown_stop(self) -> None:
        self.remote["userTraffic"] = {"usedTrafficBytes": 5000, "lifetimeUsedTrafficBytes": 5000}

        async def unapplied(_panel: PanelApiService, command: ReplacementPatch) -> None:
            assert command.payload["status"] == "DISABLED"
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
            assert state.execution.status == "unknown" and state.execution.attempted_at
            assert state.progress.stage == "stopping_old"
            assert state.progress.pending_action == "stop_old"
            assert state.service.used_bytes == 5000 and state.service.quota_bytes == 10000

    async def lower_quota(self) -> int:
        async with self.sessions.begin() as session:
            plan = await session.get(ServicePlan, self.plan.id)
            assert plan
            await save_plan(
                session,
                plan_id=plan.id,
                expected_revision=plan.revision,
                terms=ServicePlanTerms.model_validate(plan.terms | {"quota_bytes": 1000}),
                enabled=True,
                actor_id=1,
                quota_change_reason="Reduce below confirmed usage",
            )
        async with self.sessions() as session:
            change = await session.scalar(
                select(ServicePlanQuotaChange).where(ServicePlanQuotaChange.plan_id == self.plan.id)
            )
            assert change and change.quota_bytes == 1000
            revision: object = change.revision
            assert isinstance(revision, int)
            return revision

    async def poll_workers(self) -> None:
        worker = ServiceChangeWorker(cast(sessionmaker, self.sessions), self.panel)
        for _ in range(3):
            await self.sync(self.service, self.panel)
            await worker.tick()

    async def test_failed_stop_applies_latest_quota_before_restriction_check(self) -> None:
        await self.start_unknown_stop()
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
                    action="stop_old",
                    attempt=state.execution.attempt_count,
                    result="not_applied",
                    idempotency_key="stop-not-applied-before-quota",
                ),
            )
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.execution.status == "failed"
            assert state.execution.error_code == "exit_replacement_write_failed"
            assert state.progress.pending_action is None
        revision = await self.lower_quota()
        writes_before = len(self.writes)
        await self.poll_workers()
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.old_exit.service_id == state.service.id
            assert state.new_exit.hold_order_id == state.order.id
            assert state.connection.replacement_order_id == state.order.id
            assert state.service.used_bytes == 5000
            assert self.remote["status"] == "DISABLED", {
                "stage": state.progress.stage,
                "execution": state.execution.status,
                "error": state.execution.error_code,
                "service_quota": state.service.quota_bytes,
                "service_quota_revision": state.service.quota_revision,
                "latest_quota_revision": revision,
                "remote_cap": self.remote["trafficLimitBytes"],
                "later_writes": len(self.writes) - writes_before,
            }
            assert state.service.quota_bytes == 1000 and state.service.quota_revision == revision
        assert len(self.writes) > writes_before
        assert all(write["status"] == "DISABLED" for write in self.writes[writes_before:])

    async def test_pending_unknown_quota_change_does_not_replay_or_release_gate(self) -> None:
        await self.start_unknown_stop()
        await self.lower_quota()
        async with self.sessions() as session:
            state = await self.state(session)
            progress = state.progress
            attempts, attempted_at = state.execution.attempt_count, state.execution.attempted_at
        writes_before = len(self.writes)
        dispatch_calls = self.dispatch.call_count
        status_calls = self.panel.update_user_status_on_panel.call_count
        details_calls = self.panel.update_user_details_on_panel.call_count
        await self.poll_workers()
        assert len(self.writes) == writes_before and self.dispatch.call_count == dispatch_calls
        assert self.panel.update_user_status_on_panel.call_count == status_calls
        assert self.panel.update_user_details_on_panel.call_count == details_calls
        assert self.remote["status"] == "ACTIVE" and self.remote["trafficLimitBytes"] == 10000
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.execution.id == self.operation.id and state.execution.status == "unknown"
            assert state.progress == progress and state.progress.pending_action == "stop_old"
            assert (state.execution.attempt_count, state.execution.attempted_at) == (
                attempts,
                attempted_at,
            )
            assert state.connection.replacement_order_id == state.order.id
            assert state.old_exit.service_id == state.service.id
            assert state.old_exit.hold_order_id is None
            assert state.new_exit.service_id is None
            assert state.new_exit.hold_order_id == state.order.id
            assert state.service.used_bytes == 5000


class ExitReplacementBlockedPeriodTests(RunnerDatabaseTestCase):
    async def asyncSetUp(self) -> None:
        def monthly_terms(**changes: object) -> ServicePlanTerms:
            return sample_terms(**(changes | {"traffic_rule": "monthly"}))

        with patch("tests.unit.test_service_exit_replacement.sample_terms", monthly_terms):
            await super().asyncSetUp()
        self.remote["userTraffic"] = {"usedTrafficBytes": 5000, "lifetimeUsedTrafficBytes": 5000}

    async def test_expired_pending_cutover_only_disables_active_bound_exit(self) -> None:
        await self.tick()
        await self.attest()
        await self.confirm()
        for _ in range(3):
            await self.tick()
        assert self.remote["status"] == "ACTIVE"
        assert (await self.progress()).stage == "restoring"
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.service.cycle_ends_at
            boundary = as_utc(state.service.cycle_ends_at) + timedelta(seconds=1)
            expired = as_utc(state.service.expires_at) + timedelta(seconds=1)
            old_cycle = state.service.cycle_started_at
            assert boundary < as_utc(state.service.expires_at)
        with at_time(boundary):
            async with self.sessions.begin() as session:
                state = await self.state(session)
                self.sample(state)
                await prepare_period(session, state.service, state.connection, boundary)
                assert state.connection.cycle_cutover_bytes == 5000
        writes_before = len(self.writes)
        cap = self.remote["trafficLimitBytes"]
        worker = ServiceChangeWorker(cast(sessionmaker, self.sessions), self.panel)
        with at_time(expired):
            for _ in range(3):
                await self.sync(self.service, self.panel)
                await worker.tick()
            async with self.sessions() as session:
                state = await self.state(session)
                periods = list(await session.scalars(select(ServiceUsagePeriod)))
                assert len(periods) == 1 and periods[0].confirmed_at is None
                assert state.connection.cycle_cutover_bytes == 5000
                assert state.service.used_bytes == 5000
                assert state.connection.usage_total_bytes == 5000
                assert state.service.cycle_started_at == old_cycle
                assert state.progress.pending_action is None
                assert state.execution.status != "failed"
                assert state.execution.error_code == "panel_cycle_unconfirmed"
                assert state.connection.replacement_order_id == state.order.id
                assert state.new_exit.service_id == state.service.id
                assert state.old_exit.hold_order_id == state.order.id
        assert self.remote["status"] == "DISABLED"
        assert self.remote["trafficLimitBytes"] == cap == 10000
        assert len(self.writes) == writes_before + 1
        assert self.writes[-1]["status"] == "DISABLED"
        assert "trafficLimitBytes" not in self.writes[-1]
