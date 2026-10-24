"""UC-07/08, UA-02: real sessions must authorize before resource or secret access."""

import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiohttp import ClientError, ClientResponse, DummyCookieJar, ServerTimeoutError, web
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import event, select, update

from bot.app.web import (
    admin_console_node_onboarding_routes as onboarding_routes,
)
from bot.app.web import (
    admin_console_resource_operation_routes as operation_routes,
)
from bot.app.web.admin_api_impl.auth import admin_auth_middleware
from bot.app.web.admin_console_resource_schemas import ConsoleResourcePreviewBody
from bot.app.web.cache_headers import api_no_store_middleware
from bot.app.web.context import PANEL_SERVICE, SESSION_FACTORY, SETTINGS
from bot.app.web.webapp.assets import _csrf_protection_middleware
from bot.app.web.webapp.auth_common import _hash_email_password
from bot.app.web.webapp.routes import setup_subscription_webapp_routes
from bot.app.web.webapp_auth import verify_webapp_session_token
from bot.services.panel_api_contracts import PanelApiOperation
from bot.services.panel_api_service import PanelApiService
from bot.services.resource_preview_read import stable_resource_preview
from config.settings import Settings
from db.auth_models import AccountRole
from db.models import User
from db.resource_operation_models import ResourceOperation
from tests.unit.test_admin_console_resource_preview import N1, SECRET, inventory_fixture
from tests.unit.test_user_services import ServiceDatabaseTestCase

OPERATIONS = "/api/admin/console/resources/operations"
DEPLOYMENT = "/api/admin/console/nodes/onboarding/deployment"
OPERATION_ID = "a" * 32
DEPLOYMENT_SECRET = "isolated-node-certificate-secret-never-persist"
PANEL_KEY = "isolated-panel-api-key-never-return"
PANEL_URL = "https://panel.invalid/api"

type RequestCase = tuple[str, str, dict[str, object] | None]


@dataclass
class PanelResponse:
    status: int
    body: str
    headers: ClassVar[dict[str, str]] = {"Content-Type": "application/json"}

    async def __aenter__(self) -> "PanelResponse":
        return self

    async def __aexit__(self, *_args: object) -> None:
        pass

    async def text(self) -> str:
        return self.body


@pytest.mark.filterwarnings(
    "ignore:It is recommended to use web.RequestKey: aiohttp.web_exceptions.NotAppKeyWarning"
)
class ResourceOperationsAuthTests(ServiceDatabaseTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.settings = Settings.model_validate(
            {
                "POSTGRES_USER": "test",
                "POSTGRES_PASSWORD": "test",
                "BOT_TOKEN": "1234567890:AA_secret_bot_token_value",
                "WEBAPP_SESSION_SECRET": "isolated-resource-auth-secret",
                "WEBAPP_SESSION_TTL_SECONDS": 600,
                "EMAIL_LOGIN_ENABLED": True,
                "SMTP_HOST": "smtp.invalid",
                "SMTP_USERNAME": "test",
                "SMTP_PASSWORD": "test",
                "SMTP_FROM_EMAIL": "test@example.com",
                "PANEL_API_URL": PANEL_URL,
                "PANEL_API_KEY": PANEL_KEY,
                "REDIS_URL": None,
                "_env_file": None,
            }
        )
        self.inventory = inventory_fixture()
        self.keygen_result: PanelResponse | Exception = PanelResponse(
            200, json.dumps({"response": {"secretKey": DEPLOYMENT_SECRET, "apiKey": PANEL_KEY}})
        )
        self.panel = PanelApiService(self.settings)
        self.transport = Mock(side_effect=self._panel_request)
        # Keep real Panel parsing/redaction; replace only the network transport.
        self.panel_session = self.enterContext(
            patch.object(
                self.panel,
                "_get_session",
                new=AsyncMock(return_value=SimpleNamespace(request=self.transport)),
            )
        )
        self.panel_once = self.enterContext(
            patch.object(self.panel, "_request_once", wraps=self.panel._request_once)
        )
        change = ConsoleResourcePreviewBody.model_validate(
            {"change": {"operation": "node_restart", "target_id": N1}}
        ).change
        async with self.sessions.begin() as session:
            preview, _ = await stable_resource_preview(session, self.panel, change)
            assert preview.coverage == "complete" and preview.fingerprint is not None
            self.fingerprint = preview.fingerprint
            attempted_at = datetime.now(UTC) - timedelta(seconds=1)
            session.add(
                ResourceOperation(
                    id=OPERATION_ID,
                    actor_id=2,
                    idempotency_key="auth-existing-operation",
                    operation="node_restart",
                    target_id=N1,
                    request=change.model_dump(mode="json"),
                    preview=preview.model_dump(mode="json"),
                    baseline_ids=[],
                    fingerprint=self.fingerprint,
                    status="failed",
                    gate_key=None,
                    version=1,
                    attempt_count=1,
                    attempts=[
                        {"number": 1, "started_at": attempted_at.isoformat(), "receipt": "rejected"}
                    ],
                    evidence=[],
                    error_code="resource_write_rejected",
                    created_at=attempted_at,
                    attempted_at=attempted_at,
                    completed_at=attempted_at,
                )
            )
        self.cases: list[RequestCase] = [
            ("GET", OPERATIONS, None),
            ("GET", f"{OPERATIONS}/{OPERATION_ID}", None),
            (
                "POST",
                OPERATIONS,
                {
                    "change": change.model_dump(mode="json"),
                    "expected_fingerprint": self.fingerprint,
                    "idempotency_key": "auth-submission",
                },
            ),
            (
                "POST",
                f"{OPERATIONS}/{OPERATION_ID}/retry",
                {"expected_version": 1, "expected_fingerprint": self.fingerprint},
            ),
            ("POST", f"{OPERATIONS}/{OPERATION_ID}/reconcile", {"expected_version": 1}),
            (
                "POST",
                f"{OPERATIONS}/{OPERATION_ID}/evidence",
                {
                    "expected_version": 1,
                    "attempt": 1,
                    "result": "not_applied",
                    "evidence_digest": "b" * 64,
                    "checked_at": datetime.now(UTC).isoformat(),
                },
            ),
            ("POST", DEPLOYMENT, {"management_port": 2222}),
        ]
        app = web.Application(
            middlewares=[
                api_no_store_middleware,
                _csrf_protection_middleware,
                admin_auth_middleware,
            ]
        )
        app[SETTINGS] = self.settings
        app[SESSION_FACTORY] = self.sessions
        app[PANEL_SERVICE] = self.panel
        # Production registration, including all seven routes and real login/session routes.
        setup_subscription_webapp_routes(app)
        self.client = TestClient(TestServer(app), cookie_jar=DummyCookieJar())
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.statements: list[str] = []
        event.listen(self.engine.sync_engine, "before_cursor_execute", self._record_sql)
        self.addCleanup(
            event.remove, self.engine.sync_engine, "before_cursor_execute", self._record_sql
        )
        self.business_db = self.enterContext(
            patch.object(
                operation_routes, "get_session_factory", wraps=operation_routes.get_session_factory
            )
        )
        self.business_panel = self.enterContext(
            patch.object(
                operation_routes, "get_panel_service", wraps=operation_routes.get_panel_service
            )
        )
        self.deployment_panel = self.enterContext(
            patch.object(
                onboarding_routes, "get_panel_service", wraps=onboarding_routes.get_panel_service
            )
        )

    def _panel_request(self, method: str, url: str, **kwargs: object) -> PanelResponse:
        assert method == "GET" and url.startswith(PANEL_URL + "/"), (method, url)
        headers = kwargs["headers"]
        assert isinstance(headers, dict) and headers["Authorization"] == f"Bearer {PANEL_KEY}"
        endpoint = url.removeprefix(PANEL_URL)
        if endpoint == "/keygen":
            if isinstance(self.keygen_result, Exception):
                raise self.keygen_result
            return self.keygen_result
        return PanelResponse(200, json.dumps({"response": self.inventory[endpoint]}))

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

    async def _snapshot(self) -> list[dict[str, object]]:
        async with self.sessions() as session:
            return [
                dict(row)
                for row in (await session.execute(select(ResourceOperation.__table__))).mappings()
            ]

    def _reset_access(self) -> None:
        self.statements.clear()
        for mock in (
            self.business_db,
            self.business_panel,
            self.deployment_panel,
            self.transport,
            self.panel_session,
            self.panel_once,
        ):
            mock.reset_mock()

    def _assert_only_auth_sql(self, tables: list[str]) -> None:
        assert all(sql.lstrip().startswith("SELECT") for sql in self.statements)
        assert [
            table
            for sql in self.statements
            for table in re.findall(r"\b(?:FROM|JOIN)\s+(\w+)", sql)
        ] == tables

    async def _login(self, role: str | None = "admin") -> tuple[str, str]:
        async with self.sessions.begin() as session:
            await session.execute(
                update(User)
                .where(User.user_id == 2)
                .values(
                    email="resource-admin@example.com",
                    email_verified_at=datetime.now(UTC),
                    password_hash=_hash_email_password("Isolated-Auth-2026!"),
                )
            )
            if role is not None:
                session.add(AccountRole(user_id=2, role=role))
        response = await self.client.post(
            "/api/auth/email/password",
            json={"email": "resource-admin@example.com", "password": "Isolated-Auth-2026!"},
        )
        assert response.status == 200, await response.text()
        result = await response.json()
        assert result["ok"] is True and result["user_id"] == 2
        token, csrf = result["token"], result["csrf_token"]
        assert response.cookies["rw_webapp_session"].value == token
        assert response.cookies["rw_webapp_session"]["secure"]
        assert response.cookies["rw_webapp_csrf"].value == csrf
        assert verify_webapp_session_token(self.settings, token) == 2
        return token, csrf

    @staticmethod
    def _headers(token: str, csrf: str) -> tuple[dict[str, str], ...]:
        cookie = {
            "Cookie": f"rw_webapp_session={token}; rw_webapp_csrf={csrf}",
            "X-CSRF-Token": csrf,
        }
        bearer = {"Authorization": f"Bearer {token}"}
        return cookie, bearer, {**cookie, **bearer}

    async def _denied(
        self,
        headers: dict[str, str],
        status: int,
        error: str,
        tables: list[str],
        *,
        writes_only: bool = False,
    ) -> None:
        before = await self._snapshot()
        assert len(before) == 1
        for method, endpoint, body in self.cases:
            if writes_only and method != "POST":
                continue
            for malformed in (False, True):
                with self.subTest(method=method, endpoint=endpoint, malformed=malformed):
                    self._reset_access()
                    response = await self.client.request(
                        method,
                        endpoint + ("?limit=invalid" if malformed and method == "GET" else ""),
                        headers={**headers, "If-None-Match": "*"},
                        json=body if not malformed else None,
                        data="{" if malformed and method == "POST" else None,
                    )
                    assert response.status == status, (endpoint, await response.text())
                    result = await response.json()
                    assert result["ok"] is False and result["error"] == error, result
                    assert set(result) <= {"ok", "error", "message"}
                    response_text = await response.text()
                    assert all(
                        secret not in response_text
                        for secret in (DEPLOYMENT_SECRET, PANEL_KEY, SECRET)
                    )
                    assert response.headers["Cache-Control"] == "private, no-store"
                    assert not response.cookies
                    for accessor in (self.business_db, self.business_panel, self.deployment_panel):
                        accessor.assert_not_called()
                    self.panel_once.assert_not_awaited()
                    self.panel_session.assert_not_awaited()
                    self.transport.assert_not_called()
                    self._assert_only_auth_sql(tables)
        assert await self._snapshot() == before

    async def _ok(self, case: RequestCase, headers: dict[str, str]) -> ClientResponse:
        method, endpoint, body = case
        self._reset_access()
        response = await self.client.request(method, endpoint, json=body, headers=headers)
        assert response.status == 200, (endpoint, await response.text())
        assert (await response.json())["ok"] is True
        assert response.headers["Cache-Control"] == "private, no-store"
        text = await response.text()
        assert SECRET not in text and PANEL_KEY not in text
        if endpoint == DEPLOYMENT:
            self.business_db.assert_not_called()
            self.business_panel.assert_not_called()
            self.deployment_panel.assert_called_once()
            self._assert_only_auth_sql(["users", "account_roles"])
        else:
            self.business_db.assert_called_once()
            self.deployment_panel.assert_not_called()
            assert any("resource_operations" in sql for sql in self.statements)
            assert DEPLOYMENT_SECRET not in text
        if method == "GET":
            self.business_panel.assert_not_called()
            self.transport.assert_not_called()
        else:
            if endpoint != DEPLOYMENT:
                self.business_panel.assert_called_once()
            assert self.transport.call_count > 0
            self.panel_session.assert_awaited()
            self.panel_once.assert_awaited()
            assert all(call.args[0] == "GET" for call in self.transport.call_args_list)
        return response

    async def test_anonymous_cannot_access_any_resource_or_deployment_route(self) -> None:
        await self._denied({}, 401, "unauthorized", [])

    async def test_ordinary_account_cannot_access_any_route(self) -> None:
        token, csrf = await self._login(role=None)
        for headers in self._headers(token, csrf):
            await self._denied(headers, 403, "forbidden", ["users", "account_roles"])

    async def _revoked(self, role: str) -> None:
        token, csrf = await self._login(role)
        headers = self._headers(token, csrf)
        # Exercise real records and credential retrieval before revoking the same session.
        for case in (self.cases[0], self.cases[1], self.cases[-1]):
            await self._ok(case, headers[0])
        async with self.sessions.begin() as session:
            assignment = await session.get(AccountRole, (2, role))
            assert assignment is not None and assignment.revoked_at is None
            await session.execute(
                update(AccountRole)
                .where(AccountRole.user_id == 2, AccountRole.role == role)
                .values(revoked_at=datetime.now(UTC), revoked_by=1)
            )
        assert verify_webapp_session_token(self.settings, token) == 2
        restored = await self.client.get("/api/auth/session", headers=headers[0])
        assert restored.status == 200
        assert await restored.json() == {"ok": True, "authenticated": True, "csrf_token": csrf}
        for transport in headers:
            await self._denied(transport, 403, "forbidden", ["users", "account_roles"])

    async def test_revoked_admin_old_cookie_and_bearer_cannot_reach_business(self) -> None:
        await self._revoked("admin")

    async def test_revoked_owner_old_cookie_and_bearer_cannot_reach_business(self) -> None:
        await self._revoked("owner")

    async def test_banned_admin_session_cannot_reach_business(self) -> None:
        token, csrf = await self._login()
        async with self.sessions.begin() as session:
            await session.execute(update(User).where(User.user_id == 2).values(is_banned=True))
        for headers in self._headers(token, csrf):
            await self._denied(headers, 403, "forbidden", ["users"])

    async def test_tampered_and_expired_sessions_do_not_access_database_or_panel(self) -> None:
        token, csrf = await self._login()
        payload, signature = token.split(".")
        tampered = payload + "." + ("A" if signature[0] != "A" else "B") + signature[1:]
        assert verify_webapp_session_token(self.settings, tampered) is None
        for headers in self._headers(tampered, csrf):
            await self._denied(headers, 401, "unauthorized", [])
        with patch("bot.app.web.webapp_auth.time.time", return_value=time.time() + 601):
            assert verify_webapp_session_token(self.settings, token) is None
            for headers in self._headers(token, csrf):
                await self._denied(headers, 401, "unauthorized", [])

    async def test_cookie_writes_require_csrf_before_database_and_panel(self) -> None:
        token, csrf = await self._login()
        cookie = self._headers(token, csrf)[0]
        await self._ok(self.cases[0], cookie)
        for headers in (
            {"Cookie": cookie["Cookie"]},
            {"Cookie": f"rw_webapp_session={token}", "X-CSRF-Token": csrf},
            {**cookie, "X-CSRF-Token": "mismatched"},
            {**cookie, "Origin": "https://untrusted.invalid"},
        ):
            await self._denied(headers, 403, "csrf_failed", [], writes_only=True)

    async def test_authorized_operations_use_real_sql_and_panel_reads(self) -> None:
        token, csrf = await self._login()
        headers = self._headers(token, csrf)[0]
        listed = await (await self._ok(self.cases[0], headers)).json()
        assert listed["total"] == 1 and listed["items"][0]["id"] == OPERATION_ID
        detail = await (await self._ok(self.cases[1], headers)).json()
        assert detail["id"] == OPERATION_ID and detail["can_retry"] is True
        retried = await (await self._ok(self.cases[3], headers)).json()
        assert retried["operation"]["status"] == "pending"
        assert retried["operation"]["version"] == 2
        async with self.sessions.begin() as session:
            row = await session.get(ResourceOperation, OPERATION_ID)
            assert row is not None
            # A recorded unknown attempt is the precondition for both reconciliation APIs.
            row.status, row.completed_at = "unknown", None
            row.attempts = [{**row.attempts[0], "receipt": "unknown"}]
        reconciled = await (
            await self._ok(
                ("POST", f"{OPERATIONS}/{OPERATION_ID}/reconcile", {"expected_version": 2}), headers
            )
        ).json()
        assert reconciled["operation"]["status"] == "unknown"
        assert reconciled["operation"]["gate_active"] is True
        evidence = dict(self.cases[5][2] or {})
        evidence["expected_version"] = reconciled["operation"]["version"]
        accepted = await (
            await self._ok(("POST", f"{OPERATIONS}/{OPERATION_ID}/evidence", evidence), headers)
        ).json()
        assert accepted["operation"]["evidence"][0]["actor_id"] == 2
        async with self.sessions() as session:
            row = await session.get(ResourceOperation, OPERATION_ID)
            assert row is not None and row.status == "failed" and row.gate_key is None
            assert row.evidence[0]["evidence_digest"] == evidence["evidence_digest"]
        assert SECRET not in json.dumps(await self._snapshot(), default=str)

    async def test_authorized_submission_records_actor_without_dispatching(self) -> None:
        token, csrf = await self._login()
        headers = self._headers(token, csrf)[0]
        started = await (await self._ok(self.cases[2], headers)).json()
        assert started["duplicate"] is False
        assert started["operation"]["status"] == "pending"
        request_body = self.cases[2][2]
        assert request_body is not None
        async with self.sessions() as session:
            submitted = await session.get(ResourceOperation, started["operation"]["id"])
            assert submitted is not None and submitted.actor_id == 2
            assert submitted.request == request_body["change"]
            assert submitted.fingerprint == self.fingerprint
            assert submitted.attempt_count == 0 and submitted.attempts == []
        snapshot = json.dumps(await self._snapshot(), default=str)
        assert all(secret not in snapshot for secret in (SECRET, PANEL_KEY, DEPLOYMENT_SECRET))

    async def test_deployment_requires_explicit_post_and_never_persists_secret(self) -> None:
        token, csrf = await self._login()
        cookie, bearer, _ = self._headers(token, csrf)
        before = await self._snapshot()
        for method in ("GET", "HEAD", "OPTIONS", "PUT"):
            self._reset_access()
            response = await self.client.request(method, DEPLOYMENT, headers=cookie)
            assert response.status == 405
            assert "no-store" in response.headers["Cache-Control"]
            assert DEPLOYMENT_SECRET not in await response.text()
            self.deployment_panel.assert_not_called()
            self.business_db.assert_not_called()
            self.transport.assert_not_called()
            self._assert_only_auth_sql(["users", "account_roles"])
        # Valid bearer auth intentionally does not require browser CSRF cookies.
        for headers in (cookie, bearer):
            with self.assertLogs(level="DEBUG") as logs:
                response = await self._ok(self.cases[-1], headers)
            result = await response.json()
            assert result["secret_key"] == DEPLOYMENT_SECRET
            assert result["management_port"] == 2222 and result["installation_performed"] is False
            self.panel_once.assert_any_await(
                "GET",
                "/keygen",
                operation=PanelApiOperation.NODE_KEYGEN,
                log_full_response=False,
                preserve_http_status=True,
            )
            assert [call.args[:2] for call in self.transport.call_args_list] == [
                ("GET", PANEL_URL + "/system/metadata"),
                ("GET", PANEL_URL + "/keygen"),
            ]
            output = "\n".join(logs.output)
            assert "Sensitive response redacted" in output
            assert all(secret not in output for secret in (DEPLOYMENT_SECRET, PANEL_KEY, SECRET))
            assert await self._snapshot() == before

    async def test_deployment_upstream_failures_redact_logs_responses_and_storage(self) -> None:
        token, csrf = await self._login()
        headers = self._headers(token, csrf)[0]
        before = await self._snapshot()
        failures: list[PanelResponse | Exception] = [
            PanelResponse(500, json.dumps({"response": {"secretKey": DEPLOYMENT_SECRET}})),
            PanelResponse(200, DEPLOYMENT_SECRET),
            PanelResponse(200, json.dumps({"response": {"unexpected": DEPLOYMENT_SECRET}})),
            ServerTimeoutError(DEPLOYMENT_SECRET),
            ClientError(DEPLOYMENT_SECRET),
            RuntimeError(DEPLOYMENT_SECRET),
        ]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                self.keygen_result = failure
                self._reset_access()
                with self.assertLogs(level="DEBUG") as logs:
                    response = await self.client.post(
                        DEPLOYMENT, json={"management_port": 2222}, headers=headers
                    )
                assert response.status == 503
                assert await response.json() == {
                    "ok": False,
                    "error": "resource_deployment_unavailable",
                    "message": "resource_deployment_unavailable",
                }
                assert response.headers["Cache-Control"] == "private, no-store"
                self.deployment_panel.assert_called_once()
                self.business_db.assert_not_called()
                self._assert_only_auth_sql(["users", "account_roles"])
                assert self.transport.call_count == 2
                assert self.transport.call_args.args[:2] == ("GET", PANEL_URL + "/keygen")
                output = "\n".join(logs.output)
                assert all(
                    secret not in output for secret in (DEPLOYMENT_SECRET, PANEL_KEY, SECRET)
                )
                assert await self._snapshot() == before

    async def test_deployment_exception_before_transport_is_not_exposed(self) -> None:
        token, csrf = await self._login()
        before = await self._snapshot()
        self._reset_access()
        # The metadata read succeeds, but keygen fails outside _request_once's try block.
        self.panel_session.side_effect = [
            self.panel_session.return_value,
            RuntimeError(DEPLOYMENT_SECRET),
        ]
        with self.assertLogs(level="DEBUG") as logs:
            response = await self.client.post(
                DEPLOYMENT,
                json={"management_port": 2222},
                headers=self._headers(token, csrf)[0],
            )
        assert response.status == 503
        assert await response.json() == {
            "ok": False,
            "error": "resource_sources_incomplete",
            "message": "resource_sources_incomplete",
        }
        assert response.headers["Cache-Control"] == "private, no-store"
        self.deployment_panel.assert_called_once()
        self.business_db.assert_not_called()
        self._assert_only_auth_sql(["users", "account_roles"])
        assert self.panel_session.await_count == 2
        assert self.panel_once.await_count == 2
        self.transport.assert_called_once()
        assert self.transport.call_args.args[:2] == ("GET", PANEL_URL + "/system/metadata")
        assert DEPLOYMENT_SECRET not in "\n".join(logs.output)
        assert await self._snapshot() == before
