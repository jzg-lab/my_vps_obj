"""Retain account access intents; old pending jobs have unknown authors and results."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, bindparam, inspect, text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    connection.execute(
        text("""CREATE TABLE IF NOT EXISTS account_operations (
        id VARCHAR(32) PRIMARY KEY,
        actor_id BIGINT,
        target_id BIGINT NOT NULL,
        user_id BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
        before_banned BOOLEAN,
        desired_banned BOOLEAN NOT NULL,
        source VARCHAR(16) NOT NULL,
        status VARCHAR(16) NOT NULL,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL,
        attempted_at TIMESTAMPTZ,
        first_failed_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        error_code VARCHAR(64),
        CONSTRAINT ck_account_operation_status
            CHECK (status IN ('pending','unknown','failed','succeeded','superseded')),
        CONSTRAINT ck_account_operation_source CHECK (source IN ('administrator','worker')),
        CONSTRAINT ck_account_operation_attempts CHECK (attempt_count >= 0)
    )""")
    )
    for name, columns in (
        ("ix_account_operation_history", "created_at, id"),
        ("ix_account_operation_target", "target_id, created_at, id"),
        ("ix_account_operations_user_id", "user_id"),
    ):
        connection.execute(
            text(f"CREATE INDEX IF NOT EXISTS {name} ON account_operations({columns})")
        )
    if "operation_id" not in {
        column["name"] for column in inspect(connection).get_columns("account_access_sync")
    }:
        connection.execute(
            text(
                "ALTER TABLE account_access_sync ADD COLUMN operation_id VARCHAR(32) "
                "REFERENCES account_operations(id) ON DELETE RESTRICT"
            )
        )
    pending = (
        connection.execute(
            text("""SELECT a.user_id, u.is_banned, a.attempted_at, a.last_error
            FROM account_access_sync a JOIN users u ON u.user_id = a.user_id
            WHERE a.pending IS TRUE AND a.operation_id IS NULL""")
        )
        .mappings()
        .all()
    )
    for row in pending:
        operation_id = uuid4().hex
        attempted_at = row["attempted_at"]
        if isinstance(attempted_at, str):
            attempted_at = datetime.fromisoformat(attempted_at)
        connection.execute(
            text("""INSERT INTO account_operations
                (id, target_id, user_id, desired_banned, source, status,
                 attempt_count, created_at, attempted_at, error_code)
                VALUES (:id, :user_id, :user_id, :desired, 'worker', :status,
                        0, :now, :attempted_at, :error)""").bindparams(
                bindparam("now", type_=DateTime(timezone=True)),
                bindparam("attempted_at", type_=DateTime(timezone=True)),
            ),
            {
                "id": operation_id,
                "user_id": row["user_id"],
                "desired": bool(row["is_banned"]),
                "status": "unknown" if row["attempted_at"] or row["last_error"] else "pending",
                "now": datetime.now(UTC),
                "attempted_at": attempted_at,
                "error": "account_sync_unconfirmed" if row["last_error"] else None,
            },
        )
        connection.execute(
            text("UPDATE account_access_sync SET operation_id = :id WHERE user_id = :user_id"),
            {"id": operation_id, "user_id": row["user_id"]},
        )


CHAIN_0119_ACCOUNT_OPERATIONS = [
    Migration(
        id="0119_account_operations",
        description="Retain account ban intents, synchronization attempts and archived results",
        upgrade=_upgrade,
    )
]
