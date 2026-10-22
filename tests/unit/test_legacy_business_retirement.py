"""The deployed website cannot issue old account-level subscription entitlements."""

import asyncio
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from aiogram import Dispatcher
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer, make_mocked_request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.app.web.openapi import generate_openapi
from bot.app.web.webapp.application import create_subscription_webapp_application
from bot.app.web.webapp.auth_referral import _grant_referral_welcome_bonus_if_eligible
from bot.app.web.webapp.legacy_business import (
    SINGLE_SUBSCRIPTION_RETIRED,
    legacy_business_middleware,
    retired_single_subscription_route,
)
from bot.app.web.webapp_auth import create_webapp_session_token
from config.settings import Settings
from db.models import Subscription, User
from db.service_models import UserService
from tests.unit.test_user_services import ServiceDatabaseTestCase


class LegacyBusinessRetirementTests(ServiceDatabaseTestCase):
    def application(self) -> tuple[web.Application, Settings]:
        settings = Settings(POSTGRES_USER="test", POSTGRES_PASSWORD="test", _env_file=None)
        app = create_subscription_webapp_application(
            Dispatcher(), None, settings, cast(sessionmaker, self.sessions)
        )
        # Exercise the real HTTP stack without unrelated logo/network cache warmers.
        app.on_startup.clear()
        app.on_shutdown.clear()
        assert app[SINGLE_SUBSCRIPTION_RETIRED]
        assert legacy_business_middleware in app.middlewares
        return app, settings

    @pytest.mark.filterwarnings(
        "ignore:It is recommended to use web.RequestKey: aiohttp.web_exceptions.NotAppKeyWarning"
    )
    async def test_retired_user_and_admin_requests_cannot_create_old_entitlements(self) -> None:
        app, settings = self.application()
        admin = {"Authorization": "Bearer " + create_webapp_session_token(settings, 1)}
        user = {"Authorization": "Bearer " + create_webapp_session_token(settings, 2)}
        paths = [
            ("POST", "/api/trial/activate", user),
            ("POST", "/api/promo/apply", user),
            ("POST", "/api/payments", user),
            ("POST", "/api/payments/123/qa/complete", user),
            ("POST", "/api/gifts/claim", user),
            ("POST", "/api/subscription/reissue", user),
            ("POST", "/api/subscription/auto-renew", user),
            ("POST", "/api/partner/balance/renew", user),
            ("POST", "/api/referral/welcome-bonus/claim", user),
            ("POST", "/api/extensions/orders", user),
            ("POST", "/api/extensions/checkout", user),
            ("GET", "/api/devices", user),
            ("GET", "/api/tariffs/topup-options", user),
            ("GET", "/api/subscription-guides", user),
            ("GET", "/api/subscription-guides/public/" + "a" * 32, {}),
            ("GET", "/s/" + "a" * 32 + "/clash", {}),
            ("POST", "/api/admin/users/2/extend", admin),
            ("POST", "/api/admin/users/2/tariff", admin),
            ("POST", "/api/admin/users/2/traffic-grant", admin),
            ("POST", "/api/admin/users/2/balance-adjustment", admin),
            ("PATCH", "/api/admin/users/2/squad-overrides", admin),
            ("POST", "/api/admin/gifts", admin),
            ("POST", "/api/admin/promos", admin),
            ("PUT", "/api/admin/tariffs", admin),
            ("POST", "/api/admin/payments/123/finalize", admin),
            ("POST", "/api/admin/partners", admin),
            ("POST", "/api/admin/sync", admin),
        ]
        async with TestClient(TestServer(app)) as client:
            for method, path, headers in paths:
                with self.subTest(method=method, path=path):
                    response = await client.request(method, path, headers=headers, json={})
                    assert response.status == 410, await response.text()
                    assert await response.json() == {
                        "ok": False,
                        "error": "legacy_business_retired",
                    }
            response = await client.post("/api/admin/users/2/extend", headers=user, json={})
            assert response.status == 403
            response = await client.get("/api/devices")
            assert response.status == 401
            assert (await client.get("/api/services", headers=user)).status == 200
            assert (await client.get("/api/service-catalog", headers=user)).status == 200
            assert (await client.get("/api/admin/service-plans", headers=admin)).status == 200
        async with self.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Subscription)) == 0
            assert await session.scalar(select(func.count()).select_from(UserService)) == 0

    async def test_login_bonus_cannot_bypass_retirement(self) -> None:
        app, _ = self.application()
        request = make_mocked_request("POST", "/api/auth/email/verify", app=app)
        session = AsyncMock(spec=AsyncSession)
        with patch("bot.app.web.webapp.auth_referral.user_dal.lock_user_by_id") as lock:
            assert (
                await _grant_referral_welcome_bonus_if_eligible(
                    request, session, User(user_id=2, referred_by_id=1)
                )
                is None
            )
        lock.assert_not_called()
        session.execute.assert_not_called()


def test_retirement_preserves_account_support_and_independent_service_boundaries() -> None:
    for method, path in (
        ("POST", "/api/auth/email/verify"),
        ("POST", "/api/account/merge/confirm"),
        ("DELETE", "/api/admin/users/{user_id}"),
        ("POST", "/api/admin/users/{user_id}/ban"),
        ("POST", "/api/admin/users/{user_id}/access-sync"),
        ("POST", "/api/admin/services"),
        ("POST", "/api/admin/service-plans"),
        ("POST", "/api/support/tickets/{id}/messages"),
        ("POST", "/api/admin/backups/create"),
        ("GET", "/api/admin/payments"),
        ("GET", "/api/admin/gifts/{gift_id}"),
        ("GET", "/api/subscription-notifications"),
    ):
        assert not retired_single_subscription_route(method, path), (method, path)


def test_openapi_explains_retirement_without_losing_historical_types() -> None:
    document = generate_openapi()
    retired = document["paths"]["/api/admin/users/{user_id}/extend"]["post"]
    assert retired["deprecated"] is True
    assert "410" in retired["responses"]
    assert retired["responses"]["200"]["description"] == "Historical response (not served)"
    assert "deprecated" not in document["paths"]["/api/admin/services"]["post"]


def test_payment_and_account_panel_webhooks_are_retired() -> None:
    asyncio.run(_check_retired_webhooks())


async def _check_retired_webhooks() -> None:
    from bot.app.web.web_server import _register_legacy_business_webhooks

    settings = Settings(
        POSTGRES_USER="test",
        POSTGRES_PASSWORD="test",
        WEBHOOK_BASE_URL="https://example.invalid",
        _env_file=None,
    )
    app = web.Application()
    _register_legacy_business_webhooks(app, settings)
    routes = []
    for route in app.router.routes():
        assert route.resource is not None
        routes.append((route.method, route.resource.canonical))
    assert ("POST", settings.panel_webhook_path) in routes
    assert ("GET", "/webhook/freekassa") in routes
    assert len(routes) > 3
    async with TestClient(TestServer(app)) as client:
        # No panel/provider context is supplied: even malformed or stale deliveries
        # must return before parsing, queueing, or applying entitlements.
        for method, path in routes:
            response = await client.request(method, path, data=b"not json")
            assert response.status == 410, (method, path)
            assert await response.json() == {"ok": False, "error": "legacy_business_retired"}


def test_runtime_keeps_only_account_and_operational_workers() -> None:
    import main_worker

    assert {task.name for task in main_worker._core_worker_tasks()} == {
        "AccountAccessSync",
        "ServiceProvisioning",
        "ServiceChanges",
        "ServiceUsage",
        "OutboundSettingsRefresh",
        "AdminBroadcastWorker",
        "BackupWorker",
    }


@pytest.mark.parametrize(
    "provider", ["yookassa", "panel", "panel_sync", "retired_telegram_payment"]
)
@pytest.mark.parametrize("moved", [True, False])
def test_old_queued_events_are_preserved_without_entitlements_or_ack(
    provider: str,
    moved: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asyncio.run(_check_retired_queue_event(provider, moved, monkeypatch))


async def _check_retired_queue_event(
    provider: str,
    moved: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import main_worker

    from bot.infra.webhook_queue import ClaimedWebhookEvent
    from bot.plugins import PluginContext

    settings = Settings(POSTGRES_USER="test", POSTGRES_PASSWORD="test", _env_file=None)
    ctx = PluginContext(settings=settings)
    claimed = ClaimedWebhookEvent(
        event={"provider": provider, "event_id": "old-event", "payload": {"value": 42}},
        raw='{"preserved":"original"}',
    )
    dead_letter = AsyncMock(return_value=moved)
    acknowledge = AsyncMock()
    retry = AsyncMock()
    monkeypatch.setattr(
        main_worker, "pop_webhook_event", AsyncMock(side_effect=[claimed, asyncio.CancelledError()])
    )
    monkeypatch.setattr(main_worker, "dead_letter_webhook_event", dead_letter)
    monkeypatch.setattr(main_worker, "acknowledge_webhook_event", acknowledge)
    monkeypatch.setattr(main_worker, "retry_webhook_event", retry)
    monkeypatch.setattr(main_worker, "webhook_queue_depth", AsyncMock(return_value=0))
    with pytest.raises(asyncio.CancelledError):
        await main_worker._webhook_consumer(ctx, main_worker._core_queue_handlers())
    dead_letter.assert_awaited_once()
    call = dead_letter.await_args
    assert call is not None
    assert call.args == (settings, claimed)
    assert call.kwargs["delivery_attempts"] == 1
    assert isinstance(call.kwargs["error"], main_worker.RetiredBusinessEventError)
    acknowledge.assert_not_awaited()
    retry.assert_not_awaited()
