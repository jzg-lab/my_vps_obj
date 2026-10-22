"""Keep independent usage observations across retries and panel outages."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    for column in (
        "usage_total_bytes BIGINT",
        "usage_attempted_at TIMESTAMPTZ",
        "usage_error VARCHAR(128)",
    ):
        connection.execute(
            text(f"ALTER TABLE service_connections ADD COLUMN IF NOT EXISTS {column}")
        )


CHAIN_0112_SERVICE_USAGE = [
    Migration(
        id="0112_service_usage",
        description="Persist independent service usage observations and failures",
        upgrade=_upgrade,
    )
]
