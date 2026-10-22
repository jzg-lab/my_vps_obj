"""Durable monthly checkpoints without resetting cumulative panel counters."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .engine import Migration


def _upgrade(connection: Connection) -> None:
    connection.execute(
        text("ALTER TABLE service_connections ADD COLUMN IF NOT EXISTS cycle_cutover_bytes BIGINT")
    )
    connection.execute(
        text("""CREATE TABLE IF NOT EXISTS service_usage_periods (
        service_id VARCHAR(32) NOT NULL REFERENCES user_services(id) ON DELETE RESTRICT,
        cycle_started_at TIMESTAMPTZ NOT NULL,
        cycle_ends_at TIMESTAMPTZ NOT NULL,
        used_bytes BIGINT NOT NULL, quota_bytes BIGINT NOT NULL,
        cutover_bytes BIGINT NOT NULL, next_started_at TIMESTAMPTZ NOT NULL,
        next_ends_at TIMESTAMPTZ NOT NULL, created_at TIMESTAMPTZ NOT NULL,
        confirmed_at TIMESTAMPTZ,
        PRIMARY KEY (service_id, cycle_started_at)
    )""")
    )
    for column in ("usage_raw_bytes BIGINT", "usage_lifetime_offset BIGINT"):
        connection.execute(
            text(f"ALTER TABLE service_connections ADD COLUMN IF NOT EXISTS {column}")
        )
    connection.execute(
        text(
            "ALTER TABLE user_services ADD COLUMN IF NOT EXISTS "
            "quota_revision INTEGER NOT NULL DEFAULT 0"
        )
    )
    connection.execute(
        text("""CREATE TABLE IF NOT EXISTS service_plan_quota_changes (
        plan_id VARCHAR(32) NOT NULL REFERENCES service_plans(id) ON DELETE RESTRICT,
        revision INTEGER NOT NULL, quota_bytes BIGINT NOT NULL, reason VARCHAR(1000) NOT NULL,
        actor_id BIGINT NOT NULL, created_at TIMESTAMPTZ NOT NULL,
        PRIMARY KEY (plan_id, revision)
    )""")
    )


CHAIN_0113_SERVICE_ENTITLEMENTS = [
    Migration(
        id="0113_service_entitlements",
        description="Persist fixed monthly cutovers and closed-period usage",
        upgrade=_upgrade,
    )
]
