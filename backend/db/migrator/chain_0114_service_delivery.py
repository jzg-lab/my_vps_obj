"""Keep revocation intent and administrator evidence independently of panel replies."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    statements = (
        "ALTER TABLE service_connections ADD COLUMN IF NOT EXISTS revoke_requested_at TIMESTAMPTZ",
        "ALTER TABLE service_connections ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ",
        "ALTER TABLE dedicated_exits ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 1",
        """CREATE TABLE IF NOT EXISTS dedicated_exit_audit (
            id VARCHAR(32) PRIMARY KEY,
            exit_id VARCHAR(32) NOT NULL REFERENCES dedicated_exits(id) ON DELETE RESTRICT,
            service_id VARCHAR(32) REFERENCES user_services(id) ON DELETE RESTRICT,
            actor_id BIGINT NOT NULL, action VARCHAR(24) NOT NULL,
            idempotency_key VARCHAR(128) NOT NULL, evidence JSON NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT uq_exit_audit_request UNIQUE(exit_id, idempotency_key)
        )""",
        "CREATE INDEX IF NOT EXISTS ix_dedicated_exit_audit_exit_id "
        "ON dedicated_exit_audit(exit_id)",
    )
    for statement in statements:
        connection.execute(text(statement))


CHAIN_0114_SERVICE_DELIVERY = [
    Migration(
        id="0114_service_delivery",
        description="Audit dedicated exit verification and reclaim; persist service revocation",
        upgrade=_upgrade,
    )
]
