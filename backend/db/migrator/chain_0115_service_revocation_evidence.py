"""Distinguish a metered deletion retry from an unexplained missing identity."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    connection.execute(
        text(
            "ALTER TABLE service_connections ADD COLUMN IF NOT EXISTS "
            "revoke_delete_requested_at TIMESTAMPTZ"
        )
    )


CHAIN_0115_SERVICE_REVOCATION_EVIDENCE = [
    Migration(
        id="0115_service_revocation_evidence",
        description="Persist final metering evidence with the intent to delete an identity",
        upgrade=_upgrade,
    )
]
