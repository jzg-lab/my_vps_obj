"""0119 is executed twice in memory; no external database is contacted."""

from datetime import UTC, datetime

from sqlalchemy import create_engine, inspect, text

from db.account_operation_models import AccountOperation
from db.migrator.chain_0119_account_operations import _upgrade


def test_0119_is_repeatable_and_preserves_unknown_legacy_intents_without_fabricating_history() -> (
    None
):
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
            connection.execute(
                text("CREATE TABLE users (user_id BIGINT PRIMARY KEY, is_banned BOOLEAN)")
            )
            connection.execute(
                text("""CREATE TABLE account_access_sync (
                user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                pending BOOLEAN NOT NULL, last_error VARCHAR(64), attempted_at TIMESTAMPTZ)""")
            )
            connection.execute(text("INSERT INTO users VALUES (1, TRUE), (2, FALSE), (3, FALSE)"))
            connection.execute(
                text(
                    "INSERT INTO account_access_sync VALUES (1, TRUE, :error, :time), "
                    "(2, TRUE, NULL, NULL), (3, FALSE, NULL, :time)"
                ),
                {"error": "https://private.example/SECRET", "time": datetime.now(UTC).isoformat()},
            )
            _upgrade(connection)
            _upgrade(connection)
            rows = (
                connection.execute(text("SELECT * FROM account_operations ORDER BY target_id"))
                .mappings()
                .all()
            )
            assert len(rows) == 2
            assert (
                rows[0]["status"] == "unknown"
                and rows[0]["error_code"] == "account_sync_unconfirmed"
            )
            assert rows[1]["status"] == "pending" and rows[1]["desired_banned"] == 0
            assert all(row["source"] == "worker" and row["actor_id"] is None for row in rows)
            assert all(row["before_banned"] is None and row["completed_at"] is None for row in rows)
            assert all(row["attempt_count"] == 0 and row["first_failed_at"] is None for row in rows)
            assert {
                column["name"] for column in inspect(connection).get_columns("account_operations")
            } == set(AccountOperation.__table__.columns.keys())
            for row in rows:
                pointer = connection.scalar(
                    text("SELECT operation_id FROM account_access_sync WHERE user_id=:id"),
                    {"id": row["target_id"]},
                )
                assert pointer == row["id"]
            connection.execute(text("DELETE FROM users WHERE user_id=1"))
            assert (
                connection.scalar(text("SELECT user_id FROM account_operations WHERE target_id=1"))
                is None
            )
            assert connection.scalar(text("SELECT COUNT(*) FROM account_operations")) == 2
    finally:
        engine.dispose()
