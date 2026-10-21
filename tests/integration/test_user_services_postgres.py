"""Service activation races and append-only DDL on disposable PostgreSQL schemas."""

import asyncio
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.dal.user_services_dal import ServiceConflict, activate_service, save_plan
from db.migrator.chain_0107_user_services import _upgrade
from db.models import Base, User
from db.service_models import DedicatedExit, ServiceOrder, UserService
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
