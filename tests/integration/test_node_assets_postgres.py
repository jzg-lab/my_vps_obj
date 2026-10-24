"""Opt-in PostgreSQL migration/persistence checks in the existing disposable schema."""

import re

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.dal import node_assets_dal as assets
from db.migrator.chain_0120_node_assets import _upgrade
from db.node_asset_models import NodeAsset
from tests.integration.test_user_services_postgres import DATABASE_URL, scenario

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="Disposable PostgreSQL URL is required")


async def fresh_assets(factory: async_sessionmaker[AsyncSession]) -> str:
    async with factory.begin() as session:
        schema = await session.scalar(text("SELECT current_schema()"))
        assert isinstance(schema, str) and re.fullmatch(r"user_services_test_[0-9a-f]{32}", schema)
        # The shared fixture may create this model; only migration 0120 may recreate it here.
        await session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        await session.execute(text(f'DROP TABLE IF EXISTS "{schema}".node_assets'))
        connection = await session.connection()
        before = await connection.run_sync(
            lambda conn: inspect(conn).get_table_names(schema=schema)
        )
        assert "node_assets" not in before
        await connection.run_sync(_upgrade)
        await connection.run_sync(_upgrade)
        after = await connection.run_sync(lambda conn: inspect(conn).get_table_names(schema=schema))
        assert set(after) == {*before, "node_assets"}
        columns, checks, indexes, foreign_keys, primary_key = await connection.run_sync(
            lambda conn: (
                inspect(conn).get_columns("node_assets", schema=schema),
                inspect(conn).get_check_constraints("node_assets", schema=schema),
                inspect(conn).get_indexes("node_assets", schema=schema),
                inspect(conn).get_foreign_keys("node_assets", schema=schema),
                inspect(conn).get_pk_constraint("node_assets", schema=schema),
            )
        )
        assert {column["name"] for column in columns} == set(NodeAsset.__table__.columns.keys())
        assert all(not column["nullable"] for column in columns)
        assert {check["name"] for check in checks} == {
            "ck_node_asset_name",
            "ck_node_asset_address",
        }
        assert [(index["name"], index["column_names"]) for index in indexes] == [
            ("ix_node_assets_created", ["created_at", "id"])
        ]
        assert primary_key["constrained_columns"] == ["id"] and not foreign_keys
    return schema


def test_0120_creates_from_absent_table_and_repeated_upgrade_preserves_records() -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        schema = await fresh_assets(factory)
        async with factory.begin() as session:
            row = await assets.create_asset(
                session, name="Pending", address="192.0.2.20", notes="retain"
            )
            asset_id, created_at = row.id, row.created_at
            relation = f"{schema}.node_assets"
            oid = await session.scalar(
                text("SELECT CAST(to_regclass(:name) AS oid)"), {"name": relation}
            )
        async with factory.begin() as session:
            assert await session.scalar(text("SELECT current_schema()")) == schema
            await session.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            connection = await session.connection()
            await connection.run_sync(_upgrade)
            await connection.run_sync(_upgrade)
            assert (
                await session.scalar(
                    text("SELECT CAST(to_regclass(:name) AS oid)"), {"name": relation}
                )
                == oid
            )
        async with factory() as session:
            saved = await assets.get_asset(session, asset_id)
            assert saved is not None
            assert (saved.name, saved.address, saved.notes) == ("Pending", "192.0.2.20", "retain")
            assert saved.created_at == saved.updated_at == created_at
            assert saved.created_at.utcoffset() is not None
            assert (await assets.list_assets(session, page=0, page_size=20))[1] == 1

    scenario(run)


def test_local_crud_commits_across_sessions_without_merging_same_addresses() -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        await fresh_assets(factory)
        async with factory.begin() as session:
            first = await assets.create_asset(
                session, name="Same name", address="::1", notes="first"
            )
            second = await assets.create_asset(
                session, name="Same name", address="::1", notes="second"
            )
            first_id, second_id = first.id, second.id
            created_at, second_updated = first.created_at, second.updated_at
        async with factory() as session:
            page, total = await assets.list_assets(session, page=0, page_size=1)
            assert total == 2 and len(page) == 1 and first_id != second_id
            other_page, other_total = await assets.list_assets(session, page=1, page_size=1)
            assert other_total == 2 and {page[0].id, other_page[0].id} == {first_id, second_id}
            assert (await assets.list_assets(session, page=2, page_size=1)) == ([], 2)
        async with factory.begin() as session:
            updated = await assets.update_asset(
                session, first_id, name="Renamed", address="node.example", notes=""
            )
            assert updated is not None and updated.created_at == created_at
            updated_at = updated.updated_at
            assert updated_at >= created_at
        async with factory() as session:
            saved, untouched = (
                await assets.get_asset(session, first_id),
                await assets.get_asset(session, second_id),
            )
            assert saved is not None and untouched is not None
            assert (saved.name, saved.address, saved.notes) == ("Renamed", "node.example", "")
            assert (saved.created_at, saved.updated_at) == (created_at, updated_at)
            assert (untouched.name, untouched.notes, untouched.updated_at) == (
                "Same name",
                "second",
                second_updated,
            )
        async with factory() as session:
            await assets.update_asset(
                session, first_id, name="Rollback", address="::1", notes="not saved"
            )
            await session.rollback()
        async with factory.begin() as session:
            saved = await assets.get_asset(session, first_id)
            assert saved is not None and saved.name == "Renamed"
            assert await assets.delete_asset(session, first_id)
        async with factory.begin() as session:
            assert await assets.get_asset(session, first_id) is None
            assert not await assets.delete_asset(session, first_id)
            assert (
                await assets.update_asset(
                    session, first_id, name="No upsert", address="::1", notes=""
                )
                is None
            )
            remaining, total = await assets.list_assets(session, page=0, page_size=20)
            assert total == 1 and remaining[0].id == second_id

    scenario(run)
