"""Store local display metadata for managed Remnawave node UUIDs."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    connection.execute(
        text("""CREATE TABLE IF NOT EXISTS node_metadata (
        node_id VARCHAR(36) PRIMARY KEY,
        display_name VARCHAR(120),
        region VARCHAR(120),
        provider VARCHAR(120),
        updated_at TIMESTAMPTZ NOT NULL,
        CONSTRAINT ck_node_metadata_display_name
            CHECK (display_name IS NULL OR length(trim(display_name)) > 0),
        CONSTRAINT ck_node_metadata_region
            CHECK (region IS NULL OR length(trim(region)) > 0),
        CONSTRAINT ck_node_metadata_provider
            CHECK (provider IS NULL OR length(trim(provider)) > 0)
    )""")
    )


CHAIN_0122_NODE_METADATA = [
    Migration(
        id="0122_node_metadata",
        description="Store local display labels for managed Remnawave nodes",
        upgrade=_upgrade,
    )
]
