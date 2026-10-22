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
from bot.services.service_usage_sync import synchronize_service_usage
from db.dal.service_delivery_dal import record_exit_evidence, request_service_delivery
from db.dal.user_services_dal import ServiceConflict, activate_service, create_exit, save_plan
from db.migrator.chain_0107_user_services import _upgrade
from db.migrator.chain_0108_service_account_history import _upgrade as upgrade_history
from db.migrator.chain_0109_account_access_sync import _upgrade as upgrade_access
from db.migrator.chain_0110_service_provisioning import _upgrade as upgrade_provisioning
from db.migrator.chain_0111_service_changes import _upgrade as upgrade_changes
from db.migrator.chain_0112_service_usage import _upgrade as upgrade_usage
from db.migrator.chain_0113_service_entitlements import _upgrade as upgrade_entitlements
from db.migrator.chain_0114_service_delivery import _upgrade as upgrade_delivery
from db.migrator.chain_0115_service_revocation_evidence import (
    _upgrade as upgrade_revocation_evidence,
)
from db.models import Base, User
from db.service_models import (
    AccountAccessSync,
    DedicatedExit,
    DedicatedExitAudit,
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
                    "dedicated_exit_audit",
                    "account_access_sync",
                    "service_usage_periods",
                    "service_plan_quota_changes",
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
                await connection.run_sync(upgrade_changes)
                await connection.run_sync(upgrade_changes)
                await connection.run_sync(upgrade_usage)
                await connection.run_sync(upgrade_usage)
                await connection.run_sync(upgrade_entitlements)
                await connection.run_sync(upgrade_entitlements)
                await connection.run_sync(upgrade_delivery)
                await connection.run_sync(upgrade_delivery)
                await connection.run_sync(upgrade_revocation_evidence)
                await connection.run_sync(upgrade_revocation_evidence)
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


def test_concurrent_delivery_requests_commit_one_intent_without_changing_usage() -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        async with factory.begin() as session:
            plan = await save_plan(session, terms=sample_terms(), enabled=True, actor_id=1)
            service, _, _ = await activate_service(
                session,
                user_id=1,
                actor_id=1,
                plan_id=plan.id,
                expected_revision=1,
                idempotency_key="prepare-delivery",
            )
            connection = await session.get(ServiceConnection, service.id)
            assert connection
            connection.panel_user_uuid = str(UUID(int=70))
            connection.usage_total_bytes = 123
            connection.usage_raw_bytes = 123
            service.used_bytes = 123
            service.last_usage_sync_at = datetime.now(UTC)

        async def deliver() -> tuple[str, bool]:
            async with factory.begin() as session:
                _, order, duplicate = await request_service_delivery(
                    session,
                    service_id=service.id,
                    user_id=1,
                    actor_id=1,
                    expected_revision=1,
                    idempotency_key="same-delivery",
                )
                return order.id, duplicate

        results = await asyncio.gather(*(deliver() for _ in range(8)))
        assert len({order_id for order_id, _ in results}) == 1
        assert sum(not duplicate for _, duplicate in results) == 1
        async with factory() as session:
            connection = await session.get(ServiceConnection, service.id)
            saved = await session.get(UserService, service.id)
            assert connection and connection.state == "pending" and connection.sync_pending
            assert connection.usage_total_bytes == 123
            assert saved and saved.used_bytes == 123 and saved.revision == 2

    scenario(run)


def test_concurrent_exit_evidence_and_old_reclaim_retry_preserve_new_allocation() -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        async with factory.begin() as session:
            plan = await save_plan(
                session,
                terms=sample_terms(resource_type="dedicated", squad_uuids=[], resource_pool="pool"),
                enabled=True,
                actor_id=1,
            )
            resource = await create_exit(
                session,
                label="Isolated test",
                ip_address="192.0.2.9",
                resource_pool="pool",
                squad_uuid=str(UUID(int=99)),
            )
            service, _, _ = await activate_service(
                session,
                user_id=1,
                actor_id=1,
                plan_id=plan.id,
                expected_revision=1,
                idempotency_key="original",
                exit_id=resource.id,
            )
            connection = await session.get(ServiceConnection, service.id)
            assert connection
            connection.state = "revoked"
            connection.revoked_at = datetime.now(UTC)
            service.desired_status = "cancelled"
        command: dict[str, object] = {
            "expected_revision": resource.revision,
            "service_id": service.id,
            "idempotency_key": "reclaim",
            "checked_at": datetime.now(UTC).isoformat(),
            "evidence": "Disposable PostgreSQL fixture only, not actual Node evidence",
            "connections_stopped": True,
            "old_config_rejected": True,
        }

        async def reclaim() -> bool:
            async with factory.begin() as session:
                _, _, duplicate = await record_exit_evidence(
                    session, exit_id=resource.id, actor_id=1, action="reclaim", command=command
                )
                assert isinstance(duplicate, bool)
                return duplicate

        results = await asyncio.gather(*(reclaim() for _ in range(8)))
        assert results.count(False) == 1
        async with factory.begin() as session:
            second, _, _ = await activate_service(
                session,
                user_id=2,
                actor_id=1,
                plan_id=plan.id,
                expected_revision=1,
                idempotency_key="next",
                exit_id=resource.id,
            )
        assert await reclaim()
        async with factory() as session:
            current = await session.get(DedicatedExit, resource.id)
            assert current and current.service_id == second.id and current.verified_at is None
            assert await session.scalar(select(func.count()).select_from(DedicatedExitAudit)) == 1

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


def test_concurrent_usage_observations_count_each_byte_once() -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        async with factory.begin() as session:
            plan = await save_plan(session, terms=sample_terms(), enabled=True, actor_id=1)
            service, _, _ = await activate_service(
                session,
                user_id=1,
                actor_id=1,
                plan_id=plan.id,
                expected_revision=1,
                idempotency_key="usage",
            )
        panel, users = panel_fixture()
        await provision_service_identity(cast(sessionmaker, factory), service.id, panel)
        remote = users[f"svc_{service.id}"]
        for total in (1234, 2345):
            remote["userTraffic"] = {"usedTrafficBytes": total, "lifetimeUsedTrafficBytes": total}
            await asyncio.gather(
                *(
                    synchronize_service_usage(cast(sessionmaker, factory), service.id, panel)
                    for _ in range(8)
                )
            )
            async with factory() as session:
                saved = await session.get(UserService, service.id)
                connection = await session.get(ServiceConnection, service.id)
                assert saved and connection
                assert saved.used_bytes == connection.usage_total_bytes == total
                assert saved.revision == 1 and connection.usage_error is None
        async with factory.begin() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection
            connection.usage_error = "panel_usage_unavailable"
        async with factory() as session:
            db_connection = await session.connection()
            await db_connection.run_sync(upgrade_usage)
            await session.commit()
        async with factory() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection and connection.usage_total_bytes == 2345
            assert connection.usage_error == "panel_usage_unavailable"

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


def test_delete_holds_owner_lock_until_legacy_cleanup_and_service_detachment() -> None:
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
            user = await session.get(User, 2)
            assert connection and user
            connection.panel_user_uuid = str(UUID(int=50))
            connection.state = "revoked"
            user.panel_user_uuid = str(UUID(int=51))
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
        panel.bind(service, "11")

        async def update(user_uuid: str, enable: bool, log_response: bool = False) -> bool:
            started.set()
            await finish.wait()
            return await panel.update_user_status_on_panel(user_uuid, enable, log_response)

        blocking_panel = SimpleNamespace(
            update_user_status_on_panel=update,
            get_user_by_uuid_lookup=panel.get_user_by_uuid_lookup,
            update_user_details_on_panel=panel.update_user_details_on_panel,
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


def test_concurrent_renewals_are_idempotent_and_stale_changes_conflict() -> None:
    from datetime import timedelta

    from config.service_changes import ServiceChange
    from db.dal.service_changes_dal import change_service

    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        async with factory.begin() as session:
            plan = await save_plan(session, terms=sample_terms(), enabled=True, actor_id=1)
            service, _, _ = await activate_service(
                session,
                user_id=1,
                actor_id=1,
                plan_id=plan.id,
                expected_revision=1,
                idempotency_key="activate",
            )
            service.used_bytes = 9000
        change = ServiceChange.model_validate(
            {"action": "renew", "days": 31, "price": "2.30", "currency": "CNY"}
        )

        async def renew(key: str) -> tuple[str, bool]:
            async with factory.begin() as session:
                updated, order, duplicate = await change_service(
                    session,
                    service_id=service.id,
                    user_id=1,
                    actor_id=1,
                    expected_revision=1,
                    idempotency_key=key,
                    change=change,
                )
                assert updated.expires_at == service.expires_at + timedelta(days=31)
                assert updated.used_bytes == 9000 and updated.revision == 2
                return order.id, duplicate

        results = await asyncio.gather(*(renew("same-renewal") for _ in range(8)))
        assert len({order for order, _ in results}) == 1
        assert sum(not duplicate for _, duplicate in results) == 1
        with pytest.raises(ServiceConflict, match="service_revision_changed"):
            await renew("stale-renewal")
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(ServiceOrder)) == 2

    scenario(run)


def test_quota_edit_concurrent_with_activation_converges_without_inverse_lock_order() -> None:
    from bot.services.service_change_sync import synchronize_service_change
    from db.service_models import ServicePlanQuotaChange

    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        async with factory.begin() as session:
            plan = await save_plan(session, terms=sample_terms(), enabled=True, actor_id=1)
            existing, _, _ = await activate_service(
                session,
                user_id=2,
                actor_id=1,
                plan_id=plan.id,
                expected_revision=1,
                idempotency_key="existing",
            )

        async def open_stale() -> None:
            async with factory.begin() as session:
                await activate_service(
                    session,
                    user_id=1,
                    actor_id=1,
                    plan_id=plan.id,
                    expected_revision=1,
                    idempotency_key="during-edit",
                )

        panel, _ = panel_fixture()
        async with factory.begin() as session:
            await save_plan(
                session,
                plan_id=plan.id,
                expected_revision=1,
                terms=sample_terms(quota_bytes=5000),
                enabled=True,
                actor_id=1,
                quota_change_reason="Changed allowance",
            )
            opening = asyncio.create_task(open_stale())
            await asyncio.sleep(0.05)
            assert not opening.done()
            await asyncio.wait_for(
                synchronize_service_change(cast(sessionmaker, factory), existing.id, panel),
                timeout=5,
            )
        with pytest.raises(ServiceConflict, match="plan_revision_changed"):
            await asyncio.wait_for(opening, timeout=5)
        await asyncio.gather(
            *(
                synchronize_service_change(cast(sessionmaker, factory), existing.id, panel)
                for _ in range(8)
            )
        )
        async with factory() as session:
            saved = await session.get(UserService, existing.id)
            assert saved and saved.quota_bytes == 5000 and saved.quota_revision == 2
            assert saved.terms["quota_bytes"] == 10000
            assert (
                await session.scalar(select(func.count()).select_from(ServicePlanQuotaChange)) == 1
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ServiceOrder)
                    .where(ServiceOrder.kind == "quota")
                )
                == 1
            )

    scenario(run)


def test_parallel_monthly_retries_keep_one_cutover_with_continuous_traffic() -> None:
    from datetime import timedelta
    from typing import Any

    from bot.services.service_change_sync import synchronize_service_change
    from config.service_periods import monthly_period
    from db.service_models import ServiceUsagePeriod

    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        async with factory.begin() as session:
            plan = await save_plan(
                session, terms=sample_terms(traffic_rule="monthly"), enabled=True, actor_id=1
            )
            service, _, _ = await activate_service(
                session,
                user_id=2,
                actor_id=1,
                plan_id=plan.id,
                expected_revision=1,
                idempotency_key="monthly",
            )
            service.starts_at = datetime(2024, 1, 31, tzinfo=UTC)
            service.expires_at = datetime.now(UTC) + timedelta(days=365)
            service.cycle_started_at, service.cycle_ends_at = monthly_period(
                service.starts_at, service.starts_at
            )
        panel, users = panel_fixture()
        await provision_service_identity(cast(sessionmaker, factory), service.id, panel)
        remote = users[f"svc_{service.id}"]
        lookup = panel.get_user_by_uuid_lookup.side_effect
        assert callable(lookup)

        async def moving(reference: str) -> dict[str, Any]:
            remote["userTraffic"]["usedTrafficBytes"] += 1
            remote["userTraffic"]["lifetimeUsedTrafficBytes"] += 1
            result = await lookup(reference)
            assert isinstance(result, dict)
            return result

        async def update(_reference: str, payload: dict[str, Any]) -> dict[str, Any]:
            remote.update(payload)
            return remote

        panel.get_user_by_uuid_lookup.side_effect = moving
        panel.update_user_details_on_panel.side_effect = update
        await asyncio.wait_for(
            asyncio.gather(
                *(
                    synchronize_service_change(cast(sessionmaker, factory), service.id, panel)
                    for _ in range(8)
                )
            ),
            timeout=10,
        )
        async with factory() as session:
            period = await session.scalar(select(ServiceUsagePeriod))
            assert period and period.confirmed_at and period.cutover_bytes == 1
            assert await session.scalar(select(func.count()).select_from(ServiceUsagePeriod)) == 1
            connection = await session.get(ServiceConnection, service.id)
            assert connection and connection.cycle_cutover_bytes is None
        assert remote["trafficLimitBytes"] == 10001 and remote["status"] == "DISABLED"
        panel.update_user_details_on_panel.assert_awaited_once()

    scenario(run)


def test_parallel_terminal_settlement_writes_one_audit_without_confirming_allowance() -> None:
    from datetime import timedelta

    from bot.services.service_panel_state import locked_service
    from bot.services.service_period_sync import (
        prepare_service_cycle,
        settle_cancelled_service_period,
    )
    from config.service_periods import monthly_period
    from db.service_models import ServiceUsagePeriod

    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        async with factory.begin() as session:
            plan = await save_plan(
                session, terms=sample_terms(traffic_rule="monthly"), enabled=True, actor_id=1
            )
            service, _, _ = await activate_service(
                session,
                user_id=2,
                actor_id=1,
                plan_id=plan.id,
                expected_revision=1,
                idempotency_key="terminal",
            )
            service.starts_at = datetime(2024, 1, 31, tzinfo=UTC)
            service.expires_at = datetime.now(UTC) + timedelta(days=365)
            service.cycle_started_at, service.cycle_ends_at = monthly_period(
                service.starts_at, service.starts_at
            )
        panel, users = panel_fixture()
        await provision_service_identity(cast(sessionmaker, factory), service.id, panel)
        remote = users[f"svc_{service.id}"]
        remote["userTraffic"] = {"usedTrafficBytes": 900, "lifetimeUsedTrafficBytes": 900}
        await prepare_service_cycle(cast(sessionmaker, factory), service.id, panel)
        async with factory.begin() as session:
            saved = await session.get(UserService, service.id)
            assert saved
            saved.desired_status = "cancelled"
        remote["status"] = "DISABLED"
        remote["userTraffic"] = {"usedTrafficBytes": 1200, "lifetimeUsedTrafficBytes": 1200}
        panel.reset_mock()

        async def settle() -> None:
            async with factory.begin() as session:
                locked = await locked_service(session, service.id)
                assert locked
                _, saved, connection = locked
                assert await settle_cancelled_service_period(
                    session, saved, connection, remote, actor_id=1
                )

        await asyncio.wait_for(asyncio.gather(*(settle() for _ in range(8))), timeout=10)
        async with factory() as session:
            saved = await session.get(UserService, service.id)
            connection = await session.get(ServiceConnection, service.id)
            period = await session.scalar(select(ServiceUsagePeriod))
            orders = list(
                await session.scalars(
                    select(ServiceOrder).where(ServiceOrder.kind == "settle_usage")
                )
            )
            assert saved and connection and period
            assert saved.desired_status == "cancelled" and saved.used_bytes == 300
            assert connection.cycle_cutover_bytes is None and connection.usage_total_bytes == 1200
            assert (
                period.cutover_bytes == 900
                and period.used_bytes == 900
                and period.confirmed_at is None
            )
            assert len(orders) == 1 and orders[0].snapshot["allowance_confirmed"] is False
        panel.update_user_status_on_panel.assert_not_awaited()
        panel.update_user_details_on_panel.assert_not_awaited()

    scenario(run)
