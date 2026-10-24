"""Exercise real auth middleware and handlers without listening on a socket."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request
from pydantic import ValidationError
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.app.web import admin_console_account_operations_routes as routes
from bot.app.web.admin_api_impl.auth import admin_auth_middleware
from bot.app.web.admin_console_account_operations_schemas import ConsoleAccountOperationsQuery
from bot.app.web.cache_headers import api_no_store_middleware
from bot.app.web.context import SESSION_FACTORY, SETTINGS
from bot.app.web.route_contracts import ADMIN_SECURITY, get_contracts
from bot.app.web.webapp_auth import create_webapp_session_token
from bot.services.account_access_sync import set_account_ban
from config.settings import Settings
from db.account_operation_models import AccountOperation
from db.auth_models import AccountRole
from db.models import User
from db.service_models import AccountAccessSync
from tests.unit.test_user_services import ServiceDatabaseTestCase

PATH = "/api/admin/console/account-operations"
pytestmark = pytest.mark.filterwarnings(
    "ignore:It is recommended to use web.RequestKey instances:"
    "aiohttp.web_exceptions.NotAppKeyWarning"
)


class AccountOperationRouteTests(ServiceDatabaseTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.settings = Settings.model_validate(
            {
                "POSTGRES_USER": "test",
                "POSTGRES_PASSWORD": "test",
                "BOT_TOKEN": "1234567890:AA_secret_bot_token_value",
            }
        )
        self.app = web.Application()
        web_sessions = sessionmaker(
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        web_sessions.configure(bind=self.engine)
        self.app[SESSION_FACTORY] = web_sessions
        self.app[SETTINGS] = self.settings
        routes.setup_admin_console_account_operations_routes(self.app)
        with patch(
            "bot.services.account_access_sync.can_ban_account", AsyncMock(return_value=True)
        ):
            async with self.sessions.begin() as session:
                await set_account_ban(session, user_id=2, actor_id=1, banned=True)
                job = await session.get(AccountAccessSync, 2)
                assert job and job.operation_id
                self.operation_id = job.operation_id

    async def request(
        self,
        query: str = "",
        *,
        operation_id: str | None = None,
        user_id: int | None = 1,
        cookie: bool = False,
    ) -> web.StreamResponse:
        headers: dict[str, str] = {}
        if user_id is not None:
            token = create_webapp_session_token(self.settings, user_id)
            headers = (
                {"Cookie": f"rw_webapp_session={token}"}
                if cookie
                else {"Authorization": f"Bearer {token}"}
            )
        request = make_mocked_request(
            "GET",
            PATH + (f"/{operation_id}" if operation_id else "") + query,
            headers=headers,
            app=self.app,
            match_info={"operation_id": operation_id} if operation_id else {},
        )
        handler = (
            routes.admin_console_account_operation_route
            if operation_id
            else routes.admin_console_account_operations_route
        )

        async def authorized(req: web.Request) -> web.StreamResponse:
            response = await admin_auth_middleware(req, handler)
            assert isinstance(response, web.StreamResponse)
            return response

        try:
            response = await api_no_store_middleware(request, authorized)
            assert isinstance(response, web.StreamResponse)
            return response
        except web.HTTPException as exc:
            return exc

    async def test_web_factory_creates_async_sessions_with_the_same_database_and_options(
        self,
    ) -> None:
        session = self.app[SESSION_FACTORY]()
        assert isinstance(session, AsyncSession)
        async with session:
            assert session.bind is self.engine
            assert not session.autoflush and not session.sync_session.expire_on_commit
            operation = await session.get(AccountOperation, self.operation_id)
            assert operation and operation.target_id == 2

    async def test_list_and_detail_return_typed_private_records_and_real_totals(self) -> None:
        response = await self.request("?needs_attention=true&page_size=1")
        assert isinstance(response, web.Response) and response.text
        assert response.status == 200 and response.headers["Cache-Control"] == "private, no-store"
        body = json.loads(response.text)
        assert body["ok"] and body["total"] == 1 and body["page"] == 0 and body["page_size"] == 1
        row = body["operations"][0]
        assert row["id"] == self.operation_id and row["needs_attention"]
        assert row["actor_id"] == 1 and row["target_id"] == row["user_id"] == 2
        assert row["before_banned"] is False and row["desired_banned"] is True
        detail = await self.request(operation_id=self.operation_id)
        assert isinstance(detail, web.Response) and detail.text
        assert json.loads(detail.text)["operation"] == row
        page = await self.request("?page=10&page_size=1")
        assert isinstance(page, web.Response) and page.text
        assert json.loads(page.text)["operations"] == [] and json.loads(page.text)["total"] == 1
        contracts = get_contracts()
        for name in (
            "admin_console_account_operations_route",
            "admin_console_account_operation_route",
        ):
            assert contracts[name].security == ADMIN_SECURITY

    async def test_roles_and_old_cookies_are_rechecked_before_any_audit_query(self) -> None:
        for cookie in (False, True):
            for user_id, expected in ((None, 401), (2, 403), (3, 403)):
                with (
                    patch.object(routes, "list_account_operations", AsyncMock()) as listing,
                    patch.object(routes, "get_account_operation", AsyncMock()) as detail,
                ):
                    for operation_id in (None, self.operation_id):
                        response = await self.request(
                            "?status=invalid",
                            operation_id=operation_id,
                            user_id=user_id,
                            cookie=cookie,
                        )
                        assert response.status == expected
                        assert "no-store" in response.headers["Cache-Control"]
                    listing.assert_not_awaited()
                    detail.assert_not_awaited()
        async with self.sessions.begin() as session:
            await session.execute(delete(AccountRole).where(AccountRole.user_id == 1))
        with patch.object(routes, "get_session_factory") as business:
            for cookie in (False, True):
                for operation_id in (None, self.operation_id):
                    assert (
                        await self.request(operation_id=operation_id, cookie=cookie)
                    ).status == 403
            business.assert_not_called()

    async def test_invalid_filters_and_ids_fail_closed(self) -> None:
        for query in (
            "?status=arbitrary",
            "?source=api",
            "?page=-1",
            "?page_size=201",
            "?page=1&page=2",
            "?user_id=1.5",
            "?actor_id=9007199254740992",
            "?needs_attention=1",
            "?extra=ignored",
            "?archived=yes",
        ):
            with patch.object(routes, "get_session_factory") as business:
                assert (await self.request(query)).status == 400
                business.assert_not_called()
        assert (await self.request(operation_id="invalid")).status == 400
        assert (await self.request(operation_id="0" * 32)).status == 404

    async def test_archived_history_is_private_sanitized_and_not_an_actionable_live_account(
        self,
    ) -> None:
        async with self.sessions.begin() as session:
            operation = await session.get(AccountOperation, self.operation_id)
            assert operation
            operation.status = "unknown"
            operation.attempted_at = datetime.now(UTC)
            operation.error_code = "SECRET https://token@private.example/subscription"
            await session.execute(delete(User).where(User.user_id == 2))
        response = await self.request("?archived=only&user_id=2")
        assert isinstance(response, web.Response) and response.text
        assert "SECRET" not in response.text and "subscription" not in response.text
        body = json.loads(response.text)
        row = body["operations"][0]
        assert body["total"] == 1 and row["archived"] and row["user_id"] is None
        assert row["target_id"] == 2 and row["actor_id"] == 1
        assert row["error_code"] == "account_sync_unconfirmed" and not row["needs_attention"]
        response = await self.request("?needs_attention=true")
        assert isinstance(response, web.Response) and response.text
        assert json.loads(response.text)["total"] == 0


@pytest.mark.parametrize("values", [{"page": True}, {"actor_id": False}, {"page_size": 1.0}])
def test_query_rejects_boolean_and_float_integer_coercion(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ConsoleAccountOperationsQuery.model_validate(values)
