"""Real local DAL and callers, including gate arrival after a committed marker."""

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.app.web.admin_console_global_operations_schemas import ConsoleGlobalOperationOut
from bot.services.service_delivery import deliver_service_identity
from bot.services.service_provisioning import provision_service_identity
from bot.services.service_revocation import revoke_service_identity
from config.service_exit_replacement import ReplacementWriteResolution
from db.dal.global_service_operations_dal import OperationFilters, list_global_operation_records
from db.dal.service_accounts_dal import deletion_connections
from db.dal.service_delivery_dal import request_service_delivery
from db.dal.service_exit_replacement_dal import (
    begin_replacement_action,
    bind_replacement_exit,
    resolve_replacement_write,
)
from db.dal.user_services_dal import ServiceConflict
from db.service_models import ServiceConnection
from tests.unit.test_service_exit_replacement import DIGEST, ReplacementDatabaseTestCase


class ReplacementGateTests(ReplacementDatabaseTestCase):
    async def test_global_history_loads_gate_and_progress_without_lazy_queries(self) -> None:
        async with self.sessions() as session:
            rows, total, _ = await list_global_operation_records(
                session, OperationFilters(phase="exit_replace"), limit=10
            )
        assert total == 1
        out = ConsoleGlobalOperationOut.from_row(rows[0])
        assert out.phase == "exit_replace" and out.replacement_progress
        assert out.retry_block_reason is None and out.retryable

    async def test_local_failure_keeps_gate_for_explicit_retry(self) -> None:
        async with self.sessions.begin() as session:
            state = await self.state(session)
            await begin_replacement_action(session, state, action="stop_old", expected_version=1)
            await resolve_replacement_write(
                session,
                state,
                actor_id=1,
                expected_version=2,
                resolution=ReplacementWriteResolution(
                    action="stop_old",
                    attempt=1,
                    provenance="panel_response",
                    report_digest=DIGEST,
                    completed_at=datetime.now(UTC),
                    result="not_applied",
                ),
            )
            assert state.execution.status == "failed" and state.execution.first_failed_at
        async with self.sessions.begin() as session:
            state = await self.state(session)
            await begin_replacement_action(session, state, action="stop_old", expected_version=3)
            assert state.execution.attempt_count == 2 and state.execution.status == "unknown"
            assert state.new_exit.hold_order_id == state.order.id

    async def test_binding_rejects_changed_identity_and_old_observation(self) -> None:
        async with self.sessions.begin() as session:
            state = await self.confirmed(session)
            observation = self.observation(state)
            for changes in (
                {"panel_user_uuid": "other"},
                {"group_ids": [state.old_exit.squad_uuid]},
                {"resource_fingerprint": "b" * 64},
                {"observed_at": datetime.now(UTC) - timedelta(days=1)},
            ):
                with self.subTest(changes=changes), pytest.raises(ServiceConflict):
                    await bind_replacement_exit(
                        session,
                        state,
                        actor_id=1,
                        expected_version=4,
                        idempotency_key="bind",
                        observation=observation.model_copy(update=changes),
                    )
            assert state.old_exit.service_id == state.service.id and state.new_exit.hold_order_id

    async def test_changed_candidate_and_malformed_progress_cannot_be_reloaded(self) -> None:
        async with self.sessions.begin() as session:
            state = await self.state(session)
            state.new_exit.squad_uuid = "changed-group"
        async with self.sessions() as session:
            with pytest.raises(ServiceConflict, match="scope_changed"):
                await self.state(session)
        async with self.sessions.begin() as session:
            state = await session.get(type(self.operation), self.operation.id)
            assert state
            state.replacement_progress = {"stage": "restoring"}
        async with self.sessions() as session:
            with pytest.raises(ServiceConflict, match="state_invalid"):
                await self.state(session)

    async def test_delete_checks_unbound_hold_even_without_current_binding(self) -> None:
        async with self.sessions.begin() as session:
            state = await self.state(session)
            state.old_exit.service_id = None
            state.connection.replacement_order_id = None
            state.connection.state = "revoked"
            await session.flush()
            with pytest.raises(ServiceConflict, match="dedicated_exit_reclaim_required"):
                await deletion_connections(session, 1)

    async def test_gate_arriving_after_each_worker_marker_blocks_enable_and_delete(self) -> None:
        commit = AsyncSession.commit
        for kind in ("prepare", "delivery", "revocation"):
            with self.subTest(kind=kind):
                async with self.sessions.begin() as session:
                    connection = await session.get(ServiceConnection, self.service.id)
                    assert connection
                    connection.replacement_order_id = None
                    connection.state = "error" if kind == "prepare" else "pending"
                    connection.sync_pending = False
                    connection.last_error = None
                    await session.flush()
                    if kind == "delivery":
                        await request_service_delivery(
                            session,
                            service_id=self.service.id,
                            user_id=1,
                            actor_id=1,
                            expected_revision=2,
                            idempotency_key="delivery-race",
                        )
                    elif kind == "revocation":
                        service = await session.get(type(self.service), self.service.id)
                        assert service
                        service.desired_status = "cancelled"
                        connection.revoke_requested_at = datetime.now(UTC)
                inserted = False

                async def insert_gate(session: AsyncSession) -> None:
                    nonlocal inserted
                    await commit(session)
                    if not inserted:
                        inserted = True
                        async with self.sessions.begin() as other:
                            connection = await other.get(ServiceConnection, self.service.id)
                            assert connection
                            connection.replacement_order_id = self.operation.order_id

                self.panel.reset_mock()
                workers = {
                    "prepare": provision_service_identity,
                    "delivery": deliver_service_identity,
                    "revocation": revoke_service_identity,
                }
                with patch.object(AsyncSession, "commit", insert_gate):
                    await workers[kind](
                        cast(sessionmaker, self.sessions), self.service.id, self.panel
                    )
                assert inserted
                self.panel.create_panel_user.assert_not_awaited()
                self.panel.update_user_details_on_panel.assert_not_awaited()
                self.panel.delete_user_from_panel.assert_not_awaited()
                assert all(
                    call.args[1] is False
                    for call in self.panel.update_user_status_on_panel.await_args_list
                )
                async with self.sessions() as session:
                    state = await self.state(session)
                    assert state.connection.panel_user_uuid and state.connection.state != "revoked"
                    assert state.new_exit.hold_order_id and state.old_exit.service_id
