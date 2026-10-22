"""Durable independent service changes, separate from connection preparation."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    connection.execute(
        text(
            "ALTER TABLE user_services ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 1"
        )
    )
    for column in (
        "sync_pending BOOLEAN NOT NULL DEFAULT FALSE",
        "sync_error VARCHAR(128)",
        "sync_attempted_at TIMESTAMPTZ",
        "sync_confirmed_at TIMESTAMPTZ",
    ):
        connection.execute(
            text(f"ALTER TABLE service_connections ADD COLUMN IF NOT EXISTS {column}")
        )


CHAIN_0111_SERVICE_CHANGES = [
    Migration(
        id="0111_service_changes",
        description="Persist independent pause, resume and renewal synchronization",
        upgrade=_upgrade,
    )
]
