"""Structural PostgreSQL DDL replay only; real DDL runs in the main-owned scenario."""

from typing import cast
from unittest.mock import patch

from sqlalchemy.engine import Connection
from sqlalchemy.sql.elements import TextClause

from db.migrator.chain_0117_exit_replacement import _upgrade


class RecordingDDL:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.keys: dict[str, list[dict[str, object]]] = {}
        self.checks: dict[str, dict[str, str]] = {
            "service_operation_executions": {
                "ck_service_execution_phase": (
                    "phase IN ('prepare','delivery','entitlement','revocation','usage')"
                )
            }
        }

    def get_foreign_keys(self, table: str) -> list[dict[str, object]]:
        return self.keys.get(table, [])

    def get_check_constraints(self, table: str) -> list[dict[str, str]]:
        return [{"name": name, "sqltext": sql} for name, sql in self.checks.get(table, {}).items()]

    def execute(self, statement: TextClause) -> None:
        sql = str(statement)
        self.statements.append(sql)
        if "ADD CONSTRAINT" in sql:
            words = sql.split()
            table, name = words[2], words[5]
            if "FOREIGN KEY" in sql:
                column = sql.split("FOREIGN KEY (")[1].split(")")[0]
                existing = self.keys.setdefault(table, [])
                assert not any(key["constrained_columns"] == [column] for key in existing)
                existing.append({"constrained_columns": [column]})
            else:
                checks = self.checks.setdefault(table, {})
                assert name not in checks
                checks[name] = sql.split(" CHECK ", 1)[1]
        elif "DROP CONSTRAINT" in sql:
            words = sql.split()
            self.checks[words[2]].pop(words[-1], None)


def test_0117_replays_without_dropping_bindings_or_readding_constraints() -> None:
    connection = RecordingDDL()
    with patch("db.migrator.chain_0117_exit_replacement.inspect", return_value=connection):
        _upgrade(cast(Connection, connection))
        first = list(connection.statements)
        connection.statements.clear()
        _upgrade(cast(Connection, connection))
    assert len([sql for sql in first if "ADD COLUMN IF NOT EXISTS" in sql]) == 3
    assert (
        len([sql for sql in first if "REFERENCES service_orders(id) ON DELETE RESTRICT" in sql])
        == 2
    )
    assert len([sql for sql in first if "DROP CONSTRAINT" in sql]) == 1
    assert all("IF NOT EXISTS" in sql for sql in connection.statements)
    assert all("DROP COLUMN" not in sql and "UPDATE " not in sql for sql in first)
    assert "UNIQUE INDEX IF NOT EXISTS uq_service_connection_replacement" in " ".join(first)
    assert "service_id IS NULL OR hold_order_id IS NULL" in " ".join(first)
    assert "replacement_progress IS NOT NULL" in " ".join(first)
