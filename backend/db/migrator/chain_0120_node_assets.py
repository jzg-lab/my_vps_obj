"""Add the manual, unmanaged inventory without linking any existing resources."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    connection.execute(
        text("""CREATE TABLE IF NOT EXISTS node_assets (
        id VARCHAR(32) PRIMARY KEY,
        name VARCHAR(120) NOT NULL,
        address VARCHAR(253) NOT NULL,
        notes VARCHAR(2000) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL,
        CONSTRAINT ck_node_asset_name CHECK (length(trim(name)) > 0),
        CONSTRAINT ck_node_asset_address CHECK (length(trim(address)) > 0)
    )""")
    )
    connection.execute(
        text("CREATE INDEX IF NOT EXISTS ix_node_assets_created ON node_assets(created_at, id)")
    )


CHAIN_0120_NODE_ASSETS = [
    Migration(
        id="0120_node_assets",
        description="Store administrator-maintained unmanaged node records locally",
        upgrade=_upgrade,
    )
]
