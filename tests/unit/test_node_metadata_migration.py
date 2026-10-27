"""The managed-node metadata migration is additive and idempotent."""

from sqlalchemy import create_engine, inspect, text

from db.migrator.chain_0122_node_metadata import _upgrade


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
