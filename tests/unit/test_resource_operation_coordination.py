"""Offline real DAL/worker gates; PostgreSQL cross-process exclusion is tested separately."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from bot.app.web.admin_console_resource_operation_schemas import ConsoleResourceOperationStartBody
from bot.services.account_access_sync import set_account_ban, synchronize_account_access
from bot.services.resource_operation_runner import run_pending_resource_operation
from bot.services.resource_operations import CHANGE_ADAPTER, start_resource_operation
from bot.services.resource_preview_read import stable_resource_preview
from bot.services.service_change_sync import synchronize_service_change
from bot.services.service_delivery import service_subscription
from bot.services.service_provisioning import ServiceProvisioningWorker, provision_service_identity
from config.service_changes import ServiceChange
from config.service_exit_replacement import ReplacementRequest
from db.dal.resource_operations_dal import resource_gate_active
from db.dal.service_changes_dal import change_service
from db.dal.service_exit_replacement_dal import reserve_exit_replacement
from db.dal.service_operations_dal import begin_execution
from db.dal.user_delete_dal import delete_user_and_relations
from db.dal.user_merge_dal import UserMergeConflictError, merge_users
from db.dal.user_services_dal import ServiceConflict, activate_service, save_plan
from db.models import Subscription, User
from db.service_models import (
    DedicatedExit,
    ServiceConnection,
    ServiceOperationExecution,
    UserService,
)
from tests.unit.test_admin_console_resource_preview import G1, G2, N1
from tests.unit.test_admin_user_ban import AccessPanel
from tests.unit.test_resource_operations import ResourceOperationDatabaseCase
from tests.unit.test_service_provisioning import panel_fixture
from tests.unit.test_user_services import sample_terms


class ResourceCoordinationTests(ResourceOperationDatabaseCase):
    async def test_worker_waits_without_attempts_then_provisions_after_gate_resolution(
        self,
    ) -> None:
        service, _, _ = await self.activate()
        operation = await self.submit()
        panel, users = panel_fixture()
        worker = ServiceProvisioningWorker(cast(sessionmaker, self.sessions), panel)
        await worker.tick()
        self.lose_reply = True
        await run_pending_resource_operation(self.sessions, self.panel)
        await worker.tick()
        panel.create_panel_user.assert_not_awaited()
        assert users == {}
        async with self.sessions() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection is not None and connection.attempted_at is None
            assert connection.state == "pending" and connection.panel_user_uuid is None
            executions = list(await session.scalars(select(ServiceOperationExecution)))
            assert len(executions) == 1 and executions[0].status == "pending"
            assert executions[0].attempted_at is None and executions[0].attempt_count == 0
        await self.evidence(operation.id, "applied")
        await worker.tick()
        panel.create_panel_user.assert_awaited_once()
        assert list(users) == [f"svc_{service.id}"]
        assert (await self.output(operation.id)).status == "succeeded"
        self.writes.assert_awaited_once()

    async def test_pending_gate_blocks_new_activation_provision_and_subscription(self) -> None:
        service, _, _ = await self.activate()
        operation = await self.submit()
        with pytest.raises(ServiceConflict, match="resource_operation_in_progress"):
            await self.activate("second")
        duplicate, _, replay = await self.activate()
        assert duplicate.id == service.id and replay
        await provision_service_identity(self.sessions, service.id, self.panel)
        async with self.sessions() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection is not None and connection.state == "pending"
            assert connection.attempted_at is None and connection.panel_user_uuid is None
            with pytest.raises(ServiceConflict, match="resource_operation_in_progress"):
                await service_subscription(
                    session, user_id=1, service_id=service.id, panel=self.panel
                )
        assert (await self.output(operation.id)).gate_active
        self.panel.create_panel_user.assert_not_called()

    async def test_resource_unknown_does_not_prevent_pause_ban_or_accurate_sampling(self) -> None:
        service, _, _ = await self.activate(user_id=2)
        access = AccessPanel()
        access.bind(service, "11")
        access.states["11"] = "ACTIVE"
        self.panel.get_user_by_uuid_lookup = AsyncMock(side_effect=access.get_user_by_uuid_lookup)
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection is not None
            connection.state, connection.panel_user_uuid = "ready", "11"
        operation = await self.submit()
        self.lose_reply = True
        await run_pending_resource_operation(self.sessions, self.panel)
        assert (await self.output(operation.id)).status == "unknown"
        access.users["11"]["userTraffic"] = {
            "usedTrafficBytes": 500,
            "lifetimeUsedTrafficBytes": 500,
        }
        async with self.sessions.begin() as session:
            await change_service(
                session,
                service_id=service.id,
                user_id=2,
                actor_id=1,
                expected_revision=1,
                idempotency_key="pause",
                change=ServiceChange(action="pause"),
            )
        await synchronize_service_change(self.sessions, service.id, access)
        assert access.states["11"] == "DISABLED"
        async with self.sessions() as session:
            saved = await session.get(UserService, service.id)
            assert saved is not None and saved.used_bytes == 500
            assert await resource_gate_active(session)
        # Role policy is unrelated to the resource gate and uses a PG-only advisory function.
        with patch(
            "bot.services.account_access_sync.can_ban_account", AsyncMock(return_value=True)
        ):
            async with self.sessions.begin() as session:
                await set_account_ban(session, user_id=2, actor_id=1, banned=True)
            async with self.sessions() as session:
                await synchronize_account_access(session, 2, access)
        assert all(not enabled for _, enabled in access.updates)
        async with self.sessions() as session:
            saved_user = await session.get(User, 2)
            assert saved_user is not None and saved_user.is_banned
        async with self.sessions.begin() as session:
            with pytest.raises(ServiceConflict, match="resource_operation_in_progress"):
                await change_service(
                    session,
                    service_id=service.id,
                    user_id=2,
                    actor_id=1,
                    expected_revision=2,
                    idempotency_key="resume",
                    change=ServiceChange(action="resume"),
                )

    async def test_unknown_gate_prevents_legacy_unban_enable_delete_and_merge(self) -> None:
        async with self.sessions.begin() as session:
            user = await session.get(User, 2)
            assert user is not None
            user.is_banned = True
            user.panel_user_uuid = "90"
            session.add(
                Subscription(
                    user_id=2,
                    panel_user_uuid="91",
                    is_active=True,
                    end_date=datetime.now(UTC) + timedelta(days=1),
                )
            )
        operation = await self.submit()
        self.lose_reply = True
        await run_pending_resource_operation(self.sessions, self.panel)
        access = AccessPanel()
        access.states = {"90": "DISABLED", "91": "DISABLED"}
        async with self.sessions.begin() as session:
            await set_account_ban(session, user_id=2, actor_id=1, banned=False)
        async with self.sessions() as session:
            job = await synchronize_account_access(session, 2, access)
            assert job is not None and job.pending
            assert job.last_error == "resource_operation_in_progress"
        assert access.states["91"] == "DISABLED"
        assert all(not enabled for _, enabled in access.updates)
        async with self.sessions.begin() as session:
            with pytest.raises(ServiceConflict, match="resource_operation_in_progress"):
                await delete_user_and_relations(session, 2)
            with pytest.raises(UserMergeConflictError) as raised:
                await merge_users(session, source_user_id=2, target_user_id=3)
            assert raised.value.code == "resource_operation_in_progress"
            assert await session.get(User, 2) is not None
        assert (await self.output(operation.id)).gate_active

    async def test_authorization_committed_first_invalidates_preview_under_real_coordination(
        self,
    ) -> None:
        change = CHANGE_ADAPTER.validate_python({"operation": "node_disable", "target_id": N1})
        async with self.sessions() as session:
            preview, _ = await stable_resource_preview(session, self.panel, change)
        assert preview.fingerprint is not None
        body = ConsoleResourceOperationStartBody(
            change=change, expected_fingerprint=preview.fingerprint, idempotency_key="raced"
        )
        held, release = asyncio.Event(), asyncio.Event()

        async def activating() -> None:
            async with self.sessions.begin() as session:
                await activate_service(
                    session,
                    user_id=1,
                    actor_id=1,
                    plan_id=self.plan.id,
                    expected_revision=1,
                    idempotency_key="first",
                )
                held.set()
                await release.wait()

        async def resource() -> None:
            async with self.sessions.begin() as session:
                await start_resource_operation(session, self.panel, actor_id=1, body=body)

        first = asyncio.create_task(activating())
        await asyncio.wait_for(held.wait(), 2)
        second = asyncio.create_task(resource())
        await asyncio.sleep(0)
        assert not second.done()
        release.set()
        await first
        with pytest.raises(ServiceConflict, match="resource_preview_changed"):
            await asyncio.wait_for(second, 2)
        self.writes.assert_not_awaited()

    async def test_unresolved_prior_service_write_blocks_resource_submission(self) -> None:
        service, _, _ = await self.activate()
        async with self.sessions.begin() as session:
            saved = await session.get(UserService, service.id)
            assert saved is not None
            await begin_execution(session, saved, "prepare", create=True)
        with pytest.raises(ServiceConflict, match="resource_prior_write_unknown"):
            await self.submit()
        self.writes.assert_not_awaited()

    async def test_replacement_and_resource_reservations_are_mutually_exclusive(self) -> None:
        old_id, new_id = uuid4().hex, uuid4().hex
        async with self.sessions.begin() as session:
            plan = await save_plan(
                session,
                actor_id=1,
                enabled=True,
                terms=sample_terms(
                    resource_type="dedicated", squad_uuids=[], resource_pool="private"
                ),
            )
            session.add_all(
                [
                    DedicatedExit(
                        id=exit_id,
                        label="Exit",
                        ip_address=ip,
                        resource_pool="private",
                        squad_uuid=group,
                        enabled=True,
                        verified_at=datetime.now(UTC),
                        created_at=datetime.now(UTC),
                    )
                    for exit_id, ip, group in ((old_id, "192.0.2.1", G1), (new_id, "192.0.2.2", G2))
                ]
            )
        async with self.sessions.begin() as session:
            service, _, _ = await activate_service(
                session,
                user_id=1,
                actor_id=1,
                plan_id=plan.id,
                expected_revision=1,
                idempotency_key="dedicated",
                exit_id=old_id,
            )
        access = AccessPanel()
        access.bind(service, "11")
        access.users["11"]["activeInternalSquads"] = [G1]
        access.states["11"] = "ACTIVE"
        self.panel.get_user_by_uuid_lookup = AsyncMock(side_effect=access.get_user_by_uuid_lookup)
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, service.id)
            old, new = (
                await session.get(DedicatedExit, old_id),
                await session.get(DedicatedExit, new_id),
            )
            assert connection is not None and old is not None and new is not None
            connection.state, connection.panel_user_uuid = "ready", "11"
            command = ReplacementRequest(
                expected_revision=1,
                old_exit_id=old_id,
                new_exit_id=new_id,
                expected_old_exit_revision=old.revision,
                expected_new_exit_revision=new.revision,
                resource_fingerprint="b" * 64,
                reason="Checked candidate",
            )
        resource = await self.submit()
        async with self.sessions.begin() as session:
            with pytest.raises(ServiceConflict, match="resource_operation_in_progress"):
                await reserve_exit_replacement(
                    session,
                    service_id=service.id,
                    user_id=1,
                    actor_id=1,
                    idempotency_key="replace",
                    request=command,
                )
        self.reject = True
        await run_pending_resource_operation(self.sessions, self.panel)
        assert (await self.output(resource.id)).status == "failed"
        async with self.sessions.begin() as session:
            await reserve_exit_replacement(
                session,
                service_id=service.id,
                user_id=1,
                actor_id=1,
                idempotency_key="replace",
                request=command,
            )
        change = CHANGE_ADAPTER.validate_python({"operation": "node_disable", "target_id": N1})
        async with self.sessions.begin() as session:
            with pytest.raises(ServiceConflict, match="resource_replacement_in_progress"):
                await start_resource_operation(
                    session,
                    self.panel,
                    actor_id=1,
                    body=ConsoleResourceOperationStartBody(
                        change=change,
                        expected_fingerprint="a" * 64,
                        idempotency_key="after-replacement",
                    ),
                )
