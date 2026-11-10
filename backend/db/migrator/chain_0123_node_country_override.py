"""Allow local country corrections without changing the remote node."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    if "country_code" not in {
        column["name"] for column in inspect(connection).get_columns("node_metadata")
    }:
        connection.execute(text("ALTER TABLE node_metadata ADD COLUMN country_code VARCHAR(2)"))


CHAIN_0123_NODE_COUNTRY_OVERRIDE = [
    Migration(
        id="0123_node_country_override",
        description="Allow local country corrections for managed nodes",
        upgrade=_upgrade,
    )
]
