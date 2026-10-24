"""Resource uncertainty must remain recoverable without delaying service restrictions."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.admin_console_resource_operation_schemas import (
    ConsoleResourceOperationEvidenceBody,
    ConsoleResourceOperationStartBody,
)
from bot.app.web.admin_console_resource_schemas import ResourceNodeChange
from bot.services.resource_operation_panel import ResourceReceipt
from bot.services.resource_operation_reconciliation import accept_resource_evidence
from bot.services.resource_operation_runner import run_resource_operation
from bot.services.resource_operations import start_resource_operation
from bot.services.resource_preview_read import stable_resource_preview
from config.service_changes import ServiceChange
from config.settings import Settings
from db.dal.service_changes_dal import change_service
from db.resource_operation_models import ResourceOperation
from db.service_models import UserService
from tests.unit.test_admin_console_resource_preview import N1, inventory_fixture, panel_fixture
from tests.unit.test_user_services import ServiceDatabaseTestCase


class ResourceDispatchBoundaryTests(ServiceDatabaseTestCase):
    async def prepare_operation(self):
        panel, requests = panel_fixture(inventory_fixture())
        panel.settings = Settings(
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            BOT_TOKEN="1234567890:AA_test_bot_token_value",
            PANEL_WRITE_MODE="live",
            _env_file=None,
        )
        change = ResourceNodeChange(operation="node_restart", target_id=UUID(N1))
        async with self.sessions.begin() as session:
            preview, _ = await stable_resource_preview(session, panel, change)
            assert preview.fingerprint is not None and not preview.blockers
            result = await start_resource_operation(
                session,
                panel,
                actor_id=1,
                body=ConsoleResourceOperationStartBody(
                    change=change,
                    expected_fingerprint=preview.fingerprint,
                    idempotency_key="dispatch-boundary",
                ),
            )
        return panel, requests, result.operation.id

    async def test_cancelled_before_send_keeps_an_attempt_that_can_be_reconciled(self) -> None:
        panel, requests, operation_id = await self.prepare_operation()
        original_commit = AsyncSession.commit
        cancelled = False

        async def cancel_at_uncertainty(session: AsyncSession) -> None:
            nonlocal cancelled
            reached = any(
                isinstance(row, ResourceOperation)
                and row.id == operation_id
                and row.status == "unknown"
                for row in session.identity_map.values()
            )
            await original_commit(session)
            if reached and not cancelled:
                cancelled = True
                raise asyncio.CancelledError

        dispatch = AsyncMock()
        with (
            patch.object(AsyncSession, "commit", cancel_at_uncertainty),
            patch("bot.services.resource_operation_runner.dispatch_resource", dispatch),
            self.assertRaises(asyncio.CancelledError),
        ):
            await run_resource_operation(self.sessions, panel, operation_id)
        assert cancelled
        dispatch.assert_not_awaited()
        async with self.sessions.begin() as session:
            row = await session.get(ResourceOperation, operation_id)
            assert row is not None and row.status == "unknown" and row.gate_key is not None
            assert row.attempt_count == 1, "Committed uncertainty must have a reconcilable attempt."
            result = await accept_resource_evidence(
                session,
                panel,
                operation_id,
                actor_id=1,
                body=ConsoleResourceOperationEvidenceBody(
                    expected_version=row.version,
                    attempt=row.attempt_count,
                    result="not_applied",
                    evidence_digest="a" * 64,
                    checked_at=datetime.now(UTC),
                ),
            )
        assert result.operation.status == "failed"
        assert result.operation.gate_active is False and result.operation.can_retry is True
        assert requests.await_count > 0
        assert all(call.args[0] == "GET" for call in requests.await_args_list)

    async def test_remote_attempt_does_not_block_committing_a_service_pause(self) -> None:
        service, _, _ = await self.activate()
        panel, _, operation_id = await self.prepare_operation()
        paused = False

        async def pause() -> None:
            nonlocal paused
            async with self.sessions.begin() as session:
                await change_service(
                    session,
                    service_id=service.id,
                    user_id=1,
                    actor_id=1,
                    expected_revision=service.revision,
                    idempotency_key="pause-during-resource-write",
                    change=ServiceChange(action="pause"),
                )
            paused = True

        async def remote_attempt(*_args: object) -> ResourceReceipt:
            # The request remains in flight until the real restriction has committed.
            await asyncio.wait_for(pause(), timeout=2)
            return ResourceReceipt("accepted", N1)

        dispatch = AsyncMock(side_effect=remote_attempt)
        with patch("bot.services.resource_operation_runner.dispatch_resource", dispatch):
            await run_resource_operation(self.sessions, panel, operation_id)
        dispatch.assert_awaited_once()
        assert paused
        async with self.sessions() as session:
            saved = await session.get(UserService, service.id)
            assert saved is not None and saved.desired_status == "paused"
