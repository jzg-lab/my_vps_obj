"""The managed-node metadata migration is additive and idempotent."""

from sqlalchemy import create_engine, inspect, text

from db.migrator.chain_0122_node_metadata import _upgrade
from db.migrator.chain_0123_node_country_override import _upgrade as upgrade_country
from db.migrator.chain_0124_node_country_lookup_ip import _upgrade as upgrade_lookup_ip


def test_0122_creates_the_local_metadata_table_idempotently() -> None:
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE retained (id INTEGER PRIMARY KEY)"))
            _upgrade(connection)
            _upgrade(connection)
            assert set(inspect(connection).get_table_names()) == {"node_metadata", "retained"}
            assert {
                column["name"] for column in inspect(connection).get_columns("node_metadata")
            } == {
                "node_id",
                "display_name",
                "region",
                "provider",
                "updated_at",
            }
    finally:
        engine.dispose()


def test_0123_preserves_existing_labels_and_can_run_twice() -> None:
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            _upgrade(connection)
            connection.execute(
                text(
                    "INSERT INTO node_metadata (node_id, display_name, updated_at) "
                    "VALUES ('node', 'Retained label', CURRENT_TIMESTAMP)"
                )
            )
            upgrade_country(connection)
            upgrade_country(connection)
            assert connection.execute(
                text("SELECT display_name, country_code FROM node_metadata")
            ).one() == ("Retained label", None)
    finally:
        engine.dispose()


def test_0124_preserves_country_corrections_and_can_run_twice() -> None:
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            _upgrade(connection)
            upgrade_country(connection)
            connection.execute(
                text(
                    "INSERT INTO node_metadata (node_id, country_code, updated_at) "
                    "VALUES ('node', 'JP', CURRENT_TIMESTAMP)"
                )
            )
            upgrade_lookup_ip(connection)
            upgrade_lookup_ip(connection)
            assert connection.execute(
                text("SELECT country_code, country_lookup_ip FROM node_metadata")
            ).one() == ("JP", None)
    finally:
        engine.dispose()
