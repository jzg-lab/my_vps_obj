"""PostgreSQL compatibility and scale evidence, confined to a disposable schema."""

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, event, insert, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.app.web.admin_console_global_operations_schemas import (
    ConsoleGlobalOperationOut,
    ConsoleGlobalOperationsQuery,
)
from db.dal.global_service_operations_dal import (
    OperationFilters,
    OperationPosition,
    global_operations_statement,
    list_global_operation_records,
)
from db.dal.user_services_dal import save_plan
from db.models import Base, User
from db.service_models import ServiceOperationExecution, ServiceOrder, UserService
from tests.unit.test_user_services import sample_terms

DATABASE_URL = os.environ.get("CORE_PERFORMANCE_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="Disposable PostgreSQL URL is required")
STAMP = datetime(2026, 1, 1, tzinfo=UTC)


@asynccontextmanager
async def isolated_sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    schema = "global_operations_test_" + uuid4().hex
    admin = create_async_engine(DATABASE_URL)
    engine = create_async_engine(
        DATABASE_URL, connect_args={"server_settings": {"search_path": schema}}
    )
    created = False
    try:
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
        async with engine.begin() as connection:
            assert await connection.scalar(text("SELECT current_schema()")) == schema
            await connection.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    finally:
        await engine.dispose()
        try:
            if created:
                async with admin.begin() as connection:
                    await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
                    assert (
                        await connection.scalar(
                            text("SELECT count(*) FROM pg_namespace WHERE nspname=:schema"),
                            {"schema": schema},
                        )
                        == 0
                    )
                print(f"Cleaned disposable schema: {schema}")
        finally:
            await admin.dispose()


def test_postgres_filters_pagination_and_explain_scale() -> None:
    async def run() -> None:
        async with isolated_sessions() as sessions:
            async with sessions.begin() as session:
                session.add_all([User(user_id=1), User(user_id=2)])
                await session.flush()
                plan = await save_plan(session, terms=sample_terms(), enabled=True, actor_id=1)
                await session.execute(
                    insert(UserService),
                    [
                        {
                            "id": f"{number:032x}",
                            "user_id": None if number % 10 == 0 else 1 + number % 2,
                            "plan_id": plan.id,
                            "plan_revision": 1,
                            "revision": 1,
                            "terms": sample_terms().model_dump(mode="json"),
                            "quota_bytes": 10000,
                            "used_bytes": 0,
                            "starts_at": STAMP,
                            "expires_at": datetime.now(UTC) + timedelta(days=90),
                            "desired_status": "active",
                            "created_at": STAMP,
                        }
                        for number in range(100)
                    ],
                )
            for size in (1000, 10000):
                async with sessions.begin() as session:
                    await session.execute(delete(ServiceOperationExecution))
                    await session.execute(delete(ServiceOrder))
                    await session.execute(
                        insert(ServiceOrder),
                        [
                            {
                                "id": f"{number:032x}",
                                "service_id": f"{number % 100:032x}",
                                "user_id": 1,
                                "request_owner_id": 1,
                                "actor_id": 1,
                                "kind": "retry" if number % 11 == 0 else "activate",
                                "idempotency_key": f"key:{number}",
                                "request": {"secret": "NEVER_EXPOSE"},
                                "snapshot": {"secret": "NEVER_EXPOSE"},
                                "created_at": STAMP,
                            }
                            for number in range(size)
                        ],
                    )
                    await session.execute(
                        insert(ServiceOperationExecution),
                        [
                            {
                                "id": f"{number:032x}",
                                "service_id": f"{number % 100:032x}",
                                "order_id": f"{number:032x}" if number % 2 == 0 else None,
                                "request_owner_id": 1,
                                "phase": "prepare",
                                "target_revision": 1,
                                "source": "worker",
                                "actor_id": None,
                                "status": (
                                    "pending",
                                    "unknown",
                                    "failed",
                                    "succeeded",
                                    "superseded",
                                )[number % 5],
                                "error_code": "panel_usage_unavailable"
                                if number % 10 == 0
                                else None,
                                "attempt_count": 1,
                                "created_at": STAMP,
                                "completed_at": STAMP if number % 5 == 3 else None,
                            }
                            for number in range(size)
                        ],
                    )
                    # Analyze only these schema-local fixtures.
                    for table in (
                        "service_operation_executions",
                        "service_orders",
                        "user_services",
                    ):
                        await session.execute(text(f"ANALYZE {table}"))
                total_expected = size + sum(
                    number % 2 == 1 and number % 11 != 0 for number in range(size)
                )
                cases = [
                    (OperationFilters(), total_expected),
                    (OperationFilters(needs_attention=True), size // 2),
                    (OperationFilters(user_id=2, phase="prepare", status="failed"), size // 10),
                    (OperationFilters(archived="only", needs_attention=True), size // 10),
                    (
                        OperationFilters(service_id=f"{1:032x}"),
                        size // 100 * 2 - sum(number % 11 == 0 for number in range(1, size, 100)),
                    ),
                    (OperationFilters(user_id=1, archived="only"), 0),
                ]
                for filters, expected in cases:
                    async with sessions() as session:
                        statements: list[str] = []

                        def capture(
                            _conn,
                            _cursor,
                            statement,
                            _params,
                            _context,
                            _many,
                            statements=statements,
                        ):
                            statements.append(statement)

                        connection = await session.connection()
                        event.listen(connection.sync_connection, "before_cursor_execute", capture)
                        try:
                            rows, total, more = await list_global_operation_records(
                                session, filters, limit=25
                            )
                        finally:
                            event.remove(
                                connection.sync_connection, "before_cursor_execute", capture
                            )
                    assert len(statements) == 1 and total == expected
                    assert more == (expected > 25)
                    outputs = [ConsoleGlobalOperationOut.from_row(row) for row in rows]
                    assert "NEVER_EXPOSE" not in str(outputs)
                    if filters.archived == "only":
                        assert all(
                            set(row.customer.model_dump().values()) == {None} for row in outputs
                        )
                    for row in rows:
                        success = row.execution is not None and int(row.service.id, 16) % 5 == 3
                        assert row.last_success_at == (STAMP if success else None)
                    statement = global_operations_statement(filters, limit=25)
                    compiled = statement.compile(
                        dialect=connection.dialect, compile_kwargs={"literal_binds": True}
                    )
                    async with sessions() as session:
                        explain = await session.scalar(
                            text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + str(compiled))
                        )
                    assert isinstance(explain, list)
                    report = explain[0]
                    plan_text = json.dumps(report)
                    assert "Actual Rows" in plan_text
                    print(
                        f"PostgreSQL size={size}+{size}, filters={filters}, total={total}, "
                        f"execution_ms={report['Execution Time']}, "
                        f"planning_ms={report['Planning Time']}"
                    )
                    if filters == OperationFilters():
                        print("PostgreSQL full-list plan:", json.dumps(report))
                # Cross the execution/order boundary without losing tied timestamps and IDs.
                query = ConsoleGlobalOperationsQuery()
                boundary = query.next_cursor(
                    OperationPosition(STAMP, "execution", f"{size - 2:032x}")
                )
                async with sessions() as session:
                    page, total, _ = await list_global_operation_records(
                        session,
                        query.filters(),
                        limit=2,
                        after=ConsoleGlobalOperationsQuery(cursor=boundary).position(),
                    )
                    assert total == total_expected
                    assert [(row.position.record_type, row.position.id) for row in page] == [
                        ("execution", f"{size - 1:032x}"),
                        ("order", f"{1:032x}"),
                    ]
                    empty, total, more = await list_global_operation_records(
                        session,
                        OperationFilters(),
                        limit=25,
                        after=OperationPosition(STAMP, "order", "f" * 32),
                    )
                    assert empty == [] and total == total_expected and not more

    asyncio.run(run())
