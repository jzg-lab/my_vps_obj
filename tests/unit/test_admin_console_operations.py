"""UC-04/05 endpoints do not mutate rights or expose panel credentials on reads."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import delete, func, select

from bot.app.web.admin_api_impl.auth import admin_auth_middleware
from bot.app.web.admin_console_operations_routes import setup_admin_console_operations_routes
from bot.app.web.context import PANEL_SERVICE, SESSION_FACTORY, SETTINGS
from bot.app.web.webapp.assets import _csrf_protection_middleware
from bot.app.web.webapp_auth import create_webapp_session_token
from config.settings import Settings
from db.auth_models import AccountRole
from db.dal.user_services_dal import ServiceConflict, activate_service, create_exit, save_plan
from db.service_models import (
    DedicatedExit,
    ServiceConnection,
    ServiceOperationExecution,
    ServiceOrder,
    UserService,
)
from tests.unit.test_admin_console_nodes import NODE, panel_fixture, panel_responses
from tests.unit.test_user_services import ServiceDatabaseTestCase, sample_terms


@pytest.mark.filterwarnings(
    "ignore:It is recommended to use web.RequestKey: aiohttp.web_exceptions.NotAppKeyWarning"
)
class AdminConsoleOperationsTests(ServiceDatabaseTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.responses = panel_responses()
        self.panel, self.panel_request = panel_fixture(self.responses)
        self.lookup = AsyncMock()
        patcher = patch.object(self.panel, "get_user_by_uuid_lookup", self.lookup)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.settings = Settings(
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            BOT_TOKEN="1234567890:AA_secret_bot_token_value",
            _env_file=None,
        )
        app = web.Application(middlewares=[_csrf_protection_middleware, admin_auth_middleware])
        app[SETTINGS] = self.settings
        app[SESSION_FACTORY] = self.sessions
        app[PANEL_SERVICE] = self.panel
        setup_admin_console_operations_routes(app)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.admin = {"Authorization": "Bearer " + create_webapp_session_token(self.settings, 1)}
        self.body = {"user_id": 2, "plan_id": self.plan.id, "expected_revision": 1}

    async def preflight(self, **changes: object) -> dict:
        response = await self.client.post(
            "/api/admin/console/service-preflight",
            json={**self.body, **changes},
            headers=self.admin,
        )
        assert response.status == 200, await response.text()
        assert response.headers["Cache-Control"] == "private, no-store"
        payload = await response.json()
        assert isinstance(payload, dict)
        return payload

    async def prepare_diagnostic(self) -> tuple[str, dict[str, object]]:
        service, _, _ = await self.activate(user_id=2)
        now = datetime.now(UTC)
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, service.id)
            saved = await session.get(UserService, service.id)
            assert connection and saved
            connection.panel_user_uuid = NODE
            connection.state = "ready"
            connection.usage_total_bytes = 7
            connection.usage_raw_bytes = 7
            saved.used_bytes = 7
            saved.last_usage_sync_at = now
            remote: dict[str, object] = {
                "uuid": NODE,
                "username": connection.username,
                "description": f"my_vps_obj:service:{service.id}",
                "status": "ACTIVE",
                "expireAt": service.expires_at.isoformat(),
                "trafficLimitBytes": service.quota_bytes,
                "trafficLimitStrategy": "NO_RESET",
                "activeInternalSquads": service.terms["squad_uuids"],
                "userTraffic": {"usedTrafficBytes": 19, "lifetimeUsedTrafficBytes": 19},
                "subscriptionUrl": "https://NEVER_EXPOSE.example/secret",
                "password": "NEVER_EXPOSE",
            }
        self.lookup.return_value = {"ok": True, "user": remote}
        return service.id, remote

    async def diagnostics(self, service_id: str) -> dict:
        response = await self.client.get(
            f"/api/admin/console/services/{service_id}/diagnostics",
            headers=self.admin,
        )
        assert response.status == 200, await response.text()
        assert response.headers["Cache-Control"] == "private, no-store"
        assert "NEVER_EXPOSE" not in await response.text()
        payload = await response.json()
        assert isinstance(payload, dict)
        return payload

    async def test_preflight_distinguishes_pending_creation_from_delivery(self) -> None:
        result = await self.preflight()
        assert result["allow_pending_creation"] is True
        assert result["resource_readiness"] == "ready"
        assert result["ready_for_delivery"] is False
        assert len(result["hosts"]) == len(result["nodes"]) == 1
        assert "NEVER_EXPOSE" not in str(result)
        async with self.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(UserService)) == 0
            assert await session.scalar(select(func.count()).select_from(ServiceOrder)) == 0

    async def test_preflight_unknown_partial_and_real_empty_do_not_become_ready(self) -> None:
        for payload, readiness in ((RuntimeError("NEVER_EXPOSE"), "unknown"), ([], "blocked")):
            with self.subTest(readiness=readiness):
                self.responses["/nodes"] = payload
                result = await self.preflight()
                assert result["allow_pending_creation"] is True
                assert result["resource_readiness"] == readiness
                assert result["ready_for_delivery"] is False
                assert "NEVER_EXPOSE" not in str(result)

    async def test_preflight_rechecks_account_plan_and_revision(self) -> None:
        for changes in ({"user_id": 3}, {"user_id": 999}, {"expected_revision": 2}):
            with self.subTest(changes=changes):
                assert (await self.preflight(**changes))["allow_pending_creation"] is False
        async with self.sessions.begin() as session:
            await save_plan(
                session,
                plan_id=self.plan.id,
                expected_revision=1,
                terms=sample_terms(),
                enabled=False,
                actor_id=1,
            )
        assert (await self.preflight(expected_revision=2))["allow_pending_creation"] is False

    async def test_preflight_dedicated_verification_is_separate_from_reservation(self) -> None:
        async with self.sessions.begin() as session:
            plan = await save_plan(
                session,
                terms=sample_terms(resource_type="dedicated", resource_pool="pool", squad_uuids=[]),
                enabled=True,
                actor_id=1,
            )
            resource = await create_exit(
                session,
                label="Exit",
                ip_address="192.0.2.4",
                resource_pool="pool",
                squad_uuid=str(sample_terms().squad_uuids[0]),
            )
        result = await self.preflight(plan_id=plan.id, exit_id=resource.id)
        assert result["allow_pending_creation"] is True
        assert result["resource_readiness"] == "blocked"
        async with self.sessions() as session:
            saved = await session.get(DedicatedExit, resource.id)
            assert saved and saved.service_id is None and saved.verified_at is None
        async with self.sessions.begin() as session:
            await activate_service(
                session,
                user_id=2,
                actor_id=1,
                plan_id=plan.id,
                expected_revision=1,
                exit_id=resource.id,
                idempotency_key="occupy",
            )
        assert (await self.preflight(plan_id=plan.id, exit_id=resource.id))[
            "allow_pending_creation"
        ] is False
        async with self.sessions.begin() as session:
            with self.assertRaisesRegex(ServiceConflict, "exit_unavailable"):
                await activate_service(
                    session,
                    user_id=1,
                    actor_id=1,
                    plan_id=plan.id,
                    expected_revision=1,
                    exit_id=resource.id,
                    idempotency_key="race",
                )

    async def test_diagnostics_has_new_observation_without_accepting_traffic(self) -> None:
        service_id, _ = await self.prepare_diagnostic()
        result = await self.diagnostics(service_id)
        assert result["remote"]["availability"] == "available"
        assert result["remote"]["identity_matches"] is True
        assert result["remote"]["terms_match"] is True
        assert result["remote"]["raw_used_bytes"] == 19
        assert result["remote"]["observed_at"]
        assert result["target_access"] == "enabled" and result["data_plane_verified"] is False
        async with self.sessions() as session:
            service = await session.get(UserService, service_id)
            connection = await session.get(ServiceConnection, service_id)
            assert service and connection
            assert service.used_bytes == connection.usage_total_bytes == 7
            assert connection.sync_confirmed_at is None

    async def test_diagnostics_ownership_conflict_hides_other_identity(self) -> None:
        service_id, remote = await self.prepare_diagnostic()
        remote["username"] = "NEVER_EXPOSE"
        self.lookup.return_value = {"ok": True, "user": remote}
        result = await self.diagnostics(service_id)
        assert result["remote"]["availability"] == "conflict"
        assert result["remote"]["raw_used_bytes"] is None
        assert result["remote"]["status"] is None
        assert result["remote"]["terms_match"] is None

    async def test_diagnostics_known_regression_and_raw_errors_are_safe(self) -> None:
        service_id, remote = await self.prepare_diagnostic()
        remote["userTraffic"] = {"usedTrafficBytes": 2, "lifetimeUsedTrafficBytes": 2}
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, service_id)
            assert connection
            connection.last_error = "NEVER_EXPOSE"
            connection.usage_error = "panel_usage_regressed"
        result = await self.diagnostics(service_id)
        assert result["remote"]["usage_readable"] is False
        assert result["remote"]["error"] == "panel_usage_regressed"
        assert result["errors"]["preparation"] == "unclassified_service_error"
        assert result["target_access"] == "unknown"
        assert "reconcile_usage" in result["next_steps"]

    async def test_diagnostics_outage_missing_and_account_restrictions(self) -> None:
        service_id, _ = await self.prepare_diagnostic()
        self.lookup.side_effect = RuntimeError("NEVER_EXPOSE")
        assert (await self.diagnostics(service_id))["remote"]["availability"] == "unavailable"
        self.lookup.side_effect = None
        self.lookup.return_value = {"ok": False, "not_found": True}
        assert (await self.diagnostics(service_id))["remote"]["availability"] == "not_found"
        async with self.sessions.begin() as session:
            service = await session.get(UserService, service_id)
            assert service
            service.desired_status = "paused"
        result = await self.diagnostics(service_id)
        assert result["target_access"] == "disabled" and result["status"] == "paused"

    async def test_every_route_requires_current_admin_role_before_panel_reads(self) -> None:
        service, _, _ = await self.activate()
        path = f"/api/admin/console/services/{service.id}/diagnostics"
        history = f"/api/admin/console/services/{service.id}/operations"
        async with self.sessions() as session:
            operation = await session.scalar(select(ServiceOperationExecution))
            assert operation
            retry = f"{history}/{operation.id}/retry"
        retry_body = {"user_id": 1, "expected_revision": 1, "idempotency_key": "retry"}
        for user_id in (None, 2, 3):
            headers = (
                {"Authorization": "Bearer " + create_webapp_session_token(self.settings, user_id)}
                if user_id
                else {}
            )
            expected = 403 if user_id else 401
            assert (await self.client.get(path, headers=headers)).status == expected
            assert (await self.client.get(history, headers=headers)).status == expected
            assert (
                await self.client.post(retry, json=retry_body, headers=headers)
            ).status == expected
            assert (
                await self.client.post(
                    "/api/admin/console/service-preflight", json=self.body, headers=headers
                )
            ).status == expected
        async with self.sessions.begin() as session:
            await session.execute(delete(AccountRole).where(AccountRole.user_id == 1))
        assert (await self.client.get(path, headers=self.admin)).status == 403
        assert (await self.client.get(history, headers=self.admin)).status == 403
        assert (await self.client.post(retry, json=retry_body, headers=self.admin)).status == 403
        assert (
            await self.client.post(
                "/api/admin/console/service-preflight", json=self.body, headers=self.admin
            )
        ).status == 403
        self.lookup.assert_not_awaited()
        self.panel_request.assert_not_awaited()

    async def test_preflight_rejects_extra_fields_and_cookie_requests_without_csrf(self) -> None:
        response = await self.client.post(
            "/api/admin/console/service-preflight",
            json={**self.body, "force": True},
            headers=self.admin,
        )
        assert response.status == 400
        response = await self.client.post(
            "/api/admin/console/service-preflight",
            json=self.body,
            cookies={"rw_webapp_session": create_webapp_session_token(self.settings, 1)},
        )
        assert response.status == 403 and (await response.json())["error"] == "csrf_failed"
        self.panel_request.assert_not_awaited()

    async def test_preflight_never_reuses_stale_online_evidence_or_unknown_visibility(self) -> None:
        assert (await self.preflight())["resource_readiness"] == "ready"
        self.responses["/nodes"] = RuntimeError("NEVER_EXPOSE")
        result = await self.preflight()
        assert result["resource_readiness"] == "unknown"
        assert result["nodes"][0]["status"] == "unknown"
        self.responses.update(panel_responses())
        hosts = self.responses["/hosts"]
        assert isinstance(hosts, list)
        hosts[0].pop("internalSquads")
        result = await self.preflight()
        assert result["resource_readiness"] == "unknown"

    async def test_diagnostics_missing_local_records_and_no_prepared_identity(self) -> None:
        service, _, _ = await self.activate()
        result = await self.diagnostics(service.id)
        assert result["remote"]["availability"] == "not_prepared"
        assert result["remote"]["attempted_at"] is None
        assert result["data_plane_verified"] is False
        self.lookup.assert_not_awaited()
        for service_id, query, expected in (
            ("invalid", "", 400),
            ("f" * 32, "", 404),
            (service.id, "?force=true", 400),
        ):
            response = await self.client.get(
                f"/api/admin/console/services/{service_id}/diagnostics{query}",
                headers=self.admin,
            )
            assert response.status == expected

    async def test_uncertain_create_stays_unknown_and_does_not_claim_absence(self) -> None:
        service, _, _ = await self.activate()
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection
            connection.state = "error"
            connection.last_error = "panel_identity_unconfirmed"
        result = await self.diagnostics(service.id)
        assert result["remote"]["availability"] == "unconfirmed"
        assert result["remote"]["observed_at"] is None
        assert result["remote"]["attempted_at"] is None
        self.lookup.assert_not_awaited()

    async def test_history_keeps_legacy_result_unknown_and_never_exposes_requests(self) -> None:
        service, order, _ = await self.activate()
        async with self.sessions.begin() as session:
            await session.execute(delete(ServiceOperationExecution))
            saved = await session.get(ServiceOrder, order.id)
            assert saved
            saved.snapshot = {"password": "NEVER_EXPOSE"}
        path = f"/api/admin/console/services/{service.id}/operations"
        response = await self.client.get(path + "?limit=1", headers=self.admin)
        assert response.status == 200 and response.headers["Cache-Control"] == "private, no-store"
        assert "NEVER_EXPOSE" not in await response.text()
        result = await response.json()
        record = result["operations"][0]
        assert result["total"] == 1 and result["limit"] == 1
        assert record["status"] == "unknown" and record["attempt_count"] is None
        assert record["first_failed_at"] is record["completed_at"] is None
        assert record["retryable"] is False
        response = await self.client.get(path + "?offset=1", headers=self.admin)
        result = await response.json()
        assert result["total"] == 1 and result["operations"] == []
        for query in ("?limit=0", "?offset=-1", "?force=true"):
            assert (await self.client.get(path + query, headers=self.admin)).status == 400

    async def test_retry_saves_existing_intent_and_replay_without_remote_calls(self) -> None:
        service, _, _ = await self.activate(user_id=2)
        async with self.sessions() as session:
            operation = await session.scalar(select(ServiceOperationExecution))
            assert operation
            path = f"/api/admin/console/services/{service.id}/operations/{operation.id}/retry"
        body = {"user_id": 2, "expected_revision": 1, "idempotency_key": "ui-retry"}
        orders = []
        for duplicate in (False, True):
            response = await self.client.post(path, json=body, headers=self.admin)
            assert response.status == 200, await response.text()
            assert response.headers["Cache-Control"] == "private, no-store"
            result = await response.json()
            assert result["accepted"] is True and result["duplicate"] is duplicate
            assert result["operation"]["status"] == "pending"
            assert result["operation"]["attempt_count"] == 0
            orders.append(result["retry_order_id"])
        assert orders[0] == orders[1]
        response = await self.client.post(
            path, json={**body, "expected_revision": 2}, headers=self.admin
        )
        assert response.status == 409 and (await response.json())["error"] == "idempotency_conflict"
        response = await self.client.post(path, json={**body, "force": True}, headers=self.admin)
        assert response.status == 400
        response = await self.client.post(
            path,
            json=body,
            cookies={"rw_webapp_session": create_webapp_session_token(self.settings, 1)},
        )
        assert response.status == 403 and (await response.json())["error"] == "csrf_failed"
        async with self.sessions() as session:
            saved = await session.get(UserService, service.id)
            assert saved and saved.revision == 1 and saved.used_bytes == 0
            assert saved.expires_at == service.expires_at.replace(tzinfo=None)
            assert await session.scalar(select(func.count()).select_from(ServiceOrder)) == 2
        self.lookup.assert_not_awaited()
        self.panel_request.assert_not_awaited()
