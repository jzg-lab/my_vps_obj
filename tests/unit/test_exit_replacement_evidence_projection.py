"""Real SQLite replacement evidence projections; Panel transport stays offline."""

from copy import deepcopy
from typing import cast

from sqlalchemy import event
from sqlalchemy.orm import sessionmaker

from bot.app.web.admin_console_exit_replacement_schemas import (
    ConsoleExitReplacementOut,
    ConsoleExitReplacementQuery,
)
from bot.services.service_exit_replacement import current_state
from bot.services.service_exit_replacement_view import replacement_view
from bot.services.service_usage_sync import synchronize_service_usage
from db.service_models import DedicatedExitAudit
from tests.unit.test_service_exit_replacement_runner import RunnerDatabaseTestCase


class ExitReplacementEvidenceProjectionTests(RunnerDatabaseTestCase):
    async def read_projection(self) -> ConsoleExitReplacementOut:
        statements: list[str] = []
        remote_before = deepcopy(self.remote)
        writes_before = deepcopy(self.writes)
        mutations = (
            self.dispatch,
            self.panel.update_user_details_on_panel,
            self.panel.update_user_status_on_panel,
        )
        calls_before = [method.call_count for method in mutations]
        requests_before = self.panel._request.await_count

        def collect(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: bool,
        ) -> None:
            statements.append(statement.lstrip().split(None, 1)[0].upper())

        event.listen(self.engine.sync_engine, "before_cursor_execute", collect)
        try:
            async with self.sessions() as session:
                output = await replacement_view(
                    session,
                    self.panel,
                    self.service.id,
                    ConsoleExitReplacementQuery(operation_id=self.operation.id),
                )
                assert not session.new and not session.dirty and not session.deleted
        finally:
            event.remove(self.engine.sync_engine, "before_cursor_execute", collect)
        assert statements and not set(statements) & {"INSERT", "UPDATE", "DELETE", "REPLACE"}
        assert [method.call_count for method in mutations] == calls_before
        assert all(
            call.args[0] == "GET" for call in self.panel._request.await_args_list[requests_before:]
        )
        assert self.writes == writes_before and self.remote == remote_before
        assert output.replacement is not None
        return output.replacement

    async def confirmed_projection(self) -> ConsoleExitReplacementOut:
        await self.tick()
        await self.attest()
        await self.confirm()
        output = await self.read_projection()
        assert output.progress.stage == "switching"
        assert output.progress.binding_audit_id is None
        assert output.old_stop and output.old_stop.valid
        assert output.candidate_verification and output.candidate_verification.valid
        return output

    async def test_late_usage_invalidates_only_unbound_stop_evidence(self) -> None:
        before = await self.confirmed_projection()
        self.remote["userTraffic"] = {"usedTrafficBytes": 1, "lifetimeUsedTrafficBytes": 1}
        await self.tick()
        await self.tick()
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.execution.status == "failed"
            assert state.execution.error_code == "exit_replacement_usage_unconfirmed"
            assert state.progress.binding_audit_id is None
            assert state.old_exit.service_id == state.service.id
            assert state.new_exit.hold_order_id == state.order.id
            assert state.connection.replacement_order_id == state.order.id
            assert state.service.used_bytes == 1
            stop = await session.get(DedicatedExitAudit, state.progress.stop_audit_id)
            assert stop
            assert (
                stop.evidence["usage_total_bytes"],
                stop.evidence["usage_raw_bytes"],
                stop.evidence["usage_lifetime_offset"],
            ) == (0, 0, 0)
        after = await self.read_projection()
        assert after.resource_fingerprint == after.requested_resource_fingerprint
        assert (
            after.accounting.usage_total_bytes,
            after.accounting.usage_raw_bytes,
            after.accounting.usage_lifetime_offset,
        ) == (1, 1, 0)
        assert after.candidate_verification == before.candidate_verification
        assert after.candidate_verification and after.candidate_verification.valid
        assert after.old_stop and before.old_stop
        assert after.old_stop.audit_id == before.old_stop.audit_id
        assert not after.old_stop.valid

    async def test_bound_exit_usage_preserves_historical_stop_evidence(self) -> None:
        await self.check_post_binding_usage(completed=False)

    async def test_completed_exit_usage_preserves_historical_stop_evidence(self) -> None:
        await self.check_post_binding_usage(completed=True)

    async def check_post_binding_usage(self, *, completed: bool) -> None:
        before = await self.confirmed_projection()
        for _ in range(3):
            await self.tick()
        assert (await self.progress()).stage == "restoring"
        assert self.remote["status"] == "ACTIVE"
        if completed:
            await self.tick()
        stage = "completed" if completed else "restoring"
        assert (await self.progress()).stage == stage
        self.remote["userTraffic"] = {"usedTrafficBytes": 1, "lifetimeUsedTrafficBytes": 1}
        await synchronize_service_usage(
            cast(sessionmaker, self.sessions), self.service.id, self.panel
        )
        async with self.sessions() as session:
            state = await current_state(
                session, self.service.id, self.operation.id, allow_terminal=True
            )
            assert state.progress.stage == stage and state.progress.binding_audit_id
            assert state.new_exit.service_id == state.service.id
            assert state.new_exit.hold_order_id is None
            assert state.old_exit.service_id is None
            assert state.old_exit.hold_order_id == state.order.id
            assert state.connection.replacement_order_id == (None if completed else state.order.id)
            assert state.connection.usage_error is None
            assert state.service.used_bytes == 1
            stop = await session.get(DedicatedExitAudit, state.progress.stop_audit_id)
            assert stop
            assert (
                stop.evidence["usage_total_bytes"],
                stop.evidence["usage_raw_bytes"],
                stop.evidence["usage_lifetime_offset"],
            ) == (0, 0, 0)
        after = await self.read_projection()
        assert after.progress.stage == stage and after.progress.binding_audit_id
        assert after.current_exit_id == self.new_id
        assert after.gate_active is (not completed)
        assert after.resource_fingerprint == after.requested_resource_fingerprint
        assert (
            after.accounting.usage_total_bytes,
            after.accounting.usage_raw_bytes,
            after.accounting.usage_lifetime_offset,
        ) == (1, 1, 0)
        assert after.candidate_verification == before.candidate_verification
        assert after.candidate_verification and after.candidate_verification.valid
        assert after.old_stop == before.old_stop
        assert after.old_stop and after.old_stop.valid
