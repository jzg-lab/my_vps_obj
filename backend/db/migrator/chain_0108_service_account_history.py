"""Detach retained service history and keep activation request scopes stable on merge."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    for statement in (
        "ALTER TABLE service_orders ADD COLUMN IF NOT EXISTS request_owner_id BIGINT",
        "UPDATE service_orders SET request_owner_id = user_id WHERE request_owner_id IS NULL",
        "ALTER TABLE service_orders ALTER COLUMN request_owner_id SET NOT NULL",
        "ALTER TABLE user_services ALTER COLUMN user_id DROP NOT NULL",
        "ALTER TABLE service_orders ALTER COLUMN user_id DROP NOT NULL",
        "ALTER TABLE service_orders DROP CONSTRAINT IF EXISTS uq_service_order_key",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_service_order_request_key "
        "ON service_orders(request_owner_id, idempotency_key)",
    ):
        connection.execute(text(statement))


CHAIN_0108_SERVICE_ACCOUNT_HISTORY = [
    Migration(
        id="0108_service_account_history",
        description="Retain detached service history and original activation request scopes",
        upgrade=_upgrade,
    )
]
