"""Fair retry ordering for independent connection preparation."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    connection.execute(
        text("ALTER TABLE service_connections ADD COLUMN IF NOT EXISTS attempted_at TIMESTAMPTZ")
    )


CHAIN_0110_SERVICE_PROVISIONING = [
    Migration(
        id="0110_service_provisioning",
        description="Record independent identity preparation attempts for durable retry",
        upgrade=_upgrade,
    )
]
