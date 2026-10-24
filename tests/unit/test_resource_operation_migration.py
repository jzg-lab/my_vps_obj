"""0118 really runs twice against isolated SQLite; PostgreSQL is main-owned."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, insert, inspect
from sqlalchemy.exc import IntegrityError

from db.migrator.chain_0118_resource_operations import _upgrade
from db.resource_operation_models import ResourceOperation


def test_append_only_0118_is_idempotent_and_enforces_gate_and_request_uniqueness() -> None:
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            assert "resource_operations" not in inspect(connection).get_table_names()
            _upgrade(connection)
            _upgrade(connection)
            assert {
                column["name"] for column in inspect(connection).get_columns("resource_operations")
            } == set(ResourceOperation.__table__.columns.keys())
            values = {
                "id": "a" * 32,
                "actor_id": 1,
                "idempotency_key": "request",
                "operation": "node_create",
                "request": {},
                "preview": {},
                "baseline_ids": [],
                "fingerprint": "b" * 64,
                "status": "pending",
                "gate_key": "primary",
                "version": 1,
                "attempt_count": 0,
                "attempts": [],
                "evidence": [],
                "created_at": datetime.now(UTC),
            }
            connection.execute(insert(ResourceOperation).values(**values))
            for changes in (
                {"id": "b" * 32, "idempotency_key": "second"},
                {"id": "b" * 32, "gate_key": None, "status": "failed"},
                {"id": "b" * 32, "idempotency_key": "second", "gate_key": None},
            ):
                with pytest.raises(IntegrityError):
                    connection.execute(insert(ResourceOperation).values(**(values | changes)))
    finally:
        engine.dispose()
