"""Durable account connection synchronization, independent of HTTP request lifetime."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    for statement in (
        """CREATE TABLE IF NOT EXISTS account_access_sync (
            user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
            pending BOOLEAN NOT NULL DEFAULT TRUE,
            last_error VARCHAR(64), attempted_at TIMESTAMPTZ
        )""",
        "CREATE INDEX IF NOT EXISTS ix_account_access_sync_pending ON account_access_sync(pending)",
        """INSERT INTO account_access_sync (user_id, pending)
            SELECT user_id, TRUE FROM users WHERE is_banned IS TRUE
            ON CONFLICT (user_id) DO NOTHING""",
    ):
        connection.execute(text(statement))


CHAIN_0109_ACCOUNT_ACCESS_SYNC = [
    Migration(
        id="0109_account_access_sync",
        description="Persist pending account access changes for worker retries",
        upgrade=_upgrade,
    )
]
