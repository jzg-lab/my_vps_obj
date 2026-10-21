"""Account deletion/merge retain independent entitlements without granting new access."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import select

from bot.app.web.admin_api_impl import users_actions
from bot.app.web.admin_api_impl.auth import admin_auth_middleware
from bot.app.web.context import SESSION_FACTORY, SETTINGS
from bot.app.web.service_routes import setup_service_admin_routes, setup_service_user_routes
from bot.app.web.webapp_auth import create_webapp_session_token
from config.settings import Settings
from db.dal.service_accounts_dal import deletion_connections
from db.dal.user_delete_dal import delete_user_and_relations
from db.dal.user_merge_dal import merge_users
from db.dal.user_services_dal import ServiceConflict, create_exit, get_service, list_orders
from db.models import User
from db.service_models import ServiceConnection, ServiceOrder, UserService
from tests.unit.test_user_services import ServiceDatabaseTestCase


class ServiceAccountTests(ServiceDatabaseTestCase):
    async def delete_account(self, panel: object | None = None) -> web.Response:
        request = SimpleNamespace(
            app={
                "settings": SimpleNamespace(),
                "async_session_factory": self.sessions,
                "panel_service": panel,
            },
            match_info={"user_id": "2"},
        )
        with (
            patch.object(users_actions, "_require_admin_user_id", return_value=1),
            patch.object(users_actions, "_invalidate_after_admin_user_mutation", AsyncMock()),
        ):
            response = await users_actions.admin_user_delete_route(request)
            assert isinstance(response, web.Response)
            return response

    async def test_delete_retains_snapshots_usage_and_revoked_identity(self) -> None:
        service, order, _ = await self.activate(user_id=2)
        async with self.sessions.begin() as session:
            saved = await session.get(UserService, service.id)
            connection = await session.get(ServiceConnection, service.id)
            assert saved and connection
            saved.used_bytes = 456
            connection.state = "ready"
            connection.panel_user_uuid = str(UUID(int=12))
        panel = SimpleNamespace(
            delete_user_from_panel=AsyncMock(return_value=True),
            get_user_by_uuid_lookup=AsyncMock(return_value={"not_found": True}),
        )
        response = await self.delete_account(panel)
        assert response.status == 200
        panel.delete_user_from_panel.assert_awaited_once_with(str(UUID(int=12)), log_response=False)
        async with self.sessions() as session:
            assert await session.get(User, 2) is None
            saved = await session.get(UserService, service.id)
            saved_order = await session.get(ServiceOrder, order.id)
            connection = await session.get(ServiceConnection, service.id)
            assert saved and saved_order and connection
            assert saved.user_id is None and saved.desired_status == "cancelled"
            assert saved.used_bytes == 456 and saved.quota_bytes == service.quota_bytes
            assert saved.terms == service.terms and saved.expires_at == service.expires_at.replace(
                tzinfo=None
            )
            assert saved_order.user_id is None and saved_order.request_owner_id == 2
            assert saved_order.snapshot == order.snapshot and saved_order.request == order.request
            assert connection.state == "revoked" and connection.panel_user_uuid == str(UUID(int=12))
            assert await get_service(session, service.id, user_id=1) is None
            assert await get_service(session, service.id, user_id=2) is None
            history, count = await list_orders(session, user_id=None, limit=10, offset=0)
            assert count == 1 and history[0].id == order.id

    async def test_never_provisioned_service_can_be_cancelled_without_panel(self) -> None:
        service, _, _ = await self.activate(user_id=2)
        assert (await self.delete_account()).status == 200
        async with self.sessions() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection and connection.state == "revoked"

    async def test_failed_remote_delete_keeps_account_history_and_binding(self) -> None:
        service, _, _ = await self.activate(user_id=2)
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection
            connection.state = "ready"
            connection.panel_user_uuid = str(UUID(int=12))
        panel = SimpleNamespace(
            delete_user_from_panel=AsyncMock(return_value=False),
            get_user_by_uuid_lookup=AsyncMock(return_value={"not_found": False}),
        )
        assert (await self.delete_account(panel)).status == 502
        async with self.sessions() as session:
            assert await session.get(User, 2) is not None
            connection = await session.get(ServiceConnection, service.id)
            assert connection and connection.state == "ready"
        # Acknowledgement alone (including dry-run writes) is not proof of revocation.
        panel.delete_user_from_panel.return_value = True
        assert (await self.delete_account(panel)).status == 502
        panel.get_user_by_uuid_lookup.return_value = {"not_found": True}
        assert (await self.delete_account(panel)).status == 200

    async def test_bound_exit_blocks_deletion_before_remote_calls(self) -> None:
        service, _, _ = await self.activate(user_id=2)
        async with self.sessions.begin() as session:
            resource = await create_exit(
                session,
                label="Reserved",
                ip_address="192.0.2.3",
                resource_pool="test",
                squad_uuid=str(UUID(int=3)),
            )
            resource.service_id = service.id
        panel = SimpleNamespace(
            delete_user_from_panel=AsyncMock(return_value=True),
            get_user_by_uuid_lookup=AsyncMock(return_value={"not_found": True}),
        )
        response = await self.delete_account(panel)
        assert response.status == 409
        assert json.loads(response.text or "{}")["error"] == "dedicated_exit_reclaim_required"
        panel.delete_user_from_panel.assert_not_awaited()
        async with self.sessions.begin() as session:
            with pytest.raises(ServiceConflict, match="dedicated_exit_reclaim_required"):
                await delete_user_and_relations(session, 2)

    async def test_direct_dal_delete_requires_revocation_and_unknown_result_blocks(self) -> None:
        service, _, _ = await self.activate(user_id=2)
        async with self.sessions.begin() as session:
            with pytest.raises(ServiceConflict, match="service_connection_revoke_required"):
                await delete_user_and_relations(session, 2)
            connection = await session.get(ServiceConnection, service.id)
            assert connection
            connection.state = "error"
            await session.flush()
            with pytest.raises(ServiceConflict, match="service_connection_unconfirmed"):
                await deletion_connections(session, 2)
        assert (await self.delete_account()).status == 409

    async def test_merge_preserves_colliding_keys_and_independent_identities(self) -> None:
        source, source_order, _ = await self.activate(user_id=2)
        target, target_order, _ = await self.activate(user_id=1)
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, source.id)
            saved = await session.get(UserService, source.id)
            assert connection and saved
            connection.panel_user_uuid = str(UUID(int=14))
            connection.state = "ready"
            saved.used_bytes = 123
            resource = await create_exit(
                session,
                label="Reserved",
                ip_address="192.0.2.3",
                resource_pool="test",
                squad_uuid=str(UUID(int=3)),
            )
            resource.service_id = source.id
            await session.flush()
            await merge_users(session, source_user_id=2, target_user_id=1)
        async with self.sessions() as session:
            assert await session.get(User, 2) is None
            services = list(await session.scalars(select(UserService)))
            assert len(services) == 2 and {s.user_id for s in services} == {1}
            moved = await session.get(UserService, source.id)
            order = await session.get(ServiceOrder, source_order.id)
            connection = await session.get(ServiceConnection, source.id)
            assert moved and order and connection
            assert moved.used_bytes == 123 and moved.quota_bytes == source.quota_bytes
            assert order.request_owner_id == 2 and order.idempotency_key == "open"
            assert order.snapshot == source_order.snapshot
            assert connection.username == f"svc_{source.id}"
            assert connection.panel_user_uuid == str(UUID(int=14))
        replay, order, duplicate = await self.activate(user_id=1)
        assert duplicate and replay.id == target.id and order.id == target_order.id
        with pytest.raises(ServiceConflict, match="user_not_found"):
            await self.activate(user_id=2)

    async def test_recreated_account_cannot_replay_retained_order(self) -> None:
        await self.activate(user_id=2)
        assert (await self.delete_account()).status == 200
        async with self.sessions.begin() as session:
            session.add(User(user_id=2))
        with pytest.raises(ServiceConflict, match="idempotency_owner_changed"):
            await self.activate(user_id=2)
        service, _, replay = await self.activate(key="fresh", user_id=2)
        assert service.user_id == 2 and not replay

    @pytest.mark.filterwarnings(
        "ignore:It is recommended to use web.RequestKey: aiohttp.web_exceptions.NotAppKeyWarning"
    )
    async def test_archived_history_is_admin_only_and_cannot_mix_owner_filters(self) -> None:
        service, order, _ = await self.activate(user_id=2)
        assert (await self.delete_account()).status == 200
        settings = Settings(
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            BOT_TOKEN="1234567890:AA_secret_bot_token_value",
            _env_file=None,
        )
        app = web.Application(middlewares=[admin_auth_middleware])
        app[SESSION_FACTORY] = self.sessions
        app[SETTINGS] = settings
        headers = {"Authorization": "Bearer " + create_webapp_session_token(settings, 1)}
        setup_service_admin_routes(app)
        setup_service_user_routes(app)
        async with TestClient(TestServer(app)) as client:
            assert (await client.get("/api/admin/services?deleted=true")).status == 401
            for endpoint, key, row_id in (
                ("services", "services", service.id),
                ("service-orders", "orders", order.id),
            ):
                response = await client.get(f"/api/admin/{endpoint}?deleted=true", headers=headers)
                body = await response.json()
                assert response.status == 200 and body["total"] == 1
                assert body[key][0]["id"] == row_id and body[key][0]["user_id"] is None
                assert (
                    await client.get(
                        f"/api/admin/{endpoint}?deleted=true&user_id=1", headers=headers
                    )
                ).status == 400
                response = await client.get(
                    f"/api/admin/{endpoint}?deleted=true&offset=1", headers=headers
                )
                assert (await response.json())[key] == []
            assert (await client.get("/api/services?deleted=true")).status == 401
