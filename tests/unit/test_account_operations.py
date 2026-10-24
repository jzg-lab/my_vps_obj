"""Account audit regressions use only in-memory SQLite and local panel doubles."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.account_access_sync import (
    AccountAccessWorker,
    set_account_ban,
    synchronize_account_access,
)
from db.account_operation_models import AccountOperation
from db.dal.account_access_dal import enqueue_access_sync
from db.dal.account_operation_reads_dal import AccountOperationFilters, list_account_operations
from db.dal.account_operations_dal import begin_account_attempt, finish_account_attempt
from db.dal.user_delete_dal import delete_user_and_relations
from db.dal.user_services_dal import ServiceConflict
from db.models import User
from db.service_models import AccountAccessSync, ServiceConnection, UserService
from tests.unit.test_admin_user_ban import AccessPanel
from tests.unit.test_user_services import ServiceDatabaseTestCase


class AccountOperationTests(ServiceDatabaseTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        policy = patch(
            "bot.services.account_access_sync.can_ban_account", AsyncMock(return_value=True)
        )
        policy.start()
        self.addCleanup(policy.stop)
        self.panel = AccessPanel()

    async def connect(self, key: str = "service", reference: str = "11") -> UserService:
        service, _, _ = await self.activate(key, user_id=2)
        assert isinstance(service, UserService)
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection
            connection.state = "ready"
            connection.panel_user_uuid = reference
        self.panel.states[reference] = "ACTIVE"
        self.panel.bind(service, reference)
        return service

    async def save_ban(self, banned: bool, actor: int = 1) -> str:
        async with self.sessions.begin() as session:
            await set_account_ban(session, user_id=2, actor_id=actor, banned=banned)
            job = await session.get(AccountAccessSync, 2)
            assert isinstance(job, AccountAccessSync)
            operation_id = job.operation_id
            assert isinstance(operation_id, str) and operation_id
            return operation_id

    async def operation(self, operation_id: str) -> AccountOperation:
        async with self.sessions() as session:
            result = await session.get(AccountOperation, operation_id)
            assert result
            return result

    async def test_ban_mapping_preserves_nullable_column_and_legacy_null_values(self) -> None:
        column = User.__table__.c.is_banned
        assert column.nullable and column.default is not None and column.default.arg is False
        assert column.server_default is None
        async with self.sessions.begin() as session:
            await session.execute(update(User).where(User.user_id == 2).values(is_banned=None))
        async with self.sessions() as session:
            user = await session.get(User, 2)
            assert user and user.is_banned is None
        operation = await self.operation(await self.save_ban(True))
        assert operation.before_banned is False and operation.desired_banned is True

    async def test_successful_ban_and_unban_keep_two_actor_results_without_services(self) -> None:
        ban = await self.save_ban(True)
        async with self.sessions() as session:
            await synchronize_account_access(session, 2, None)
        unban = await self.save_ban(False, actor=3)
        async with self.sessions() as session:
            await synchronize_account_access(session, 2, None)
        first, second = await self.operation(ban), await self.operation(unban)
        assert ban != unban
        assert (first.actor_id, first.before_banned, first.desired_banned) == (1, False, True)
        assert (second.actor_id, second.before_banned, second.desired_banned) == (3, True, False)
        for row in (first, second):
            assert row.status == "succeeded" and row.source == "administrator"
            assert row.attempt_count == 1 and row.completed_at is not None
            assert row.user_id == row.target_id == 2

    async def test_intent_and_audit_rollback_together(self) -> None:
        async with self.sessions() as session:
            await set_account_ban(session, user_id=2, actor_id=1, banned=True)
            await session.rollback()
        async with self.sessions() as session:
            user = await session.get(User, 2)
            assert user and not user.is_banned
            assert await session.get(AccountAccessSync, 2) is None
            assert list(await session.scalars(select(AccountOperation))) == []

    async def test_new_intent_supersedes_old_history_without_reassigning_it(self) -> None:
        first = await self.save_ban(True)
        second = await self.save_ban(False)
        assert first != second
        assert (await self.operation(first)).status == "superseded"
        assert (await self.operation(second)).status == "pending"
        async with self.sessions() as session:
            await synchronize_account_access(session, 2, None)
        assert (await self.operation(first)).status == "superseded"
        assert (await self.operation(second)).status == "succeeded"

    async def test_deleted_target_and_actor_preserve_history_without_linking_recreated_account(
        self,
    ) -> None:
        operation_id = await self.save_ban(True, actor=3)
        async with self.sessions.begin() as session:
            assert await delete_user_and_relations(session, 2)
            await session.execute(delete(User).where(User.user_id == 3))
        row = await self.operation(operation_id)
        assert row.user_id is None and row.target_id == 2 and row.actor_id == 3
        async with self.sessions.begin() as session:
            session.add(User(user_id=2))
        assert (await self.operation(operation_id)).user_id is None

    async def test_outage_and_automatic_retries_update_one_manual_record(self) -> None:
        await self.connect()
        operation_id = await self.save_ban(True)
        async with self.sessions() as session:
            await synchronize_account_access(session, 2, None)
        failed = await self.operation(operation_id)
        assert failed.status == "failed" and failed.error_code == "panel_service_unavailable"
        assert failed.attempt_count == 1 and failed.first_failed_at is not None
        self.panel.lookup_failed = True
        await AccountAccessWorker(self.sessions, self.panel).tick()
        unknown = await self.operation(operation_id)
        assert unknown.status == "unknown" and unknown.error_code == "panel_access_unconfirmed"
        assert unknown.first_failed_at == failed.first_failed_at and unknown.attempt_count == 2
        self.panel.lookup_failed = False
        await AccountAccessWorker(self.sessions, self.panel).tick()
        done = await self.operation(operation_id)
        assert done.status == "succeeded" and done.attempt_count == 3
        assert done.actor_id == 1 and done.source == "administrator" and done.error_code is None
        async with self.sessions() as session:
            assert len(list(await session.scalars(select(AccountOperation)))) == 1

    async def test_repeated_pending_command_reuses_record_but_another_actor_is_a_new_intent(
        self,
    ) -> None:
        first = await self.save_ban(True)
        assert await self.save_ban(True) == first
        second = await self.save_ban(True, actor=3)
        assert second != first
        assert (await self.operation(first)).status == "superseded"
        assert (await self.operation(second)).before_banned is True

    async def test_worker_only_jobs_never_invent_a_manual_actor(self) -> None:
        async with self.sessions.begin() as session:
            job = await enqueue_access_sync(session, 2)
            operation_id = job.operation_id
        assert operation_id
        await AccountAccessWorker(self.sessions, None).tick()
        row = await self.operation(operation_id)
        assert row.source == "worker" and row.actor_id is None and row.before_banned is None
        assert row.status == "succeeded"

    async def test_panel_exception_details_never_enter_history_or_logs(self) -> None:
        async with self.sessions.begin() as session:
            await session.execute(
                update(User).where(User.user_id == 2).values(panel_user_uuid="11")
            )
        operation_id = await self.save_ban(True)
        with (
            patch.object(
                self.panel,
                "update_user_status_on_panel",
                AsyncMock(side_effect=RuntimeError("SECRET")),
            ),
            patch.object(
                self.panel, "get_user_by_uuid_lookup", AsyncMock(side_effect=RuntimeError("SECRET"))
            ),
            self.assertLogs("bot.services.account_access_sync", level="WARNING") as logs,
        ):
            await AccountAccessWorker(self.sessions, self.panel).tick()
        assert "SECRET" not in " ".join(logs.output)
        row = await self.operation(operation_id)
        assert row.status == "unknown" and row.error_code == "panel_access_unconfirmed"

    async def test_denied_ban_does_not_write_an_intent_or_history(self) -> None:
        with (
            patch(
                "bot.services.account_access_sync.can_ban_account", AsyncMock(return_value=False)
            ),
            pytest.raises(ServiceConflict, match="forbidden"),
        ):
            await self.save_ban(True)
        async with self.sessions() as session:
            assert await session.get(AccountAccessSync, 2) is None
            assert list(await session.scalars(select(AccountOperation))) == []

    async def test_new_ban_intent_after_marker_commit_is_not_completed_by_old_attempt(self) -> None:
        await self.connect()
        first = await self.save_ban(True)
        commit = AsyncSession.commit
        injected = False
        second: str | None = None

        async def unban_after_marker(session: AsyncSession) -> None:
            nonlocal injected, second
            await commit(session)
            if not injected:
                injected = True
                second = await self.save_ban(False)

        with patch.object(AsyncSession, "commit", unban_after_marker):
            async with self.sessions() as session:
                result = await synchronize_account_access(session, 2, self.panel)
                assert result and result.pending and result.operation_id == second
        assert second and self.panel.updates == []
        assert (await self.operation(first)).status == "superseded"
        assert (await self.operation(second)).status == "pending"
        assert (await self.operation(second)).attempt_count == 0
        await AccountAccessWorker(self.sessions, self.panel).tick()
        assert (await self.operation(second)).status == "succeeded"

    async def test_older_attempt_cannot_overwrite_newer_attempt_on_same_intent(self) -> None:
        operation_id = await self.save_ban(True)
        async with self.sessions.begin() as session:
            user = await session.get(User, 2)
            job = await session.get(AccountAccessSync, 2)
            assert user and job
            old = await begin_account_attempt(session, user, job)
            latest = await begin_account_attempt(session, user, job)
            assert not await finish_account_attempt(session, user, job, old, error=None)
            assert job.pending
            assert await finish_account_attempt(
                session, user, job, latest, error="panel_access_unconfirmed"
            )
        row = await self.operation(operation_id)
        assert row.status == "unknown" and row.attempt_count == 2 and row.completed_at is None

    async def test_remote_success_local_failure_stays_unknown_and_retry_keeps_same_record(
        self,
    ) -> None:
        await self.connect()
        operation_id = await self.save_ban(True)
        commit = AsyncSession.commit
        commits = 0

        async def fail_result_commit(session: AsyncSession) -> None:
            nonlocal commits
            commits += 1
            if commits == 2:
                raise RuntimeError("simulated commit loss")
            await commit(session)

        with (
            patch.object(AsyncSession, "commit", fail_result_commit),
            pytest.raises(RuntimeError, match="simulated commit loss"),
        ):
            async with self.sessions() as session:
                await synchronize_account_access(session, 2, self.panel)
        assert self.panel.states["11"] == "DISABLED"
        row = await self.operation(operation_id)
        assert row.status == "unknown" and row.attempt_count == 1 and row.completed_at is None
        await AccountAccessWorker(self.sessions, self.panel).tick()
        row = await self.operation(operation_id)
        assert row.status == "succeeded" and row.attempt_count == 2

    async def test_unban_audit_success_does_not_enable_ineligible_services(self) -> None:
        for index, state in enumerate(("paused", "cancelled", "expired", "exhausted"), 11):
            service = await self.connect(state, str(index))
            async with self.sessions.begin() as session:
                saved = await session.get(UserService, service.id)
                assert saved
                if state in {"paused", "cancelled"}:
                    saved.desired_status = state
                elif state == "expired":
                    saved.starts_at = datetime.now(UTC) - timedelta(days=2)
                    saved.expires_at = datetime.now(UTC) - timedelta(days=1)
                else:
                    saved.used_bytes = saved.quota_bytes
                    self.panel.users[str(index)]["userTraffic"] = {
                        "usedTrafficBytes": saved.used_bytes,
                        "lifetimeUsedTrafficBytes": saved.used_bytes,
                    }
        await self.save_ban(True)
        await AccountAccessWorker(self.sessions, self.panel).tick()
        operation_id = await self.save_ban(False)
        self.panel.updates.clear()
        await AccountAccessWorker(self.sessions, self.panel).tick()
        assert (await self.operation(operation_id)).status == "succeeded"
        assert not any(enabled for _, enabled in self.panel.updates)
        assert set(self.panel.states.values()) == {"DISABLED"}

    async def test_database_filter_total_and_out_of_range_page_include_serviceless_accounts(
        self,
    ) -> None:
        first = await self.save_ban(True)
        second = await self.save_ban(False, actor=3)
        async with self.sessions() as session:
            filters = AccountOperationFilters(user_id=2)
            rows, total = await list_account_operations(session, filters, page_size=1)
            assert total == 2 and [row.operation.id for row in rows] == [second]
            rows, total = await list_account_operations(session, filters, page_size=1, page=1)
            assert total == 2 and [row.operation.id for row in rows] == [first]
            rows, total = await list_account_operations(session, filters, page_size=1, page=2)
            assert rows == [] and total == 2
            rows, total = await list_account_operations(
                session, AccountOperationFilters(needs_attention=True)
            )
            assert total == 1 and rows[0].operation.id == second and rows[0].needs_attention
            for filters in (
                AccountOperationFilters(actor_id=3),
                AccountOperationFilters(status="pending"),
                AccountOperationFilters(source="administrator", needs_attention=True),
            ):
                rows, total = await list_account_operations(session, filters)
                assert total == 1 and rows[0].operation.id == second
        async with self.sessions.begin() as session:
            assert await delete_user_and_relations(session, 2)
        async with self.sessions() as session:
            rows, total = await list_account_operations(
                session, AccountOperationFilters(archived="only", user_id=2)
            )
            assert total == 2 and all(not row.needs_attention for row in rows)
            assert await list_account_operations(
                session, AccountOperationFilters(needs_attention=True)
            ) == ([], 0)
