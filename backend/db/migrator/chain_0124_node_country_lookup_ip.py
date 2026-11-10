"""Store an optional public IP used only for node country lookup."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    if "country_lookup_ip" not in {
        column["name"] for column in inspect(connection).get_columns("node_metadata")
    }:
        connection.execute(
            text("ALTER TABLE node_metadata ADD COLUMN country_lookup_ip VARCHAR(45)")
        )


CHAIN_0124_NODE_COUNTRY_LOOKUP_IP = [
    Migration(
        id="0124_node_country_lookup_ip",
        description="Store an optional public IP for node country lookup",
        upgrade=_upgrade,
    )
]
