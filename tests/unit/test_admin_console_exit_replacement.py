"""Actual aiohttp role/CSRF boundaries and the stable replacement command contract."""

from datetime import UTC, datetime

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from pydantic import ValidationError

from bot.app.web.admin_api_impl.auth import admin_auth_middleware
from bot.app.web.admin_console_exit_replacement_routes import (
    setup_admin_console_exit_replacement_routes,
)
from bot.app.web.admin_console_exit_replacement_schemas import ConsoleExitReplacementEvidenceBody
from bot.app.web.admin_console_operations_routes import setup_admin_console_operations_routes
from bot.app.web.context import PANEL_SERVICE, SESSION_FACTORY, SETTINGS
from bot.app.web.route_contracts import get_contracts
from bot.app.web.service_delivery_routes import (
    ExitReclaimCommand,
    ExitVerifyCommand,
    setup_service_delivery_admin_routes,
)
from bot.app.web.webapp.assets import _csrf_protection_middleware
from bot.app.web.webapp_auth import create_webapp_session_token
from config.settings import Settings
from tests.unit.test_service_exit_replacement import DIGEST
from tests.unit.test_service_exit_replacement_runner import RunnerDatabaseTestCase


def test_evidence_never_accepts_client_machine_provenance_or_coerced_true() -> None:
    body = {
        "operation_id": "a" * 32,
        "expected_operation_version": 1,
        "resource_fingerprint": "b" * 64,
        "checked_at": datetime.now(UTC),
        "evidence_digest": "c" * 64,
        "purpose": "resolve_write",
        "action": "stop_old",
        "attempt": 1,
        "result": "applied",
        "idempotency_key": "receipt",
    }
    assert ConsoleExitReplacementEvidenceBody.model_validate(body).purpose == "resolve_write"
    for change in (
        {"provenance": "machine"},
        {"attempt": True},
        {"authorization_removed": 1},
        {"privateKey": "SECRET"},
        {"purpose": "stop"},
    ):
        with pytest.raises(ValidationError):
            ConsoleExitReplacementEvidenceBody.model_validate(body | change)


def test_ordinary_evidence_contract_still_uses_strict_legacy_shape() -> None:
    base = {
        "expected_revision": 1,
        "service_id": "a" * 32,
        "idempotency_key": "ordinary",
        "checked_at": datetime.now(UTC),
        "evidence": "Verified external report",
    }
    verify = base | {"observed_ip": "192.0.2.1", "fixed": True, "exclusive": True}
    assert ExitVerifyCommand.model_validate(verify).root.__class__.__name__ == "ExitVerifyBody"
    reclaim = base | {"connections_stopped": True, "old_config_rejected": True}
    assert ExitReclaimCommand.model_validate(reclaim).root.__class__.__name__ == "ExitReclaimBody"
    with pytest.raises(ValidationError):
        ExitVerifyCommand.model_validate(verify | {"replacement_operation_id": "b" * 32})


@pytest.mark.filterwarnings(
    "ignore:It is recommended to use web.RequestKey: aiohttp.web_exceptions.NotAppKeyWarning"
)
class ExitReplacementHttpTests(RunnerDatabaseTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
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
        setup_admin_console_exit_replacement_routes(app)
        setup_admin_console_operations_routes(app)
        setup_service_delivery_admin_routes(app)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.admin_token = create_webapp_session_token(self.settings, 1)
        self.admin = {"Authorization": "Bearer " + self.admin_token}
        self.path = f"/api/admin/console/services/{self.service.id}/exit-replacement"

    async def test_get_is_private_fresh_and_contains_no_secrets_or_side_effect(self) -> None:
        self.remote["password"] = "SECRET_MUST_NEVER_APPEAR"
        before = await self.progress()
        response = await self.client.get(self.path, headers=self.admin)
        assert response.status == 200, await response.text()
        assert response.headers["Cache-Control"] == "private, no-store"
        assert "SECRET_MUST_NEVER_APPEAR" not in await response.text()
        payload = await response.json()
        assert payload["ok"] is True
        assert payload["replacement"]["requested_resource_fingerprint"] == self.fingerprint
        assert payload["replacement"]["operation"]["attempt_count"] == 0
        assert await self.progress() == before and not self.writes

    async def test_role_precedes_payload_and_sources_and_cookie_csrf_is_required(self) -> None:
        self.panel._request.reset_mock()
        ordinary = {"Authorization": "Bearer " + create_webapp_session_token(self.settings, 2)}
        for method, suffix in (
            ("GET", ""),
            ("POST", ""),
            ("POST", "/confirm"),
            ("POST", "/evidence"),
        ):
            response = await self.client.request(
                method, self.path + suffix, headers=ordinary, data="SECRET"
            )
            assert response.status == 403
            assert response.headers["Cache-Control"] == "private, no-store"
            assert "SECRET" not in await response.text()
        self.panel._request.assert_not_awaited()
        response = await self.client.post(
            self.path, cookies={"rw_webapp_session": self.admin_token}, json={}
        )
        assert response.status == 403
        assert response.headers["Cache-Control"] == "private, no-store"

    async def test_invalid_evidence_and_source_exceptions_do_not_echo_credentials(self) -> None:
        response = await self.client.post(
            self.path + "/evidence",
            headers=self.admin,
            json={"purpose": "PRIVATE_KEY_SECRET", "provenance": "machine"},
        )
        assert response.status == 400 and "PRIVATE_KEY_SECRET" not in await response.text()
        assert response.headers["Cache-Control"] == "private, no-store"
        self.panel._request.side_effect = RuntimeError("PRIVATE_KEY_SECRET")
        response = await self.client.get(self.path, headers=self.admin)
        assert response.status == 200 and "PRIVATE_KEY_SECRET" not in await response.text()
        assert (await response.json())["replacement"]["coverage"] == "partial"

    async def test_registered_handlers_and_ordinary_evidence_discriminants(self) -> None:
        contracts = get_contracts()
        for name in ("route", "start_route", "confirm_route", "evidence_route"):
            assert f"admin_console_service_exit_replacement_{name}" in contracts
        for name in ("admin_exit_verify_route", "admin_exit_reclaim_route"):
            model = contracts[name].request_model
            assert model is not None and "anyOf" in model.model_json_schema()

    async def test_start_replay_returns_same_operation_without_a_remote_attempt(self) -> None:
        body = self.request.model_dump(mode="json")
        body["expected_resource_fingerprint"] = body.pop("resource_fingerprint")
        body.update(user_id=1, idempotency_key="replace")
        response = await self.client.post(self.path, headers=self.admin, json=body)
        assert response.status == 200, await response.text()
        result = await response.json()
        assert result["duplicate"] and result["replacement"]["operation"]["id"] == self.operation.id
        assert result["replacement"]["operation"]["attempt_count"] == 0 and not self.writes

    async def test_http_evidence_confirm_and_existing_reclaim_complete_without_http_remote_writes(
        self,
    ) -> None:
        await self.tick()
        response = await self.client.get(self.path, headers=self.admin)
        result = await response.json()
        current = result["replacement"]
        accounting = current["accounting"]
        now = datetime.now(UTC).isoformat()
        response = await self.client.post(
            self.path + "/evidence",
            headers=self.admin,
            json={
                "operation_id": self.operation.id,
                "expected_operation_version": current["progress"]["version"],
                "resource_fingerprint": current["resource_fingerprint"],
                "checked_at": now,
                "evidence_digest": DIGEST,
                "purpose": "stop",
                "authorization_removed": True,
                "connections_stopped": True,
                "old_config_rejected": True,
                "usage_observed_at": now,
                "usage_total_bytes": accounting["usage_total_bytes"],
                "usage_raw_bytes": accounting["usage_raw_bytes"],
                "usage_lifetime_offset": accounting["usage_lifetime_offset"],
                "usage_evidence_digest": DIGEST,
                "idempotency_key": "http-stop",
            },
        )
        assert response.status == 200, await response.text()
        current = (await response.json())["replacement"]
        assert current["progress"]["stage"] == "awaiting_confirmation"
        candidate = current["candidate_exit"]
        verify = {
            "replacement_operation_id": self.operation.id,
            "service_id": self.service.id,
            "expected_revision": candidate["revision"],
            "expected_operation_version": current["progress"]["version"],
            "scope_fingerprint": candidate["scope_fingerprint"],
            "checked_at": datetime.now(UTC).isoformat(),
            "observed_ip": candidate["ip_address"],
            "fixed": True,
            "exclusive": True,
            "evidence_digest": DIGEST,
            "idempotency_key": "http-verify",
        }
        verify_path = f"/api/admin/dedicated-exits/{self.new_id}/verify"
        response = await self.client.post(verify_path, headers=self.admin, json=verify)
        assert response.status == 200, await response.text()
        assert (await response.json())["audit"]["action"] == "replace_verify"
        response = await self.client.post(verify_path, headers=self.admin, json=verify)
        assert response.status == 200 and (await response.json())["duplicate"] is True
        response = await self.client.get(self.path, headers=self.admin)
        result = await response.json()
        current = result["replacement"]
        confirm = {
            "user_id": 1,
            "operation_id": self.operation.id,
            "expected_revision": result["service_revision"],
            "expected_operation_version": current["progress"]["version"],
            "expected_old_exit_revision": current["old_exit"]["revision"],
            "expected_new_exit_revision": current["candidate_exit"]["revision"],
            "expected_resource_fingerprint": current["resource_fingerprint"],
            "old_stop_audit_id": current["old_stop"]["audit_id"],
            "candidate_verify_audit_id": current["candidate_verification"]["audit_id"],
            "confirm_replace_and_request_restore": True,
            "idempotency_key": "http-confirm",
        }
        response = await self.client.post(self.path + "/confirm", headers=self.admin, json=confirm)
        assert response.status == 200, await response.text()
        assert (await response.json())["replacement"]["restore_requested"] is True
        assert len(self.writes) == 1
        for _ in range(4):
            await self.tick()
        response = await self.client.get(self.path, headers=self.admin)
        current = (await response.json())["replacement"]
        assert current["progress"]["stage"] == "completed"
        assert current["progress"]["restore_result"] == "enabled"
        assert current["old_resource_state"] == "held"
        before = len(self.writes)
        reclaim = {
            "replacement_operation_id": self.operation.id,
            "service_id": self.service.id,
            "reclaim_purpose": "retained_old",
            "expected_revision": current["old_exit"]["revision"],
            "expected_operation_version": current["progress"]["version"],
            "scope_fingerprint": current["old_exit"]["scope_fingerprint"],
            "checked_at": datetime.now(UTC).isoformat(),
            "connections_stopped": True,
            "old_config_rejected": True,
            "evidence_digest": DIGEST,
            "idempotency_key": "http-reclaim",
        }
        response = await self.client.post(
            f"/api/admin/dedicated-exits/{self.old_id}/reclaim", headers=self.admin, json=reclaim
        )
        assert response.status == 200, await response.text()
        assert response.headers["Cache-Control"] == "private, no-store"
        result = await response.json()
        assert result["audit"]["action"] == "replace_reclaim"
        assert result["exit"]["hold_order_id"] is None
        assert len(self.writes) == before
