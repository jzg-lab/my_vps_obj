"""Persist observed execution results without inventing evidence for old orders."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    connection.execute(
        text("""CREATE TABLE IF NOT EXISTS service_operation_executions (
        id VARCHAR(32) PRIMARY KEY,
        service_id VARCHAR(32) NOT NULL REFERENCES user_services(id) ON DELETE RESTRICT,
        order_id VARCHAR(32) UNIQUE REFERENCES service_orders(id) ON DELETE RESTRICT,
        request_owner_id BIGINT NOT NULL,
        phase VARCHAR(16) NOT NULL,
        target_revision INTEGER NOT NULL,
        source VARCHAR(16) NOT NULL,
        actor_id BIGINT,
        status VARCHAR(16) NOT NULL,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL,
        attempted_at TIMESTAMPTZ,
        first_failed_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        error_code VARCHAR(64),
        CONSTRAINT ck_service_execution_phase
            CHECK (phase IN ('prepare','delivery','entitlement','revocation','usage')),
        CONSTRAINT ck_service_execution_status
            CHECK (status IN ('pending','unknown','failed','succeeded','superseded')),
        CONSTRAINT ck_service_execution_source CHECK (source IN ('administrator','worker')),
        CONSTRAINT ck_service_execution_counts CHECK (target_revision > 0 AND attempt_count >= 0)
    )""")
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_service_executions_history "
            "ON service_operation_executions(service_id, created_at, id)"
        )
    )


CHAIN_0116_SERVICE_OPERATION_EXECUTIONS = [
    Migration(
        id="0116_service_operation_executions",
        description="Persist service operation attempts and verified outcomes",
        upgrade=_upgrade,
    )
]
