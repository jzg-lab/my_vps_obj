"""Reserve replacement resources without releasing the current unique binding."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    for table, column, sql_type in (
        ("dedicated_exits", "hold_order_id", "VARCHAR(32)"),
        ("service_connections", "replacement_order_id", "VARCHAR(32)"),
        ("service_operation_executions", "replacement_progress", "JSON"),
    ):
        connection.execute(
            text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {sql_type}")
        )
    for table, column, name in (
        ("dedicated_exits", "hold_order_id", "fk_dedicated_exit_hold"),
        ("service_connections", "replacement_order_id", "fk_service_connection_replacement"),
    ):
        keys = inspect(connection).get_foreign_keys(table)
        if not any(key["constrained_columns"] == [column] for key in keys):
            connection.execute(
                text(
                    f"ALTER TABLE {table} ADD CONSTRAINT {name} FOREIGN KEY ({column}) "
                    "REFERENCES service_orders(id) ON DELETE RESTRICT"
                )
            )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_dedicated_exits_hold_order_id "
            "ON dedicated_exits(hold_order_id)"
        )
    )
    connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_service_connection_replacement "
            "ON service_connections(replacement_order_id)"
        )
    )
    checks = {
        item["name"]: item["sqltext"]
        for item in inspect(connection).get_check_constraints("service_operation_executions")
    }
    if "exit_replace" not in checks.get("ck_service_execution_phase", ""):
        connection.execute(
            text(
                "ALTER TABLE service_operation_executions "
                "DROP CONSTRAINT IF EXISTS ck_service_execution_phase"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE service_operation_executions "
                "ADD CONSTRAINT ck_service_execution_phase CHECK "
                "(phase IN ('prepare','delivery','entitlement',"
                "'revocation','usage','exit_replace'))"
            )
        )
    for table, name, expression in (
        (
            "dedicated_exits",
            "ck_dedicated_exit_binding_hold",
            "service_id IS NULL OR hold_order_id IS NULL",
        ),
        (
            "service_operation_executions",
            "ck_service_execution_replacement",
            "(phase = 'exit_replace' AND replacement_progress IS NOT NULL) OR "
            "(phase != 'exit_replace' AND replacement_progress IS NULL)",
        ),
    ):
        if name not in {item["name"] for item in inspect(connection).get_check_constraints(table)}:
            connection.execute(
                text(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expression})")
            )


CHAIN_0117_EXIT_REPLACEMENT = [
    Migration(
        id="0117_exit_replacement",
        description="Persist exit replacement holds and lifecycle gate",
        upgrade=_upgrade,
    )
]
