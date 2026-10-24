"""UC-06 uses complete local scopes and fresh inventory, without executing writes."""

import copy
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from pydantic import ValidationError
from sqlalchemy import delete

from bot.app.web.admin_api_impl.auth import admin_auth_middleware
from bot.app.web.admin_console_resource_routes import setup_admin_console_resource_routes
from bot.app.web.admin_console_resource_schemas import (
    ConsoleResourcePreviewBody,
    ConsoleResourcePreviewOut,
    ResourceChange,
    ResourceSourceOut,
)
from bot.app.web.context import PANEL_SERVICE, SESSION_FACTORY, SETTINGS
from bot.app.web.route_contracts import get_contracts
from bot.app.web.webapp_auth import create_webapp_session_token
from bot.services.panel_api_service import PanelApiService
from bot.services.resource_preview import build_resource_preview as _build_resource_preview
from bot.services.resource_preview_authorizations import (
    PreviewAuthorizations,
    read_preview_authorizations,
)
from bot.services.resource_preview_panel import PreviewInventory, read_preview_inventory
from config.settings import Settings
from db.dal.admin_console_nodes_dal import ServiceResourceRow
from db.models import User
from db.service_models import DedicatedExit, ServiceConnection, UserService
from tests.unit.test_user_services import ServiceDatabaseTestCase, sample_terms


def uid(value: int) -> str:
    return str(UUID(int=value))


G1, G2, G3 = uid(1), uid(2), uid(3)
N1, N2, N3 = uid(101), uid(102), uid(103)
I1, I2, I3 = uid(201), uid(202), uid(203)
P1, P2 = uid(301), uid(302)
H1 = uid(401)
SECRET = "SECRET_MUST_NEVER_APPEAR"


def inventory_fixture() -> dict[str, object]:
    return {
        "/system/metadata": {"version": "3.4.5"},
        "/nodes": [
            {
                "uuid": node,
                "name": "Same name",
                "isDisabled": False,
                "configProfile": {
                    "activeConfigProfileUuid": profile,
                    "activeInbounds": [{"uuid": inbound} for inbound in inbounds],
                },
                "proxyUrl": SECRET,
                "usersOnline": 9,
            }
            for node, profile, inbounds in ((N1, P1, [I1, I2]), (N2, P1, [I2]), (N3, P2, [I3]))
        ],
        "/internal-squads": {
            "total": 3,
            "internalSquads": [
                {"uuid": group, "name": "Same group name", "inbounds": [{"uuid": inbound}]}
                for group, inbound in ((G1, I1), (G2, I2), (G3, I3))
            ],
        },
        "/hosts": [
            {
                "uuid": H1,
                "remark": "Host",
                "address": "192.0.2.1",
                "port": 443,
                "inbound": {"configProfileUuid": P1, "configProfileInboundUuid": I1},
                "nodes": [N1],
                "isDisabled": False,
                "isHidden": False,
                "internalSquads": {"mode": "EXCLUDE", "squads": []},
                "path": SECRET,
                "xhttpExtraParams": {"password": SECRET},
            }
        ],
        "/config-profiles": {
            "total": 2,
            "configProfiles": [
                {
                    "uuid": profile,
                    "name": "Profile",
                    "config": {"privateKey": SECRET},
                    "inbounds": [
                        {"uuid": inbound, "profileUuid": profile, "tag": "Same inbound tag"}
                        for inbound in inbounds
                    ],
                    "nodes": [{"uuid": node} for node in nodes],
                }
                for profile, inbounds, nodes in ((P1, [I1, I2], [N1, N2]), (P2, [I3], [N3]))
            ],
        },
    }


def fixture_rows() -> list[ServiceResourceRow]:
    now = datetime(2026, 10, 24, tzinfo=UTC)
    rows: list[ServiceResourceRow] = []
    for number, customer, group in ((1, 11, G1), (2, 11, G1), (3, 22, G2), (4, 33, G3)):
        service_id = f"{number:032x}"
        rows.append(
            (
                UserService(
                    id=service_id,
                    user_id=customer,
                    revision=1,
                    desired_status="active",
                    expires_at=now + timedelta(days=1),
                    terms=sample_terms(squad_uuids=[group]).model_dump(mode="json"),
                ),
                ServiceConnection(
                    service_id=service_id,
                    state="ready",
                    panel_user_uuid=str(number),
                    username=f"svc{number}",
                ),
                None,
                User(user_id=customer, is_banned=False),
            )
        )
    return rows


def panel_fixture(payloads: dict[str, object]) -> tuple[PanelApiService, AsyncMock]:
    panel = Mock(spec=PanelApiService)

    async def read(method: str, endpoint: str, **kwargs: object) -> dict[str, object]:
        assert method == "GET"
        assert kwargs["log_full_response"] is False
        result = payloads[endpoint]
        if isinstance(result, Exception):
            raise result
        return {"response": copy.deepcopy(result)}

    request = AsyncMock(side_effect=read)
    panel._request = request

    async def lookup(reference: str, log_response: bool = False) -> dict[str, object]:
        assert log_response is False
        override = payloads.get("identity:" + reference)
        if isinstance(override, Exception):
            raise override
        if isinstance(override, dict):
            return copy.deepcopy(override)
        number = int(reference)
        return {
            "ok": True,
            "not_found": False,
            "user": {
                "uuid": reference,
                "username": f"svc{number}",
                "description": f"my_vps_obj:service:{number:032x}",
                "activeInternalSquads": [
                    {"uuid": G1 if number <= 2 else G2 if number == 3 else G3}
                ],
                "subscriptionUrl": SECRET,
            },
        }

    panel.get_user_by_uuid_lookup = AsyncMock(side_effect=lookup)
    return cast(PanelApiService, panel), request


def build_resource_preview(
    change: ResourceChange,
    inventory: PreviewInventory,
    rows: list[ServiceResourceRow],
    *,
    local_available: bool = True,
) -> ConsoleResourcePreviewOut:
    scopes = PreviewAuthorizations(
        {
            row[0].id: {
                UUID(G1 if int(row[0].id, 16) <= 2 else G2 if int(row[0].id, 16) == 3 else G3)
            }
            for row in rows
        },
        ResourceSourceOut(
            source="authorizations", availability="available", observed_at=datetime.now(UTC)
        ),
    )
    return _build_resource_preview(
        change,
        inventory,
        rows,
        local_available=local_available,
        authorizations=scopes,
    )


def group_change() -> dict[str, object]:
    return {"operation": "group_inbounds", "target_id": G1, "inbound_ids": [I3]}


class ResourcePreviewTests(IsolatedAsyncioTestCase):
    async def test_observed_authorization_drift_is_included_and_fingerprinted(self) -> None:
        payloads = inventory_fixture()
        panel, _ = panel_fixture(payloads)
        rows = fixture_rows()
        change = ConsoleResourcePreviewBody.model_validate(
            {
                "change": {
                    "operation": "host_update",
                    "target_id": H1,
                    "patch": {"is_disabled": True},
                }
            }
        ).change
        inventory = await read_preview_inventory(panel)
        before = _build_resource_preview(
            change, inventory, rows, authorizations=await read_preview_authorizations(panel, rows)
        )
        payloads["identity:3"] = {
            "ok": True,
            "not_found": False,
            "user": {
                "uuid": "3",
                "username": "svc3",
                "description": f"my_vps_obj:service:{3:032x}",
                "activeInternalSquads": [G1],
                "subscriptionUrl": SECRET,
            },
        }
        after = _build_resource_preview(
            change, inventory, rows, authorizations=await read_preview_authorizations(panel, rows)
        )
        assert before.direct.customer_ids == [11]
        assert after.direct.customer_ids == [11, 22]
        assert after.fingerprint and after.fingerprint != before.fingerprint
        service = after.direct.services[-1]
        assert service.configured_group_ids == [G2] and service.observed_group_ids == [G1]
        assert service.group_ids == [G1, G2]
        assert SECRET not in after.model_dump_json()

    async def test_missing_or_foreign_remote_scope_is_not_accepted(self) -> None:
        for replacement in (
            RuntimeError(SECRET),
            {"ok": False, "not_found": False},
            {"ok": True, "user": {"uuid": "3", "username": "other"}},
            {
                "ok": True,
                "user": {
                    "uuid": "3",
                    "username": "svc3",
                    "description": f"my_vps_obj:service:{3:032x}",
                },
            },
        ):
            with self.subTest(replacement_type=type(replacement).__name__):
                payloads = inventory_fixture()
                payloads["identity:3"] = replacement
                panel, _ = panel_fixture(payloads)
                rows = fixture_rows()
                scopes = await read_preview_authorizations(panel, rows)
                change = ConsoleResourcePreviewBody.model_validate(
                    {"change": group_change()}
                ).change
                result = _build_resource_preview(
                    change, await read_preview_inventory(panel), rows, authorizations=scopes
                )
                assert result.fingerprint is None and not result.remote_authorization_verified
                assert "authorizations_unavailable" in result.blockers
                assert SECRET not in result.model_dump_json()

    async def test_confirmed_absence_is_different_from_unbound_unknown_create(self) -> None:
        payloads = inventory_fixture()
        payloads["identity:3"] = {"ok": False, "not_found": True, "user": None}
        panel, _ = panel_fixture(payloads)
        rows = fixture_rows()
        scopes = await read_preview_authorizations(panel, rows)
        assert scopes.source.availability == "available" and scopes.groups[rows[2][0].id] == set()
        connection = rows[0][1]
        assert connection is not None
        connection.panel_user_uuid = None
        connection.attempted_at = datetime.now(UTC)
        scopes = await read_preview_authorizations(panel, rows)
        assert scopes.source.availability == "unavailable"

    async def test_profile_config_changes_guard_but_live_node_traffic_does_not(self) -> None:
        payloads = inventory_fixture()
        panel, _ = panel_fixture(payloads)
        before = (await read_preview_inventory(panel)).fingerprint
        nodes = cast(list[dict[str, object]], payloads["/nodes"])
        nodes[0]["usersOnline"] = 123
        assert (await read_preview_inventory(panel)).fingerprint == before
        profiles = cast(dict[str, object], payloads["/config-profiles"])
        profile_rows = cast(list[dict[str, object]], profiles["configProfiles"])
        profile_rows[0]["config"] = {"privateKey": "changed-secret"}
        assert (await read_preview_inventory(panel)).fingerprint != before

    async def test_group_change_includes_both_profiles_and_other_groups(self) -> None:
        panel, request = panel_fixture(inventory_fixture())
        change = ConsoleResourcePreviewBody.model_validate({"change": group_change()}).change
        result = build_resource_preview(change, await read_preview_inventory(panel), fixture_rows())
        assert result.coverage == "complete" and result.fingerprint
        assert result.current and result.current.inbound_ids == [I1]
        assert result.proposed and result.proposed.inbound_ids == [I3]
        assert result.direct.group_ids == [G1]
        assert result.direct.service_total == 2 and result.direct.customer_ids == [11]
        assert result.possible_reload.group_ids == [G2, G3]
        assert result.possible_reload.node_ids == [N1, N2, N3]
        assert result.possible_reload.profile_ids == [P1, P2]
        assert result.possible_reload.customer_ids == [22, 33]
        assert result.affected_customer_ids == [11, 22, 33]
        assert len(result.affected_service_ids) == 4
        assert SECRET not in result.model_dump_json()
        assert not result.execution_available and result.remote_authorization_verified
        assert request.await_count == 5

    async def test_dedicated_disabled_unverified_bound_resource_is_still_potential_impact(
        self,
    ) -> None:
        rows = fixture_rows()
        service, connection, _, user = rows[2]
        service.terms = sample_terms(
            resource_type="dedicated", squad_uuids=[], resource_pool="private"
        ).model_dump(mode="json")
        resource = DedicatedExit(
            id="e" * 32,
            service_id=service.id,
            revision=3,
            squad_uuid=G2,
            enabled=False,
            verified_at=None,
            resource_pool="private",
        )
        rows[2] = service, connection, resource, user
        panel, _ = panel_fixture(inventory_fixture())
        change = ConsoleResourcePreviewBody.model_validate({"change": group_change()}).change
        result = build_resource_preview(change, await read_preview_inventory(panel), rows)
        assert result.fingerprint
        assert result.possible_reload.services[0].service_id == service.id

    async def test_reclaimed_exit_requires_revocation_and_fresh_empty_remote_scope(self) -> None:
        rows = fixture_rows()
        service, connection, _, _ = rows[2]
        assert connection is not None
        service.terms = sample_terms(
            resource_type="dedicated", squad_uuids=[], resource_pool="private"
        ).model_dump(mode="json")
        payloads = inventory_fixture()
        panel, _ = panel_fixture(payloads)
        inventory = await read_preview_inventory(panel)
        change = ConsoleResourcePreviewBody.model_validate({"change": group_change()}).change
        for state, absent, blocked in (
            ("ready", True, True),
            ("revoked", False, True),
            ("revoked", True, False),
        ):
            with self.subTest(state=state, absent=absent):
                connection.state = state
                if absent:
                    payloads["identity:3"] = {"ok": False, "not_found": True}
                else:
                    payloads.pop("identity:3", None)
                result = _build_resource_preview(
                    change,
                    inventory,
                    rows,
                    authorizations=await read_preview_authorizations(panel, rows),
                )
                assert ("missing_dedicated_binding" in result.blockers) is blocked
                assert (result.fingerprint is None) is blocked
                if not blocked:
                    assert service.id not in result.affected_service_ids

    async def test_host_union_covers_old_new_filters_and_no_node_reload(self) -> None:
        panel, _ = panel_fixture(inventory_fixture())
        change = ConsoleResourcePreviewBody.model_validate(
            {
                "change": {
                    "operation": "host_update",
                    "target_id": H1,
                    "patch": {
                        "profile_id": P2,
                        "inbound_id": I3,
                        "node_ids": [N3],
                        "group_mode": "ALLOW_ONLY",
                        "group_ids": [G3],
                        "is_hidden": True,
                        "address": "vpn.example.test",
                        "port": 8443,
                    },
                }
            }
        ).change
        result = build_resource_preview(change, await read_preview_inventory(panel), fixture_rows())
        assert result.fingerprint
        assert result.direct.group_ids == [G1, G3]
        assert result.direct.node_ids == [N1, N3]
        assert result.direct.customer_ids == [11, 33]
        assert result.possible_reload.service_total == 0
        assert result.current and result.current.address == "192.0.2.1"
        assert result.proposed and result.proposed.port == 8443
        assert result.proposed.is_hidden is True

    async def test_node_actions_cover_all_authorized_groups_on_target_only(self) -> None:
        for operation in ("node_enable", "node_disable", "node_restart"):
            with self.subTest(operation=operation):
                panel, _ = panel_fixture(inventory_fixture())
                change = ConsoleResourcePreviewBody.model_validate(
                    {
                        "change": {
                            "operation": operation,
                            "target_id": N1,
                        }
                    }
                ).change
                result = build_resource_preview(
                    change, await read_preview_inventory(panel), fixture_rows()
                )
                assert result.fingerprint
                assert result.direct.group_ids == [G1, G2]
                assert result.direct.node_ids == [N1]
                assert result.possible_reload.service_total == 0

    async def test_disabled_node_restart_and_unconfigured_enable_are_blocked(self) -> None:
        panel, _ = panel_fixture(inventory_fixture())
        inventory = await read_preview_inventory(panel)
        inventory.nodes.rows[0].isDisabled = True
        change = ConsoleResourcePreviewBody.model_validate(
            {
                "change": {
                    "operation": "node_restart",
                    "target_id": N1,
                }
            }
        ).change
        result = build_resource_preview(change, inventory, fixture_rows())
        assert "node_disabled" in result.blockers and result.fingerprint is None
        change = ConsoleResourcePreviewBody.model_validate(
            {
                "change": {
                    "operation": "node_enable",
                    "target_id": N1,
                }
            }
        ).change
        inventory.nodes.rows[0].configProfile.activeConfigProfileUuid = None
        inventory.nodes.rows[0].configProfile.activeInbounds = []
        result = build_resource_preview(change, inventory, fixture_rows())
        assert "node_has_no_active_inbounds" in result.blockers

    async def test_partial_missing_duplicate_unsupported_and_secret_failures_block(self) -> None:
        for endpoint, replacement in (
            ("/system/metadata", {"version": "3.4.6"}),
            ("/nodes", [{"uuid": N1, "name": "Missing configuration"}]),
            ("/hosts", [{"uuid": H1}]),
            ("/config-profiles", {"total": 1, "configProfiles": []}),
            (
                "/internal-squads",
                {
                    "total": 2,
                    "internalSquads": [
                        {"uuid": G1, "name": "Repeated", "inbounds": []},
                        {"uuid": G1, "name": "Repeated", "inbounds": []},
                    ],
                },
            ),
            ("/nodes", RuntimeError(SECRET)),
        ):
            with self.subTest(endpoint=endpoint):
                payloads = inventory_fixture()
                payloads[endpoint] = replacement
                panel, _ = panel_fixture(payloads)
                change = ConsoleResourcePreviewBody.model_validate(
                    {"change": group_change()}
                ).change
                result = build_resource_preview(
                    change, await read_preview_inventory(panel), fixture_rows()
                )
                assert result.fingerprint is None and result.coverage == "partial"
                assert result.blockers and SECRET not in result.model_dump_json()

    async def test_unknown_ids_invalid_local_scope_and_inconsistent_topology_block(self) -> None:
        panel, _ = panel_fixture(inventory_fixture())
        inventory = await read_preview_inventory(panel)
        change = ConsoleResourcePreviewBody.model_validate({"change": group_change()}).change
        inventory.nodes.rows[0].configProfile.activeInbounds[0].uuid = UUID(int=999)
        rows = fixture_rows()
        rows[0][0].terms = {}
        result = build_resource_preview(change, inventory, rows)
        assert "missing_node_inbound" in result.blockers
        assert "invalid_service_scope" in result.blockers
        assert result.fingerprint is None

    async def test_no_sources_never_looks_like_empty_complete_impact(self) -> None:
        change = ConsoleResourcePreviewBody.model_validate({"change": group_change()}).change
        result = build_resource_preview(
            change, await read_preview_inventory(None), [], local_available=False
        )
        assert result.coverage == "partial" and result.fingerprint is None
        assert "services_unavailable" in result.blockers


@pytest.mark.parametrize(
    "change",
    [
        {"operation": "node_restart_all", "target_id": N1},
        {"operation": "node_restart", "target_id": "name"},
        {"operation": "node_disable", "target_id": N1, "force_restart": True},
        {"operation": "group_inbounds", "target_id": G1, "inbound_ids": [I1, I1]},
        {"operation": "host_update", "target_id": H1, "patch": {}},
        {"operation": "host_update", "target_id": H1, "patch": {"is_disabled": None}},
        {"operation": "host_update", "target_id": H1, "patch": {"is_disabled": "false"}},
        {"operation": "host_update", "target_id": H1, "patch": {"inbound_id": I1}},
        {"operation": "host_update", "target_id": H1, "patch": {"group_ids": []}},
        {"operation": "host_update", "target_id": H1, "patch": {"node_ids": [N1, N1]}},
        {"operation": "host_update", "target_id": H1, "patch": {"config": {"privateKey": SECRET}}},
        {
            "operation": "host_update",
            "target_id": H1,
            "patch": {"address": "https://user:secret@host"},
        },
        {"operation": "host_update", "target_id": H1, "patch": {"port": True}},
    ],
)
def test_reject_unsupported_ambiguous_or_sensitive_proposals(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ConsoleResourcePreviewBody.model_validate({"change": change})


@pytest.mark.filterwarnings(
    "ignore:It is recommended to use web.RequestKey: aiohttp.web_exceptions.NotAppKeyWarning"
)
class ResourcePreviewRouteTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.payloads = inventory_fixture()
        self.panel, self.panel_request = panel_fixture(self.payloads)
        self.rows = fixture_rows()
        self.authorized = True
        settings = Settings(
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            BOT_TOKEN="1234567890:AA_test_token_value",
            _env_file=None,
        )

        @web.middleware
        async def roles(
            request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
        ) -> web.StreamResponse:
            request["admin_authorized"] = self.authorized
            return await handler(request)

        app = web.Application(middlewares=[roles])
        app[SETTINGS] = settings
        app[PANEL_SERVICE] = self.panel
        setup_admin_console_resource_routes(app)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer " + create_webapp_session_token(settings, 1)}
        self.read_services = AsyncMock(side_effect=lambda _: (self.rows, False))
        patcher = patch(
            "bot.app.web.admin_console_resource_routes._read_services", self.read_services
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_preview_contract_permissions_no_cache_and_no_execute(self) -> None:
        for path in ("preview", "revalidate"):
            response = await self.client.post(f"/api/admin/console/resources/{path}", json={})
            assert response.status == 401
            self.authorized = False
            response = await self.client.post(
                f"/api/admin/console/resources/{path}", json={}, headers=self.headers
            )
            assert response.status == 403
        self.panel_request.assert_not_awaited()
        self.read_services.assert_not_awaited()
        self.authorized = True
        response = await self.client.post(
            "/api/admin/console/resources/preview",
            json={"change": group_change()},
            headers=self.headers,
        )
        assert response.status == 200
        assert response.headers["Cache-Control"] == "private, no-store"
        body = await response.json()
        assert body["ok"] and body["fingerprint"] and not body["execution_available"]
        assert SECRET not in json.dumps(body)
        assert self.panel_request.await_count == 10
        self.authorized = False
        response = await self.client.post(
            "/api/admin/console/resources/preview",
            json={"change": group_change()},
            headers=self.headers,
        )
        assert response.status == 403 and self.panel_request.await_count == 10
        assert (await self.client.post("/api/admin/console/resources/execute")).status == 404
        for name in (
            "admin_console_resource_preview_route",
            "admin_console_resource_revalidate_route",
        ):
            assert get_contracts()[name].request_model is not None

    async def test_revalidation_changed_scope_proposal_and_partial_read_never_valid(self) -> None:
        response = await self.client.post(
            "/api/admin/console/resources/preview",
            json={"change": group_change()},
            headers=self.headers,
        )
        fingerprint = (await response.json())["fingerprint"]
        payload = {"change": group_change(), "expected_fingerprint": fingerprint}
        response = await self.client.post(
            "/api/admin/console/resources/revalidate", json=payload, headers=self.headers
        )
        assert (await response.json())["valid"] is True
        self.rows[0][0].revision += 1
        response = await self.client.post(
            "/api/admin/console/resources/revalidate", json=payload, headers=self.headers
        )
        body = await response.json()
        assert body["ok"] and not body["valid"] and body["reason"] == "changed"
        self.rows[0][0].revision -= 1
        payload["change"] = {"operation": "group_inbounds", "target_id": G1, "inbound_ids": []}
        response = await self.client.post(
            "/api/admin/console/resources/revalidate", json=payload, headers=self.headers
        )
        assert (await response.json())["reason"] == "changed"
        self.payloads["/hosts"] = RuntimeError(SECRET)
        response = await self.client.post(
            "/api/admin/console/resources/revalidate", json=payload, headers=self.headers
        )
        body = await response.json()
        assert not body["valid"] and body["reason"] == "incomplete"
        assert body["preview"]["fingerprint"] is None and SECRET not in json.dumps(body)

    async def test_mid_read_change_and_local_failure_invalidate_snapshot(self) -> None:
        calls = 0

        async def changing(_: web.Request) -> tuple[list[ServiceResourceRow], bool]:
            nonlocal calls
            calls += 1
            self.rows[0][0].revision = calls
            return self.rows, False

        self.read_services.side_effect = changing
        response = await self.client.post(
            "/api/admin/console/resources/preview",
            json={"change": group_change()},
            headers=self.headers,
        )
        body = await response.json()
        assert body["fingerprint"] is None
        assert "sources_changed_during_read" in body["blockers"]
        self.read_services.side_effect = RuntimeError(SECRET)
        response = await self.client.post(
            "/api/admin/console/resources/preview",
            json={"change": group_change()},
            headers=self.headers,
        )
        body = await response.json()
        assert body["fingerprint"] is None and "services_unavailable" in body["blockers"]
        assert SECRET not in json.dumps(body)

    async def test_malformed_proposals_do_not_read_sources_or_reflect_secrets(self) -> None:
        response = await self.client.post(
            "/api/admin/console/resources/preview",
            json={"change": {"operation": SECRET}},
            headers=self.headers,
        )
        assert response.status == 400 and SECRET not in await response.text()
        self.panel_request.assert_not_awaited()
        self.read_services.assert_not_awaited()


class ResourcePreviewArchiveTests(ServiceDatabaseTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.revoked_at = datetime.now(UTC)
        services = [
            UserService(
                id=service_id,
                user_id=owner,
                plan_id=self.plan.id,
                plan_revision=1,
                revision=1,
                terms=sample_terms().model_dump(mode="json"),
                quota_bytes=10_000,
                used_bytes=0,
                starts_at=self.revoked_at,
                expires_at=self.revoked_at + timedelta(days=90),
                desired_status="active" if owner is not None else "cancelled",
                created_at=self.revoked_at,
            )
            for service_id, owner in (("a" * 32, 1), ("b" * 32, None))
        ]
        self.current, self.archived = services
        async with self.sessions.begin() as session:
            session.add_all(services)
            await session.flush()
            session.add_all(
                [
                    ServiceConnection(
                        service_id=self.current.id, username="current", state="pending"
                    ),
                    ServiceConnection(
                        service_id=self.archived.id,
                        username="archive",
                        state="revoked",
                        revoked_at=self.revoked_at,
                        panel_user_uuid="historical-identity",
                    ),
                ]
            )
        settings = Settings(
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            BOT_TOKEN="1234567890:AA_test_token_value",
            _env_file=None,
        )
        panel, _ = panel_fixture(inventory_fixture())
        app = web.Application(middlewares=[admin_auth_middleware])
        app[SETTINGS], app[SESSION_FACTORY], app[PANEL_SERVICE] = settings, self.sessions, panel
        setup_admin_console_resource_routes(app)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer " + create_webapp_session_token(settings, 1)}

    async def test_confirmed_archive_does_not_block_or_invent_customer(self) -> None:
        response = await self.client.post(
            "/api/admin/console/resources/preview",
            json={"change": group_change()},
            headers=self.headers,
        )
        assert response.status == 200
        body = ConsoleResourcePreviewOut.model_validate(await response.json())
        assert body.coverage == "complete" and body.fingerprint
        assert body.affected_service_ids == [self.current.id]
        assert body.affected_customer_ids == [1]
        assert self.archived.id not in body.model_dump_json()

    async def test_unfinished_archives_invalidate_old_preview(self) -> None:
        response = await self.client.post(
            "/api/admin/console/resources/preview",
            json={"change": group_change()},
            headers=self.headers,
        )
        fingerprint = (await response.json())["fingerprint"]
        assert fingerprint
        for state, has_evidence, sync_pending, desired in (
            ("ready", True, False, "cancelled"),
            ("error", False, False, "cancelled"),
            ("revoked", False, False, "cancelled"),
            ("revoked", True, True, "cancelled"),
            ("revoked", True, False, "active"),
        ):
            with self.subTest(
                state=state, has_evidence=has_evidence, sync_pending=sync_pending, desired=desired
            ):
                async with self.sessions.begin() as session:
                    service = await session.get(UserService, self.archived.id)
                    connection = await session.get(ServiceConnection, self.archived.id)
                    assert service and connection
                    service.desired_status = desired
                    connection.state = state
                    connection.revoked_at = self.revoked_at if has_evidence else None
                    connection.sync_pending = sync_pending
                response = await self.client.post(
                    "/api/admin/console/resources/revalidate",
                    json={"change": group_change(), "expected_fingerprint": fingerprint},
                    headers=self.headers,
                )
                assert response.status == 200
                body = await response.json()
                assert body["valid"] is False and body["reason"] == "incomplete"
                preview = ConsoleResourcePreviewOut.model_validate(body["preview"])
                assert preview.coverage == "partial" and preview.fingerprint is None
                assert "archived_resource_scope_unconfirmed" in preview.blockers
                assert not preview.remote_authorization_verified
                assert preview.affected_customer_ids == [1]
                assert preview.affected_service_ids == [self.current.id]
                assert (
                    next(s for s in preview.sources if s.source == "services").availability
                    == "invalid"
                )

    async def test_archived_disabled_exit_binding_cannot_disappear(self) -> None:
        async with self.sessions.begin() as session:
            session.add(
                DedicatedExit(
                    id="e" * 32,
                    label="Archived exit",
                    ip_address="192.0.2.10",
                    resource_pool="private",
                    squad_uuid=G2,
                    service_id=self.archived.id,
                    enabled=False,
                    verified_at=None,
                    created_at=datetime.now(UTC),
                )
            )
        response = await self.client.post(
            "/api/admin/console/resources/preview",
            json={"change": group_change()},
            headers=self.headers,
        )
        assert response.status == 200
        body = await response.json()
        assert body["fingerprint"] is None and body["coverage"] == "partial"
        assert "archived_resource_scope_unconfirmed" in body["blockers"]

    async def test_missing_archived_connection_invalidates_old_preview(self) -> None:
        response = await self.client.post(
            "/api/admin/console/resources/preview",
            json={"change": group_change()},
            headers=self.headers,
        )
        fingerprint = (await response.json())["fingerprint"]
        assert fingerprint
        async with self.sessions.begin() as session:
            await session.execute(
                delete(ServiceConnection).where(ServiceConnection.service_id == self.archived.id)
            )
        response = await self.client.post(
            "/api/admin/console/resources/revalidate",
            json={"change": group_change(), "expected_fingerprint": fingerprint},
            headers=self.headers,
        )
        assert response.status == 200
        body = await response.json()
        assert not body["valid"] and body["reason"] == "incomplete"
        assert body["preview"]["fingerprint"] is None
        assert "archived_resource_scope_unconfirmed" in body["preview"]["blockers"]
