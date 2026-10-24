"""Real aiohttp routes, roles and CSRF; only upstream reads/writes are faked."""

from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import func, select

from bot.app.web.admin_api_impl.auth import admin_auth_middleware
from bot.app.web.admin_console_node_onboarding_routes import (
    setup_admin_console_node_onboarding_routes,
)
from bot.app.web.admin_console_resource_operation_routes import (
    resource_private_response,
    setup_admin_console_resource_operation_routes,
)
from bot.app.web.admin_console_resource_routes import setup_admin_console_resource_routes
from bot.app.web.context import PANEL_SERVICE, SESSION_FACTORY, SETTINGS
from bot.app.web.webapp.assets import _csrf_protection_middleware
from bot.app.web.webapp_auth import create_webapp_session_token
from bot.services.service_change_sync import ServiceChangeWorker
from db.resource_operation_models import ResourceOperation
from tests.unit.test_admin_console_resource_preview import N1, SECRET
from tests.unit.test_resource_operations import ResourceOperationDatabaseCase

PATH = "/api/admin/console/resources/operations"
DEPLOY = "/api/admin/console/nodes/onboarding/deployment"


def test_private_hook_is_added_once_in_both_setup_orders() -> None:
    for first, second in (
        (setup_admin_console_node_onboarding_routes, setup_admin_console_resource_operation_routes),
        (setup_admin_console_resource_operation_routes, setup_admin_console_node_onboarding_routes),
    ):
        app = web.Application()
        first(app)
        second(app)
        assert list(app.on_response_prepare).count(resource_private_response) == 1


@pytest.mark.filterwarnings(
    "ignore:It is recommended to use web.RequestKey: aiohttp.web_exceptions.NotAppKeyWarning"
)
class ResourceOperationHttpTests(ResourceOperationDatabaseCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        app = web.Application(middlewares=[_csrf_protection_middleware, admin_auth_middleware])
        app[SETTINGS] = self.panel.settings
        app[SESSION_FACTORY] = self.sessions
        app[PANEL_SERVICE] = self.panel
        setup_admin_console_node_onboarding_routes(app)
        setup_admin_console_resource_operation_routes(app)
        setup_admin_console_resource_routes(app)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.token = create_webapp_session_token(self.panel.settings, 1)
        self.admin = {"Authorization": "Bearer " + self.token}

    async def test_all_roles_and_csrf_are_checked_before_sources_or_secret_generation(self) -> None:
        ordinary = {
            "Authorization": "Bearer " + create_webapp_session_token(self.panel.settings, 2)
        }
        for method, path in (
            ("GET", PATH),
            ("GET", PATH + "/" + "a" * 32),
            ("POST", PATH),
            ("POST", PATH + "/" + "a" * 32 + "/retry"),
            ("POST", PATH + "/" + "a" * 32 + "/reconcile"),
            ("POST", PATH + "/" + "a" * 32 + "/evidence"),
            ("POST", DEPLOY),
        ):
            response = await self.client.request(method, path, headers=ordinary, data=SECRET)
            assert response.status == 403
            assert response.headers["Cache-Control"] == "private, no-store"
            assert SECRET not in await response.text()
            if method == "POST":
                response = await self.client.post(
                    path, cookies={"rw_webapp_session": self.token}, json={}
                )
                assert response.status == 403
                assert response.headers["Cache-Control"] == "private, no-store"
        self.reads.assert_not_awaited()
        self.writes.assert_not_awaited()

    async def test_http_submit_commits_only_and_get_polls_the_same_worker_operation(self) -> None:
        change = {"operation": "node_disable", "target_id": N1}
        response = await self.client.post(
            "/api/admin/console/resources/preview", headers=self.admin, json={"change": change}
        )
        assert response.status == 200, await response.text()
        preview = await response.json()
        assert preview["execution_available"] is True
        body = {
            "change": change,
            "expected_fingerprint": preview["fingerprint"],
            "idempotency_key": "http-intent",
        }
        response = await self.client.post(PATH, headers=self.admin, json=body)
        assert response.status == 200, await response.text()
        accepted = await response.json()
        operation = accepted["operation"]
        assert operation["status"] == "pending" and operation["attempts"] == []
        assert response.headers["Cache-Control"] == "private, no-store"
        self.writes.assert_not_awaited()
        duplicate = await self.client.post(PATH, headers=self.admin, json=body)
        assert (await duplicate.json())["duplicate"] is True
        await ServiceChangeWorker(self.sessions, self.panel).tick()
        polled = await self.client.get(PATH + "/" + operation["id"], headers=self.admin)
        finished = await polled.json()
        assert finished["id"] == operation["id"] and finished["status"] == "succeeded"
        assert finished["observation"]["runtime"] == "unverified"
        assert SECRET not in await polled.text()
        history = await self.client.get(PATH, headers=self.admin)
        assert (await history.json())["total"] == 1
        assert (await history.json())["items"][0]["id"] == operation["id"]
        self.writes.assert_awaited_once()

    async def test_keygen_is_explicit_one_shot_private_and_not_persisted(self) -> None:
        generated = AsyncMock(return_value={"status_code": 200, "response": {"secretKey": SECRET}})
        self.panel._request_once = generated
        response = await self.client.post(
            DEPLOY, headers=self.admin, json={"management_port": 2222}
        )
        assert response.status == 200, await response.text()
        assert response.headers["Cache-Control"] == "private, no-store"
        body = await response.json()
        assert body["secret_key"] == SECRET and body["installation_performed"] is False
        assert body["credential_semantics"] == "new_node_certificate_existing_panel_ca"
        generated.assert_awaited_once()
        assert generated.await_args is not None
        assert generated.await_args.args == ("GET", "/keygen")
        assert generated.await_args.kwargs["log_full_response"] is False
        async with self.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(ResourceOperation)) == 0
        self.panel.settings.PANEL_WRITE_MODE = "dry_run"
        generated.reset_mock()
        response = await self.client.post(
            DEPLOY, headers=self.admin, json={"management_port": 2222}
        )
        assert response.status == 409 and (await response.json())["error"] == "resource_dry_run"
        generated.assert_not_awaited()

    async def test_input_and_source_exceptions_never_echo_secrets(self) -> None:
        response = await self.client.post(PATH, headers=self.admin, json={"password": SECRET})
        assert response.status == 400 and SECRET not in await response.text()
        self.panel._request_once = AsyncMock(side_effect=RuntimeError(SECRET))
        response = await self.client.post(
            DEPLOY, headers=self.admin, json={"management_port": 2222}
        )
        assert response.status == 503 and SECRET not in await response.text()
        assert response.headers["Cache-Control"] == "private, no-store"
