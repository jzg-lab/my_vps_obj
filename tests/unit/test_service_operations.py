"""Execution evidence and retries never replay commercial service changes."""

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import patch

import pytest
from sqlalchemy import delete, func, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.services.account_access_sync import synchronize_account_access
from bot.services.service_delivery import deliver_service_identity
from bot.services.service_provisioning import provision_service_identity
from bot.services.service_revocation import revoke_service_identity
from bot.services.service_usage_sync import synchronize_service_usage
from config.service_changes import ServiceChange
from config.service_periods import as_utc
from db.dal.account_access_dal import enqueue_access_sync
from db.dal.service_accounts_dal import merge_history
from db.dal.service_changes_dal import change_service
from db.dal.service_delivery_dal import request_service_delivery, request_service_revocation
from db.dal.service_operations_dal import list_operation_records, retry_execution
from db.dal.user_services_dal import ServiceConflict, activate_service, create_exit, save_plan
from db.migrator.chain_0116_service_operation_executions import _upgrade
from db.models import User
from db.service_models import (
    ServiceConnection,
    ServiceOperationExecution,
    ServiceOrder,
    UserService,
)
from tests.unit.test_service_changes import ServiceChangeTestCase
from tests.unit.test_user_services import sample_terms


class ServiceOperationTests(ServiceChangeTestCase):
    async def execution(self, order_id: str) -> ServiceOperationExecution:
        async with self.sessions() as session:
            row = await session.scalar(
                select(ServiceOperationExecution).where(
                    ServiceOperationExecution.order_id == order_id
                )
            )
            assert row is not None
            return row

    async def retry(
        self,
        service: UserService,
        operation: ServiceOperationExecution,
        *,
        user_id: int = 1,
        expected_revision: int | None = None,
        idempotency_key: str = "retry",
    ) -> tuple[ServiceOperationExecution, ServiceOrder, bool]:
        async with self.sessions.begin() as session:
            execution, order, duplicate = await retry_execution(
                session,
                service_id=service.id,
                operation_id=operation.id,
                user_id=user_id,
                actor_id=1,
                expected_revision=service.revision
                if expected_revision is None
                else expected_revision,
                idempotency_key=idempotency_key,
            )
            return execution, order, duplicate

    async def test_order_and_execution_are_atomic_and_activation_replay_adds_neither(self) -> None:
        service, order, _ = await self.activate()
        execution = await self.execution(order.id)
        assert execution.status == "pending" and execution.attempt_count == 0
        assert execution.first_failed_at is execution.attempted_at is None
        assert execution.request_owner_id == 1 and execution.target_revision == service.revision
        replay, same_order, duplicate = await self.activate()
        assert duplicate and replay.id == service.id and same_order.id == order.id
        async with self.sessions() as session:
            await activate_service(
                session,
                user_id=1,
                actor_id=1,
                plan_id=self.plan.id,
                expected_revision=1,
                idempotency_key="rolled-back",
            )
            await session.rollback()
        async with self.sessions() as session:
            for model in (UserService, ServiceOrder, ServiceOperationExecution):
                assert await session.scalar(select(func.count()).select_from(model)) == 1

    async def test_remote_success_local_commit_failure_stays_unknown_and_recovers_identity(
        self,
    ) -> None:
        service, order, _ = await self.activate()
        original_create = self.panel.create_panel_user.side_effect
        assert callable(original_create)

        async def create(username: str, **kwargs: object) -> None:
            row = await self.execution(order.id)
            assert row.status == "unknown" and row.attempt_count == 1
            assert row.attempted_at is not None and row.completed_at is None
            await original_create(username, **kwargs)

        self.panel.create_panel_user.side_effect = create
        commit = AsyncSession.commit
        failed = False

        async def failing_commit(session: AsyncSession) -> None:
            nonlocal failed
            if not failed and any(
                isinstance(row, ServiceOperationExecution) and row.status == "succeeded"
                for row in session.identity_map.values()
            ):
                failed = True
                raise RuntimeError("local commit failed")
            await commit(session)

        with (
            patch.object(AsyncSession, "commit", failing_commit),
            pytest.raises(RuntimeError, match="local commit failed"),
        ):
            await provision_service_identity(
                cast(sessionmaker, self.sessions), service.id, self.panel
            )
        assert failed and len(self.remote_users) == 1
        unknown = await self.execution(order.id)
        assert unknown.status == "unknown" and unknown.completed_at is None
        await provision_service_identity(cast(sessionmaker, self.sessions), service.id, self.panel)
        recovered = await self.execution(order.id)
        assert recovered.status == "succeeded" and recovered.attempt_count == 2
        assert recovered.completed_at is not None
        self.panel.create_panel_user.assert_awaited_once()

    async def test_local_preparation_refusals_never_invent_remote_attempts(self) -> None:
        for case, expected in (
            ("banned", "account_banned"),
            ("expired", "service_expired"),
            ("resource", "service_not_deliverable"),
        ):
            with self.subTest(case=case):
                if case == "resource":
                    async with self.sessions.begin() as session:
                        plan = await save_plan(
                            session,
                            terms=sample_terms(
                                resource_type="dedicated", resource_pool="test", squad_uuids=[]
                            ),
                            enabled=True,
                            actor_id=1,
                        )
                        resource = await create_exit(
                            session,
                            label="Unverified",
                            ip_address="192.0.2.8",
                            resource_pool="test",
                            squad_uuid=str(sample_terms().squad_uuids[0]),
                        )
                        service, order, _ = await activate_service(
                            session,
                            user_id=1,
                            actor_id=1,
                            plan_id=plan.id,
                            expected_revision=1,
                            idempotency_key=case,
                            exit_id=resource.id,
                        )
                else:
                    service, order, _ = await self.activate(case)
                async with self.sessions.begin() as session:
                    user = await session.get(User, 1)
                    saved = await session.get(UserService, service.id)
                    assert user and saved
                    user.is_banned = case == "banned"
                    if case == "expired":
                        saved.starts_at = datetime.now(UTC) - timedelta(days=2)
                        saved.expires_at = datetime.now(UTC) - timedelta(days=1)
                assert (await self.execution(order.id)).status == "pending"
                for _ in range(2):
                    await provision_service_identity(
                        cast(sessionmaker, self.sessions), service.id, self.panel
                    )
                result = await self.execution(order.id)
                assert result.status == "failed" and result.error_code == expected
                assert result.attempt_count == 0 and result.attempted_at is None
                assert result.first_failed_at is not None
                async with self.sessions.begin() as session:
                    connection = await session.get(ServiceConnection, service.id)
                    user = await session.get(User, 1)
                    assert connection and user
                    assert connection.attempted_at is None
                    user.is_banned = False
        assert not self.panel.mock_calls

    async def test_local_pause_and_missing_panel_do_not_claim_remote_attempts(self) -> None:
        service, _, _ = await self.activate()
        paused, order, _ = await self.change(service, "pause")
        async with self.sessions.begin() as session:
            await enqueue_access_sync(session, 1)
        async with self.sessions() as session:
            await synchronize_account_access(session, 1, None)
        queued = await self.execution(order.id)
        assert (
            queued.status == "pending" and queued.attempted_at is None and queued.attempt_count == 0
        )
        await self.sync(paused, self.panel)
        result = await self.execution(order.id)
        assert (
            result.status == "succeeded"
            and result.attempted_at is None
            and result.attempt_count == 0
        )
        async with self.sessions() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection and connection.sync_attempted_at is None
        assert not self.panel.mock_calls

    async def test_only_observed_failure_sets_first_failure_and_timeout_keeps_it(self) -> None:
        service, order, _ = await self.activate()
        self.remote_users[f"svc_{service.id}"] = {
            "uuid": "foreign",
            "username": f"svc_{service.id}",
            "description": "foreign",
        }
        await provision_service_identity(cast(sessionmaker, self.sessions), service.id, self.panel)
        failed = await self.execution(order.id)
        assert failed.status == "failed" and failed.error_code == "panel_identity_conflict"
        assert failed.first_failed_at is not None and failed.completed_at is None
        requeued, _, _ = await self.retry(service, failed)
        assert requeued.status == "pending" and requeued.error_code == failed.error_code
        assert requeued.first_failed_at == failed.first_failed_at
        assert requeued.attempt_count == failed.attempt_count
        assert requeued.attempted_at == failed.attempted_at
        self.panel.get_users_by_filter.side_effect = TimeoutError("NEVER_EXPOSE")
        await provision_service_identity(cast(sessionmaker, self.sessions), service.id, self.panel)
        unknown = await self.execution(order.id)
        assert unknown.status == "unknown" and unknown.error_code == "panel_identity_unconfirmed"
        assert unknown.first_failed_at == failed.first_failed_at and unknown.attempt_count == 2

    async def test_retry_is_idempotent_and_never_replays_renewal_or_usage(self) -> None:
        service, _, _ = await self.activate()
        panel, remote = await self.prepare(service, ready=True)
        remote["userTraffic"] = {"usedTrafficBytes": 123, "lifetimeUsedTrafficBytes": 123}
        renewed, order, _ = await self.change(service)
        original_update = panel.update_user_details_on_panel.side_effect
        panel.update_user_details_on_panel.side_effect = TimeoutError("NEVER_EXPOSE")
        await self.sync(service, panel)
        execution = await self.execution(order.id)
        assert execution.status == "unknown" and execution.first_failed_at is None
        retried, retry_order, duplicate = await self.retry(renewed, execution)
        assert not duplicate and retried.id == execution.id and retry_order.kind == "retry"
        assert retried.attempt_count == execution.attempt_count
        assert retried.status == execution.status == "unknown"
        assert retried.error_code == execution.error_code
        assert retried.attempted_at == execution.attempted_at
        panel.update_user_details_on_panel.side_effect = original_update
        await self.sync(service, panel)
        assert (await self.execution(order.id)).status == "succeeded"
        _, replay_order, duplicate = await self.retry(renewed, execution)
        assert duplicate and replay_order.id == retry_order.id
        with pytest.raises(ServiceConflict, match="idempotency_conflict"):
            await self.retry(renewed, execution, expected_revision=1)
        async with self.sessions() as session:
            saved = await session.get(UserService, service.id)
            connection = await session.get(ServiceConnection, service.id)
            assert saved and connection
            assert as_utc(saved.expires_at) == as_utc(renewed.expires_at)
            assert saved.revision == renewed.revision and saved.used_bytes == 123
            assert saved.quota_bytes == renewed.quota_bytes and connection.panel_user_uuid == "1"
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ServiceOrder)
                    .where(ServiceOrder.kind == "retry")
                )
                == 1
            )
        panel.create_panel_user.assert_awaited_once()

    async def test_retry_rejects_cross_service_key_and_changed_ownership(self) -> None:
        first, first_order, _ = await self.activate()
        second, second_order, _ = await self.activate("second")
        operation = await self.execution(first_order.id)
        other_operation = await self.execution(second_order.id)
        await self.retry(first, operation)
        with pytest.raises(ServiceConflict, match="idempotency_conflict"):
            await self.retry(second, other_operation)
        with pytest.raises(ServiceConflict, match="operation_not_found"):
            await self.retry(second, operation, idempotency_key="wrong-service")
        async with self.sessions.begin() as session:
            await merge_history(session, 1, 2)
        with pytest.raises(ServiceConflict, match="service_not_found"):
            await self.retry(first, operation)
        with pytest.raises(ServiceConflict, match="idempotency_owner_changed"):
            await self.retry(first, operation, user_id=2)

    async def test_retry_rechecks_restrictions_reconciliation_and_archive(self) -> None:
        for case, expected in (
            ("banned", "account_banned"),
            ("expired", "service_expired"),
            ("exhausted", "service_exhausted"),
            ("reset", "usage_reconciliation_required"),
            ("regressed", "usage_reconciliation_required"),
            ("revoked", "service_not_editable"),
            ("archived", "service_not_found"),
        ):
            with self.subTest(case=case):
                service, order, _ = await self.activate(case)
                operation = await self.execution(order.id)
                async with self.sessions.begin() as session:
                    user = await session.get(User, 1)
                    saved = await session.get(UserService, service.id)
                    connection = await session.get(ServiceConnection, service.id)
                    assert user and saved and connection
                    user.is_banned = case == "banned"
                    if case == "expired":
                        saved.starts_at = datetime.now(UTC) - timedelta(days=1)
                        saved.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                    if case == "exhausted":
                        saved.used_bytes = saved.quota_bytes
                    if case in {"reset", "regressed"}:
                        connection.usage_error = f"panel_usage_{case}"
                    if case == "revoked":
                        connection.state = "revoked"
                    if case == "archived":
                        saved.user_id = None
                with pytest.raises(ServiceConflict, match=expected):
                    await self.retry(service, operation, idempotency_key=f"retry:{case}")
                async with self.sessions.begin() as session:
                    user = await session.get(User, 1)
                    assert user
                    user.is_banned = False

    async def test_later_command_supersedes_unconfirmed_result(self) -> None:
        service, activation, _ = await self.activate()
        panel, _ = await self.prepare(service, ready=True)
        paused, pause, _ = await self.change(service, "pause")
        resumed, resume, _ = await self.change(paused, "resume", key="resume")
        assert (await self.execution(pause.id)).status == "superseded"
        with pytest.raises(ServiceConflict, match="service_revision_changed"):
            await self.retry(resumed, await self.execution(pause.id))
        await self.sync(resumed, panel)
        assert (await self.execution(resume.id)).status == "succeeded"
        assert (await self.execution(pause.id)).status == "superseded"
        assert (await self.execution(activation.id)).status == "succeeded"

    async def test_superseded_failure_keeps_observed_cause_and_time(self) -> None:
        service, order, _ = await self.activate()
        self.remote_users[f"svc_{service.id}"] = {
            "uuid": "foreign",
            "username": f"svc_{service.id}",
            "description": "foreign",
        }
        await provision_service_identity(cast(sessionmaker, self.sessions), service.id, self.panel)
        failed = await self.execution(order.id)
        await self.change(service, "pause")
        superseded = await self.execution(order.id)
        assert superseded.status == "superseded" and superseded.completed_at is not None
        assert superseded.error_code == failed.error_code == "panel_identity_conflict"
        assert superseded.first_failed_at == failed.first_failed_at

    async def test_account_worker_persists_unknown_before_retrying_existing_pause(self) -> None:
        service, _, _ = await self.activate()
        panel, remote = await self.prepare(service, ready=True)
        paused, order, _ = await self.change(service, "pause")
        description = remote["description"]
        remote["description"] = "foreign"
        await self.sync(paused, panel)
        failed = await self.execution(order.id)
        assert failed.status == "failed"
        remote["description"] = description
        async with self.sessions.begin() as session:
            await enqueue_access_sync(session, 1)
        lookup = panel.get_user_by_uuid_lookup.side_effect
        assert callable(lookup)

        async def observe(reference: str):
            row = await self.execution(order.id)
            assert row.status == "unknown" and row.attempt_count == failed.attempt_count + 1
            return await lookup(reference)

        panel.get_user_by_uuid_lookup.side_effect = observe
        async with self.sessions() as session:
            await synchronize_account_access(session, 1, panel)
        result = await self.execution(order.id)
        assert result.status == "succeeded" and result.first_failed_at == failed.first_failed_at
        assert remote["status"] == "DISABLED"

    async def test_account_worker_defers_new_intent_after_releasing_its_marker_lock(self) -> None:
        service, _, _ = await self.activate()
        panel, remote = await self.prepare(service, ready=True)
        remote["status"] = "DISABLED"
        async with self.sessions.begin() as session:
            await enqueue_access_sync(session, 1)
        commit = AsyncSession.commit
        pause_order_id: str | None = None

        async def pause_after_marker_commit(session: AsyncSession) -> None:
            nonlocal pause_order_id
            await commit(session)
            if pause_order_id is None:
                async with self.sessions.begin() as other:
                    _, pause, _ = await change_service(
                        other,
                        service_id=service.id,
                        user_id=1,
                        actor_id=1,
                        expected_revision=1,
                        idempotency_key="concurrent-pause",
                        change=ServiceChange(action="pause"),
                    )
                    pause_order_id = pause.id

        with patch.object(AsyncSession, "commit", pause_after_marker_commit):
            async with self.sessions() as session:
                job = await synchronize_account_access(session, 1, panel)
                assert job and job.pending
        assert pause_order_id is not None
        result = await self.execution(pause_order_id)
        assert result.status == "pending" and result.attempt_count == 0
        panel.get_user_by_uuid_lookup.assert_not_awaited()
        panel.update_user_status_on_panel.assert_not_awaited()
        async with self.sessions() as session:
            job = await synchronize_account_access(session, 1, panel)
            assert job and not job.pending
        assert (await self.execution(pause_order_id)).status == "succeeded"
        assert remote["status"] == "DISABLED"

    async def test_ban_enforcement_does_not_claim_admin_resume_succeeded(self) -> None:
        service, _, _ = await self.activate()
        panel, remote = await self.prepare(service, ready=True)
        paused, _, _ = await self.change(service, "pause")
        await self.sync(paused, panel)
        resumed, order, _ = await self.change(paused, "resume", key="resume")
        async with self.sessions.begin() as session:
            user = await session.get(User, 1)
            assert user
            user.is_banned = True
        await self.sync(resumed, panel)
        result = await self.execution(order.id)
        assert result.status == "failed" and result.error_code == "account_banned"
        assert remote["status"] == "DISABLED"

    async def test_restriction_does_not_turn_remote_timeout_into_confirmed_failure(self) -> None:
        service, _, _ = await self.activate()
        panel, _ = await self.prepare(service, ready=True)
        renewed, order, _ = await self.change(service)
        async with self.sessions.begin() as session:
            user = await session.get(User, 1)
            assert user
            user.is_banned = True
        panel.get_user_by_uuid_lookup.side_effect = TimeoutError("NEVER_EXPOSE")
        await self.sync(renewed, panel)
        unknown = await self.execution(order.id)
        assert unknown.status == "unknown" and unknown.first_failed_at is None

    async def test_automatic_failure_deduplicates_and_stable_polling_creates_no_history(
        self,
    ) -> None:
        service, _, _ = await self.activate()
        panel, _ = await self.prepare(service, ready=True)
        for _ in range(3):
            await self.sync(service, panel)
            await synchronize_service_usage(cast(sessionmaker, self.sessions), service.id, panel)
        async with self.sessions() as session:
            assert (
                await session.scalar(select(func.count()).select_from(ServiceOperationExecution))
                == 1
            )
        lookup = panel.get_user_by_uuid_lookup.side_effect
        panel.get_user_by_uuid_lookup.side_effect = TimeoutError("NEVER_EXPOSE")
        for attempt in range(3):
            await synchronize_service_usage(cast(sessionmaker, self.sessions), service.id, panel)
            if attempt == 0:
                async with self.sessions() as session:
                    incident = await session.scalar(
                        select(ServiceOperationExecution).where(
                            ServiceOperationExecution.phase == "usage"
                        )
                    )
                    connection = await session.get(ServiceConnection, service.id)
                    assert incident and connection and incident.attempt_count == 1
                    assert incident.attempted_at == connection.usage_attempted_at
                    assert incident.attempted_at is not None
        async with self.sessions() as session:
            incident = await session.scalar(
                select(ServiceOperationExecution).where(ServiceOperationExecution.phase == "usage")
            )
            assert incident and incident.status == "unknown" and incident.first_failed_at is None
            assert (
                incident.order_id is None
                and incident.source == "worker"
                and incident.attempt_count == 3
            )
            incident_id = incident.id
        panel.get_user_by_uuid_lookup.side_effect = lookup
        for _ in range(3):
            await synchronize_service_usage(cast(sessionmaker, self.sessions), service.id, panel)
        async with self.sessions() as session:
            incident = await session.get(ServiceOperationExecution, incident_id)
            assert incident and incident.status == "succeeded" and incident.completed_at is not None
            assert (
                await session.scalar(select(func.count()).select_from(ServiceOperationExecution))
                == 2
            )

    async def test_usage_reconciliation_guard_preserves_last_real_attempt(self) -> None:
        service, _, _ = await self.activate()
        panel, remote = await self.prepare(service, ready=True)
        for count in (100, 50):
            remote["userTraffic"] = {"usedTrafficBytes": count, "lifetimeUsedTrafficBytes": count}
            await synchronize_service_usage(cast(sessionmaker, self.sessions), service.id, panel)
        async with self.sessions() as session:
            incident = await session.scalar(
                select(ServiceOperationExecution).where(ServiceOperationExecution.phase == "usage")
            )
            connection = await session.get(ServiceConnection, service.id)
            assert incident and connection
            assert incident.status == "failed" and incident.attempt_count == 1
            assert incident.first_failed_at is not None and incident.attempted_at is not None
            attempted_at = connection.usage_attempted_at
            operation_attempted_at = incident.attempted_at
            first_failed_at = incident.first_failed_at
            incident_id = incident.id
        panel.get_user_by_uuid_lookup.reset_mock()
        for _ in range(2):
            await synchronize_service_usage(cast(sessionmaker, self.sessions), service.id, panel)
        panel.get_user_by_uuid_lookup.assert_not_awaited()
        async with self.sessions() as session:
            incident = await session.get(ServiceOperationExecution, incident_id)
            connection = await session.get(ServiceConnection, service.id)
            assert incident and connection
            assert incident.attempt_count == 1 and incident.attempted_at == operation_attempted_at
            assert incident.first_failed_at == first_failed_at
            assert connection.usage_attempted_at == attempted_at

    async def test_delivery_and_revocation_only_complete_after_existing_state_machine(self) -> None:
        service, _, _ = await self.activate()
        panel, remote = await self.prepare(service)
        await synchronize_service_usage(cast(sessionmaker, self.sessions), service.id, panel)
        async with self.sessions.begin() as session:
            delivered, order, _ = await request_service_delivery(
                session,
                service_id=service.id,
                user_id=1,
                actor_id=1,
                expected_revision=1,
                idempotency_key="deliver",
            )
        assert (await self.execution(order.id)).status == "pending"
        update_status = panel.update_user_status_on_panel.side_effect
        panel.update_user_status_on_panel.side_effect = None
        panel.update_user_status_on_panel.return_value = True
        await deliver_service_identity(cast(sessionmaker, self.sessions), service.id, panel)
        assert remote["status"] == "DISABLED"
        assert (await self.execution(order.id)).status == "unknown"
        panel.update_user_status_on_panel.side_effect = update_status
        await self.sync(delivered, panel)
        assert remote["status"] == "ACTIVE"
        assert (await self.execution(order.id)).status == "succeeded"
        async with self.sessions.begin() as session:
            _, revoke, _ = await request_service_revocation(
                session,
                service_id=service.id,
                user_id=1,
                actor_id=1,
                expected_revision=delivered.revision,
                idempotency_key="revoke",
                reason="test",
            )

        async def delete_user(_reference: str) -> bool:
            self.remote_users.clear()
            return True

        panel.delete_user_from_panel.side_effect = delete_user
        await revoke_service_identity(cast(sessionmaker, self.sessions), service.id, panel)
        assert (await self.execution(revoke.id)).status == "succeeded"
        panel.delete_user_from_panel.assert_awaited_once()

    async def test_revocation_result_and_terminal_state_commit_together(self) -> None:
        service, _, _ = await self.activate()
        panel, _ = await self.prepare(service, ready=True)
        async with self.sessions.begin() as session:
            _, order, _ = await request_service_revocation(
                session,
                service_id=service.id,
                user_id=1,
                actor_id=1,
                expected_revision=1,
                idempotency_key="revoke",
                reason="test",
            )

        async def delete_user(_reference: str) -> bool:
            self.remote_users.clear()
            return True

        panel.delete_user_from_panel.side_effect = delete_user
        commit = AsyncSession.commit

        async def fail_terminal_commit(session: AsyncSession) -> None:
            if any(
                isinstance(row, ServiceConnection) and row.state == "revoked"
                for row in session.identity_map.values()
            ):
                execution = next(
                    row
                    for row in session.identity_map.values()
                    if isinstance(row, ServiceOperationExecution) and row.order_id == order.id
                )
                assert execution.status == "succeeded"
                raise RuntimeError("terminal commit failed")
            await commit(session)

        with (
            patch.object(AsyncSession, "commit", fail_terminal_commit),
            pytest.raises(RuntimeError, match="terminal commit failed"),
        ):
            await revoke_service_identity(cast(sessionmaker, self.sessions), service.id, panel)
        unknown = await self.execution(order.id)
        assert unknown.status == "unknown" and unknown.completed_at is None
        async with self.sessions() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection and connection.state != "revoked"
        await revoke_service_identity(cast(sessionmaker, self.sessions), service.id, panel)
        assert (await self.execution(order.id)).status == "succeeded"
        panel.delete_user_from_panel.assert_awaited_once()

    async def test_history_has_real_total_and_legacy_orders_remain_unknown(self) -> None:
        service, order, _ = await self.activate()
        await self.change(service, "pause")
        async with self.sessions.begin() as session:
            await session.execute(
                delete(ServiceOperationExecution).where(
                    ServiceOperationExecution.order_id == order.id
                )
            )
        async with self.sessions() as session:
            page, total = await list_operation_records(session, service.id, limit=1, offset=1)
            assert total == 2 and len(page) == 1
            legacy, execution = page[0]
            assert legacy and legacy.id == order.id and execution is None
            empty, total = await list_operation_records(session, service.id, limit=1, offset=5)
            assert empty == [] and total == 2

    async def test_migration_is_repeatable_and_does_not_backfill_history(self) -> None:
        service, order, _ = await self.activate()
        async with self.engine.begin() as connection:
            await connection.execute(text("DROP TABLE service_operation_executions"))
            await connection.run_sync(_upgrade)
            await connection.run_sync(_upgrade)
            indexes = await connection.run_sync(
                lambda conn: inspect(conn).get_indexes("service_operation_executions")
            )
            assert "ix_service_executions_history" in {item["name"] for item in indexes}
        async with self.sessions() as session:
            assert await session.get(ServiceOrder, order.id) is not None
            assert await session.get(UserService, service.id) is not None
            assert (
                await session.scalar(select(func.count()).select_from(ServiceOperationExecution))
                == 0
            )
