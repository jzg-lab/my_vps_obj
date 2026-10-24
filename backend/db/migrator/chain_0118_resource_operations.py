"""Append one durable resource-operation table without changing service ownership."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    connection.execute(
        text("""CREATE TABLE IF NOT EXISTS resource_operations (
        id VARCHAR(32) PRIMARY KEY,
        actor_id BIGINT NOT NULL,
        idempotency_key VARCHAR(128) NOT NULL,
        operation VARCHAR(32) NOT NULL,
        target_id VARCHAR(36),
        recovery_of VARCHAR(32),
        request JSON NOT NULL,
        preview JSON NOT NULL,
        baseline_ids JSON NOT NULL,
        fingerprint VARCHAR(64) NOT NULL,
        status VARCHAR(16) NOT NULL,
        gate_key VARCHAR(64) UNIQUE,
        version INTEGER NOT NULL DEFAULT 1,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        attempts JSON NOT NULL,
        observation JSON,
        evidence JSON NOT NULL,
        error_code VARCHAR(64),
        created_at TIMESTAMPTZ NOT NULL,
        attempted_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        CONSTRAINT uq_resource_operation_request UNIQUE (actor_id, idempotency_key),
        CONSTRAINT ck_resource_operation_status
            CHECK (status IN ('pending','unknown','failed','succeeded','superseded')),
        CONSTRAINT ck_resource_operation_counts CHECK (version > 0 AND attempt_count >= 0),
        CONSTRAINT ck_resource_operation_gate CHECK (
            (status IN ('pending','unknown') AND gate_key IS NOT NULL) OR
            (status IN ('failed','succeeded','superseded') AND gate_key IS NULL))
    )""")
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_resource_operation_history "
            "ON resource_operations(created_at, id)"
        )
    )


CHAIN_0118_RESOURCE_OPERATIONS = [
    Migration(
        id="0118_resource_operations",
        description="Persist confirmed resource intents and unresolved mutation gates",
        upgrade=_upgrade,
    )
]
