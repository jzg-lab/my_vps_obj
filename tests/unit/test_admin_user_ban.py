"""Ban intent survives outages; unban does not restore ineligible independent services."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.app.web.account_access_routes import setup_account_access_routes
from bot.app.web.admin_api_impl import users_ban
from bot.app.web.admin_api_impl.auth import admin_auth_middleware
from bot.app.web.admin_api_impl.schemas import AdminUserBanBody
from bot.app.web.context import SESSION_FACTORY, SETTINGS
from bot.app.web.webapp_auth import create_webapp_session_token
from bot.services.account_access_sync import AccountAccessWorker, set_account_ban
from config.service_periods import as_utc
from config.settings import Settings
from db.dal.account_access_dal import enqueue_access_sync
from db.dal.user_merge_dal import merge_users
from db.models import Subscription, User
from db.service_models import AccountAccessSync, ServiceConnection, UserService
from tests.unit.test_user_services import ServiceDatabaseTestCase, sample_terms


class AccessPanel:
    def __init__(self) -> None:
        self.states: dict[str, str] = {}
        self.users: dict[str, dict[str, Any]] = {}
        self.failed: set[str] = set()
        self.updates: list[tuple[str, bool]] = []
        self.lookup_failed = False

    async def update_user_status_on_panel(
        self, user_uuid: str, enable: bool, log_response: bool = False
    ) -> bool:
        self.updates.append((user_uuid, enable))
        if user_uuid not in self.failed and user_uuid in self.states:
            self.states[user_uuid] = "ACTIVE" if enable else "DISABLED"
        return True

    async def get_user_by_uuid_lookup(
        self, user_uuid: str, log_response: bool = False
    ) -> dict[str, Any]:
        if self.lookup_failed:
            return {"ok": False, "not_found": False}
        if user_uuid not in self.states:
            return {"ok": False, "not_found": True}
        return {
            "ok": True,
            "user": {**self.users.get(user_uuid, {}), "status": self.states[user_uuid]},
        }

    def bind(self, service: UserService, reference: str) -> None:
        self.users[reference] = {
            "uuid": reference,
            "username": f"svc_{service.id}",
            "description": f"my_vps_obj:service:{service.id}",
            "trafficLimitStrategy": "NO_RESET",
            "trafficLimitBytes": service.quota_bytes,
            "expireAt": as_utc(service.expires_at).isoformat(),
            "activeInternalSquads": service.terms["squad_uuids"],
            "userTraffic": {
                "usedTrafficBytes": service.used_bytes,
                "lifetimeUsedTrafficBytes": service.used_bytes,
            },
        }

    async def update_user_details_on_panel(
        self, user_uuid: str, update_payload: dict[str, Any], log_response: bool = False
    ) -> dict[str, Any] | None:
        if user_uuid not in self.failed and user_uuid in self.users:
            self.users[user_uuid].update(update_payload)
        return self.users.get(user_uuid)


class AdminUserBanTests(ServiceDatabaseTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.panel = AccessPanel()
        policy = patch(
            "bot.services.account_access_sync.can_ban_account", AsyncMock(return_value=True)
        )
        self.policy = policy.start()
        self.addCleanup(policy.stop)

    async def connect(self, key: str = "connected", reference: str = "11") -> UserService:
        service, _, _ = await self.activate(key=key, user_id=2)
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection
            connection.state = "ready"
            connection.panel_user_uuid = reference
        self.panel.states[reference] = "ACTIVE"
        self.panel.bind(service, reference)
        return service

    async def ban(self, banned: bool, *, unavailable: bool = False, user_id: int = 2):
        request = SimpleNamespace(
            app={
                "settings": SimpleNamespace(),
                "async_session_factory": self.sessions,
                "panel_service": None if unavailable else self.panel,
            },
            match_info={"user_id": str(user_id)},
        )
        with (
            patch.object(users_ban, "_require_admin_user_id", return_value=1),
            patch.object(
                users_ban,
                "parse_body_or_400",
                AsyncMock(return_value=AdminUserBanBody(banned=banned)),
            ),
            patch.object(users_ban, "_invalidate_after_admin_user_mutation", AsyncMock()),
        ):
            response = await users_ban.admin_user_ban_route(request)
        return response.status, json.loads(response.text)

    async def test_outage_keeps_ban_and_worker_recovers_all_identities_after_restart(self) -> None:
        await self.connect()
        await self.connect("second", "12")
        status, result = await self.ban(True, unavailable=True)
        assert status == 200 and result["user"]["is_banned"] is True
        assert result["access_sync"]["pending"] is True
        async with self.sessions() as session:
            user = await session.get(User, 2)
            assert user and user.is_banned
            job = await session.get(AccountAccessSync, 2)
            assert job and job.pending and job.last_error == "panel_service_unavailable"
        self.panel.failed.add("11")
        await AccountAccessWorker(self.sessions, self.panel).tick()
        assert self.panel.states == {"11": "ACTIVE", "12": "DISABLED"}
        async with self.sessions() as session:
            job = await session.get(AccountAccessSync, 2)
            assert job and job.pending
        self.panel.failed.clear()
        await AccountAccessWorker(self.sessions, self.panel).tick()
        async with self.sessions() as session:
            job = await session.get(AccountAccessSync, 2)
            assert job and not job.pending and job.last_error is None
        assert set(self.panel.states.values()) == {"DISABLED"}

    async def test_unban_only_enables_eligible_services_and_never_resets_usage(self) -> None:
        good = await self.connect()
        for index, state in enumerate(
            ["paused", "cancelled", "expired", "exhausted", "revoked", "error", "unverified"], 12
        ):
            service = await self.connect(state, str(index))
            async with self.sessions.begin() as session:
                saved = await session.get(UserService, service.id)
                connection = await session.get(ServiceConnection, service.id)
                assert saved and connection
                if state in {"paused", "cancelled"}:
                    saved.desired_status = state
                elif state == "expired":
                    saved.starts_at = datetime.now(UTC) - timedelta(days=2)
                    saved.expires_at = datetime.now(UTC) - timedelta(days=1)
                elif state == "exhausted":
                    saved.used_bytes = saved.quota_bytes + 10
                    self.panel.users[str(index)]["userTraffic"] = {
                        "usedTrafficBytes": saved.used_bytes,
                        "lifetimeUsedTrafficBytes": saved.used_bytes,
                    }
                elif state in {"revoked", "error"}:
                    connection.state = state
                else:
                    saved.terms = sample_terms(
                        resource_type="dedicated", squad_uuids=[], resource_pool="test"
                    ).model_dump(mode="json")
        await self.ban(True)
        self.panel.updates.clear()
        status, result = await self.ban(False)
        assert status == 200 and result["access_sync"]["pending"] is False
        assert [reference for reference, enable in self.panel.updates if enable] == ["11"]
        assert self.panel.states["11"] == "ACTIVE"
        async with self.sessions() as session:
            service = await session.get(UserService, good.id)
            assert service and service.quota_bytes == good.quota_bytes and service.used_bytes == 0

    async def test_acknowledged_write_and_unknown_lookup_are_not_confirmation(self) -> None:
        await self.connect()
        self.panel.lookup_failed = True
        _, result = await self.ban(True)
        assert result["access_sync"]["pending"] is True
        self.panel.lookup_failed = False
        _, result = await self.ban(True)
        assert result["access_sync"]["pending"] is False

    async def test_latest_unban_replaces_failed_ban_intent(self) -> None:
        await self.connect()
        await self.ban(True, unavailable=True)
        await self.ban(False, unavailable=True)
        await AccountAccessWorker(self.sessions, self.panel).tick()
        assert self.panel.states["11"] == "ACTIVE"
        async with self.sessions() as session:
            user = await session.get(User, 2)
            assert user and not user.is_banned

    async def test_pending_provisioning_is_not_created_but_unknown_result_needs_retry(self) -> None:
        service, _, _ = await self.activate(user_id=2)
        _, result = await self.ban(True)
        assert not result["access_sync"]["pending"] and self.panel.updates == []
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection
            connection.state = "error"
        _, result = await self.ban(True)
        assert result["access_sync"]["pending"] and self.panel.updates == []

    async def test_missing_and_protected_users_do_not_queue_or_change_access(self) -> None:
        assert (await self.ban(True, user_id=99))[0] == 404
        self.policy.return_value = False
        assert (await self.ban(True))[0] == 403
        async with self.sessions() as session:
            user = await session.get(User, 2)
            assert user and not user.is_banned
            assert await session.get(AccountAccessSync, 2) is None
        assert self.panel.updates == []

    async def test_merge_preserves_a_pending_unban_for_moved_services(self) -> None:
        await self.connect()
        async with self.sessions.begin() as session:
            await enqueue_access_sync(session, 2)
            await merge_users(session, source_user_id=2, target_user_id=1)
        await AccountAccessWorker(self.sessions, self.panel).tick()
        assert self.panel.states["11"] == "ACTIVE"
        async with self.sessions() as session:
            assert await session.get(AccountAccessSync, 2) is None
            job = await session.get(AccountAccessSync, 1)
            assert job and not job.pending

    async def test_set_ban_is_transactional_and_does_not_call_remote(self) -> None:
        async with self.sessions() as session:
            await set_account_ban(session, user_id=2, actor_id=1, banned=True)
            await session.rollback()
        async with self.sessions() as session:
            assert await session.get(AccountAccessSync, 2) is None
            user = await session.get(User, 2)
            assert user and not user.is_banned
        assert self.panel.updates == []

    async def test_legacy_unban_requires_an_active_unexpired_entitlement(self) -> None:
        async with self.sessions.begin() as session:
            user = await session.get(User, 2)
            assert user
            user.panel_user_uuid = "90"
            session.add_all(
                [
                    Subscription(
                        user_id=2,
                        panel_user_uuid=" 0091 ",
                        is_active=True,
                        end_date=datetime.now(UTC) + timedelta(days=1),
                    ),
                    Subscription(
                        user_id=2,
                        panel_user_uuid="92",
                        is_active=True,
                        end_date=datetime.now(UTC) - timedelta(days=1),
                    ),
                ]
            )
        self.panel.states.update({"90": "DISABLED", "91": "DISABLED", "92": "DISABLED"})
        await self.ban(False)
        assert self.panel.states == {"90": "DISABLED", "91": "ACTIVE", "92": "DISABLED"}

    @pytest.mark.filterwarnings(
        "ignore:It is recommended to use web.*Key: aiohttp.web_exceptions.NotAppKeyWarning"
    )
    async def test_http_retry_is_admin_only_and_does_not_change_ban_intent(self) -> None:
        await self.connect()
        settings = Settings(POSTGRES_USER="test", POSTGRES_PASSWORD="test", _env_file=None)
        app = web.Application(middlewares=[admin_auth_middleware])
        app[SETTINGS] = settings
        app[SESSION_FACTORY] = self.sessions
        app["panel_service"] = self.panel
        setup_account_access_routes(app)
        admin_headers = {"Authorization": "Bearer " + create_webapp_session_token(settings, 1)}
        user_headers = {"Authorization": "Bearer " + create_webapp_session_token(settings, 2)}
        path = "/api/admin/users/2/access-sync"
        async with TestClient(TestServer(app)) as client:
            for method in (client.get, client.post):
                assert (await method(path)).status == 401
                assert (await method(path, headers=user_headers)).status == 403
            assert (
                await client.get("/api/admin/users/99/access-sync", headers=admin_headers)
            ).status == 404
            response = await client.post(path, headers=admin_headers)
            assert response.status == 200
            assert (await response.json())["access_sync"]["attempted_at"] is None
            assert self.panel.updates == []
            await self.ban(True, unavailable=True)
            response = await client.get(path, headers=admin_headers)
            assert (await response.json())["access_sync"]["pending"] is True
            self.panel.failed.add("11")
            response = await client.post(path, headers=admin_headers)
            assert (await response.json())["access_sync"]["pending"] is True
            self.panel.failed.clear()
            response = await client.post(path, headers=admin_headers)
            assert (await response.json())["access_sync"]["pending"] is False
        async with self.sessions() as session:
            user = await session.get(User, 2)
            assert user and user.is_banned
