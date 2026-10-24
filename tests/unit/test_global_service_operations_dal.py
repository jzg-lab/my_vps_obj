"""Global evidence filtering and paging use a single snapshot, without lazy loads."""

from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Literal

from sqlalchemy import delete, event, insert, select, text
from sqlalchemy.dialects import postgresql

from bot.app.web.admin_console_global_operations_schemas import ConsoleGlobalOperationOut
from config.service_periods import as_utc
from db.dal.global_service_operations_dal import (
    GlobalOperationRow,
    OperationFilters,
    OperationPosition,
    global_operations_statement,
    list_global_operation_records,
)
from db.models import User
from db.service_models import (
    ServiceConnection,
    ServiceOperationExecution,
    ServiceOrder,
    UserService,
)
from tests.unit.test_user_services import ServiceDatabaseTestCase

STAMP = datetime(2026, 1, 1, tzinfo=UTC)


class GlobalOperationDatabaseCase(ServiceDatabaseTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.first, _, _ = await self.activate("first")
        self.second, _, _ = await self.activate("second", user_id=2)
        self.archived, _, _ = await self.activate("archived")
        async with self.sessions.begin() as session:
            await session.execute(delete(ServiceOperationExecution))
            await session.execute(delete(ServiceOrder))
            archived = await session.get(UserService, self.archived.id)
            assert archived is not None
            archived.user_id = None
            for service in await session.scalars(select(UserService)):
                service.expires_at = datetime.now(UTC) + timedelta(days=90)
                service.terms = {**service.terms, "description": "NEVER_EXPOSE_TERMS"}
            for connection in await session.scalars(select(ServiceConnection)):
                connection.panel_user_uuid = "NEVER_EXPOSE_PANEL_" + connection.service_id[:10]

    async def add_record(
        self,
        number: int,
        *,
        service: UserService | None = None,
        record_type: Literal["execution", "order"] = "execution",
        status: str = "pending",
        phase: str = "prepare",
        kind: str = "activate",
        source: str = "worker",
        error: str | None = None,
        created_at: datetime = STAMP,
        order_id: str | None = None,
        completed_at: datetime | None = None,
    ) -> str:
        service = service or self.first
        record_id = f"{number:032x}"
        async with self.sessions.begin() as session:
            if record_type == "order":
                session.add(
                    ServiceOrder(
                        id=record_id,
                        service_id=service.id,
                        user_id=service.user_id,
                        request_owner_id=1,
                        actor_id=1,
                        kind=kind,
                        idempotency_key=f"NEVER_EXPOSE_KEY_{number}",
                        request={"secret": "NEVER_EXPOSE_REQUEST"},
                        snapshot={"secret": "NEVER_EXPOSE_SNAPSHOT"},
                        created_at=created_at,
                    )
                )
            else:
                session.add(
                    ServiceOperationExecution(
                        id=record_id,
                        service_id=service.id,
                        order_id=order_id,
                        request_owner_id=service.user_id or 1,
                        phase=phase,
                        target_revision=1,
                        source=source,
                        actor_id=1 if source == "administrator" else None,
                        status=status,
                        attempt_count=0 if status == "pending" else 1,
                        created_at=created_at,
                        error_code=error,
                        completed_at=completed_at,
                        attempted_at=None if status == "pending" else STAMP,
                        first_failed_at=STAMP if status == "failed" else None,
                    )
                )
        return record_id

    async def listing(
        self,
        filters: OperationFilters | None = None,
        *,
        limit: int = 25,
        after: OperationPosition | None = None,
    ) -> tuple[list[GlobalOperationRow], int, bool]:
        async with self.sessions() as session:
            rows, total, more = await list_global_operation_records(
                session, filters or OperationFilters(), limit=limit, after=after
            )
        return rows, total, more


class GlobalServiceOperationsTests(GlobalOperationDatabaseCase):
    async def test_cross_table_equal_ids_tied_times_and_empty_page_total(self) -> None:
        await self.add_record(1)
        await self.add_record(2)
        await self.add_record(1, record_type="order")
        await self.add_record(3, record_type="order")
        expected = [("execution", 1), ("execution", 2), ("order", 1), ("order", 3)]
        after = None
        for record_type, number in expected:
            rows, total, more = await self.listing(limit=1, after=after)
            assert total == 4 and len(rows) == 1
            assert (rows[0].position.record_type, rows[0].position.id) == (
                record_type,
                f"{number:032x}",
            )
            assert more == (number != 3)
            after = rows[-1].position
        rows, total, more = await self.listing(limit=1, after=after)
        assert (rows, total, more) == ([], 4, False)
        assert (await self.listing(OperationFilters(user_id=99)))[1] == 0

    async def test_insert_before_cursor_does_not_shift_next_page(self) -> None:
        await self.add_record(1)
        await self.add_record(2, created_at=STAMP - timedelta(seconds=1))
        rows, _, _ = await self.listing(limit=1)
        await self.add_record(3, created_at=STAMP + timedelta(seconds=1))
        remaining, total, more = await self.listing(limit=1, after=rows[0].position)
        assert [row.position.id for row in remaining] == [f"{2:032x}"]
        assert total == 3 and not more

    async def test_exact_filters_attention_and_legacy_semantics(self) -> None:
        await self.add_record(1)
        await self.add_record(2, status="pending", error="panel_usage_unavailable")
        await self.add_record(3, status="unknown", service=self.second, phase="usage")
        await self.add_record(4, status="failed", phase="revocation", service=self.archived)
        await self.add_record(5, status="succeeded", phase="entitlement")
        await self.add_record(6, status="superseded", phase="delivery")
        await self.add_record(7, record_type="order")
        cases = [
            (OperationFilters(), [1, 2, 3, 4, 5, 6, 7]),
            (OperationFilters(needs_attention=True), [2, 3, 4]),
            (OperationFilters(status="unknown"), [3, 7]),
            (OperationFilters(status="pending"), [1, 2]),
            (OperationFilters(status="failed"), [4]),
            (OperationFilters(status="succeeded"), [5]),
            (OperationFilters(status="superseded"), [6]),
            (OperationFilters(phase="prepare"), [1, 2]),
            (OperationFilters(phase="delivery"), [6]),
            (OperationFilters(phase="entitlement"), [5]),
            (OperationFilters(phase="revocation"), [4]),
            (OperationFilters(phase="usage"), [3]),
            (OperationFilters(user_id=1), [1, 2, 5, 6, 7]),
            (OperationFilters(archived="only"), [4]),
            (OperationFilters(archived="exclude"), [1, 2, 3, 5, 6, 7]),
            (OperationFilters(user_id=1, archived="only"), []),
            (
                OperationFilters(
                    status="unknown",
                    phase="usage",
                    user_id=2,
                    service_id=self.second.id,
                    archived="exclude",
                    needs_attention=True,
                ),
                [3],
            ),
        ]
        for filters, expected in cases:
            with self.subTest(filters=filters):
                rows, total, _ = await self.listing(filters)
                assert total == len(expected)
                assert [row.position.id for row in rows] == [
                    f"{number:032x}" for number in expected
                ]
        rows, _, _ = await self.listing()
        legacy = ConsoleGlobalOperationOut.from_row(rows[-1])
        assert legacy.status == legacy.source == "unknown"
        assert legacy.phase is legacy.attempt_count is legacy.attempted_at is None
        assert not legacy.needs_attention and not legacy.retryable

    async def test_current_owner_and_archived_null_identity_ignore_order_owner(self) -> None:
        order_id = await self.add_record(1, record_type="order")
        await self.add_record(2, order_id=order_id, source="administrator")
        await self.add_record(3, service=self.archived, status="failed")
        async with self.sessions.begin() as session:
            service = await session.get(UserService, self.first.id)
            user = await session.get(User, 2)
            assert service and user
            service.user_id = 2
            user.first_name = "Current owner"
        assert (await self.listing(OperationFilters(user_id=1)))[1] == 0
        rows, total, _ = await self.listing(OperationFilters(user_id=2))
        assert total == 1
        result = ConsoleGlobalOperationOut.from_row(rows[0])
        assert result.customer.user_id == 2 and result.customer.first_name == "Current owner"
        assert result.retry_block_reason == "idempotency_owner_changed"
        assert result.source == "administrator" and result.actor_id == 1
        rows, total, _ = await self.listing(OperationFilters(archived="only", needs_attention=True))
        archived = ConsoleGlobalOperationOut.from_row(rows[0])
        assert total == 1 and archived.archived
        assert set(archived.customer.model_dump().values()) == {None}
        assert archived.retry_block_reason == "service_not_editable"

    async def test_execution_replaces_order_and_retry_order_is_not_new_operation(self) -> None:
        order_id = await self.add_record(1, record_type="order", kind="pause")
        await self.add_record(2, order_id=order_id, phase="entitlement")
        await self.add_record(3, record_type="order", kind="retry")
        rows, total, _ = await self.listing()
        assert total == 1 and rows[0].order and rows[0].order.id == order_id
        assert ConsoleGlobalOperationOut.from_row(rows[0]).kind == "pause"

    async def test_last_success_is_same_service_and_phase_even_when_filtered_out(self) -> None:
        await self.add_record(1, status="failed")
        await self.add_record(2, status="succeeded", completed_at=STAMP)
        later = STAMP + timedelta(seconds=2)
        await self.add_record(3, status="succeeded", completed_at=later)
        await self.add_record(
            4, status="succeeded", phase="usage", completed_at=later + timedelta(days=1)
        )
        await self.add_record(
            5, status="succeeded", service=self.second, completed_at=later + timedelta(days=2)
        )
        await self.add_record(6, record_type="order")
        rows, total, _ = await self.listing(OperationFilters(needs_attention=True), limit=1)
        assert total == 1 and as_utc(rows[0].last_success_at) == later
        assert ConsoleGlobalOperationOut.from_row(rows[0]).first_failed_at == STAMP
        legacy, _, _ = await self.listing(OperationFilters(status="unknown"))
        assert legacy[0].last_success_at is None

    async def test_all_retry_phases_are_detached_safe_and_delivery_requires_order(self) -> None:
        for number, phase in enumerate(
            ("prepare", "delivery", "entitlement", "revocation", "usage"), 1
        ):
            await self.add_record(number, phase=phase, error="panel_usage_unavailable")
        rows, _, _ = await self.listing()
        outputs = {row.phase: row for row in map(ConsoleGlobalOperationOut.from_row, rows)}
        assert outputs["prepare"].retryable
        assert outputs["delivery"].retry_block_reason == "operation_not_retryable"
        await self.add_record(6, record_type="order", kind="deliver")
        rows, _, _ = await self.listing(OperationFilters(phase="delivery"))
        assert ConsoleGlobalOperationOut.from_row(rows[0]).retryable
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, self.first.id)
            assert connection
            connection.sync_pending = True
            connection.usage_error = "panel_usage_unavailable"
        rows, _, _ = await self.listing()
        outputs = {row.phase: row for row in map(ConsoleGlobalOperationOut.from_row, rows)}
        assert outputs["entitlement"].retryable and outputs["usage"].retryable
        async with self.sessions.begin() as session:
            service = await session.get(UserService, self.first.id)
            connection = await session.get(ServiceConnection, self.first.id)
            assert service and connection
            service.desired_status = "cancelled"
            connection.revoke_requested_at = STAMP
        rows, _, _ = await self.listing(OperationFilters(phase="revocation"))
        assert ConsoleGlobalOperationOut.from_row(rows[0]).retryable

    async def test_one_statement_no_secret_loading_and_scale_plan(self) -> None:
        order_id = await self.add_record(1, record_type="order")
        await self.add_record(1, order_id=order_id, error="NEVER_EXPOSE_ERROR")
        async with self.sessions.begin() as session:
            await session.execute(
                insert(ServiceOperationExecution),
                [
                    {
                        "id": f"{number:032x}",
                        "service_id": self.first.id,
                        "request_owner_id": 1,
                        "phase": "prepare",
                        "target_revision": 1,
                        "source": "worker",
                        "status": "pending",
                        "attempt_count": 0,
                        "created_at": STAMP,
                    }
                    for number in range(2, 10001)
                ],
            )
            await session.execute(
                insert(ServiceOrder),
                [
                    {
                        "id": f"{number:032x}",
                        "service_id": self.first.id,
                        "user_id": 1,
                        "request_owner_id": 1,
                        "actor_id": 1,
                        "kind": "activate",
                        "idempotency_key": f"scale:{number}",
                        "request": {},
                        "snapshot": {},
                        "created_at": STAMP,
                    }
                    for number in range(2, 10001)
                ],
            )
        statements: list[str] = []

        def capture(_conn, _cursor, statement, _parameters, _context, _many):
            statements.append(statement)

        event.listen(self.engine.sync_engine, "before_cursor_execute", capture)
        try:
            for limit in (1, 25, 200):
                statements.clear()
                started = perf_counter()
                rows, total, more = await self.listing(limit=limit)
                payloads = [ConsoleGlobalOperationOut.from_row(row) for row in rows]
                elapsed = perf_counter() - started
                assert len(statements) == 1 and total == 19999 and more
                assert len(payloads) == limit and "NEVER_EXPOSE" not in str(payloads)
                assert rows[0].order is not None
                assert "request" not in rows[0].order.__dict__
                assert "snapshot" not in rows[0].order.__dict__
                assert "terms" not in rows[0].service.__dict__
                print(
                    f"SQLite 10000 executions + 10000 orders: limit={limit}, "
                    f"total={total}, SQL=1, seconds={elapsed:.4f}"
                )
        finally:
            event.remove(self.engine.sync_engine, "before_cursor_execute", capture)
        statement = global_operations_statement(OperationFilters(), limit=25)
        postgres_sql = str(statement.compile(dialect=postgresql.dialect()))
        assert "service_orders.request" not in postgres_sql
        assert "service_orders.snapshot" not in postgres_sql
        assert "operation_total" in postgres_sql and "filtered_operations" in postgres_sql
        compiled = statement.compile(
            dialect=self.engine.dialect, compile_kwargs={"literal_binds": True}
        )
        async with self.engine.connect() as connection:
            plan = (await connection.execute(text("EXPLAIN QUERY PLAN " + str(compiled)))).all()
        print("SQLite query plan:", "\n".join(str(row[-1]) for row in plan))

    async def test_pending_session_changes_are_not_flushed_by_read(self) -> None:
        await self.add_record(1)
        async with self.sessions() as session:
            session.autoflush = True
            service = await session.get(UserService, self.first.id)
            assert service
            service.revision = 50
            rows, total, _ = await list_global_operation_records(
                session, OperationFilters(), limit=25
            )
            assert total == 1 and rows[0].service.revision == 1
            await session.rollback()
