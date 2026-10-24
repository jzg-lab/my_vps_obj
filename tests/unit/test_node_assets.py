"""Offline validation/SQL checks only; no database or network is opened."""

from datetime import UTC, datetime
from typing import cast
from unittest import IsolatedAsyncioTestCase
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.schema import CreateTable

from bot.app.web.admin_console_node_assets_schemas import (
    ConsoleNodeAssetBody,
    ConsoleNodeAssetOut,
    ConsoleNodeAssetsQuery,
)
from db.dal import node_assets_dal as dal
from db.migrator.chain_0120_node_assets import CHAIN_0120_NODE_ASSETS, _upgrade
from db.node_asset_models import NodeAsset


@pytest.mark.parametrize(
    "address",
    ["192.0.2.1", "10.0.0.1", "::1", "2001:db8::1", "node.example.com", "node-1", "a."],
)
def test_only_syntax_is_checked_and_private_addresses_are_allowed(address: str) -> None:
    body = ConsoleNodeAssetBody(
        name="  Test node  ", address=f" {address} ", notes="  note\nnext  "
    )
    assert (body.name, body.address, body.notes) == ("Test node", address, "note\nnext")


@pytest.mark.parametrize(
    "address",
    [
        "",
        "  ",
        "https://node.example.com",
        "node.example.com:443",
        "user@node.example.com",
        "[::1]",
        "fe80::1%eth0",
        "999.1.2.3",
        "127.1",
        "12345",
        "a..b",
        "-a.example",
        "a-.example",
        "a_b.example",
        ".example",
        "a" * 64 + ".example",
        "a" * 254,
        "a\nb",
        "a\tb",
        "a/b",
        "a?b",
        "a#b",
        "a\\b",
        "a\x00b",
        "a\x7fb",
    ],
)
def test_invalid_address_is_not_accepted_as_an_arbitrary_connection_string(address: str) -> None:
    with pytest.raises(ValidationError):
        ConsoleNodeAssetBody(name="Node", address=address)


@pytest.mark.parametrize(
    "values",
    [
        {"name": ""},
        {"name": " \t "},
        {"name": "a" * 121},
        {"name": "a\nb"},
        {"name": None},
        {"address": None},
        {"notes": None},
        {"name": 42},
        {"notes": "a" * 2001},
        {"notes": "a\x00b"},
        {"node_id": "remote-id"},
        {"is_online": True},
        {"management_state": "managed"},
    ],
)
def test_body_rejects_invalid_values_and_remote_control_fields(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ConsoleNodeAssetBody.model_validate({"name": "Node", "address": "node.example", **values})


def test_lengths_notes_default_and_exact_output_surface() -> None:
    body = ConsoleNodeAssetBody(name="a" * 120, address="node.example", notes="a" * 2000)
    assert len(body.notes) == 2000
    assert ConsoleNodeAssetBody(name="Node", address="::1").notes == ""
    now = datetime.now(UTC)
    row = NodeAsset(id="a" * 32, **body.model_dump(), created_at=now, updated_at=now)
    output = ConsoleNodeAssetOut.from_orm_asset(row).model_dump(mode="json")
    assert set(output) == {
        "id",
        "name",
        "address",
        "notes",
        "management_state",
        "created_at",
        "updated_at",
    }
    assert output["management_state"] == "unmanaged"
    assert str(output["created_at"]).endswith("+00:00")


@pytest.mark.parametrize("query", [{"page": -1}, {"page_size": 0}, {"page_size": 101}, {"q": "x"}])
def test_pagination_is_bounded(query: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ConsoleNodeAssetsQuery.model_validate(query)


def test_migration_emits_only_repeatable_local_ddl_and_matches_model() -> None:
    connection = Mock(spec=Connection)
    _upgrade(cast(Connection, connection))
    _upgrade(cast(Connection, connection))
    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert statements[:2] == statements[2:]
    assert "CREATE TABLE IF NOT EXISTS node_assets" in statements[0]
    assert "CREATE INDEX IF NOT EXISTS ix_node_assets_created" in statements[1]
    assert CHAIN_0120_NODE_ASSETS[0].id == "0120_node_assets"
    table = NodeAsset.__table__
    model_ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    for column in ("id", "name", "address", "notes", "created_at", "updated_at"):
        assert column in statements[0] and column in model_ddl
    for column in ("name VARCHAR(120)", "address VARCHAR(253)", "notes VARCHAR(2000)"):
        assert column in statements[0] and column in model_ddl
    for constraint in ("ck_node_asset_name", "ck_node_asset_address"):
        assert constraint in statements[0] and constraint in model_ddl
    assert "TIMESTAMPTZ NOT NULL" in statements[0]
    assert "TIMESTAMP WITH TIME ZONE NOT NULL" in model_ddl
    assert not table.foreign_keys
    assert not any(column.unique for column in table.columns)
    assert "UPDATE " not in " ".join(statements) and "DELETE " not in " ".join(statements)


class NodeAssetDalTests(IsolatedAsyncioTestCase):
    async def test_create_keeps_same_address_as_two_distinct_local_records(self) -> None:
        session = Mock(spec=AsyncSession)
        first = await dal.create_asset(
            cast(AsyncSession, session), name="Node", address="::1", notes=""
        )
        second = await dal.create_asset(
            cast(AsyncSession, session), name="Node", address="::1", notes=""
        )
        assert first.id != second.id and len(first.id) == len(second.id) == 32
        assert first.created_at == first.updated_at
        assert first.created_at.tzinfo == UTC
        assert session.add.call_count == session.flush.await_count == 2
        session.execute.assert_not_called()
        session.commit.assert_not_called()

    async def test_list_returns_real_total_not_page_length_and_stable_pagination(self) -> None:
        session = Mock(spec=AsyncSession)
        session.execute.return_value = Mock(scalar_one=Mock(return_value=42))
        session.scalars.return_value = Mock(all=Mock(return_value=[]))
        items, total = await dal.list_assets(cast(AsyncSession, session), page=3, page_size=10)
        assert items == [] and total == 42
        statement = session.scalars.call_args.args[0].compile(dialect=postgresql.dialect())
        assert "node_assets.created_at DESC, node_assets.id DESC" in str(statement)
        assert set(statement.params.values()) == {10, 30}
        assert "node_assets" in str(session.execute.call_args.args[0])

    async def test_get_update_and_delete_target_only_the_local_id(self) -> None:
        session = Mock(spec=AsyncSession)
        session.get.return_value = None
        assert await dal.get_asset(cast(AsyncSession, session), "a" * 32) is None
        session.get.assert_awaited_once_with(NodeAsset, "a" * 32)
        session.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=None))
        assert (
            await dal.update_asset(
                cast(AsyncSession, session), "a" * 32, name="New", address="::1", notes=""
            )
            is None
        )
        update = session.execute.call_args.args[0].compile(dialect=postgresql.dialect())
        assert "WHERE node_assets.id =" in str(update) and "created_at=" not in str(update)
        assert update.params["name"] == "New" and update.params["notes"] == ""
        assert update.params["updated_at"].tzinfo == UTC
        assert not await dal.delete_asset(cast(AsyncSession, session), "a" * 32)
        deletion = session.execute.call_args.args[0].compile(dialect=postgresql.dialect())
        assert "DELETE FROM node_assets WHERE node_assets.id =" in str(deletion)
        session.execute.return_value.scalar_one_or_none.return_value = "a" * 32
        assert await dal.delete_asset(cast(AsyncSession, session), "a" * 32)
        session.commit.assert_not_called()
