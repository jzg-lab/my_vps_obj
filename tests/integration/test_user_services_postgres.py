"""Service activation races and append-only DDL on disposable PostgreSQL schemas."""

import asyncio
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from bot.app.web.admin_api_impl import users_actions
from bot.services.account_access_sync import set_account_ban, synchronize_account_access
from bot.services.service_provisioning import provision_service_identity
from db.dal.user_services_dal import ServiceConflict, activate_service, save_plan
from db.migrator.chain_0107_user_services import _upgrade
from db.migrator.chain_0108_service_account_history import _upgrade as upgrade_history
from db.migrator.chain_0109_account_access_sync import _upgrade as upgrade_access
from db.migrator.chain_0110_service_provisioning import _upgrade as upgrade_provisioning
from db.models import Base, User
from db.service_models import (
    AccountAccessSync,
    DedicatedExit,
    ServiceConnection,
    ServiceOrder,
    UserService,
)
from tests.unit.test_admin_user_ban import AccessPanel
from tests.unit.test_service_provisioning import panel_fixture
from tests.unit.test_user_services import sample_terms

DATABASE_URL = os.environ.get("CORE_PERFORMANCE_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="Disposable PostgreSQL URL is required")


def scenario(run: Callable[[async_sessionmaker[AsyncSession]], Awaitable[None]]) -> None:
    async def execute() -> None:
        schema = "user_services_test_" + uuid4().hex
        admin = create_async_engine(DATABASE_URL)
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(
            DATABASE_URL, connect_args={"server_settings": {"search_path": schema}}
        )
        try:
            async with engine.begin() as connection:
                new_tables = {
                    "service_plans",
                    "service_orders",
                    "user_services",
                    "service_connections",
                    "dedicated_exits",
                    "account_access_sync",
                }
                await connection.run_sync(
                    lambda conn: Base.metadata.create_all(
                        conn,
                        tables=[
                            table
                            for table in Base.metadata.sorted_tables
                            if table.name not in new_tables
                        ],
                    )
                )
                await connection.run_sync(_upgrade)
                await connection.run_sync(_upgrade)
                await connection.run_sync(upgrade_history)
                await connection.run_sync(upgrade_history)
                await connection.run_sync(upgrade_access)
                await connection.run_sync(upgrade_access)
                await connection.run_sync(upgrade_provisioning)
                await connection.run_sync(upgrade_provisioning)
            factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
            async with factory.begin() as session:
                session.add_all([User(user_id=1), User(user_id=2)])
            await run(factory)
        finally:
            await engine.dispose()
            async with admin.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await admin.dispose()

    asyncio.run(execute())


def test_concurrent_retries_create_exactly_one_service_and_order() -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        async with factory.begin() as session:
            plan = await save_plan(session, terms=sample_terms(), enabled=True, actor_id=1)

        async def create() -> tuple[str, bool]:
            async with factory.begin() as session:
                service, _, duplicate = await activate_service(
                    session,
                    user_id=1,
                    actor_id=1,
                    plan_id=plan.id,
                    expected_revision=1,
                    idempotency_key="same-request",
                )
                return service.id, duplicate

        results = await asyncio.gather(*(create() for _ in range(8)))
        assert len({service_id for service_id, _ in results}) == 1
        assert sum(not duplicate for _, duplicate in results) == 1
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(ServiceOrder)) == 1

    scenario(run)


def test_parallel_provisioning_prepares_one_disabled_identity() -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        async with factory.begin() as session:
            plan = await save_plan(session, terms=sample_terms(), enabled=True, actor_id=1)
            service, _, _ = await activate_service(
                session,
                user_id=1,
                actor_id=1,
                plan_id=plan.id,
                expected_revision=1,
                idempotency_key="prepare",
            )
        panel, remote_users = panel_fixture()
        await asyncio.gather(
            *(
                provision_service_identity(cast(sessionmaker, factory), service.id, panel)
                for _ in range(8)
            )
        )
        panel.create_panel_user.assert_awaited_once()
        assert len(remote_users) == 1
        assert next(iter(remote_users.values()))["status"] == "DISABLED"
        async with factory() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection is not None and connection.panel_user_uuid == "1"
            assert connection.state == "pending" and connection.last_error is None

    scenario(run)


def test_two_users_cannot_reserve_the_same_exit() -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        exit_id = uuid4().hex
        async with factory.begin() as session:
            plan = await save_plan(
                session,
                terms=sample_terms(resource_type="dedicated", squad_uuids=[], resource_pool="test"),
                enabled=True,
                actor_id=1,
            )
            session.add(
                DedicatedExit(
                    id=exit_id,
                    label="Test",
                    ip_address="192.0.2.1",
                    resource_pool="test",
                    squad_uuid=str(UUID(int=2)),
                    enabled=True,
                    created_at=datetime.now(UTC),
                )
            )

        async def create(user_id: int) -> str:
            try:
                async with factory.begin() as session:
                    await activate_service(
                        session,
                        user_id=user_id,
                        actor_id=1,
                        plan_id=plan.id,
                        expected_revision=1,
                        idempotency_key="same-exit",
                        exit_id=exit_id,
                    )
                return "created"
            except ServiceConflict as exc:
                return str(exc)

        assert sorted(await asyncio.gather(create(1), create(2))) == ["created", "exit_unavailable"]
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(UserService)) == 1

    scenario(run)


def test_ban_committed_while_activation_waits_prevents_grant() -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        async with factory.begin() as session:
            plan = await save_plan(session, terms=sample_terms(), enabled=True, actor_id=1)

        async def create() -> None:
            async with factory.begin() as session:
                cached_user = await session.get(User, 1)
                assert cached_user and not cached_user.is_banned
                await activate_service(
                    session,
                    user_id=1,
                    actor_id=1,
                    plan_id=plan.id,
                    expected_revision=1,
                    idempotency_key="ban-race",
                )

        async with factory.begin() as session:
            user = await session.get(User, 1)
            assert user is not None
            user.is_banned = True
            await session.flush()
            pending = asyncio.create_task(create())
            await asyncio.sleep(0.05)
            assert not pending.done()
        with pytest.raises(ServiceConflict, match="account_banned"):
            await pending

    scenario(run)


def test_history_upgrade_backfills_existing_orders_and_is_repeatable() -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        async with factory.begin() as session:
            plan = await save_plan(session, terms=sample_terms(), enabled=True, actor_id=1)
            service, order, _ = await activate_service(
                session,
                user_id=2,
                actor_id=1,
                plan_id=plan.id,
                expected_revision=1,
                idempotency_key="before-upgrade",
            )
            # Reconstruct the previous schema with existing data, only in this disposable schema.
            await session.execute(text("DROP INDEX uq_service_order_request_key"))
            await session.execute(text("ALTER TABLE service_orders DROP COLUMN request_owner_id"))
            await session.execute(
                text(
                    "ALTER TABLE service_orders ADD CONSTRAINT uq_service_order_key "
                    "UNIQUE (user_id, idempotency_key)"
                )
            )
            await session.execute(
                text("ALTER TABLE service_orders ALTER COLUMN user_id SET NOT NULL")
            )
            await session.execute(
                text("ALTER TABLE user_services ALTER COLUMN user_id SET NOT NULL")
            )
        async with factory.begin() as session:
            connection = await session.connection()
            await connection.run_sync(upgrade_history)
            await connection.run_sync(upgrade_history)
        async with factory.begin() as session:
            replay, same_order, duplicate = await activate_service(
                session,
                user_id=2,
                actor_id=1,
                plan_id=plan.id,
                expected_revision=1,
                idempotency_key="before-upgrade",
            )
            assert duplicate and replay.id == service.id and same_order.id == order.id
            assert same_order.request_owner_id == 2 and same_order.snapshot == order.snapshot

    scenario(run)


def test_delete_holds_owner_lock_until_remote_revocation_and_detachment() -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        async with factory.begin() as session:
            plan = await save_plan(session, terms=sample_terms(), enabled=True, actor_id=1)
            service, _, _ = await activate_service(
                session,
                user_id=2,
                actor_id=1,
                plan_id=plan.id,
                expected_revision=1,
                idempotency_key="before-delete",
            )
            connection = await session.get(ServiceConnection, service.id)
            assert connection
            connection.panel_user_uuid = str(UUID(int=50))
            connection.state = "ready"
        started, finish = asyncio.Event(), asyncio.Event()

        async def delete_remote(*_args: object, **_kwargs: object) -> bool:
            started.set()
            await finish.wait()
            return True

        request = SimpleNamespace(
            app={
                "settings": SimpleNamespace(),
                "async_session_factory": factory,
                "panel_service": SimpleNamespace(
                    delete_user_from_panel=delete_remote,
                    get_user_by_uuid_lookup=AsyncMock(return_value={"not_found": True}),
                ),
            },
            match_info={"user_id": "2"},
        )

        async def activate() -> None:
            async with factory.begin() as session:
                await activate_service(
                    session,
                    user_id=2,
                    actor_id=1,
                    plan_id=plan.id,
                    expected_revision=1,
                    idempotency_key="during-delete",
                )

        with (
            patch.object(users_actions, "_require_admin_user_id", return_value=1),
            patch.object(users_actions, "_invalidate_after_admin_user_mutation", AsyncMock()),
        ):
            deleting = asyncio.create_task(users_actions.admin_user_delete_route(request))
            await asyncio.wait_for(started.wait(), timeout=5)
            opening = asyncio.create_task(activate())
            try:
                await asyncio.sleep(0.05)
                assert not opening.done()
            finally:
                finish.set()
            assert (await deleting).status == 200
            with pytest.raises(ServiceConflict, match="user_not_found"):
                await opening
        async with factory() as session:
            assert await session.get(User, 2) is None
            retained = await session.get(UserService, service.id)
            assert retained and retained.user_id is None and retained.desired_status == "cancelled"

    scenario(run)


def test_access_upgrade_queues_existing_bans_without_reopening_completed_jobs() -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        async with factory.begin() as session:
            user = await session.get(User, 2)
            assert user
            user.is_banned = True
        async with factory.begin() as session:
            await session.execute(text("DROP TABLE account_access_sync"))
            connection = await session.connection()
            await connection.run_sync(upgrade_access)
            await connection.run_sync(upgrade_access)
            job = await session.get(AccountAccessSync, 2)
            assert job and job.pending
            assert await session.get(AccountAccessSync, 1) is None
            job.pending = False
        async with factory.begin() as session:
            connection = await session.connection()
            await connection.run_sync(upgrade_access)
            job = await session.get(AccountAccessSync, 2)
            assert job and not job.pending

    scenario(run)


def test_unban_waits_for_running_sync_then_queues_the_latest_intent() -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        async with factory.begin() as session:
            plan = await save_plan(session, terms=sample_terms(), enabled=True, actor_id=1)
            service, _, _ = await activate_service(
                session,
                user_id=2,
                actor_id=1,
                plan_id=plan.id,
                expected_revision=1,
                idempotency_key="sync-race",
            )
            connection = await session.get(ServiceConnection, service.id)
            assert connection
            connection.panel_user_uuid = "11"
            connection.state = "ready"
            await set_account_ban(session, user_id=2, actor_id=1, banned=True)
        started, finish = asyncio.Event(), asyncio.Event()
        panel = AccessPanel()
        panel.states["11"] = "ACTIVE"

        async def update(user_uuid: str, enable: bool, log_response: bool = False) -> bool:
            started.set()
            await finish.wait()
            return await panel.update_user_status_on_panel(user_uuid, enable, log_response)

        blocking_panel = SimpleNamespace(
            update_user_status_on_panel=update,
            get_user_by_uuid_lookup=panel.get_user_by_uuid_lookup,
        )

        async def sync() -> None:
            async with factory() as session:
                await synchronize_account_access(session, 2, blocking_panel)

        async def unban() -> None:
            async with factory.begin() as session:
                await set_account_ban(session, user_id=2, actor_id=1, banned=False)

        running = asyncio.create_task(sync())
        try:
            await asyncio.wait_for(started.wait(), timeout=5)
            waiting = asyncio.create_task(unban())
            await asyncio.sleep(0.05)
            assert not waiting.done()
        finally:
            finish.set()
        await asyncio.wait_for(asyncio.gather(running, waiting), timeout=5)
        assert panel.states["11"] == "DISABLED"
        async with factory() as session:
            user = await session.get(User, 2)
            job = await session.get(AccountAccessSync, 2)
            assert user and not user.is_banned and job and job.pending
            await synchronize_account_access(session, 2, panel)
        assert panel.states["11"] == "ACTIVE"

    scenario(run)
