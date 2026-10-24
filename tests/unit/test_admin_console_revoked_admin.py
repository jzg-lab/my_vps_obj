"""UA-02: old authenticated sessions cannot retain revoked console permissions."""

import re
from contextlib import ExitStack
from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest
from aiohttp import DummyCookieJar, web
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import event, select

from bot.app.web import (
    admin_console_exit_replacement_routes,
    admin_console_global_operations_routes,
    admin_console_nodes_routes,
    admin_console_operations_routes,
    admin_console_resource_routes,
    admin_console_services_routes,
)
from bot.app.web.admin_api_impl.auth import admin_auth_middleware
from bot.app.web.cache_headers import api_no_store_middleware
from bot.app.web.context import PANEL_SERVICE, SESSION_FACTORY, SETTINGS
from bot.app.web.webapp.assets import _csrf_protection_middleware
from bot.app.web.webapp.auth_common import _hash_email_password
from bot.app.web.webapp.routes import setup_subscription_webapp_routes
from bot.app.web.webapp_auth import verify_webapp_session_token
from config.settings import Settings
from db.auth_models import AccountRole
from db.models import User
from db.service_models import (
    ServiceConnection,
    ServiceOperationExecution,
    ServiceOrder,
    UserService,
)
from tests.unit.test_admin_console_resource_preview import N1, inventory_fixture, panel_fixture
from tests.unit.test_user_services import ServiceDatabaseTestCase


@pytest.mark.filterwarnings(
    "ignore:It is recommended to use web.RequestKey: aiohttp.web_exceptions.NotAppKeyWarning"
)
class RevokedConsoleAdminTests(ServiceDatabaseTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.settings = Settings(
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            BOT_TOKEN="1234567890:AA_secret_bot_token_value",
            WEBAPP_SESSION_SECRET="isolated-revocation-test-secret",
            EMAIL_LOGIN_ENABLED=True,
            SMTP_HOST="smtp.invalid",
            SMTP_USERNAME="test",
            SMTP_PASSWORD="test",
            SMTP_FROM_EMAIL="test@example.com",
            REDIS_URL=None,
            ADMIN_PANEL_STATS_CACHE_TTL_SECONDS=600,
            _env_file=None,
        )
        self.panel, self.panel_request = panel_fixture(inventory_fixture())
        # Real auth/cache middleware in production order, without unrelated startup jobs.
        self.app = web.Application(
            middlewares=[
                api_no_store_middleware,
                _csrf_protection_middleware,
                admin_auth_middleware,
            ]
        )
        self.app[SETTINGS] = self.settings
        self.app[SESSION_FACTORY] = self.sessions
        self.app[PANEL_SERVICE] = self.panel
        setup_subscription_webapp_routes(self.app)
        self.client = TestClient(TestServer(self.app), cookie_jar=DummyCookieJar())
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.statements: list[str] = []
        event.listen(self.engine.sync_engine, "before_cursor_execute", self._record_sql)
        self.addCleanup(
            event.remove, self.engine.sync_engine, "before_cursor_execute", self._record_sql
        )

    def _record_sql(
        self,
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        self.statements.append(statement)

    async def _business_snapshot(self) -> dict[str, list[dict[str, object]]]:
        async with self.sessions() as session:
            return {
                table.name: [dict(row) for row in (await session.execute(select(table))).mappings()]
                for table in (
                    UserService.__table__,
                    ServiceConnection.__table__,
                    ServiceOrder.__table__,
                    ServiceOperationExecution.__table__,
                )
            }

    async def _exercise_revocation(self, role: str) -> None:
        password = "Isolated-Revocation-2026!"
        async with self.sessions.begin() as session:
            user = await session.get(User, 2)
            assert user is not None
            user.email = "revoked-admin@example.com"
            user.email_verified_at = datetime.now(UTC)
            user.password_hash = _hash_email_password(password)
            session.add(AccountRole(user_id=2, role=role))
        service, _, _ = await self.activate(user_id=2)
        async with self.sessions() as session:
            operation = await session.scalar(
                select(ServiceOperationExecution).where(
                    ServiceOperationExecution.service_id == service.id,
                    ServiceOperationExecution.phase == "prepare",
                )
            )
            assert operation is not None
            operation_id = operation.id

        login = await self.client.post(
            "/api/auth/email/password",
            json={"email": "revoked-admin@example.com", "password": password},
        )
        assert login.status == 200
        login_body = await login.json()
        assert login_body["ok"] is True and login_body["user_id"] == 2
        token = login_body["token"]
        csrf = login_body["csrf_token"]
        assert login.cookies["rw_webapp_session"].value == token
        assert login.cookies["rw_webapp_csrf"].value == csrf
        assert login.cookies["rw_webapp_session"]["secure"]
        # Replay the actual Secure cookies explicitly over aiohttp's isolated HTTP server.
        cookie_headers = {
            "Cookie": f"rw_webapp_session={token}; rw_webapp_csrf={csrf}",
            "X-CSRF-Token": csrf,
        }
        bearer_headers = {"Authorization": f"Bearer {token}"}
        path = f"/api/admin/console/services/{service.id}"
        preview: dict[str, object] = {
            "change": {"operation": "node_restart", "target_id": N1},
        }
        requests: list[tuple[str, str, dict[str, object] | None]] = [
            ("GET", "/api/admin/console/summary", None),
            ("GET", "/api/admin/console/services", None),
            ("GET", path, None),
            ("GET", "/api/admin/console/nodes", None),
            ("GET", f"/api/admin/console/nodes/{N1}", None),
            ("GET", path + "/resources", None),
            ("GET", f"/api/admin/console/operations?service_id={service.id}", None),
            (
                "POST",
                "/api/admin/console/service-preflight",
                {"user_id": 2, "plan_id": self.plan.id, "expected_revision": self.plan.revision},
            ),
            ("GET", path + "/diagnostics", None),
            ("GET", path + "/operations", None),
            ("GET", path + "/exit-replacement", None),
            ("GET", "/api/admin/console/resources/catalog", None),
            ("POST", "/api/admin/console/resources/preview", preview),
            (
                "POST",
                "/api/admin/console/resources/revalidate",
                {**preview, "expected_fingerprint": "0" * 64},
            ),
            (
                "POST",
                path + f"/operations/{operation_id}/retry",
                {
                    "user_id": 2,
                    "expected_revision": service.revision,
                    "idempotency_key": "isolated-revocation-retry",
                },
            ),
        ]
        for method, endpoint, body in requests:
            response = await self.client.request(
                method, endpoint, json=body, headers=cookie_headers
            )
            assert response.status == 200, (method, endpoint, await response.text())
            assert (await response.json())["ok"] is True
            assert response.headers["Cache-Control"] == "private, no-store"

        # The shared-service fixture has no replacement. Prove the three write routes
        # reach validation before revocation, then verify auth wins over the same body.
        for suffix in ("", "/confirm", "/evidence"):
            endpoint = path + "/exit-replacement" + suffix
            response = await self.client.post(endpoint, json={}, headers=cookie_headers)
            assert response.status == 400
            assert await response.json() == {
                "ok": False,
                "error": "invalid_replacement_request",
                "message": "invalid_replacement_request",
            }
            assert response.headers["Cache-Control"] == "private, no-store"
            requests.append(("POST", endpoint, {}))

        # A live cache hit before revocation is essential; empty or disabled caches prove less.
        panel_reads = self.panel_request.await_count
        cached = await self.client.get("/api/admin/console/nodes", headers=cookie_headers)
        assert cached.status == 200 and (await cached.json())["total"] == 3
        assert self.panel_request.await_count == panel_reads and panel_reads > 0
        before = await self._business_snapshot()
        async with self.sessions.begin() as session:
            assignment = await session.get(AccountRole, (2, role))
            assert assignment is not None and assignment.revoked_at is None
            # Simulate a separately committed revocation; keep the user/session/CSRF intact.
            assignment.revoked_at = datetime.now(UTC)
            assignment.revoked_by = 1

        # The token is not expired: 403 must come from the current database role, not 401/CSRF.
        assert verify_webapp_session_token(self.settings, token) == 2
        restored = await self.client.get("/api/auth/session", headers=cookie_headers)
        assert restored.status == 200
        assert await restored.json() == {"ok": True, "authenticated": True, "csrf_token": csrf}
        assert not restored.cookies

        with ExitStack() as stack:
            business_access: list[Mock] = [
                stack.enter_context(patch.object(module, accessor, wraps=getattr(module, accessor)))
                for module in (
                    admin_console_exit_replacement_routes,
                    admin_console_services_routes,
                    admin_console_nodes_routes,
                    admin_console_global_operations_routes,
                    admin_console_operations_routes,
                    admin_console_resource_routes,
                )
                for accessor in ("get_session_factory", "get_panel_service")
                if hasattr(module, accessor)
            ]
            for transport, headers in (
                ("cookie-and-csrf", cookie_headers),
                ("old-bearer", bearer_headers),
                ("cookie-csrf-and-old-bearer", {**cookie_headers, **bearer_headers}),
            ):
                for malformed in (False, True):
                    for method, endpoint, body in requests:
                        with self.subTest(transport=transport, malformed=malformed, path=endpoint):
                            self.statements.clear()
                            target = endpoint
                            if malformed and method == "GET":
                                target += ("&" if "?" in target else "?") + "invalid_filter=1"
                            response = await self.client.request(
                                method,
                                target,
                                json=body if not malformed else None,
                                data="{" if malformed and method == "POST" else None,
                                headers={
                                    **headers,
                                    "If-None-Match": "*",
                                    "If-Modified-Since": "Wed, 01 Jan 2031 00:00:00 GMT",
                                },
                            )
                            assert response.status == 403
                            assert await response.json() == {"ok": False, "error": "forbidden"}
                            assert "no-store" in response.headers["Cache-Control"]
                            assert not response.cookies
                            for accessor in business_access:
                                accessor.assert_not_called()
                            assert self.panel_request.await_count == panel_reads
                            assert len(self.statements) == 2
                            assert all(sql.lstrip().startswith("SELECT") for sql in self.statements)
                            assert [
                                table
                                for sql in self.statements
                                for table in re.findall(r"\b(?:FROM|JOIN)\s+(\w+)", sql)
                            ] == ["users", "account_roles"]
        assert await self._business_snapshot() == before
        assert verify_webapp_session_token(self.settings, token) == 2

    async def test_revoked_admin_rejects_old_credentials_before_business_and_cache(self) -> None:
        await self._exercise_revocation("admin")

    async def test_revoked_owner_rejects_old_credentials_before_business_and_cache(self) -> None:
        await self._exercise_revocation("owner")
