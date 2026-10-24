"""Opt-in PostgreSQL resource gates; only Panel transport is simulated."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from asyncpg.exceptions import PostgresError
from sqlalchemy import event, func, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, SessionTransaction, sessionmaker

from bot.app.web.admin_console_resource_operation_schemas import (
    ConsoleResourceOperationEvidenceBody,
    ConsoleResourceOperationRetryBody,
    ConsoleResourceOperationStartBody,
)
from bot.app.web.admin_console_resource_schemas import (
    ResourceHostChange,
    ResourceHostPatch,
    ResourceNodeChange,
)
from bot.services.account_access_sync import set_account_ban
from bot.services.panel_api_service import PanelApiService
from bot.services.resource_operation_reconciliation import accept_resource_evidence
from bot.services.resource_operation_runner import (
    run_pending_resource_operation,
    run_resource_operation,
)
from bot.services.resource_operations import (
    operation_output,
    retry_resource_operation,
    start_resource_operation,
)
from bot.services.resource_preview_read import stable_resource_preview
from bot.services.service_usage_sync import synchronize_service_usage
from config.service_changes import ServiceChange
from config.settings import Settings
from db.dal.service_changes_dal import change_service
from db.dal.user_services_dal import ServiceConflict, activate_service, save_plan
from db.migrator.chain_0118_resource_operations import _upgrade as upgrade_resources
from db.models import User
from db.resource_operation_models import ResourceOperation
from db.service_models import AccountAccessSync, ServiceConnection, ServiceOrder, UserService
from tests.integration.test_exit_replacement_postgres import contend
from tests.integration.test_user_services_postgres import DATABASE_URL, scenario
from tests.unit.test_admin_console_resource_preview import (
    G1,
    H1,
    N1,
    inventory_fixture,
    panel_fixture,
)
from tests.unit.test_user_services import sample_terms

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="Disposable PostgreSQL URL is required")


async def prepare(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[str, PanelApiService, dict[str, object], AsyncMock]:
    async with factory.begin() as session:
        schema = await session.scalar(text("SELECT current_schema()"))
        assert isinstance(schema, str) and schema.startswith("user_services_test_")
        assert await session.scalar(select(func.count()).select_from(ResourceOperation)) == 0
        # scenario owns the migration-only table creation and empty-schema double upgrade.
        plan = await save_plan(session, terms=sample_terms(), enabled=True, actor_id=1)
    payloads = inventory_fixture()
    panel, _ = panel_fixture(payloads)
    panel.settings = Settings(
        POSTGRES_USER="test",
        POSTGRES_PASSWORD="test",
        BOT_TOKEN="1234567890:AA_test_bot_token_value",
        PANEL_WRITE_MODE="live",
        _env_file=None,
    )
    writes = AsyncMock(return_value={"status_code": 202})
    panel._request_once = writes
    return plan.id, panel, payloads, writes


async def confirmation(
    session: AsyncSession, panel: PanelApiService
) -> ConsoleResourceOperationStartBody:
    change = ResourceNodeChange(operation="node_restart", target_id=UUID(N1))
    preview, _ = await stable_resource_preview(session, panel, change)
    assert preview.coverage == "complete" and not preview.blockers
    assert preview.fingerprint is not None
    return ConsoleResourceOperationStartBody(
        change=change,
        expected_fingerprint=preview.fingerprint,
        idempotency_key="confirmed-restart",
    )


async def activate(session: AsyncSession, plan_id: str) -> UserService:
    service, _, duplicate = await activate_service(
        session,
        user_id=2,
        actor_id=1,
        plan_id=plan_id,
        expected_revision=1,
        idempotency_key="activate",
    )
    assert not duplicate
    return service


def test_activation_commit_invalidates_the_confirmed_resource_preview() -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        plan_id, panel, _, writes = await prepare(factory)
        async with factory() as session:
            body = await confirmation(session, panel)

        async def first(session: AsyncSession) -> str:
            service_id = (await activate(session, plan_id)).id
            assert isinstance(service_id, str)
            return service_id

        async def second(session: AsyncSession) -> str:
            result = await start_resource_operation(session, panel, actor_id=1, body=body)
            operation_id = result.operation.id
            assert isinstance(operation_id, str)
            return operation_id

        service_id, result = await contend(factory, first, second)
        assert isinstance(result, ServiceConflict) and result.code == "resource_preview_changed"
        async with factory.begin() as session:
            assert await session.scalar(select(func.count()).select_from(ResourceOperation)) == 0
            assert await session.scalar(select(func.count()).select_from(UserService)) == 1
            refreshed = await confirmation(session, panel)
            assert refreshed.expected_fingerprint != body.expected_fingerprint
            accepted = await start_resource_operation(session, panel, actor_id=1, body=refreshed)
            assert accepted.operation.preview.affected_customer_ids == [2]
            assert accepted.operation.preview.affected_service_ids == [service_id]
        writes.assert_not_awaited()

    scenario(run)


def test_resource_submission_commit_blocks_concurrent_activation() -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        plan_id, panel, _, writes = await prepare(factory)
        async with factory() as session:
            body = await confirmation(session, panel)

        async def first(session: AsyncSession) -> str:
            result = await start_resource_operation(session, panel, actor_id=1, body=body)
            assert result.operation.preview.affected_service_ids == []
            operation_id = result.operation.id
            assert isinstance(operation_id, str)
            return operation_id

        async def second(session: AsyncSession) -> str:
            service_id = (await activate(session, plan_id)).id
            assert isinstance(service_id, str)
            return service_id

        operation_id, result = await contend(factory, first, second)
        assert isinstance(result, ServiceConflict)
        assert result.code == "resource_operation_in_progress"
        async with factory() as session:
            row = await session.get(ResourceOperation, operation_id)
            assert row is not None and row.status == "pending" and row.gate_key == "primary"
            assert row.attempt_count == 0 and row.attempts == []
            assert await session.scalar(select(func.count()).select_from(UserService)) == 0
            assert await session.scalar(select(func.count()).select_from(ServiceOrder)) == 0
            assert await session.scalar(select(func.count()).select_from(ResourceOperation)) == 1
        writes.assert_not_awaited()

    scenario(run)


def test_unknown_gate_survives_reconnect_but_allows_pause_ban_and_metering() -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        plan_id, panel, payloads, writes = await prepare(factory)
        reference = str(UUID(int=501))
        async with factory.begin() as session:
            service = await activate(session, plan_id)
            connection = await session.get(ServiceConnection, service.id)
            assert connection is not None
            connection.panel_user_uuid = reference
            connection.state = "ready"
            payloads["identity:" + reference] = {
                "ok": True,
                "user": {
                    "uuid": reference,
                    "username": connection.username,
                    "description": f"my_vps_obj:service:{service.id}",
                    "activeInternalSquads": [{"uuid": G1}],
                    "trafficLimitStrategy": "NO_RESET",
                    "userTraffic": {"usedTrafficBytes": 123, "lifetimeUsedTrafficBytes": 123},
                },
            }
        async with factory.begin() as session:
            body = await confirmation(session, panel)
            result = await start_resource_operation(session, panel, actor_id=1, body=body)
        operation_id = result.operation.id
        writes.side_effect = TimeoutError("simulated lost response")
        await run_resource_operation(factory, panel, operation_id)
        async with factory() as session:
            old_pid = await session.scalar(text("SELECT pg_backend_pid()"))
            operation = await session.get(ResourceOperation, operation_id)
            assert operation is not None and operation.status == "unknown"
            version = operation.version
        engine = factory.kw["bind"]
        assert isinstance(engine, AsyncEngine)
        await engine.dispose()
        async with factory() as session:
            assert await session.scalar(text("SELECT pg_backend_pid()")) != old_pid
            operation = await session.get(ResourceOperation, operation_id)
            assert operation is not None and operation.status == "unknown"
            assert operation.gate_key == "primary" and operation.attempt_count == 1

        with pytest.raises(ServiceConflict, match=r"^resource_operation_in_progress$"):
            async with factory.begin() as session:
                await activate_service(
                    session,
                    user_id=1,
                    actor_id=1,
                    plan_id=plan_id,
                    expected_revision=1,
                    idempotency_key="blocked-activation",
                )
        with pytest.raises(ServiceConflict, match=r"^resource_operation_in_progress$"):
            async with factory.begin() as session:
                await change_service(
                    session,
                    service_id=service.id,
                    user_id=2,
                    actor_id=1,
                    expected_revision=1,
                    idempotency_key="blocked-renewal",
                    change=ServiceChange(
                        action="renew", days=1, price=Decimal("0"), currency="CNY"
                    ),
                )
        async with asyncio.timeout(5):
            async with factory.begin() as session:
                paused, _, _ = await change_service(
                    session,
                    service_id=service.id,
                    user_id=2,
                    actor_id=1,
                    expected_revision=1,
                    idempotency_key="allowed-pause",
                    change=ServiceChange(action="pause"),
                )
            with pytest.raises(ServiceConflict, match=r"^resource_operation_in_progress$"):
                async with factory.begin() as session:
                    await change_service(
                        session,
                        service_id=service.id,
                        user_id=2,
                        actor_id=1,
                        expected_revision=paused.revision,
                        idempotency_key="blocked-resume",
                        change=ServiceChange(action="resume"),
                    )
            async with factory.begin() as session:
                await set_account_ban(session, user_id=2, actor_id=1, banned=True)
            await synchronize_service_usage(cast(sessionmaker, factory), service.id, panel)

        await run_pending_resource_operation(factory, panel)
        await run_resource_operation(factory, panel, operation_id)
        writes.assert_awaited_once()
        async with factory() as session:
            saved = await session.get(UserService, service.id)
            connection = await session.get(ServiceConnection, service.id)
            user = await session.get(User, 2)
            access = await session.get(AccountAccessSync, 2)
            operation = await session.get(ResourceOperation, operation_id)
            assert saved is not None and saved.desired_status == "paused" and saved.revision == 2
            assert saved.expires_at == service.expires_at and saved.last_usage_sync_at is not None
            assert connection is not None and connection.usage_error is None
            assert (
                saved.used_bytes
                == connection.usage_total_bytes
                == connection.usage_raw_bytes
                == 123
            )
            assert user is not None and user.is_banned
            assert access is not None and access.pending
            assert operation is not None and operation.status == "unknown"
            assert operation.version == version and operation.gate_key == "primary"
            assert operation.attempt_count == 1 and len(operation.attempts) == 1
            assert operation.attempts[0]["receipt"] == "unknown"
            assert await session.scalar(select(func.count()).select_from(UserService)) == 1
            assert await session.scalar(select(func.count()).select_from(ServiceOrder)) == 2

    scenario(run)


def test_external_host_removal_releases_gate_without_allowing_retry_or_recovery() -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        plan_id, panel, payloads, writes = await prepare(factory)
        hosts = cast(list[dict[str, object]], payloads["/hosts"])
        host = next(row for row in hosts if row["uuid"] == H1)
        change = ResourceHostChange(
            operation="host_update", target_id=UUID(H1), patch=ResourceHostPatch(port=8443)
        )
        async with factory.begin() as session:
            preview, _ = await stable_resource_preview(session, panel, change)
            assert preview.coverage == "complete" and not preview.blockers
            assert preview.fingerprint is not None
            accepted = await start_resource_operation(
                session,
                panel,
                actor_id=1,
                body=ConsoleResourceOperationStartBody(
                    change=change,
                    expected_fingerprint=preview.fingerprint,
                    idempotency_key="removed-host-update",
                ),
            )
        operation_id = accepted.operation.id

        async def lose_reply(*_args: object, **_kwargs: object) -> None:
            host["port"] = 8443
            raise TimeoutError("simulated lost response")

        writes.side_effect = lose_reply
        await run_resource_operation(factory, panel, operation_id)
        async with factory() as session:
            row = await session.get(ResourceOperation, operation_id)
            assert row is not None and row.status == "unknown" and row.gate_key == "primary"
            assert row.attempt_count == 1 and len(row.attempts) == 1
            assert row.attempts[0]["receipt"] == "unknown"
            before = operation_output(row).operation

        hosts.remove(host)
        with pytest.raises(ServiceConflict, match=r"^resource_operation_in_progress$"):
            async with factory.begin() as session:
                await activate(session, plan_id)
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(UserService)) == 0
            assert await session.scalar(select(func.count()).select_from(ServiceOrder)) == 0

        checked_at = datetime.now(UTC)
        async with factory.begin() as session:
            await accept_resource_evidence(
                session,
                panel,
                operation_id,
                actor_id=1,
                body=ConsoleResourceOperationEvidenceBody(
                    expected_version=before.version,
                    attempt=1,
                    result="externally_removed",
                    target_id=UUID(H1),
                    evidence_digest="a" * 64,
                    checked_at=checked_at,
                    original_request_terminated=True,
                ),
            )
        async with factory() as session:
            row = await session.get(ResourceOperation, operation_id)
            assert row is not None and row.gate_key is None
            assert row.attempt_count == 1
            closed = operation_output(row).operation
            assert closed.status == "failed" and closed.error_code == "resource_target_removed"
            assert not closed.gate_active and not closed.can_retry
            assert not closed.requires_manual_reconciliation and closed.completed_at is not None
            assert closed.target_id == H1 and closed.version > before.version
            assert closed.change == before.change and closed.preview == before.preview
            assert closed.attempts == before.attempts
            assert closed.observation is not None
            assert closed.observation.configuration == "missing"
            assert closed.observation.values is None and closed.observation.runtime == "unverified"
            assert closed.observation.observed_at >= checked_at
            assert len(closed.evidence) == 1
            evidence = closed.evidence[0]
            assert evidence.result == "externally_removed" and evidence.actor_id == 1
            assert evidence.attempt == 1 and evidence.target_id == H1
            assert evidence.evidence_digest == "a" * 64 and evidence.observed_at == checked_at
            assert evidence.original_request_terminated is True

        async with factory.begin() as session:
            service = await activate(session, plan_id)
        async with factory() as session:
            assert await session.get(UserService, service.id) is not None
            assert await session.scalar(select(func.count()).select_from(UserService)) == 1
            assert await session.scalar(select(func.count()).select_from(ServiceOrder)) == 1

        assert closed.preview.fingerprint is not None
        with pytest.raises(ServiceConflict, match=r"^resource_retry_not_allowed$"):
            async with factory.begin() as session:
                await retry_resource_operation(
                    session,
                    panel,
                    operation_id,
                    ConsoleResourceOperationRetryBody(
                        expected_version=closed.version,
                        expected_fingerprint=closed.preview.fingerprint,
                    ),
                )

        # A reappearing UUID must not make recovery of the removed operation valid.
        hosts.append(host)
        recovery = ResourceHostChange(
            operation="host_update", target_id=UUID(H1), patch=ResourceHostPatch(port=443)
        )
        async with factory() as session:
            preview, _ = await stable_resource_preview(session, panel, recovery)
            assert preview.coverage == "complete" and not preview.blockers
            assert preview.fingerprint is not None
            recovery_body = ConsoleResourceOperationStartBody(
                change=recovery,
                expected_fingerprint=preview.fingerprint,
                idempotency_key="forbidden-removed-host-recovery",
                recovery_of=operation_id,
            )
        with pytest.raises(ServiceConflict, match=r"^resource_recovery_invalid$"):
            async with factory.begin() as session:
                await start_resource_operation(session, panel, actor_id=1, body=recovery_body)

        await run_resource_operation(factory, panel, operation_id)
        writes.assert_awaited_once()
        async with factory() as session:
            row = await session.get(ResourceOperation, operation_id)
            assert row is not None and row.gate_key is None and row.attempt_count == 1
            assert operation_output(row).operation == closed
            assert await session.scalar(select(func.count()).select_from(ResourceOperation)) == 1

    scenario(run)


@pytest.mark.parametrize("lose_reply", [False, True], ids=["accepted", "unknown"])
def test_concurrent_workers_dispatch_once_while_another_transaction_commits_pause(
    lose_reply: bool,
) -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        plan_id, panel, _, writes = await prepare(factory)
        async with factory.begin() as session:
            service = await activate(session, plan_id)
        async with factory.begin() as session:
            body = await confirmation(session, panel)
            accepted = await start_resource_operation(session, panel, actor_id=1, body=body)
        operation_id = accepted.operation.id
        entered, waiting, release, paused = (
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
        )
        pids: dict[str, int] = {}

        class WorkerSession(Session):
            pass

        @event.listens_for(WorkerSession, "after_begin")
        def identify(
            session: Session, _transaction: SessionTransaction, connection: Connection
        ) -> None:
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("SET LOCAL statement_timeout = '10s'"))
            pid = connection.scalar(text("SELECT pg_backend_pid()"))
            assert isinstance(pid, int)
            role = session.info["resource_worker"]
            pids[role] = pid
            if role == "second":
                waiting.set()

        engine = factory.kw["bind"]
        assert isinstance(engine, AsyncEngine)

        def worker_sessions(role: str) -> async_sessionmaker[AsyncSession]:
            return async_sessionmaker(
                engine,
                expire_on_commit=False,
                autoflush=False,
                sync_session_class=WorkerSession,
                info={"resource_worker": role},
            )

        async def wire_attempt(method: str, path: str, **kwargs: object) -> dict[str, object]:
            assert method == "POST" and path == f"/nodes/{N1}/actions/restart"
            assert kwargs["preserve_http_status"] is True and kwargs["log_full_response"] is False
            entered.set()
            await release.wait()
            assert paused.is_set(), "The restriction must commit before the remote reply"
            if lose_reply:
                raise TimeoutError("simulated lost response")
            return {"status_code": 202}

        writes.side_effect = wire_attempt
        async with asyncio.timeout(15), asyncio.TaskGroup() as tasks:
            first = tasks.create_task(
                run_resource_operation(worker_sessions("first"), panel, operation_id)
            )
            await entered.wait()
            second = tasks.create_task(
                run_resource_operation(worker_sessions("second"), panel, operation_id)
            )
            await waiting.wait()
            assert pids["first"] != pids["second"]
            async with factory() as observer:
                while True:
                    blockers = await observer.scalar(
                        text("SELECT pg_blocking_pids(:pid)"), {"pid": pids["second"]}
                    )
                    if pids["first"] in blockers:
                        break
                    assert not second.done(), "The second worker must contend on the operation row"
            async with factory.begin() as session:
                await session.execute(text("SET LOCAL lock_timeout = '2s'"))
                await session.execute(text("SET LOCAL statement_timeout = '3s'"))
                await change_service(
                    session,
                    service_id=service.id,
                    user_id=2,
                    actor_id=1,
                    expected_revision=service.revision,
                    idempotency_key="pause-during-dispatch",
                    change=ServiceChange(action="pause"),
                )
            paused.set()
            async with factory() as observer:
                saved = await observer.get(UserService, service.id)
                operation = await observer.get(ResourceOperation, operation_id)
                assert saved is not None and saved.desired_status == "paused"
                assert operation is not None and operation.status == "unknown"
                assert operation.attempt_count == 1 and operation.gate_key == "primary"
            assert not first.done() and not second.done()
            writes.assert_awaited_once()
            release.set()

        await run_pending_resource_operation(factory, panel)
        await run_pending_resource_operation(factory, panel)
        await run_resource_operation(factory, panel, operation_id)
        writes.assert_awaited_once()
        async with factory() as session:
            operation = await session.get(ResourceOperation, operation_id)
            assert operation is not None
            assert operation.status == ("unknown" if lose_reply else "succeeded")
            assert operation.gate_key == ("primary" if lose_reply else None)
            assert operation.attempt_count == 1 and len(operation.attempts) == 1
            assert operation.attempts[0]["receipt"] == ("unknown" if lose_reply else "accepted")
            assert operation.attempted_at is not None
            assert operation.evidence == []
            assert await session.scalar(select(func.count()).select_from(ResourceOperation)) == 1

    scenario(run)


def test_0118_is_idempotent_and_database_constraints_protect_resource_intents() -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        _, panel, _, writes = await prepare(factory)
        async with factory.begin() as session:
            body = await confirmation(session, panel)
            accepted = await start_resource_operation(session, panel, actor_id=1, body=body)
        async with factory.begin() as session:
            connection = await session.connection()
            await connection.run_sync(upgrade_resources)
            await connection.run_sync(upgrade_resources)
        copy_row = (
            "INSERT INTO resource_operations "
            "(id, actor_id, idempotency_key, operation, request, preview, "
            "baseline_ids, fingerprint, "
            "status, gate_key, version, attempt_count, attempts, evidence, created_at) "
            "SELECT :other, actor_id, {key}, operation, request, preview, "
            "baseline_ids, fingerprint, "
            "{status}, {gate}, version, attempt_count, attempts, evidence, created_at "
            "FROM resource_operations WHERE id = :id"
        )
        checks = [
            (
                "UPDATE resource_operations SET version = 0 WHERE id = :id",
                "23514",
                "ck_resource_operation_counts",
            ),
            (
                "UPDATE resource_operations SET attempt_count = -1 WHERE id = :id",
                "23514",
                "ck_resource_operation_counts",
            ),
            (
                "UPDATE resource_operations SET gate_key = NULL WHERE id = :id",
                "23514",
                "ck_resource_operation_gate",
            ),
            (
                "UPDATE resource_operations SET status = 'unknown', gate_key = NULL WHERE id = :id",
                "23514",
                "ck_resource_operation_gate",
            ),
            (
                "UPDATE resource_operations SET status = 'succeeded' WHERE id = :id",
                "23514",
                "ck_resource_operation_gate",
            ),
            (
                copy_row.format(key="idempotency_key", status="'failed'", gate="NULL"),
                "23505",
                "uq_resource_operation_request",
            ),
            (
                copy_row.format(key="'another-request'", status="status", gate="gate_key"),
                "23505",
                "resource_operations_gate_key_key",
            ),
        ]
        for statement, sqlstate, constraint in checks:
            with pytest.raises(IntegrityError) as raised:
                async with factory.begin() as session:
                    await session.execute(
                        text(statement), {"id": accepted.operation.id, "other": "f" * 32}
                    )
            assert raised.value.orig is not None
            cause = raised.value.orig.__cause__
            assert isinstance(cause, PostgresError)
            assert cause.sqlstate == sqlstate and cause.constraint_name == constraint
        async with factory() as session:
            operation = await session.get(ResourceOperation, accepted.operation.id)
            assert operation is not None and operation.status == "pending"
            assert operation.version == 1 and operation.attempt_count == 0
            assert operation.gate_key == "primary" and operation.attempts == []
            assert operation.fingerprint == body.expected_fingerprint
            assert operation.request == body.change.model_dump(mode="json")
            assert operation.preview == accepted.operation.preview.model_dump(mode="json")
            assert await session.scalar(select(func.count()).select_from(ResourceOperation)) == 1
        writes.assert_not_awaited()

    scenario(run)
