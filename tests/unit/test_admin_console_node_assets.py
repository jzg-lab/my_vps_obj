"""Exercise real handlers/admin/CSRF logic with mocked persistence, entirely offline."""

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import cast
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.app.web import admin_console_node_assets_routes as routes
from bot.app.web.admin_api_impl.auth import admin_auth_middleware
from bot.app.web.cache_headers import api_no_store_middleware
from bot.app.web.context import SESSION_FACTORY, SETTINGS
from bot.app.web.route_contracts import ADMIN_SECURITY, get_contracts
from bot.app.web.webapp.assets import _csrf_protection_middleware
from bot.app.web.webapp_auth import create_webapp_session_token
from config.settings import Settings
from db.models import User
from db.node_asset_models import NodeAsset

ASSET_ID = "a" * 32
BASE = "/api/admin/console/node-assets"
BODY: dict[str, object] = {"name": " Node ", "address": " 192.0.2.1 ", "notes": " note "}
HANDLERS = (
    ("GET", BASE, routes.admin_console_node_assets_route),
    ("GET", BASE + "/" + ASSET_ID, routes.admin_console_node_asset_route),
    ("POST", BASE, routes.admin_console_node_asset_create_route),
    ("PUT", BASE + "/" + ASSET_ID, routes.admin_console_node_asset_update_route),
    ("DELETE", BASE + "/" + ASSET_ID, routes.admin_console_node_asset_delete_route),
)


def asset() -> NodeAsset:
    now = datetime.now(UTC)
    return NodeAsset(
        id=ASSET_ID, name="Node", address="192.0.2.1", notes="note", created_at=now, updated_at=now
    )


@pytest.mark.filterwarnings(
    "ignore:It is recommended to use web.RequestKey: aiohttp.web_exceptions.NotAppKeyWarning"
)
class NodeAssetRouteTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.settings = Settings(
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            BOT_TOKEN="1234567890:AA_test_token_value",
            WEBAPP_SESSION_SECRET="offline-node-asset-tests",
            _env_file=None,
        )
        self.session = MagicMock(spec=AsyncSession)
        self.session.__aenter__.return_value = self.session
        self.factory = MagicMock(return_value=self.session)
        self.app = web.Application()
        self.app[SETTINGS] = self.settings
        self.app[SESSION_FACTORY] = cast(sessionmaker, self.factory)
        routes.setup_admin_console_node_assets_routes(self.app)
        self.user = User(user_id=1, telegram_id=None, is_banned=False)

    async def invoke(
        self,
        method: str,
        path: str,
        handler: Callable[[web.Request], Awaitable[web.Response]],
        *,
        authenticated: bool = True,
        admin: bool = True,
        body: object = BODY,
        csrf: str | None = "token",
        origin: str | None = None,
    ) -> web.Response:
        headers = {}
        if authenticated:
            token = create_webapp_session_token(self.settings, 1)
            headers["Cookie"] = f"rw_webapp_session={token}; rw_webapp_csrf=token"
        if csrf is not None:
            headers["X-CSRF-Token"] = csrf
        if origin is not None:
            headers["Origin"] = origin
        request = make_mocked_request(method, path, app=self.app, headers=headers)
        request.match_info.update(await self.app.router.resolve(request))

        async def authorize(req: web.Request) -> web.StreamResponse:
            response = await admin_auth_middleware(req, handler)
            assert isinstance(response, web.StreamResponse)
            return response

        async def csrf_checked(req: web.Request) -> web.StreamResponse:
            response = await _csrf_protection_middleware(req, authorize)
            assert isinstance(response, web.StreamResponse)
            return response

        with (
            patch(
                "bot.app.web.admin_api_impl.auth.user_dal.get_user_by_id",
                AsyncMock(return_value=self.user),
            ),
            patch("bot.app.web.admin_api_impl.auth.is_admin", AsyncMock(return_value=admin)),
            patch.object(web.Request, "json", AsyncMock(return_value=body)),
        ):
            try:
                result = await api_no_store_middleware(request, csrf_checked)
            except web.HTTPException as exc:
                result = exc
        assert isinstance(result, web.Response)
        assert "no-store" in result.headers["Cache-Control"]
        return result

    async def test_all_routes_deny_anonymous_and_non_admin_before_asset_access(self) -> None:
        with patch.object(routes, "node_assets_dal") as dal:
            for method, path, handler in HANDLERS:
                anonymous = await self.invoke(method, path, handler, authenticated=False)
                forbidden = await self.invoke(method, path, handler, admin=False)
                assert anonymous.status == 401 and forbidden.status == 403
            assert not dal.mock_calls

    async def test_banned_account_denied_before_asset_access(self) -> None:
        self.user.is_banned = True
        with patch.object(routes, "node_assets_dal") as dal:
            for method, path, handler in HANDLERS:
                assert (await self.invoke(method, path, handler)).status == 403
            assert not dal.mock_calls

    async def test_all_cookie_writes_require_csrf_and_reject_cross_origin(self) -> None:
        with patch.object(routes, "node_assets_dal") as dal:
            for method, path, handler in HANDLERS[2:]:
                for csrf in (None, "wrong"):
                    result = await self.invoke(method, path, handler, csrf=csrf)
                    assert result.status == 403
                    assert json.loads(result.text or "{}")["error"] == "csrf_failed"
                assert (
                    await self.invoke(method, path, handler, origin="https://evil.example")
                ).status == 403
            assert not dal.mock_calls

    async def test_list_and_detail_return_only_local_inventory_with_real_total(self) -> None:
        with patch.object(
            routes.node_assets_dal, "list_assets", AsyncMock(return_value=([asset()], 42))
        ) as read:
            result = await self.invoke("GET", BASE + "?page=2&page_size=5", HANDLERS[0][2])
            assert result.status == 200
            data = json.loads(result.text or "{}")
            assert data["total"] == 42 and len(data["items"]) == 1
            assert data["items"][0]["management_state"] == "unmanaged"
            read.assert_awaited_once_with(self.session, page=2, page_size=5)
        with patch.object(routes.node_assets_dal, "get_asset", AsyncMock(return_value=asset())):
            detail = await self.invoke(*HANDLERS[1])
            assert json.loads(detail.text or "{}")["id"] == ASSET_ID
        self.session.commit.assert_not_awaited()

    async def test_create_update_and_delete_commit_only_local_records(self) -> None:
        for handler_index, function in ((2, "create_asset"), (3, "update_asset")):
            with patch.object(
                routes.node_assets_dal, function, AsyncMock(return_value=asset())
            ) as write:
                result = await self.invoke(*HANDLERS[handler_index])
                assert result.status == 200 and json.loads(result.text or "{}")["ok"] is True
                assert write.call_args.kwargs == {
                    "name": "Node",
                    "address": "192.0.2.1",
                    "notes": "note",
                }
                if handler_index == 3:
                    assert write.call_args.args == (self.session, ASSET_ID)
        with patch.object(
            routes.node_assets_dal, "delete_asset", AsyncMock(return_value=True)
        ) as delete:
            result = await self.invoke(*HANDLERS[4])
            assert json.loads(result.text or "{}") == {"ok": True, "id": ASSET_ID, "deleted": True}
            delete.assert_awaited_once_with(self.session, ASSET_ID)
        assert self.session.commit.await_count == 3

    async def test_missing_record_never_creates_or_commits(self) -> None:
        for handler_index, function in ((1, "get_asset"), (3, "update_asset"), (4, "delete_asset")):
            with patch.object(routes.node_assets_dal, function, AsyncMock(return_value=None)):
                result = await self.invoke(*HANDLERS[handler_index])
                assert result.status == 404
                assert json.loads(result.text or "{}")["error"] == "node_asset_not_found"
        self.session.commit.assert_not_awaited()

    async def test_validation_rejects_invalid_id_query_and_body_before_dal(self) -> None:
        with patch.object(routes, "node_assets_dal") as dal:
            for query in ("?page=-1", "?page_size=101", "?page=1&page=2", "?q=x"):
                assert (await self.invoke("GET", BASE + query, HANDLERS[0][2])).status == 400
            for method, path, handler in HANDLERS[1:]:
                if method != "POST":
                    assert (
                        await self.invoke(method, path.replace(ASSET_ID, "invalid"), handler)
                    ).status == 400
                assert (await self.invoke(method, path + "?ignored=1", handler)).status == 400
            invalid_bodies: tuple[object, ...] = (
                {},
                {**BODY, "address": "https://example.com"},
                {**BODY, "node_id": "remote"},
                [],
            )
            for entry in HANDLERS[2:4]:
                for body in invalid_bodies:
                    assert (await self.invoke(*entry, body=body)).status == 400
            assert not dal.mock_calls
        self.session.commit.assert_not_awaited()

    async def test_storage_failure_is_not_success_or_empty_inventory(self) -> None:
        with patch.object(
            routes.node_assets_dal,
            "list_assets",
            AsyncMock(side_effect=SQLAlchemyError("private-db-url")),
        ):
            result = await self.invoke(*HANDLERS[0])
            assert result.status == 503 and "private-db-url" not in (result.text or "")
            assert "items" not in json.loads(result.text or "{}")
        self.session.commit.side_effect = SQLAlchemyError("private-db-url")
        with patch.object(routes.node_assets_dal, "create_asset", AsyncMock(return_value=asset())):
            result = await self.invoke(*HANDLERS[2])
            assert result.status == 503 and json.loads(result.text or "{}")["ok"] is False

    async def test_registered_routes_have_admin_contracts_and_typed_writes(self) -> None:
        contracts = get_contracts()
        for method, path, handler in HANDLERS:
            request = make_mocked_request(method, path)
            resolved = await self.app.router.resolve(request)
            assert resolved.handler is handler
            contract = contracts[handler.__name__]
            assert contract.security == ADMIN_SECURITY
            assert (contract.request_model is not None) == (method in {"POST", "PUT"})
