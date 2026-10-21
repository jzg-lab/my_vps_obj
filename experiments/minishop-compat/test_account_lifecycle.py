"""Characterize upstream account routes without loading settings or contacting a panel.

Run with MINISHOP_SOURCE pointing at the inspected v3.8.2 source checkout.
Passing gap tests reproduce omissions; they do not approve the extension design.
"""

from __future__ import annotations

import ast
import logging
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, select
from sqlalchemy.orm import Session

SOURCE = Path(os.environ["MINISHOP_SOURCE"])
PRIMARY = "00000000-0000-0000-0000-000000000001"
SECONDARY = "00000000-0000-0000-0000-000000000002"
EXTENSION = "00000000-0000-0000-0000-000000000003"


def load_functions(relative_path, names, namespace):
    """Execute unchanged function bodies; omit imports to avoid application startup."""
    path = SOURCE / relative_path
    tree = ast.parse(path.read_text(), filename=str(path))
    functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]
    if {node.name for node in functions} != set(names):
        raise RuntimeError(f"Source contract changed: {relative_path}")
    module = ast.Module(body=functions, type_ignores=[])
    exec(compile(module, str(path), "exec"), namespace)


class LocalSession:
    """Expose the small async session surface used by the selected upstream functions."""

    def __init__(self, db):
        self.db = db
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, statement):
        return self.db.execute(statement)

    async def commit(self):
        self.db.commit()
        self.committed = True

    async def rollback(self):
        self.db.rollback()
        self.rolled_back = True

    async def refresh(self, user):
        pass


class AccountLifecycleCharacterization(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        metadata = MetaData()
        self.subscriptions = Table(
            "subscriptions",
            metadata,
            Column("user_id", Integer),
            Column("panel_user_uuid", String),
        )
        self.extension_services = Table(
            "ext_probe_services",
            metadata,
            Column("user_id", Integer),
            Column("panel_user_uuid", String),
        )
        metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.session = LocalSession(self.db)
        self.user = SimpleNamespace(user_id=42, panel_user_uuid=None, is_banned=False)
        self.panel_state = {}
        self.panel_calls = []
        self.local_delete = AsyncMock(return_value=True)

        async def set_status(identity, enabled):
            self.panel_calls.append(("status", identity, enabled))
            self.panel_state[identity] = enabled
            return True

        async def delete_identity(identity, **kwargs):
            self.panel_calls.append(("delete", identity))
            del self.panel_state[identity]
            return True

        self.panel = SimpleNamespace(
            update_user_status_on_panel=AsyncMock(side_effect=set_status),
            delete_user_from_panel=AsyncMock(side_effect=delete_identity),
        )
        get_user = AsyncMock(return_value=self.user)
        dal_namespace = {
            "UUID": UUID,
            "select": select,
            "Subscription": self.subscriptions.c,
            "get_user_by_id": get_user,
        }
        load_functions(
            "backend/db/dal/user_reads_dal.py",
            ["get_panel_user_uuids_for_user"],
            dal_namespace,
        )
        self.collect = dal_namespace["get_panel_user_uuids_for_user"]
        self.namespace = {
            "_require_admin_user_id": lambda request: 100,
            "parse_body_or_400": AsyncMock(return_value=SimpleNamespace(banned=True)),
            "AdminUserBanBody": object,
            "get_settings": lambda request: SimpleNamespace(),
            "get_panel_service": lambda request: self.panel,
            "get_optional_subscription_service": lambda request: None,
            "get_session_factory": lambda request: lambda: self.session,
            "can_ban_account": AsyncMock(return_value=True),
            "user_dal": SimpleNamespace(
                get_user_by_id=get_user,
                get_panel_user_uuids_for_user=self.collect,
                delete_user_and_relations=self.local_delete,
            ),
            "message_log_dal": SimpleNamespace(create_message_log_no_commit=AsyncMock()),
            "_invalidate_after_admin_user_mutation": AsyncMock(),
            "_serialize_user": lambda user: {"is_banned": user.is_banned},
            "_ok": lambda data: {"status": 200, "data": data},
            "_error": lambda status, error, *args: {"status": status, "error": error},
            "logger": logging.getLogger(__name__),
        }
        load_functions(
            "backend/bot/app/web/admin_api_impl/users_ban.py",
            ["admin_user_ban_route"],
            self.namespace,
        )
        load_functions(
            "backend/bot/app/web/admin_api_impl/users_actions.py",
            ["_is_panel_user_confirmed_absent", "admin_user_delete_route"],
            self.namespace,
        )
        self.request = SimpleNamespace(match_info={"user_id": "42"})

    def add_identity(self, identity, *, extension=False, user_id=42):
        table = self.extension_services if extension else self.subscriptions
        self.db.execute(table.insert().values(user_id=user_id, panel_user_uuid=identity))
        self.db.commit()
        self.panel_state[identity] = True

    async def test_control_ban_disables_two_core_identities(self):
        self.add_identity(PRIMARY)
        self.add_identity(SECONDARY)
        self.add_identity(EXTENSION, user_id=99)
        response = await self.namespace["admin_user_ban_route"](self.request)
        self.assertEqual(response["status"], 200)
        self.assertEqual(self.panel_state, {PRIMARY: False, SECONDARY: False, EXTENSION: True})
        self.assertTrue(self.user.is_banned)
        self.assertTrue(self.session.committed)

    async def test_gap_collector_omits_extension_table(self):
        self.add_identity(PRIMARY)
        self.add_identity(EXTENSION, extension=True)
        identities = await self.collect(self.session, 42, user=self.user)
        self.assertEqual(identities, [PRIMARY])
        self.assertEqual(
            self.db.execute(select(self.extension_services.c.panel_user_uuid)).scalars().all(),
            [EXTENSION],
        )

    async def test_gap_ban_reports_success_with_extension_connections_untouched(self):
        self.add_identity(PRIMARY, extension=True)
        self.add_identity(SECONDARY, extension=True)
        response = await self.namespace["admin_user_ban_route"](self.request)
        self.assertEqual(response["status"], 200)
        self.assertTrue(self.user.is_banned)
        self.assertTrue(self.session.committed)
        self.assertEqual(self.panel_calls, [])
        self.assertEqual(self.panel_state, {PRIMARY: True, SECONDARY: True})

    async def test_gap_mixed_account_only_bans_core_identity(self):
        self.add_identity(PRIMARY)
        self.add_identity(EXTENSION, extension=True)
        response = await self.namespace["admin_user_ban_route"](self.request)
        self.assertEqual(response["status"], 200)
        self.assertEqual(self.panel_state, {PRIMARY: False, EXTENSION: True})

    async def test_control_delete_revokes_two_core_identities(self):
        self.add_identity(PRIMARY)
        self.add_identity(SECONDARY)
        response = await self.namespace["admin_user_delete_route"](self.request)
        self.assertEqual(response["status"], 200)
        self.assertEqual(self.panel_state, {})
        self.local_delete.assert_awaited_once_with(self.session, 42)
        self.assertTrue(self.session.committed)

    async def test_gap_delete_reports_success_without_revoking_extension_identity(self):
        self.add_identity(EXTENSION, extension=True)
        response = await self.namespace["admin_user_delete_route"](self.request)
        self.assertEqual(response["status"], 200)
        self.local_delete.assert_awaited_once_with(self.session, 42)
        self.assertTrue(self.session.committed)
        self.assertEqual(self.panel_calls, [])
        self.assertEqual(self.panel_state, {EXTENSION: True})

    async def test_control_panel_failure_prevents_local_ban_commit(self):
        self.add_identity(PRIMARY)
        self.panel.update_user_status_on_panel.side_effect = None
        self.panel.update_user_status_on_panel.return_value = False
        response = await self.namespace["admin_user_ban_route"](self.request)
        self.assertEqual(response["status"], 502)
        self.assertFalse(self.user.is_banned)
        self.assertFalse(self.session.committed)
        self.assertTrue(self.session.rolled_back)


if __name__ == "__main__":
    unittest.main(verbosity=2)
