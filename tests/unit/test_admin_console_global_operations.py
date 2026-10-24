"""Global route validation, cursor boundaries and flat safe responses."""

import base64
import json
from datetime import datetime, timedelta
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.app.web.admin_console_global_operations_routes import (
    setup_admin_console_global_operations_routes,
)
from bot.app.web.admin_console_global_operations_schemas import ConsoleGlobalOperationsQuery
from bot.app.web.context import SESSION_FACTORY
from db.dal.global_service_operations_dal import OperationPosition
from tests.unit.test_global_service_operations_dal import STAMP, GlobalOperationDatabaseCase

PATH = "/api/admin/console/operations"


class AdminConsoleGlobalOperationsTests(GlobalOperationDatabaseCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        app = web.Application()
        app[SESSION_FACTORY] = self.sessions
        setup_admin_console_global_operations_routes(app)
        # Public authentication middleware is verified by the integration owner.
        auth = patch(
            "bot.app.web.admin_console_global_operations_routes._require_admin_user_id",
            return_value=1,
        )
        self.require_admin = auth.start()
        self.addCleanup(auth.stop)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

    async def test_response_pagination_source_and_secret_whitelist(self) -> None:
        order_id = await self.add_record(1, record_type="order")
        await self.add_record(
            1, order_id=order_id, source="administrator", error="NEVER_EXPOSE_ERROR"
        )
        await self.add_record(2, service=self.archived, status="unknown")
        response = await self.client.get(PATH, params={"limit": "1"})
        assert response.status == 200
        assert response.headers["Cache-Control"] == "private, no-store"
        payload = await response.json()
        assert payload["ok"] is True and payload["total"] == 2 and payload["limit"] == 1
        assert datetime.fromisoformat(payload["observed_at"]).utcoffset() == timedelta(0)
        assert set(payload) == {"ok", "operations", "total", "limit", "next_cursor", "observed_at"}
        operation = payload["operations"][0]
        assert operation["source"] == "administrator" and operation["actor_id"] == 1
        assert operation["kind"] == "activate"
        assert operation["error_code"] == "unclassified_service_error"
        assert "NEVER_EXPOSE" not in await response.text()
        assert not {
            "request",
            "snapshot",
            "idempotency_key",
            "request_owner_id",
            "panel_user_uuid",
            "terms",
        } & set(operation)
        second = await self.client.get(
            PATH, params={"limit": "1", "cursor": payload["next_cursor"]}
        )
        next_page = await second.json()
        assert second.status == 200 and next_page["total"] == 2
        assert next_page["next_cursor"] is None
        assert next_page["operations"][0]["archived"] is True
        assert set(next_page["operations"][0]["customer"].values()) == {None}
        assert self.require_admin.call_count == 2

    async def test_invalid_query_is_400_before_any_database_access(self) -> None:
        invalid = [
            "unknown=1",
            "limit=0",
            "limit=201",
            "limit=1.0",
            "limit=+1",
            "limit=true",
            "limit=1&limit=1",
            "status=failed&status=failed",
            "status=bad",
            "phase=bad",
            "archived=true",
            "service_id=abc",
            "service_id=" + "A" * 32,
            "user_id=9007199254740992",
            "user_id=-9007199254740992",
            "user_id=1.0",
            "needs_attention=1",
            "needs_attention=yes",
            "needs_attention=TRUE",
            "user_id=",
            "cursor=",
            "cursor=!!!!",
            "cursor=A",
            "cursor=AA",
            "cursor=abcd=",
            "cursor=" + "A" * 1025,
        ]
        with patch(
            "bot.app.web.admin_console_global_operations_routes.get_session_factory"
        ) as database:
            for query in invalid:
                with self.subTest(query=query):
                    response = await self.client.get(PATH + "?" + query)
                    assert response.status == 400, await response.text()
                    assert response.headers["Cache-Control"] == "private, no-store"
            database.assert_not_called()

    async def test_cursor_rejects_changed_filters_and_invalid_payloads(self) -> None:
        query = ConsoleGlobalOperationsQuery(status="unknown", needs_attention=True)
        cursor = query.next_cursor(OperationPosition(STAMP, "execution", "1" * 32))
        changed = [
            {"status": "failed"},
            {"phase": "usage"},
            {"user_id": "2"},
            {"service_id": "2" * 32},
            {"archived": "only"},
            {"needs_attention": "false"},
        ]
        for changes in changed:
            response = await self.client.get(
                PATH,
                params={
                    "status": "unknown",
                    "needs_attention": "true",
                    "cursor": cursor,
                    **changes,
                },
            )
            assert response.status == 400
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        original = json.loads(raw)
        corruptions: list[dict[str, object]] = [
            {"version": 2},
            {"version": True},
            {"extra": "value"},
            {"record_type": "service"},
            {"id": "invalid"},
            {"filters": "0" * 64},
            {"created_at": "not-a-date"},
            {"created_at": "2026-01-01T00:00:00"},
            {"created_at": "10000-01-01T00:00:00+00:00"},
            {"created_at": "0001-01-01T00:00:00+23:00"},
            {"created_at": "9999-12-31T23:59:59-23:00"},
            {"created_at": 42},
        ]
        payloads = [
            json.dumps({**original, **changes}, separators=(",", ":")) for changes in corruptions
        ]
        payloads += [raw.decode()[:-1] + ',"id":"' + "1" * 32 + '"}', "[]", "null", "{"]
        for payload in payloads:
            with self.subTest(payload=payload):
                damaged = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
                response = await self.client.get(
                    PATH, params={"status": "unknown", "needs_attention": "true", "cursor": damaged}
                )
                assert response.status == 400, await response.text()

    async def test_cursor_allows_limit_change_and_empty_page_keeps_total(self) -> None:
        await self.add_record(1)
        query = ConsoleGlobalOperationsQuery()
        for timestamp in (STAMP, STAMP - timedelta(days=1)):
            cursor = query.next_cursor(OperationPosition(timestamp, "order", "f" * 32))
            response = await self.client.get(
                PATH,
                params={
                    "cursor": cursor,
                    "limit": "200",
                    "status": "all",
                    "needs_attention": "false",
                },
            )
            payload = await response.json()
            assert response.status == 200 and payload["total"] == 1
            assert payload["operations"] == [] and payload["next_cursor"] is None

    async def test_auth_guard_is_called_before_query_or_database(self) -> None:
        self.require_admin.side_effect = web.HTTPUnauthorized()
        with patch(
            "bot.app.web.admin_console_global_operations_routes.get_session_factory"
        ) as database:
            response = await self.client.get(PATH + "?limit=invalid")
            assert response.status == 401
            database.assert_not_called()
