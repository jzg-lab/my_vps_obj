"""Store the bounded node speed history used by the operations console."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    connection.execute(
        text("""CREATE TABLE IF NOT EXISTS node_speed_samples (
        id BIGSERIAL PRIMARY KEY,
        node_id VARCHAR(36) NOT NULL,
        sampled_at TIMESTAMPTZ NOT NULL,
        rx_bytes_per_second DOUBLE PRECISION,
        tx_bytes_per_second DOUBLE PRECISION,
        CONSTRAINT uq_node_speed_sample UNIQUE (node_id, sampled_at)
    )""")
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_node_speed_sampled_at ON node_speed_samples(sampled_at)"
        )
    )


CHAIN_0121_NODE_SPEED_SAMPLES = [
    Migration(
        id="0121_node_speed_samples",
        description="Store bounded node speed observations for operations charts",
        upgrade=_upgrade,
    )
]
