"""Subscription credentials and exit release are service-scoped and fail closed."""

from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from bot.app.web.admin_api_impl.auth import admin_auth_middleware
from bot.app.web.context import PANEL_SERVICE, SESSION_FACTORY, SETTINGS
from bot.app.web.service_delivery_schemas import ExitReclaimBody, ExitVerifyBody
from bot.app.web.service_routes import setup_service_admin_routes, setup_service_user_routes
from bot.app.web.webapp_auth import create_webapp_session_token
from bot.services.service_change_sync import synchronize_service_change
from bot.services.service_delivery import service_subscription
from bot.services.service_provisioning import provision_service_identity
from bot.services.service_revocation import revoke_service_identity
from bot.services.service_usage_sync import synchronize_service_usage
from config.settings import Settings
from db.dal.service_delivery_dal import record_exit_evidence, request_service_revocation
from db.dal.user_services_dal import ServiceConflict, activate_service, create_exit, save_plan
from db.service_models import DedicatedExit, DedicatedExitAudit, ServiceConnection, UserService
from tests.unit.test_service_provisioning import panel_fixture
from tests.unit.test_user_services import ServiceDatabaseTestCase, sample_terms


class ServiceDeliveryTests(ServiceDatabaseTestCase):
    async def test_other_workers_invalidate_stale_deletion_evidence(self) -> None:
        for worker in (synchronize_service_usage, synchronize_service_change):
            with self.subTest(worker=worker.__name__):
                service, _, _ = await self.activate(worker.__name__)
                panel, remote = await self.ready(service.id)
                async with self.sessions.begin() as session:
                    await request_service_revocation(
                        session,
                        service_id=service.id,
                        user_id=1,
                        actor_id=1,
                        expected_revision=1,
                        idempotency_key=f"stale:{worker.__name__}",
                        reason="A previous deletion did not finish",
                    )
                    saved = await session.get(UserService, service.id)
                    connection = await session.get(ServiceConnection, service.id)
                    assert saved and connection
                    saved.used_bytes = 500
                    connection.usage_total_bytes = connection.usage_raw_bytes = 500
                    connection.revoke_delete_requested_at = datetime.now(UTC)
                remote["status"] = "DISABLED"
                remote["userTraffic"] = {}
                await worker(cast(sessionmaker, self.sessions), service.id, panel)
                panel.get_user_by_uuid_lookup.side_effect = None
                panel.get_user_by_uuid_lookup.return_value = {"ok": False, "not_found": True}
                # A later failed sample must not turn the stale marker into deletion proof.
                await synchronize_service_usage(
                    cast(sessionmaker, self.sessions), service.id, panel
                )
                await revoke_service_identity(cast(sessionmaker, self.sessions), service.id, panel)
                async with self.sessions() as session:
                    connection = await session.get(ServiceConnection, service.id)
                    saved = await session.get(UserService, service.id)
                    assert saved and saved.used_bytes == 500
                    assert connection and connection.state != "revoked"
                    assert connection.revoke_delete_requested_at is None
                    assert connection.sync_error == "service_revoke_usage_unconfirmed"
                panel.delete_user_from_panel.assert_not_awaited()

    async def test_unknown_identity_disappearance_preserves_unsettled_usage(self) -> None:
        for error in (
            None,
            "panel_identity_missing",
            "panel_usage_invalid",
            "panel_usage_unavailable",
        ):
            with self.subTest(error=error):
                service, _, _ = await self.activate(str(error))
                panel, _ = await self.ready(service.id)
                async with self.sessions.begin() as session:
                    saved = await session.get(UserService, service.id)
                    connection = await session.get(ServiceConnection, service.id)
                    assert saved and connection
                    saved.used_bytes = 500
                    connection.usage_total_bytes = 500
                    connection.usage_raw_bytes = 500
                    connection.usage_error = error
                    await session.flush()
                    await request_service_revocation(
                        session,
                        service_id=service.id,
                        user_id=1,
                        actor_id=1,
                        expected_revision=1,
                        idempotency_key=f"missing:{error}",
                        reason="Cancel without hiding the missing identity incident",
                    )
                panel.get_user_by_uuid_lookup.side_effect = None
                panel.get_user_by_uuid_lookup.return_value = {"ok": False, "not_found": True}
                for _ in range(2):
                    await revoke_service_identity(
                        cast(sessionmaker, self.sessions), service.id, panel
                    )
                async with self.sessions() as session:
                    saved = await session.get(UserService, service.id)
                    connection = await session.get(ServiceConnection, service.id)
                    assert saved and saved.used_bytes == 500
                    assert connection and connection.state != "revoked"
                    assert connection.sync_pending and connection.revoked_at is None
                    assert connection.sync_error == "service_revoke_usage_unconfirmed"
                    assert connection.usage_total_bytes == connection.usage_raw_bytes == 500
                    assert connection.usage_error == error
                panel.delete_user_from_panel.assert_not_awaited()

    async def test_never_created_identity_can_be_cancelled(self) -> None:
        service, _, _ = await self.activate()
        panel, _ = panel_fixture()
        async with self.sessions.begin() as session:
            await request_service_revocation(
                session,
                service_id=service.id,
                user_id=1,
                actor_id=1,
                expected_revision=1,
                idempotency_key="cancel-unsubmitted",
                reason="No remote identity has been submitted",
            )
        await revoke_service_identity(cast(sessionmaker, self.sessions), service.id, panel)
        async with self.sessions() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection and connection.state == "revoked"
            assert connection.panel_user_uuid is None and not connection.sync_pending
        panel.create_panel_user.assert_not_awaited()
        panel.delete_user_from_panel.assert_not_awaited()

    async def test_readable_identity_invalidates_old_deletion_evidence(self) -> None:
        service, _, _ = await self.activate()
        panel, remote = await self.ready(service.id)
        async with self.sessions.begin() as session:
            await request_service_revocation(
                session,
                service_id=service.id,
                user_id=1,
                actor_id=1,
                expected_revision=1,
                idempotency_key="cancel-reappeared",
                reason="Retry an unconfirmed delete",
            )
            saved = await session.get(UserService, service.id)
            connection = await session.get(ServiceConnection, service.id)
            assert saved and connection
            saved.used_bytes = 500
            connection.usage_total_bytes = connection.usage_raw_bytes = 500
            connection.revoke_delete_requested_at = datetime.now(UTC)
        remote["status"] = "DISABLED"
        remote["userTraffic"] = {}
        await revoke_service_identity(cast(sessionmaker, self.sessions), service.id, panel)
        panel.get_user_by_uuid_lookup.side_effect = None
        panel.get_user_by_uuid_lookup.return_value = {"ok": False, "not_found": True}
        await revoke_service_identity(cast(sessionmaker, self.sessions), service.id, panel)
        async with self.sessions() as session:
            connection = await session.get(ServiceConnection, service.id)
            saved = await session.get(UserService, service.id)
            assert saved and saved.used_bytes == 500
            assert connection and connection.state != "revoked" and connection.sync_pending
            assert connection.revoke_delete_requested_at is None
            assert connection.usage_error == "panel_usage_invalid"
            assert connection.sync_error == "service_revoke_usage_unconfirmed"
        panel.delete_user_from_panel.assert_not_awaited()

    async def test_uncertain_creation_survives_restricted_retry_until_late_identity_is_revoked(
        self,
    ) -> None:
        from db.models import User

        for restriction in ("paused", "banned", "expired"):
            with self.subTest(restriction=restriction):
                service, _, _ = await self.activate(restriction)
                panel, users = panel_fixture()
                create = panel.create_panel_user.side_effect
                assert callable(create)
                panel.create_panel_user.side_effect = TimeoutError(
                    "reply missing before creation becomes visible"
                )
                await provision_service_identity(
                    cast(sessionmaker, self.sessions), service.id, panel
                )
                submitted = panel.create_panel_user.await_args
                assert submitted
                async with self.sessions.begin() as session:
                    row = await session.get(UserService, service.id)
                    user = await session.get(User, 1)
                    assert row and user
                    if restriction == "paused":
                        row.desired_status = "paused"
                    elif restriction == "banned":
                        user.is_banned = True
                    else:
                        row.starts_at = datetime.now(UTC) - timedelta(days=2)
                        row.expires_at = datetime.now(UTC) - timedelta(days=1)
                await provision_service_identity(
                    cast(sessionmaker, self.sessions), service.id, panel
                )
                async with self.sessions.begin() as session:
                    connection = await session.get(ServiceConnection, service.id)
                    assert connection and connection.state == "error" and connection.last_error
                    await request_service_revocation(
                        session,
                        service_id=service.id,
                        user_id=1,
                        actor_id=1,
                        expected_revision=1,
                        idempotency_key=f"cancel:{restriction}",
                        reason="Cancel an uncertain creation",
                    )
                await revoke_service_identity(cast(sessionmaker, self.sessions), service.id, panel)
                async with self.sessions() as session:
                    connection = await session.get(ServiceConnection, service.id)
                    assert connection and connection.revoked_at is None and connection.sync_pending
                panel.delete_user_from_panel.assert_not_awaited()
                panel.create_panel_user.assert_awaited_once()
                await create(*submitted.args, **submitted.kwargs)
                users[f"svc_{service.id}"]["uuid"] = service.id
                panel.delete_user_from_panel.side_effect = lambda _reference, current_users=users: (
                    current_users.clear() or True
                )
                await revoke_service_identity(cast(sessionmaker, self.sessions), service.id, panel)
                async with self.sessions.begin() as session:
                    connection = await session.get(ServiceConnection, service.id)
                    user = await session.get(User, 1)
                    assert connection and connection.state == "revoked" and connection.revoked_at
                    assert user
                    user.is_banned = False
                panel.delete_user_from_panel.assert_awaited_once()
                panel.create_panel_user.assert_awaited_once()

    async def test_uncertain_creation_cannot_be_reclaimed_as_never_submitted(self) -> None:
        service, _, _ = await self.activate()
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection
            connection.state = "error"
            await session.flush()
            await request_service_revocation(
                session,
                service_id=service.id,
                user_id=1,
                actor_id=1,
                expected_revision=1,
                idempotency_key="cancel-uncertain",
                reason="No confirmed creation result",
            )
        panel, _ = panel_fixture()
        await revoke_service_identity(cast(sessionmaker, self.sessions), service.id, panel)
        async with self.sessions() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection and connection.state == "error" and connection.sync_pending
            assert connection.revoked_at is None
        panel.create_panel_user.assert_not_awaited()
        panel.delete_user_from_panel.assert_not_awaited()

    async def ready(self, service_id: str):
        panel, users = panel_fixture()
        await provision_service_identity(cast(sessionmaker, self.sessions), service_id, panel)
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, service_id)
            assert connection is not None
            connection.state = "ready"
            connection.panel_user_uuid = service_id
            users[f"svc_{service_id}"]["uuid"] = service_id
            connection.usage_total_bytes = 0
            service = await session.get(UserService, service_id)
            assert service is not None
            service.last_usage_sync_at = datetime.now(UTC)
        remote = users[f"svc_{service_id}"]
        remote["status"] = "ACTIVE"
        remote["subscriptionUrl"] = f"https://subscription.example.test/{service_id}"
        return panel, remote

    async def test_subscription_is_owned_private_and_service_scoped(self) -> None:
        first, _, _ = await self.activate()
        second, _, _ = await self.activate("second")
        panel, remote = await self.ready(first.id)
        async with self.sessions() as session:
            url = await service_subscription(session, user_id=1, service_id=first.id, panel=panel)
            assert url == remote["subscriptionUrl"]
            with pytest.raises(ServiceConflict, match="service_not_found"):
                await service_subscription(session, user_id=2, service_id=first.id, panel=panel)
            with pytest.raises(ServiceConflict, match="service_not_deliverable"):
                await service_subscription(session, user_id=1, service_id=second.id, panel=panel)
        assert panel.get_user_by_uuid_lookup.await_count == 1

    async def test_pending_paused_expired_exhausted_banned_or_syncing_never_deliver(self) -> None:
        for boundary in (
            "pending",
            "paused",
            "expired",
            "exhausted",
            "banned",
            "syncing",
            "revoked",
        ):
            with self.subTest(boundary=boundary):
                service, _, _ = await self.activate(boundary, user_id=2)
                panel, _ = await self.ready(service.id)
                async with self.sessions.begin() as session:
                    row = await session.get(UserService, service.id)
                    connection = await session.get(ServiceConnection, service.id)
                    assert row is not None and connection is not None
                    if boundary in {"pending", "revoked"}:
                        connection.state = boundary
                    elif boundary == "paused":
                        row.desired_status = "paused"
                    elif boundary == "expired":
                        row.starts_at = datetime.now(UTC) - timedelta(days=2)
                        row.expires_at = datetime.now(UTC) - timedelta(days=1)
                    elif boundary == "exhausted":
                        row.used_bytes = row.quota_bytes
                    elif boundary == "syncing":
                        connection.sync_pending = True
                    else:
                        from db.models import User

                        user = await session.get(User, 2)
                        assert user is not None
                        user.is_banned = True
                async with self.sessions() as session:
                    with pytest.raises(ServiceConflict):
                        await service_subscription(
                            session, user_id=2, service_id=service.id, panel=panel
                        )
                panel.get_user_by_uuid_lookup.assert_not_awaited()
                if boundary == "banned":
                    async with self.sessions.begin() as session:
                        from db.models import User

                        user = await session.get(User, 2)
                        assert user is not None
                        user.is_banned = False

    async def test_remote_ownership_terms_status_and_url_are_rechecked(self) -> None:
        service, _, _ = await self.activate()
        panel, remote = await self.ready(service.id)
        original = dict(remote)
        for changes in (
            {"username": "account-main"},
            {"description": "wrong-owner"},
            {"activeInternalSquads": [{"uuid": "another-group"}]},
            {"trafficLimitBytes": 999_999},
            {"status": "DISABLED"},
            {"subscriptionUrl": "javascript:alert(1)"},
            {"subscriptionUrl": "https://secret@evil.test/link"},
            {"subscriptionUrl": "https://example.test/\ncredential"},
            {"subscriptionUrl": "https://example.test/\x7fcredential"},
            {"subscriptionUrl": "https://example.test:invalid/credential"},
            {"subscriptionUrl": "https://example.test:0/credential"},
        ):
            remote.clear()
            remote.update({**original, **changes})
            async with self.sessions() as session:
                with pytest.raises(ServiceConflict, match="service_delivery_unconfirmed"):
                    await service_subscription(
                        session, user_id=1, service_id=service.id, panel=panel
                    )
        panel.get_user_by_uuid_lookup.side_effect = TimeoutError("secret-subscription-url")
        async with self.sessions() as session:
            with pytest.raises(ServiceConflict, match=r"^service_delivery_unconfirmed$"):
                await service_subscription(session, user_id=1, service_id=service.id, panel=panel)

    async def test_subscription_uses_monthly_cap_and_audited_raw_counter_offset(self) -> None:
        service, _, _ = await self.activate()
        panel, remote = await self.ready(service.id)
        async with self.sessions.begin() as session:
            row = await session.get(UserService, service.id)
            connection = await session.get(ServiceConnection, service.id)
            assert row and connection
            row.terms = {**row.terms, "traffic_rule": "monthly"}
            row.used_bytes = 25
            connection.usage_total_bytes = 1050
            connection.usage_raw_bytes = 50
        remote["userTraffic"] = {"usedTrafficBytes": 50, "lifetimeUsedTrafficBytes": 50}
        remote["trafficLimitBytes"] = 10025
        async with self.sessions() as session:
            assert (
                await service_subscription(session, user_id=1, service_id=service.id, panel=panel)
                == remote["subscriptionUrl"]
            )
        remote["trafficLimitBytes"] = 10000
        async with self.sessions() as session:
            with pytest.raises(ServiceConflict, match="service_delivery_unconfirmed"):
                await service_subscription(session, user_id=1, service_id=service.id, panel=panel)

    async def test_counter_regression_prevents_destructive_revocation(self) -> None:
        service, _, _ = await self.activate()
        panel, remote = await self.ready(service.id)
        async with self.sessions.begin() as session:
            await request_service_revocation(
                session,
                service_id=service.id,
                user_id=1,
                actor_id=1,
                expected_revision=1,
                idempotency_key="regressed",
                reason="Test cancellation",
            )
            connection = await session.get(ServiceConnection, service.id)
            row = await session.get(UserService, service.id)
            assert connection and row
            connection.usage_total_bytes = 100
            connection.usage_raw_bytes = 100
            row.used_bytes = 100
        remote["status"] = "DISABLED"
        remote["userTraffic"] = {"usedTrafficBytes": 10, "lifetimeUsedTrafficBytes": 10}
        await revoke_service_identity(cast(sessionmaker, self.sessions), service.id, panel)
        async with self.sessions() as session:
            row = await session.get(UserService, service.id)
            connection = await session.get(ServiceConnection, service.id)
            assert row and row.used_bytes == 100 and row.desired_status == "cancelled"
            assert (
                connection
                and connection.usage_error == "panel_usage_regressed"
                and connection.sync_pending
            )
        panel.delete_user_from_panel.assert_not_awaited()

    async def test_revocation_is_terminal_idempotent_and_waits_for_absence(self) -> None:
        first, _, _ = await self.activate()
        second, _, _ = await self.activate("second")
        panel, remote = await self.ready(first.id)
        command = {
            "service_id": first.id,
            "user_id": 1,
            "actor_id": 1,
            "expected_revision": 1,
            "idempotency_key": "revoke",
            "reason": "Operator requested cancellation",
        }
        async with self.sessions.begin() as session:
            await request_service_revocation(session, **command)
        async with self.sessions.begin() as session:
            _, _, duplicate = await request_service_revocation(session, **command)
            assert duplicate
            with pytest.raises(ServiceConflict, match="idempotency_conflict"):
                await request_service_revocation(session, **{**command, "service_id": second.id})
        remote["userTraffic"] = {"usedTrafficBytes": 7, "lifetimeUsedTrafficBytes": 7}

        async def disable(_reference: str, _enable: bool) -> bool:
            remote["status"] = "DISABLED"
            return True

        panel.update_user_status_on_panel.side_effect = disable

        async def lose_delete_response(_reference: str) -> None:
            async with self.sessions() as session:
                connection = await session.get(ServiceConnection, first.id)
                assert connection and connection.revoke_delete_requested_at is not None
                assert connection.usage_total_bytes == 7
            raise TimeoutError("lost response")

        panel.delete_user_from_panel.side_effect = lose_delete_response
        await revoke_service_identity(cast(sessionmaker, self.sessions), first.id, panel)
        async with self.sessions() as session:
            connection = await session.get(ServiceConnection, first.id)
            other = await session.get(UserService, second.id)
            assert (
                connection is not None and connection.sync_pending and connection.revoked_at is None
            )
            assert other is not None and other.desired_status == "active"
            cancelled = await session.get(UserService, first.id)
            assert cancelled and cancelled.used_bytes == 7 and connection.usage_total_bytes == 7
            assert connection.revoke_delete_requested_at is not None
            with pytest.raises(ServiceConflict, match="service_not_deliverable"):
                await service_subscription(session, user_id=1, service_id=first.id, panel=panel)
        # A transient failed lookup must not discard the committed deletion evidence.
        panel.get_user_by_uuid_lookup.side_effect = TimeoutError("lookup unavailable")
        await revoke_service_identity(cast(sessionmaker, self.sessions), first.id, panel)
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, first.id)
            assert connection and connection.revoke_delete_requested_at is not None
            # The usage worker can observe absence before the revocation worker retries.
            connection.usage_error = "panel_identity_missing"
        panel.get_user_by_uuid_lookup.side_effect = None
        panel.get_user_by_uuid_lookup.return_value = {"ok": False, "not_found": True}
        await revoke_service_identity(cast(sessionmaker, self.sessions), first.id, panel)
        async with self.sessions() as session:
            saved = await session.get(ServiceConnection, first.id)
            assert saved
            revoked_at = saved.revoked_at
        await revoke_service_identity(cast(sessionmaker, self.sessions), first.id, panel)
        async with self.sessions() as session:
            connection = await session.get(ServiceConnection, first.id)
            assert (
                connection is not None and connection.state == "revoked" and connection.revoked_at
            )
            assert connection.revoked_at == revoked_at
            assert connection.usage_error is None
        assert remote["username"] == f"svc_{first.id}"
        panel.delete_user_from_panel.assert_awaited_once()

    @pytest.mark.filterwarnings(
        "ignore:It is recommended to use web.RequestKey: aiohttp.web_exceptions.NotAppKeyWarning"
    )
    async def test_http_ownership_admin_permissions_and_no_cache(self) -> None:
        service, _, _ = await self.activate()
        panel, remote = await self.ready(service.id)
        settings = Settings(
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            BOT_TOKEN="1234567890:AA_secret_bot_token_value",
            _env_file=None,
        )
        app = web.Application(middlewares=[admin_auth_middleware])
        app[SETTINGS] = settings
        app[SESSION_FACTORY] = self.sessions
        app[PANEL_SERVICE] = panel
        setup_service_admin_routes(app)
        setup_service_user_routes(app)
        admin = {"Authorization": "Bearer " + create_webapp_session_token(settings, 1)}
        other = {"Authorization": "Bearer " + create_webapp_session_token(settings, 2)}
        path = f"/api/services/{service.id}/subscription"
        async with TestClient(TestServer(app)) as client:
            assert (await client.get(path)).status == 401
            assert (await client.get(path, headers=other)).status == 404
            response = await client.get(path, headers=admin)
            assert response.status == 200
            assert response.headers["Cache-Control"] == "private, no-store"
            assert (await response.json())["subscription"]["subscription_url"] == remote[
                "subscriptionUrl"
            ]
            response = await client.get("/api/services", headers=admin)
            assert "subscriptionUrl" not in await response.text()
            for route in (
                f"/api/admin/services/{service.id}/deliver",
                f"/api/admin/services/{service.id}/revoke",
                "/api/admin/dedicated-exits/nope/verify",
                "/api/admin/dedicated-exits/nope/reclaim",
            ):
                assert (await client.post(route, json={}, headers=other)).status == 403
            remote["userTraffic"] = {"usedTrafficBytes": 10001, "lifetimeUsedTrafficBytes": 10001}
            response = await client.get(path, headers=admin)
            assert response.status == 503
            assert "subscription_url" not in await response.text()
            async with self.sessions() as session:
                saved = await session.get(UserService, service.id)
                assert saved and saved.used_bytes == 10001


class ExitEvidenceTests(ServiceDatabaseTestCase):
    async def allocate(self):
        async with self.sessions.begin() as session:
            plan = await save_plan(
                session,
                terms=sample_terms(resource_type="dedicated", squad_uuids=[], resource_pool="test"),
                enabled=True,
                actor_id=1,
            )
            resource = await create_exit(
                session,
                label="Test resource",
                ip_address="192.0.2.1",
                resource_pool="test",
                squad_uuid="00000000-0000-0000-0000-000000000002",
            )
            service, _, _ = await activate_service(
                session,
                user_id=1,
                actor_id=1,
                plan_id=plan.id,
                expected_revision=1,
                idempotency_key="allocate",
                exit_id=resource.id,
            )
        return resource, service, plan

    async def test_verification_requires_matching_actual_address_and_audit(self) -> None:
        resource, service, _ = await self.allocate()
        body = ExitVerifyBody(
            expected_revision=resource.revision,
            service_id=service.id,
            idempotency_key="proof",
            checked_at=datetime.now(UTC),
            evidence="Isolated test fixture; not actual Node evidence",
            observed_ip="192.0.2.1",
            fixed=True,
            exclusive=True,
        )
        command = body.model_dump(mode="json")
        async with self.sessions.begin() as session:
            with pytest.raises(ServiceConflict, match="exit_evidence_mismatch"):
                await record_exit_evidence(
                    session,
                    exit_id=resource.id,
                    actor_id=1,
                    action="verify",
                    command={**command, "observed_ip": "192.0.2.2"},
                )
            updated, audit, duplicate = await record_exit_evidence(
                session, exit_id=resource.id, actor_id=1, action="verify", command=command
            )
            assert not duplicate and updated.verified_at and audit.service_id == service.id
        async with self.sessions.begin() as session:
            _, _, duplicate = await record_exit_evidence(
                session, exit_id=resource.id, actor_id=1, action="verify", command=command
            )
            assert duplicate
            with pytest.raises(ServiceConflict, match="exit_revision_changed"):
                await record_exit_evidence(
                    session,
                    exit_id=resource.id,
                    actor_id=1,
                    action="verify",
                    command={**command, "idempotency_key": "new-stale"},
                )

    async def test_no_release_before_revocation_and_manual_stop_confirmation(self) -> None:
        resource, service, plan = await self.allocate()
        body = ExitReclaimBody(
            expected_revision=resource.revision,
            service_id=service.id,
            idempotency_key="release",
            checked_at=datetime.now(UTC),
            evidence="Unit fixture: old connections and configs rejected",
            connections_stopped=True,
            old_config_rejected=True,
        )
        async with self.sessions.begin() as session:
            with pytest.raises(ServiceConflict, match="exit_stop_unconfirmed"):
                await record_exit_evidence(
                    session,
                    exit_id=resource.id,
                    actor_id=1,
                    action="reclaim",
                    command=body.model_dump(mode="json"),
                )
            with pytest.raises(ServiceConflict, match="exit_unavailable"):
                await activate_service(
                    session,
                    user_id=2,
                    actor_id=1,
                    plan_id=plan.id,
                    expected_revision=1,
                    idempotency_key="competing",
                    exit_id=resource.id,
                )
            connection = await session.get(ServiceConnection, service.id)
            assert connection is not None
            connection.state = "revoked"
            connection.revoked_at = datetime.now(UTC)
        async with self.sessions.begin() as session:
            with pytest.raises(ServiceConflict, match="exit_stop_unconfirmed"):
                await record_exit_evidence(
                    session,
                    exit_id=resource.id,
                    actor_id=1,
                    action="reclaim",
                    command=body.model_dump(mode="json"),
                )
        body.checked_at = datetime.now(UTC)
        async with self.sessions.begin() as session:
            updated, audit, _ = await record_exit_evidence(
                session,
                exit_id=resource.id,
                actor_id=1,
                action="reclaim",
                command=body.model_dump(mode="json"),
            )
            assert updated.service_id is None and updated.verified_at is None
            assert audit.service_id == service.id
            next_service, _, _ = await activate_service(
                session,
                user_id=2,
                actor_id=1,
                plan_id=plan.id,
                expected_revision=1,
                idempotency_key="next",
                exit_id=resource.id,
            )
            assert next_service.id != service.id
        async with self.sessions.begin() as session:
            updated, _, duplicate = await record_exit_evidence(
                session,
                exit_id=resource.id,
                actor_id=1,
                action="reclaim",
                command=body.model_dump(mode="json"),
            )
            assert duplicate and updated.service_id == next_service.id
            assert len(list(await session.scalars(select(DedicatedExitAudit)))) == 1
            stored = await session.get(DedicatedExit, resource.id)
            assert stored is not None and stored.service_id == next_service.id
