"""Unified plan templates, immutable manual orders and independent user services."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    statements = (
        """CREATE TABLE IF NOT EXISTS service_plans (
            id VARCHAR(32) PRIMARY KEY, revision INTEGER NOT NULL,
            terms JSON NOT NULL, enabled BOOLEAN NOT NULL,
            created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
            updated_by BIGINT NOT NULL,
            CONSTRAINT ck_service_plan_revision CHECK (revision > 0)
        )""",
        """CREATE TABLE IF NOT EXISTS user_services (
            id VARCHAR(32) PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
            plan_id VARCHAR(32) NOT NULL REFERENCES service_plans(id) ON DELETE RESTRICT,
            plan_revision INTEGER NOT NULL, terms JSON NOT NULL,
            quota_bytes BIGINT NOT NULL, used_bytes BIGINT NOT NULL DEFAULT 0,
            starts_at TIMESTAMPTZ NOT NULL, expires_at TIMESTAMPTZ NOT NULL,
            desired_status VARCHAR(16) NOT NULL DEFAULT 'active',
            last_usage_sync_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL,
            cycle_started_at TIMESTAMPTZ, cycle_ends_at TIMESTAMPTZ,
            CONSTRAINT ck_user_service_quota CHECK (quota_bytes > 0),
            CONSTRAINT ck_user_service_used CHECK (used_bytes >= 0),
            CONSTRAINT ck_user_service_dates CHECK (expires_at > starts_at),
            CONSTRAINT ck_user_service_desired_status
                CHECK (desired_status IN ('active', 'paused', 'cancelled'))
        )""",
        "CREATE INDEX IF NOT EXISTS ix_user_services_user_id ON user_services(user_id)",
        """CREATE TABLE IF NOT EXISTS service_orders (
            id VARCHAR(32) PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
            service_id VARCHAR(32) NOT NULL REFERENCES user_services(id) ON DELETE RESTRICT,
            actor_id BIGINT NOT NULL, kind VARCHAR(24) NOT NULL,
            idempotency_key VARCHAR(128) NOT NULL, request JSON NOT NULL,
            snapshot JSON NOT NULL, created_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT uq_service_order_key UNIQUE(user_id, idempotency_key)
        )""",
        "CREATE INDEX IF NOT EXISTS ix_service_orders_user_id ON service_orders(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_service_orders_service_id ON service_orders(service_id)",
        """CREATE TABLE IF NOT EXISTS service_connections (
            service_id VARCHAR(32) PRIMARY KEY REFERENCES user_services(id) ON DELETE RESTRICT,
            username VARCHAR(64) NOT NULL UNIQUE, panel_user_uuid VARCHAR(36) UNIQUE,
            state VARCHAR(16) NOT NULL DEFAULT 'pending', last_error VARCHAR(128),
            CONSTRAINT ck_service_connection_state
                CHECK (state IN ('pending', 'ready', 'error', 'revoked'))
        )""",
        """CREATE TABLE IF NOT EXISTS dedicated_exits (
            id VARCHAR(32) PRIMARY KEY, label VARCHAR(160) NOT NULL,
            ip_address VARCHAR(45) NOT NULL UNIQUE, resource_pool VARCHAR(120) NOT NULL,
            squad_uuid VARCHAR(36) NOT NULL UNIQUE,
            service_id VARCHAR(32) UNIQUE REFERENCES user_services(id) ON DELETE RESTRICT,
            verified_at TIMESTAMPTZ, enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS ix_dedicated_exits_resource_pool "
        "ON dedicated_exits(resource_pool)",
    )
    for statement in statements:
        connection.execute(text(statement))


CHAIN_0107_USER_SERVICES = [
    Migration(
        id="0107_user_services",
        description="Separate configurable service plans, activation snapshots and user services",
        upgrade=_upgrade,
    )
]
