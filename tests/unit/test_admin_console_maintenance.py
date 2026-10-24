"""Maintenance links are explicit, admin-only and offline; legacy cards stay compatible."""

import json
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from bot.app.web.admin_api_impl.auth import admin_auth_middleware
from bot.app.web.admin_api_impl.panel_links import build_panel_maintenance_url
from bot.app.web.admin_console_maintenance_routes import (
    admin_console_maintenance_route,
    setup_admin_console_maintenance_routes,
)
from bot.app.web.admin_console_maintenance_schemas import ConsoleMaintenanceOut
from bot.app.web.cache_headers import api_no_store_middleware
from bot.app.web.context import SESSION_FACTORY, SETTINGS
from bot.app.web.route_contracts import ADMIN_SECURITY, get_contracts, ok_envelope_for
from bot.app.web.webapp_auth import create_webapp_session_token
from config.settings import Settings
from db.auth_models import AccountRole
from tests.unit.test_user_services import ServiceDatabaseTestCase


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("https://panel.example.com", "https://panel.example.com"),
        (
            " https://Panel.Example.com/prefix/API/?token=secret#secret ",
            "https://panel.example.com/prefix",
        ),
        ("http://panel.example.com:3000/api", "http://panel.example.com:3000"),
        ("https://panel.example.com./console/", "https://panel.example.com/console"),
        ("https://8.8.8.8/api", "https://8.8.8.8"),
        ("https://[2606:4700:4700::1111]:8443/api", "https://[2606:4700:4700::1111]:8443"),
    ],
)
def test_explicit_public_url_uses_shared_base_policy(configured: str, expected: str) -> None:
    assert build_panel_maintenance_url(configured) == expected


@pytest.mark.parametrize(
    "configured",
    [
        None,
        "",
        "  ",
        42,
        "javascript:alert(1)",
        "//panel.example.com",
        "https:///panel.example.com",
        "https://user:secret@panel.example.com",
        "https://user@panel.example.com",
        "https://panel.example.com:invalid",
        "https://panel.example.com:65536",
        "https://panel.example.com:0",
        "https://[broken",
        "http://remnawave:3000/api",
        "http://localhost",
        "http://panel.localhost.",
        "http://panel.local",
        "http://panel.internal",
        "http://panel.lan",
        "http://panel.home.arpa",
        "http://panel.invalid",
        "http://panel.test",
        "http://127.0.0.1",
        "http://10.0.0.1",
        "http://172.16.0.1",
        "http://192.168.1.1",
        "http://169.254.169.254",
        "http://100.64.0.1",
        "http://0.0.0.0",
        "http://224.0.0.1",
        "http://192.0.2.1",
        "http://[::1]",
        "http://[fc00::1]",
        "http://[fe80::1]",
        "http://[ff02::1]",
        "http://[::ffff:127.0.0.1]",
        "http://[fe80::1%25eth0]",
        "http://127.1",
        "http://2130706433",
        "http://0177.0.0.1",
        "http://0x7f.0.0.1",
        "http://127.0.0.0x1",
        "https://%31%32%37.0.0.1",
        "https://panel..example.com",
        "https://panel.example.com\\@127.0.0.1",
        "https://panel.example.com\n.evil.com",
        "https://panel.example.com/\tpath",
        "https://panel.example.com/has space",
        "https://panel.example.com/\x00path",
        "https://panel.example.com/\x7fpath",
    ],
)
def test_missing_unsafe_and_internal_destinations_return_null(configured: object) -> None:
    assert build_panel_maintenance_url(configured) is None


@pytest.mark.filterwarnings(
    "ignore:It is recommended to use web.RequestKey: aiohttp.web_exceptions.NotAppKeyWarning"
)
class MaintenanceRouteTests(ServiceDatabaseTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.settings = Settings(
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            BOT_TOKEN="1234567890:AA_test_token_value",
            WEBAPP_SESSION_SECRET="isolated-maintenance-test-secret",
            PANEL_PUBLIC_URL="https://panel.example.com/prefix/api?token=secret#secret",
            PANEL_API_URL="http://remnawave:3000/api",
            _env_file=None,
        )
        self.app = web.Application()
        self.app[SETTINGS], self.app[SESSION_FACTORY] = self.settings, self.sessions
        setup_admin_console_maintenance_routes(self.app)

    async def read(self, user_id: int | None = 1, query: str = "") -> web.StreamResponse:
        headers = (
            {"Authorization": "Bearer " + create_webapp_session_token(self.settings, user_id)}
            if user_id is not None
            else {}
        )
        request = make_mocked_request(
            "GET", "/api/admin/console/maintenance" + query, headers=headers, app=self.app
        )

        async def authenticated(request: web.Request) -> web.StreamResponse:
            response = await admin_auth_middleware(request, admin_console_maintenance_route)
            assert isinstance(response, web.StreamResponse)
            return response

        response = await api_no_store_middleware(request, authenticated)
        assert isinstance(response, web.StreamResponse)
        return response

    async def test_admin_get_sanitizes_without_panel_access_or_configuration_changes(self) -> None:
        before = self.settings.model_dump()
        with self.assertNoLogs("bot", level="DEBUG"):
            response = await self.read()
        assert isinstance(response, web.Response) and response.status == 200
        assert response.text is not None
        assert json.loads(response.text) == {
            "ok": True,
            "destination": "https://panel.example.com/prefix",
        }
        assert response.headers["Cache-Control"] == "private, no-store"
        assert "Location" not in response.headers and not response.cookies
        assert self.settings.model_dump() == before

    async def test_absent_or_unsafe_public_url_never_uses_even_a_public_api_url(self) -> None:
        for configured in (
            None,
            "",
            "http://panel.internal",
            "https://user:secret@panel.example.com",
        ):
            self.app[SETTINGS] = self.settings.model_copy(
                update={
                    "PANEL_PUBLIC_URL": configured,
                    "PANEL_API_URL": "https://api.example.com/api",
                }
            )
            response = await self.read()
            assert isinstance(response, web.Response) and response.status == 200
            assert response.text is not None
            assert json.loads(response.text) == {"ok": True, "destination": None}
            assert response.headers["Cache-Control"] == "private, no-store"

    async def test_admin_role_can_read_without_owner_role(self) -> None:
        async with self.sessions.begin() as session:
            session.add(AccountRole(user_id=2, role="admin"))
        response = await self.read(2)
        assert isinstance(response, web.Response) and response.status == 200
        assert response.text is not None
        assert json.loads(response.text)["destination"] == "https://panel.example.com/prefix"

    async def test_anonymous_customer_banned_and_revoked_admin_cannot_discover_url(self) -> None:
        for user_id, status in ((None, 401), (2, 403), (3, 403)):
            with pytest.raises(web.HTTPException) as denied:
                await self.read(user_id)
            assert denied.value.status == status
            assert "no-store" in denied.value.headers["Cache-Control"]
            assert "destination" not in (denied.value.text or "")
        assert (await self.read()).status == 200
        async with self.sessions.begin() as session:
            role = await session.get(AccountRole, (1, "owner"))
            assert role is not None
            role.revoked_at = datetime.now(UTC)
        with (
            patch(
                "bot.app.web.admin_console_maintenance_routes.build_panel_maintenance_url"
            ) as build,
            pytest.raises(web.HTTPForbidden) as denied,
        ):
            await self.read()
        assert "no-store" in denied.value.headers["Cache-Control"]
        build.assert_not_called()

    async def test_query_cannot_override_destination_and_contract_is_admin_only(self) -> None:
        response = await self.read(query="?destination=https://evil.example.com&token=secret")
        assert isinstance(response, web.Response) and response.status == 400
        assert "secret" not in (response.text or "")
        assert response.headers["Cache-Control"] == "private, no-store"
        contract = get_contracts()["admin_console_maintenance_route"]
        assert contract.request_model is None and contract.security == ADMIN_SECURITY
        assert contract.response_schema == ok_envelope_for(ConsoleMaintenanceOut)
        assert contract.models == (ConsoleMaintenanceOut,)
        assert {route.method for route in self.app.router.routes()} == {"GET", "HEAD"}
