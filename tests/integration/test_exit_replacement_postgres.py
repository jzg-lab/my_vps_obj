"""Replacement holds on disposable PostgreSQL; collection never opens a database."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from uuid import UUID

import pytest
from asyncpg.exceptions import PostgresError
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from config.service_exit_replacement import (
    ReplacementBindingObservation,
    ReplacementCandidateEvidence,
    ReplacementRequest,
    ReplacementStopEvidence,
)
from db.dal.service_exit_replacement_dal import (
    accept_replacement_stop,
    bind_replacement_exit,
    confirm_exit_replacement,
    lock_replacement,
    reserve_exit_replacement,
    verify_replacement_candidate,
)
from db.dal.user_services_dal import ServiceConflict, activate_service, save_plan
from db.service_models import (
    DedicatedExit,
    DedicatedExitAudit,
    ServiceConnection,
    ServiceOperationExecution,
    ServiceOrder,
    UserService,
)
from tests.integration.test_user_services_postgres import DATABASE_URL, scenario
from tests.unit.test_user_services import sample_terms

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="Disposable PostgreSQL URL is required")
DIGEST = "a" * 64


@dataclass(frozen=True)
class ReplacementFixture:
    plan_id: str
    services: tuple[UserService, UserService]
    requests: tuple[ReplacementRequest, ReplacementRequest]


async def seed(factory: async_sessionmaker[AsyncSession]) -> ReplacementFixture:
    # scenario applies 0117 twice and verifies its columns before creating this fixture.
    async with factory.begin() as session:
        plan = await save_plan(
            session,
            terms=sample_terms(resource_type="dedicated", squad_uuids=[], resource_pool="private"),
            enabled=True,
            actor_id=1,
        )
        exits = [
            DedicatedExit(
                id=f"{index:032x}",
                revision=1,
                label=f"PostgreSQL exit {index}",
                ip_address=f"192.0.2.{index}",
                resource_pool="private",
                squad_uuid=str(UUID(int=index)),
                enabled=True,
                verified_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
            )
            for index in (1, 2, 3)
        ]
        session.add_all(exits)
        await session.flush()
        services = []
        requests = []
        for owner, old in zip((1, 2), exits[:2], strict=True):
            service, _, _ = await activate_service(
                session,
                user_id=owner,
                actor_id=1,
                plan_id=plan.id,
                expected_revision=1,
                idempotency_key="activate-original",
                exit_id=old.id,
            )
            connection = await session.get(ServiceConnection, service.id)
            assert connection is not None
            connection.panel_user_uuid = str(UUID(int=100 + owner))
            connection.state = "ready"
            connection.usage_total_bytes = 123
            connection.usage_raw_bytes = 123
            connection.usage_lifetime_offset = 0
            service.used_bytes = 123
            service.last_usage_sync_at = datetime.now(UTC)
            services.append(service)
            requests.append(
                ReplacementRequest(
                    expected_revision=service.revision,
                    old_exit_id=old.id,
                    new_exit_id=exits[2].id,
                    expected_old_exit_revision=old.revision,
                    expected_new_exit_revision=exits[2].revision,
                    resource_fingerprint=DIGEST,
                    reason="Disposable PostgreSQL replacement test",
                )
            )
        return ReplacementFixture(plan.id, (services[0], services[1]), (requests[0], requests[1]))


async def reserve(
    session: AsyncSession, fixture: ReplacementFixture, index: int = 0
) -> tuple[ServiceOperationExecution, bool]:
    service = fixture.services[index]
    assert service.user_id is not None
    operation, duplicate = await reserve_exit_replacement(
        session,
        service_id=service.id,
        user_id=service.user_id,
        actor_id=1,
        idempotency_key="replace-once",
        request=fixture.requests[index],
    )
    return operation, duplicate


async def snapshot(session: AsyncSession, service_id: str) -> list[dict[str, object]]:
    return [
        dict((await session.execute(statement)).mappings().one())
        for statement in (
            select(UserService.__table__).where(UserService.id == service_id),
            select(ServiceConnection.__table__).where(ServiceConnection.service_id == service_id),
            select(DedicatedExit.__table__).where(DedicatedExit.service_id == service_id),
        )
    ]


async def contend[First, Second](
    factory: async_sessionmaker[AsyncSession],
    first: Callable[[AsyncSession], Awaitable[First]],
    second: Callable[[AsyncSession], Awaitable[Second]],
) -> tuple[First, Second | ServiceConflict]:
    held, waiting, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    pids: dict[str, int] = {}

    async def identify(session: AsyncSession, role: str) -> None:
        await session.execute(text("SET LOCAL lock_timeout = '5s'"))
        await session.execute(text("SET LOCAL statement_timeout = '10s'"))
        pid = await session.scalar(text("SELECT pg_backend_pid()"))
        assert isinstance(pid, int)
        pids[role] = pid

    async def holder() -> First:
        async with factory.begin() as session:
            await identify(session, "holder")
            result = await first(session)
            held.set()
            await release.wait()
        return result

    async def waiter() -> Second | ServiceConflict:
        await held.wait()
        try:
            async with factory.begin() as session:
                await identify(session, "waiter")
                waiting.set()
                return await second(session)
        except ServiceConflict as exc:
            return exc

    async with asyncio.timeout(15), asyncio.TaskGroup() as tasks:
        first_task = tasks.create_task(holder())
        second_task = tasks.create_task(waiter())
        await waiting.wait()
        assert pids["holder"] != pids["waiter"]
        async with factory() as observer:
            while True:
                blockers = await observer.scalar(
                    text("SELECT pg_blocking_pids(:pid)"), {"pid": pids["waiter"]}
                )
                if pids["holder"] in blockers:
                    break
                assert not second_task.done(), "Contender finished without waiting on the holder"
        # Release only after PostgreSQL proves the second transaction is blocked by the first.
        assert not second_task.done()
        release.set()
    return first_task.result(), second_task.result()


async def assert_single_reservation(session: AsyncSession, operation_id: str) -> None:
    operation = await session.get(ServiceOperationExecution, operation_id)
    assert operation and operation.phase == "exit_replace" and operation.order_id
    assert (
        await session.scalar(
            select(func.count())
            .select_from(ServiceOrder)
            .where(ServiceOrder.kind == "replace_exit")
        )
        == 1
    )
    assert (
        await session.scalar(
            select(func.count())
            .select_from(ServiceOperationExecution)
            .where(ServiceOperationExecution.phase == "exit_replace")
        )
        == 1
    )
    held = (
        await session.scalars(select(DedicatedExit).where(DedicatedExit.hold_order_id.is_not(None)))
    ).one()
    assert held.hold_order_id == operation.order_id and held.service_id is None
    gate = (
        await session.scalars(
            select(ServiceConnection).where(
                ServiceConnection.replacement_order_id == operation.order_id
            )
        )
    ).one()
    assert gate.service_id == operation.service_id
    assert (
        await session.scalar(
            select(func.count())
            .select_from(DedicatedExitAudit)
            .where(DedicatedExitAudit.action == "replace_reserve")
        )
        == 1
    )


@pytest.mark.parametrize("winner", [0, 1], ids=["owner-1-first", "owner-2-first"])
def test_cross_owner_reservations_have_one_winner_and_preserve_loser(winner: int) -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        fixture = await seed(factory)
        loser = 1 - winner
        async with factory() as session:
            before = await snapshot(session, fixture.services[loser].id)
        (operation, duplicate), rejected = await contend(
            factory,
            partial(reserve, fixture=fixture, index=winner),
            partial(reserve, fixture=fixture, index=loser),
        )
        assert not duplicate and isinstance(rejected, ServiceConflict)
        assert str(rejected) == "exit_revision_changed"
        async with factory() as session:
            await assert_single_reservation(session, operation.id)
            assert await snapshot(session, fixture.services[loser].id) == before
            for index, service in enumerate(fixture.services):
                current = await session.get(DedicatedExit, fixture.requests[index].old_exit_id)
                assert (
                    current and current.service_id == service.id and current.hold_order_id is None
                )
            order = await session.get(ServiceOrder, operation.order_id)
            assert order and order.service_id == fixture.services[winner].id
            assert order.request_owner_id == fixture.services[winner].user_id
            assert await session.scalar(select(func.count()).select_from(UserService)) == 2
            assert await session.scalar(select(func.count()).select_from(ServiceOrder)) == 3

    scenario(run)


def test_same_owner_key_reservations_replay_one_order_operation_and_hold() -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        fixture = await seed(factory)
        first, second = await contend(
            factory, partial(reserve, fixture=fixture), partial(reserve, fixture=fixture)
        )
        assert not isinstance(second, ServiceConflict)
        assert first[0].id == second[0].id and first[1] is False and second[1] is True
        async with factory.begin() as session:
            replay, duplicate = await reserve(session, fixture)
            assert duplicate and replay.id == first[0].id
        async with factory() as session:
            await assert_single_reservation(session, first[0].id)
            assert await session.scalar(select(func.count()).select_from(ServiceOrder)) == 3
            assert (
                await session.scalar(select(func.count()).select_from(ServiceOperationExecution))
                == 3
            )
            service = await session.get(UserService, fixture.services[0].id)
            assert service and service.revision == fixture.services[0].revision + 1
            current = await session.get(DedicatedExit, fixture.requests[0].old_exit_id)
            assert current and current.service_id == service.id and current.hold_order_id is None

    scenario(run)


@pytest.mark.parametrize("reserve_first", [True, False], ids=["hold-wins", "activation-wins"])
def test_reservation_and_activation_cannot_allocate_the_same_candidate(reserve_first: bool) -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        fixture = await seed(factory)
        async with factory() as session:
            before = await snapshot(session, fixture.services[0].id)

        async def activate(session: AsyncSession) -> tuple[UserService, bool]:
            service, _, duplicate = await activate_service(
                session,
                user_id=2,
                actor_id=1,
                plan_id=fixture.plan_id,
                expected_revision=1,
                idempotency_key="activate-candidate",
                exit_id=fixture.requests[0].new_exit_id,
            )
            return service, duplicate

        if reserve_first:
            (operation, duplicate), activation_rejected = await contend(
                factory, partial(reserve, fixture=fixture), activate
            )
            assert not duplicate and isinstance(activation_rejected, ServiceConflict)
            assert activation_rejected.code == "exit_unavailable"
            async with factory() as session:
                await assert_single_reservation(session, operation.id)
                assert await session.scalar(select(func.count()).select_from(UserService)) == 2
                assert await session.scalar(select(func.count()).select_from(ServiceOrder)) == 3
                assert (
                    await session.scalar(
                        select(ServiceOrder.id).where(
                            ServiceOrder.idempotency_key == "activate-candidate"
                        )
                    )
                    is None
                )
        else:
            (activated, duplicate), reserve_rejected = await contend(
                factory, activate, partial(reserve, fixture=fixture)
            )
            assert not duplicate and isinstance(reserve_rejected, ServiceConflict)
            assert reserve_rejected.code == "exit_revision_changed"
            async with factory() as session:
                assert await snapshot(session, fixture.services[0].id) == before
                candidate = await session.get(DedicatedExit, fixture.requests[0].new_exit_id)
                assert candidate and candidate.service_id == activated.id
                assert candidate.hold_order_id is None and activated.user_id == 2
                assert await session.scalar(select(func.count()).select_from(UserService)) == 3
                assert await session.scalar(select(func.count()).select_from(ServiceOrder)) == 3
                assert (
                    await session.scalar(
                        select(ServiceOperationExecution.id).where(
                            ServiceOperationExecution.phase == "exit_replace"
                        )
                    )
                    is None
                )

    scenario(run)


class BindingRollback(RuntimeError):
    pass


@pytest.mark.parametrize("after_new_binding", [False, True], ids=["old-flush", "new-flush"])
def test_binding_flush_rollback_preserves_old_binding_and_candidate_hold(
    after_new_binding: bool,
) -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        fixture = await seed(factory)
        service_id = fixture.services[0].id
        async with factory.begin() as session:
            operation, _ = await reserve(session, fixture)
        async with factory.begin() as session:
            state = await lock_replacement(
                session, service_id=service_id, user_id=1, operation_id=operation.id
            )
            observed = datetime.now(UTC)
            state.service.last_usage_sync_at = observed
            await accept_replacement_stop(
                session,
                state,
                actor_id=1,
                expected_version=state.progress.version,
                idempotency_key="stop",
                evidence=ReplacementStopEvidence(
                    resource_fingerprint=DIGEST,
                    stopped_at=observed,
                    usage_observed_at=observed,
                    stop_provenance="administrator",
                    usage_provenance="administrator",
                    stop_report_digest=DIGEST,
                    usage_report_digest=DIGEST,
                    authorization_removed=True,
                    connections_stopped=True,
                    old_config_rejected=True,
                    usage_total_bytes=123,
                    usage_raw_bytes=123,
                    usage_lifetime_offset=0,
                ),
            )
            await verify_replacement_candidate(
                session,
                state,
                actor_id=1,
                expected_version=state.progress.version,
                idempotency_key="verify",
                evidence=ReplacementCandidateEvidence(
                    resource_fingerprint=DIGEST,
                    checked_at=datetime.now(UTC),
                    observed_ip=state.new_exit.ip_address,
                    provenance="administrator",
                    report_digest=DIGEST,
                    fixed=True,
                    exclusive=True,
                ),
            )
            await confirm_exit_replacement(
                session,
                state,
                actor_id=1,
                expected_version=state.progress.version,
                expected_service_revision=state.service.revision,
                resource_fingerprint=DIGEST,
                idempotency_key="confirm",
            )
            assert state.progress.stage == "switching"
            saved_progress = state.execution.replacement_progress
            order_id = state.order.id
        async with factory() as session:
            before = await snapshot(session, service_id)
            held_before = dict(
                (
                    await session.execute(
                        select(DedicatedExit.__table__).where(
                            DedicatedExit.id == fixture.requests[0].new_exit_id
                        )
                    )
                )
                .mappings()
                .one()
            )

        fault_seen = False

        def rollback_after_flush(sync_session: Session, _context: object) -> None:
            nonlocal fault_seen
            rows = dict(
                sync_session.execute(select(DedicatedExit.id, DedicatedExit.service_id))
                .tuples()
                .all()
            )
            new_bound = rows[fixture.requests[0].new_exit_id] == service_id
            if rows[fixture.requests[0].old_exit_id] is None and new_bound == after_new_binding:
                holds = dict(
                    sync_session.execute(select(DedicatedExit.id, DedicatedExit.hold_order_id))
                    .tuples()
                    .all()
                )
                assert holds[fixture.requests[0].old_exit_id] == order_id
                assert holds[fixture.requests[0].new_exit_id] == (None if new_bound else order_id)
                fault_seen = True
                raise BindingRollback("Injected failure after persisted binding flush")

        with pytest.raises(BindingRollback, match="persisted binding flush"):
            async with factory.begin() as session:
                state = await lock_replacement(
                    session, service_id=service_id, user_id=1, operation_id=operation.id
                )
                observed = datetime.now(UTC)
                state.service.last_usage_sync_at = observed
                await session.flush()
                assert state.connection.panel_user_uuid is not None
                observation = ReplacementBindingObservation(
                    resource_fingerprint=DIGEST,
                    panel_user_uuid=state.connection.panel_user_uuid,
                    username=state.connection.username,
                    description=f"my_vps_obj:service:{service_id}",
                    group_ids=[state.new_exit.squad_uuid],
                    status="DISABLED",
                    observed_at=observed,
                    report_digest=DIGEST,
                    usage_total_bytes=123,
                    usage_raw_bytes=123,
                    usage_lifetime_offset=0,
                )
                event.listen(session.sync_session, "after_flush_postexec", rollback_after_flush)
                try:
                    await bind_replacement_exit(
                        session,
                        state,
                        actor_id=1,
                        expected_version=state.progress.version,
                        idempotency_key="bind",
                        observation=observation,
                    )
                finally:
                    event.remove(session.sync_session, "after_flush_postexec", rollback_after_flush)
        assert fault_seen, "Failure must occur after a real PostgreSQL binding flush"
        async with factory() as session:
            assert await snapshot(session, service_id) == before
            held_after = dict(
                (
                    await session.execute(
                        select(DedicatedExit.__table__).where(
                            DedicatedExit.id == fixture.requests[0].new_exit_id
                        )
                    )
                )
                .mappings()
                .one()
            )
            assert held_after == held_before
            saved = await session.get(ServiceOperationExecution, operation.id)
            assert saved and saved.replacement_progress == saved_progress
            assert (
                await session.scalar(
                    select(DedicatedExitAudit.id).where(DedicatedExitAudit.action == "replace_bind")
                )
                is None
            )

    scenario(run)


@pytest.mark.parametrize(
    ("statement", "sqlstate", "constraint"),
    [
        pytest.param(
            "UPDATE dedicated_exits SET hold_order_id = :missing WHERE id = :candidate",
            "23503",
            "fk_dedicated_exit_hold",
            id="hold-fk",
        ),
        pytest.param(
            "UPDATE service_connections SET replacement_order_id = :missing "
            "WHERE service_id = :service",
            "23503",
            "fk_service_connection_replacement",
            id="gate-fk",
        ),
        pytest.param(
            "UPDATE dedicated_exits SET hold_order_id = :order WHERE id = :old",
            "23514",
            "ck_dedicated_exit_binding_hold",
            id="bound-and-held-check",
        ),
        pytest.param(
            "UPDATE service_operation_executions SET replacement_progress = NULL "
            "WHERE id = :operation",
            "23514",
            "ck_service_execution_replacement",
            id="missing-progress-check",
        ),
        pytest.param(
            "UPDATE service_operation_executions SET replacement_progress = '{}' "
            "WHERE phase = 'prepare' AND service_id = :service",
            "23514",
            "ck_service_execution_replacement",
            id="unrelated-progress-check",
        ),
        pytest.param(
            "UPDATE service_operation_executions SET phase = 'invented', "
            "replacement_progress = NULL WHERE id = :operation",
            "23514",
            "ck_service_execution_phase",
            id="phase-check",
        ),
        pytest.param(
            "UPDATE dedicated_exits SET hold_order_id = NULL, service_id = :service "
            "WHERE id = :candidate",
            "23505",
            "dedicated_exits_service_id_key",
            id="binding-unique",
        ),
        pytest.param(
            "UPDATE service_connections SET replacement_order_id = :order "
            "WHERE service_id = :other_service",
            "23505",
            "uq_service_connection_replacement",
            id="gate-unique",
        ),
        pytest.param(
            "INSERT INTO service_orders (id, user_id, request_owner_id, service_id, actor_id, "
            "kind, idempotency_key, request, snapshot, created_at) "
            "SELECT :missing, user_id, request_owner_id, service_id, actor_id, kind, "
            "idempotency_key, request, snapshot, created_at FROM service_orders WHERE id = :order",
            "23505",
            "uq_service_order_request_key",
            id="owner-key-unique",
        ),
        pytest.param(
            "INSERT INTO service_operation_executions (id, service_id, order_id, request_owner_id, "
            "phase, target_revision, source, actor_id, status, attempt_count, created_at, "
            "replacement_progress) SELECT :missing, service_id, order_id, request_owner_id, "
            "phase, target_revision, source, actor_id, status, attempt_count, created_at, "
            "replacement_progress FROM service_operation_executions WHERE id = :operation",
            "23505",
            "service_operation_executions_order_id_key",
            id="order-operation-unique",
        ),
    ],
)
def test_raw_sql_cannot_bypass_replacement_constraints(
    statement: str, sqlstate: str, constraint: str
) -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        fixture = await seed(factory)
        async with factory.begin() as session:
            operation, _ = await reserve(session, fixture)
        params = {
            "missing": "f" * 32,
            "candidate": fixture.requests[0].new_exit_id,
            "old": fixture.requests[0].old_exit_id,
            "service": fixture.services[0].id,
            "other_service": fixture.services[1].id,
            "order": operation.order_id,
            "operation": operation.id,
        }
        with pytest.raises(IntegrityError) as raised:
            async with factory.begin() as session:
                await session.execute(text(statement), params)
        # Assert the database's precise failure, not just an arbitrary failed transaction.
        assert raised.value.orig is not None
        cause = raised.value.orig.__cause__
        assert isinstance(cause, PostgresError)
        assert cause.sqlstate == sqlstate
        assert cause.constraint_name == constraint
        async with factory() as session:
            await assert_single_reservation(session, operation.id)
            current = await session.get(DedicatedExit, fixture.requests[0].old_exit_id)
            assert current and current.service_id == fixture.services[0].id

    scenario(run)
