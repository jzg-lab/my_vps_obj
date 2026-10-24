"""Inventory is not a ranking; entitlement scope is not a live connection."""

import asyncio
import copy
import time
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import delete, func, select

from bot.app.web.admin_api_impl.auth import admin_auth_middleware
from bot.app.web.admin_console_nodes_panel import NodeInventoryReader
from bot.app.web.admin_console_nodes_routes import setup_admin_console_nodes_routes
from bot.app.web.context import PANEL_SERVICE, SESSION_FACTORY, SETTINGS
from bot.app.web.webapp_auth import create_webapp_session_token
from bot.services.panel_api_service import PanelApiService
from config.service_exit_replacement import ReplacementProgress, ReplacementRequest
from config.settings import Settings
from db.auth_models import AccountRole
from db.dal.user_services_dal import save_plan
from db.service_models import (
    DedicatedExit,
    ServiceConnection,
    ServiceOperationExecution,
    ServiceOrder,
    UserService,
)
from tests.unit.test_user_services import ServiceDatabaseTestCase, sample_terms

GROUP = str(UUID(int=1))
OTHER_GROUP = str(UUID(int=2))
NODE = str(UUID(int=101))
OTHER_NODE = str(UUID(int=102))
INBOUND = str(UUID(int=201))
OTHER_INBOUND = str(UUID(int=202))
HOST = str(UUID(int=401))
OTHER_HOST = str(UUID(int=402))


def panel_responses() -> dict[str, object]:
    return {
        "/nodes": [
            {
                "uuid": NODE,
                "name": "Same name",
                "address": "192.0.2.1",
                "countryCode": "US",
                "isConnected": True,
                "isDisabled": False,
                "isConnecting": False,
                "usersOnline": 9,
                "isTrafficTrackingActive": True,
                "trafficUsedBytes": 0,
                "trafficResetDay": 1,
                "lastStatusChange": "2026-10-23T01:00:00Z",
                "configProfile": {
                    "activeConfigProfileUuid": str(UUID(int=301)),
                    "activeInbounds": [{"uuid": INBOUND, "rawInbound": {"secret": "NEVER_EXPOSE"}}],
                },
                "proxyUrl": "https://NEVER_EXPOSE:secret@example.test",
                "note": "NEVER_EXPOSE",
            },
            {
                "uuid": OTHER_NODE,
                "name": "Same name",
                "address": "192.0.2.2",
                "configProfile": {"activeInbounds": [{"uuid": OTHER_INBOUND}]},
            },
        ],
        "/internal-squads": {
            "internalSquads": [
                {"uuid": GROUP, "name": "Shared group", "inbounds": [{"uuid": INBOUND}]},
                {"uuid": OTHER_GROUP, "name": "Other group", "inbounds": [{"uuid": OTHER_INBOUND}]},
            ]
        },
        "/hosts": [
            {
                "uuid": HOST,
                "remark": "First route",
                "address": "NEVER_EXPOSE",
                "inbound": {"configProfileInboundUuid": INBOUND},
                "nodes": [NODE],
                "isDisabled": False,
                "isHidden": False,
                "internalSquads": {"mode": "EXCLUDE", "squads": []},
            },
            {
                "uuid": OTHER_HOST,
                "remark": "Second route",
                "inbound": {"configProfileInboundUuid": OTHER_INBOUND},
                "nodes": [],
                "isDisabled": False,
                "isHidden": False,
                "excludedInternalSquads": [],
            },
        ],
    }


def panel_fixture(responses: dict[str, object]) -> tuple[PanelApiService, AsyncMock]:
    panel = Mock(spec=PanelApiService)

    async def read(method: str, endpoint: str, **kwargs: object) -> dict[str, object]:
        assert method == "GET"
        assert kwargs["log_full_response"] is False
        assert endpoint in ("/nodes", "/hosts", "/internal-squads")
        body = responses[endpoint]
        if isinstance(body, Exception):
            raise body
        if isinstance(body, dict) and body.get("error"):
            return body
        return {"response": copy.deepcopy(body)}

    request = AsyncMock(side_effect=read)
    panel._request = request
    return cast(PanelApiService, panel), request


@pytest.mark.filterwarnings(
    "ignore:It is recommended to use web.RequestKey: aiohttp.web_exceptions.NotAppKeyWarning"
)
class AdminConsoleNodesTests(ServiceDatabaseTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.responses = panel_responses()
        self.panel, self.panel_request = panel_fixture(self.responses)
        self.settings = Settings(
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            BOT_TOKEN="1234567890:AA_secret_bot_token_value",
            ADMIN_PANEL_STATS_CACHE_TTL_SECONDS=0,
            _env_file=None,
        )
        app = web.Application(middlewares=[admin_auth_middleware])
        app[SETTINGS] = self.settings
        app[SESSION_FACTORY] = self.sessions
        app[PANEL_SERVICE] = self.panel
        setup_admin_console_nodes_routes(app)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.admin = {"Authorization": "Bearer " + create_webapp_session_token(self.settings, 1)}

    async def test_permissions_and_role_revocation_are_checked_before_cached_reads(self) -> None:
        service, _, _ = await self.activate()
        paths = [
            "/api/admin/console/nodes",
            f"/api/admin/console/nodes/{NODE}",
            f"/api/admin/console/services/{service.id}/resources",
        ]
        for path in paths:
            assert (await self.client.get(path)).status == 401
            for user_id in (2, 3):
                headers = {
                    "Authorization": "Bearer " + create_webapp_session_token(self.settings, user_id)
                }
                assert (await self.client.get(path, headers=headers)).status == 403
        self.panel_request.assert_not_awaited()
        self.settings.ADMIN_PANEL_STATS_CACHE_TTL_SECONDS = 60
        for path in paths:
            response = await self.client.get(path, headers=self.admin)
            assert response.status == 200
            assert response.headers.get("Cache-Control") == "private, no-store"
        requests = self.panel_request.await_count
        async with self.sessions.begin() as session:
            await session.execute(delete(AccountRole).where(AccountRole.user_id == 1))
        for path in paths:
            assert (await self.client.get(path, headers=self.admin)).status == 403
        assert self.panel_request.await_count == requests

    async def test_inventory_pagination_and_metrics_preserve_zero_and_unknown(self) -> None:
        response = await self.client.get(
            "/api/admin/console/nodes?page_size=1&page=1", headers=self.admin
        )
        assert response.status == 200
        body = await response.json()
        assert body["ok"] and body["total"] == 2 and len(body["nodes"]) == 1
        assert body["coverage"] == "complete"
        node = body["nodes"][0]
        assert node["id"] == OTHER_NODE and node["status"] == "unknown"
        assert node["users_online"] is None and node["traffic_used_bytes"] is None
        assert node["country_code"] is None
        response = await self.client.get(
            "/api/admin/console/nodes?status=online", headers=self.admin
        )
        body = await response.json()
        assert body["total"] == 1
        node = body["nodes"][0]
        assert node["id"] == NODE and node["users_online"] == 9 and node["traffic_used_bytes"] == 0
        assert node["groups"] == [{"id": GROUP, "name": "Shared group"}]
        assert "identities_not_unique_customers" in node["online_scope"]
        assert all(item["last_success_at"] for item in body["sources"])
        assert "NEVER_EXPOSE" not in await response.text()
        response = await self.client.get("/api/admin/console/nodes?q=192.0.2.2", headers=self.admin)
        assert (await response.json())["total"] == 1
        for query in (
            "page=-1",
            "page_size=201",
            "status=unmanaged",
            "sort=traffic",
            "q=" + "a" * 201,
        ):
            assert (
                await self.client.get("/api/admin/console/nodes?" + query, headers=self.admin)
            ).status == 400

    async def test_bidirectional_scope_uses_uuids_and_deduplicates_customers_across_pages(
        self,
    ) -> None:
        first, _, _ = await self.activate()
        await self.activate("second")
        await self.activate("third", user_id=2)
        revoked, _, _ = await self.activate("revoked")
        archived, _, _ = await self.activate("archived")
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, revoked.id)
            assert connection
            connection.state = "revoked"
            service = await session.get(UserService, archived.id)
            assert service
            service.user_id = None
            await save_plan(
                session, terms=sample_terms(squad_uuids=[OTHER_GROUP]), enabled=True, actor_id=1
            )
        response = await self.client.get(
            f"/api/admin/console/nodes/{NODE}?page_size=1&page=1", headers=self.admin
        )
        assert response.status == 200
        body = await response.json()
        assert body["service_total"] == 3 and body["customer_total"] == 2
        assert len(body["services"]) == 1 and body["associations_complete"]
        assert body["current_connections"] is None
        assert body["services"][0]["status"] == "pending"
        assert not body["services"][0]["currently_eligible"]
        assert body["hosts"][0]["id"] == HOST
        assert "NEVER_EXPOSE" not in await response.text()
        response = await self.client.get(
            f"/api/admin/console/services/{first.id}/resources", headers=self.admin
        )
        body = await response.json()
        assert body["configured_group_ids"] == [GROUP]
        assert [node["id"] for node in body["nodes"]] == [NODE]
        assert [host["id"] for host in body["hosts"]] == [HOST]
        assert not body["remote_authorization_verified"]
        assert body["association_basis"] == "persisted_service_scope_not_live_connections"
        other = await self.client.get(f"/api/admin/console/nodes/{OTHER_NODE}", headers=self.admin)
        assert (await other.json())["service_total"] == 0
        async with self.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(ServiceOrder)) == 5

    async def test_dedicated_scope_requires_verified_enabled_matching_resource(self) -> None:
        service, _, _ = await self.activate()
        async with self.sessions.begin() as session:
            saved = await session.get(UserService, service.id)
            assert saved
            saved.terms = sample_terms(
                resource_type="dedicated", squad_uuids=[], resource_pool="private"
            ).model_dump(mode="json")
            session.add(
                DedicatedExit(
                    id="e" * 32,
                    revision=1,
                    label="Private",
                    ip_address="192.0.2.99",
                    resource_pool="private",
                    squad_uuid=GROUP,
                    service_id=service.id,
                    enabled=True,
                    created_at=datetime.now(UTC),
                )
            )
        path = f"/api/admin/console/services/{service.id}/resources"
        body = await (await self.client.get(path, headers=self.admin)).json()
        assert body["configured_group_ids"] == [] and body["nodes"] == []
        async with self.sessions.begin() as session:
            resource = await session.get(DedicatedExit, "e" * 32)
            assert resource
            resource.verified_at = datetime.now(UTC)
        body = await (await self.client.get(path, headers=self.admin)).json()
        assert body["configured_group_ids"] == [GROUP]
        for change in ("disabled", "wrong_pool"):
            async with self.sessions.begin() as session:
                resource = await session.get(DedicatedExit, "e" * 32)
                assert resource
                resource.enabled = change != "disabled"
                resource.resource_pool = "other" if change == "wrong_pool" else "private"
            body = await (await self.client.get(path, headers=self.admin)).json()
            assert body["configured_group_ids"] == []

    async def test_business_status_does_not_become_connected_from_scope(self) -> None:
        service, _, _ = await self.activate()
        path = f"/api/admin/console/services/{service.id}/resources"
        for desired, expired, expected in (
            ("paused", False, "paused"),
            ("active", True, "expired"),
            ("cancelled", False, "cancelled"),
        ):
            async with self.sessions.begin() as session:
                saved = await session.get(UserService, service.id)
                assert saved
                saved.desired_status = desired
                saved.expires_at = datetime.now(UTC) + timedelta(days=-1 if expired else 10)
                saved.starts_at = datetime.now(UTC) - timedelta(days=2)
            body = await (await self.client.get(path, headers=self.admin)).json()
            assert body["status"] == expected and not body["currently_eligible"]
            assert [node["id"] for node in body["nodes"]] == [NODE]

    async def test_replacement_hold_scope_survives_http_projection_and_pagination(self) -> None:
        service, _, _ = await self.activate("replacement-impact", user_id=2)
        unrelated, _, _ = await self.activate("unrelated-scope")
        unrelated_group, unrelated_node, unrelated_inbound = (
            str(UUID(int=value)) for value in (3, 103, 203)
        )
        cast(list[dict[str, object]], self.responses["/nodes"]).append(
            {
                "uuid": unrelated_node,
                "name": "Unrelated node",
                "configProfile": {"activeInbounds": [{"uuid": unrelated_inbound}]},
            }
        )
        squads = cast(dict[str, list[dict[str, object]]], self.responses["/internal-squads"])
        squads["internalSquads"].append(
            {
                "uuid": unrelated_group,
                "name": "Unrelated group",
                "inbounds": [{"uuid": unrelated_inbound}],
            }
        )
        now = datetime.now(UTC)
        old_id, candidate_id, order_id = "a" * 32, "b" * 32, "c" * 32
        async with self.sessions.begin() as session:
            saved = await session.get(UserService, service.id)
            other = await session.get(UserService, unrelated.id)
            connection = await session.get(ServiceConnection, service.id)
            assert saved and other and connection
            saved.terms = sample_terms(
                resource_type="dedicated", squad_uuids=[], resource_pool="private"
            ).model_dump(mode="json")
            other.terms = sample_terms(squad_uuids=[unrelated_group]).model_dump(mode="json")
            order = ServiceOrder(
                id=order_id,
                service_id=service.id,
                user_id=2,
                request_owner_id=2,
                actor_id=1,
                kind="replace_exit",
                idempotency_key="hold-impact",
                request={
                    "replacement": ReplacementRequest(
                        expected_revision=saved.revision,
                        old_exit_id=old_id,
                        new_exit_id=candidate_id,
                        expected_old_exit_revision=1,
                        expected_new_exit_revision=1,
                        resource_fingerprint="f" * 64,
                        reason="NEVER_EXPOSE",
                    ).model_dump(mode="json")
                },
                snapshot={},
                created_at=now,
            )
            session.add(order)
            await session.flush()
            for exit_id, group, current in (
                (old_id, GROUP, True),
                (candidate_id, OTHER_GROUP, False),
            ):
                session.add(
                    DedicatedExit(
                        id=exit_id,
                        revision=1,
                        label="Current" if current else "Candidate",
                        ip_address="192.0.2.10" if current else "192.0.2.11",
                        resource_pool="private",
                        squad_uuid=group,
                        service_id=service.id if current else None,
                        hold_order_id=None if current else order_id,
                        enabled=current,
                        verified_at=now if current else None,
                        created_at=now,
                    )
                )
            connection.replacement_order_id = order_id
            session.add(
                ServiceOperationExecution(
                    id="d" * 32,
                    service_id=service.id,
                    order_id=order_id,
                    request_owner_id=2,
                    phase="exit_replace",
                    target_revision=saved.revision,
                    source="administrator",
                    actor_id=1,
                    status="pending",
                    attempt_count=0,
                    replacement_progress=ReplacementProgress().model_dump(mode="json"),
                    created_at=now,
                )
            )

        for stage, held_node, current_group, current_node in (
            ("candidate", OTHER_NODE, GROUP, NODE),
            ("retained", NODE, OTHER_GROUP, OTHER_NODE),
            ("archived", NODE, OTHER_GROUP, OTHER_NODE),
        ):
            with self.subTest(stage=stage):
                if stage == "retained":
                    async with self.sessions.begin() as session:
                        old = await session.get(DedicatedExit, old_id)
                        candidate = await session.get(DedicatedExit, candidate_id)
                        connection = await session.get(ServiceConnection, service.id)
                        execution = await session.get(ServiceOperationExecution, "d" * 32)
                        assert old and candidate and connection and execution
                        old.service_id = None
                        old.hold_order_id = order_id
                        await session.flush()
                        candidate.hold_order_id = None
                        candidate.service_id = service.id
                        candidate.enabled = True
                        candidate.verified_at = now
                        connection.replacement_order_id = None
                        execution.status = "succeeded"
                elif stage == "archived":
                    async with self.sessions.begin() as session:
                        saved = await session.get(UserService, service.id)
                        assert saved
                        saved.user_id = None

                for page in (0, 1):
                    response = await self.client.get(
                        f"/api/admin/console/nodes/{held_node}?page_size=1&page={page}",
                        headers=self.admin,
                    )
                    assert response.status == 200
                    assert response.headers.get("Cache-Control") == "private, no-store"
                    body = await response.json()
                    assert body["coverage"] == "partial"
                    assert body["associations_complete"] is False
                    assert body["service_total"] is None and body["customer_total"] is None
                    assert body["current_connections"] is None
                    assert all(source["availability"] == "available" for source in body["sources"])
                    assert "NEVER_EXPOSE" not in await response.text()
                    if page == 0 and stage != "archived":
                        assert [(item["id"], item["user_id"]) for item in body["services"]] == [
                            (service.id, 2)
                        ]
                    else:
                        assert body["services"] == []

                if stage != "archived":
                    response = await self.client.get(
                        f"/api/admin/console/services/{service.id}/resources", headers=self.admin
                    )
                    assert response.status == 200
                    body = await response.json()
                    assert body["coverage"] == "partial"
                    assert body["configured_group_ids"] == [current_group]
                    assert [node["id"] for node in body["nodes"]] == [current_node]
                    assert body["remote_authorization_verified"] is False

                response = await self.client.get(
                    f"/api/admin/console/nodes/{unrelated_node}", headers=self.admin
                )
                assert response.status == 200
                body = await response.json()
                assert body["coverage"] == "complete" and body["associations_complete"] is True
                assert body["service_total"] == 1 and body["customer_total"] == 1
                assert [(item["id"], item["user_id"]) for item in body["services"]] == [
                    (unrelated.id, 1)
                ]
                response = await self.client.get(
                    f"/api/admin/console/services/{unrelated.id}/resources", headers=self.admin
                )
                assert response.status == 200
                assert (await response.json())["coverage"] == "complete"

        # An unlocatable archived hold cannot certify any node's impact as empty.
        async with self.sessions.begin() as session:
            old = await session.get(DedicatedExit, old_id)
            assert old
            old.squad_uuid = "invalid-group"
        response = await self.client.get(f"/api/admin/console/nodes/{NODE}", headers=self.admin)
        assert response.status == 200
        body = await response.json()
        assert body["coverage"] == "partial" and body["associations_complete"] is False
        assert body["service_total"] is None and body["customer_total"] is None
        assert body["services"] == []

    async def test_partial_and_unavailable_sources_are_not_empty_healthy_inventory(self) -> None:
        self.responses["/hosts"] = RuntimeError("NEVER_EXPOSE")
        response = await self.client.get("/api/admin/console/nodes", headers=self.admin)
        body = await response.json()
        assert body["total"] == 2 and body["coverage"] == "partial"
        assert body["sources"][1]["availability"] == "unavailable"
        detail = await self.client.get(f"/api/admin/console/nodes/{NODE}", headers=self.admin)
        body = await detail.json()
        assert body["service_total"] is None and body["customer_total"] is None
        assert not body["associations_complete"]
        assert "NEVER_EXPOSE" not in await detail.text()
        self.responses["/nodes"] = {"error": True, "status_code": 403, "details": "NEVER_EXPOSE"}
        response = await self.client.get("/api/admin/console/nodes", headers=self.admin)
        body = await response.json()
        assert len(body["nodes"]) == 2 and body["total"] is None and body["coverage"] == "stale"
        assert all(node["status"] == "unknown" for node in body["nodes"])
        assert all(
            source["last_success_at"] for source in body["sources"] if source["source"] == "nodes"
        )
        stale_detail = await self.client.get(f"/api/admin/console/nodes/{NODE}", headers=self.admin)
        assert stale_detail.status == 200 and (await stale_detail.json())["coverage"] == "stale"
        assert (
            await self.client.get(f"/api/admin/console/nodes/{UUID(int=999)}", headers=self.admin)
        ).status == 503

    async def test_validation_missing_objects_and_unknown_scope(self) -> None:
        assert (
            await self.client.get("/api/admin/console/nodes/not-a-uuid", headers=self.admin)
        ).status == 400
        assert (
            await self.client.get(f"/api/admin/console/nodes/{UUID(int=999)}", headers=self.admin)
        ).status == 404
        assert (
            await self.client.get(
                "/api/admin/console/services/invalid/resources", headers=self.admin
            )
        ).status == 400
        assert (
            await self.client.get(
                f"/api/admin/console/services/{'f' * 32}/resources", headers=self.admin
            )
        ).status == 404
        service, _, _ = await self.activate()
        self.responses["/internal-squads"] = {"internalSquads": []}
        body = await (
            await self.client.get(
                f"/api/admin/console/services/{service.id}/resources", headers=self.admin
            )
        ).json()
        assert body["groups"] == [{"id": GROUP, "name": None}]
        assert body["nodes"] == [] and body["coverage"] == "partial"

    async def test_fresh_failure_is_unknown_and_successful_empty_inventory_is_zero(self) -> None:
        self.responses["/nodes"] = {"error": True, "status_code": 403}
        body = await (await self.client.get("/api/admin/console/nodes", headers=self.admin)).json()
        assert body["coverage"] == "unavailable" and body["total"] is None
        assert body["nodes"] == [] and body["sources"][0]["last_success_at"] is None
        self.responses["/nodes"] = []
        body = await (await self.client.get("/api/admin/console/nodes", headers=self.admin)).json()
        assert body["coverage"] == "complete" and body["total"] == 0 and body["nodes"] == []


class NodeInventoryTests(IsolatedAsyncioTestCase):
    async def test_singleflight_cache_and_stale_failure_keep_last_success_time(self) -> None:
        responses = panel_responses()
        panel, request = panel_fixture(responses)
        reader = NodeInventoryReader()
        results = await asyncio.gather(*(reader.read(panel, ttl_seconds=15) for _ in range(5)))
        assert request.await_count == 3
        first = results[0]
        responses.update({path: TimeoutError("NEVER_EXPOSE") for path in responses})
        with patch("bot.utils.ttl_cache.time.monotonic", return_value=time.monotonic() + 16):
            stale = await reader.read(panel, ttl_seconds=15)
        assert stale.coverage == "stale"
        assert stale.node_out(stale.nodes.rows[0]).status == "unknown"
        assert stale.nodes.source.last_success_at == first.nodes.source.last_success_at
        assert stale.nodes.source.attempted_at >= first.nodes.source.attempted_at
        assert stale.nodes.source.error == "request_failed"
        assert len(stale.nodes.rows) == 2 and request.await_count == 6
        with patch("bot.utils.ttl_cache.time.monotonic", return_value=time.monotonic() + 400):
            missing = await reader.read(panel, ttl_seconds=15)
        assert missing.coverage == "unavailable" and missing.nodes.rows == []
        assert missing.nodes.source.last_success_at == first.nodes.source.last_success_at

    async def test_empty_malformed_duplicate_and_unsupported_inventory_are_distinct(self) -> None:
        for raw, expected_coverage, expected_rows in (
            ([], "complete", 0),
            ([{"uuid": "bad-uuid", "name": "Unknown"}], "partial", 0),
            ({"nodes": [], "total": 1}, "partial", 0),
            ({"unexpected": []}, "unavailable", 0),
            ({"error": True, "status_code": 404}, "unavailable", 0),
        ):
            responses = panel_responses()
            responses["/nodes"] = raw
            panel, _ = panel_fixture(responses)
            result = await NodeInventoryReader().read(panel, ttl_seconds=0)
            assert result.coverage == expected_coverage and len(result.nodes.rows) == expected_rows
            if raw == {"error": True, "status_code": 404}:
                assert result.nodes.source.availability == "unsupported"
        responses = panel_responses()
        nodes = cast(list[dict[str, object]], responses["/nodes"])
        nodes.append({**nodes[0], "uuid": NODE.upper(), "name": "Duplicate"})
        panel, _ = panel_fixture(responses)
        result = await NodeInventoryReader().read(panel, ttl_seconds=0)
        assert result.coverage == "partial" and len(result.nodes.rows) == 2
        missing = await NodeInventoryReader().read(None, ttl_seconds=0)
        assert missing.coverage == "unavailable"
        assert all(source.availability == "unconfigured" for source in missing.sources)

    async def test_host_filters_do_not_grant_an_inbound_via_an_unrelated_group(self) -> None:
        responses = panel_responses()
        nodes = cast(list[dict[str, object]], responses["/nodes"])
        nodes[0]["configProfile"] = {"activeInbounds": [{"uuid": INBOUND}, {"uuid": OTHER_INBOUND}]}
        hosts = cast(list[dict[str, object]], responses["/hosts"])
        hosts[0]["internalSquads"] = {"mode": "EXCLUDE", "squads": [GROUP]}
        panel, _ = panel_fixture(responses)
        reader = NodeInventoryReader()
        result = await reader.read(panel, ttl_seconds=0)
        assert [
            host.id for host in result.node_hosts(result.nodes.rows[0], groups={GROUP, OTHER_GROUP})
        ] == [OTHER_HOST]
        hosts[0]["internalSquads"] = {"mode": "ALLOW_ONLY", "squads": [GROUP]}
        result = await reader.read(panel, ttl_seconds=0)
        assert [host.id for host in result.node_hosts(result.nodes.rows[0], groups={GROUP})] == [
            HOST
        ]
        hosts[0]["isHidden"] = True
        result = await reader.read(panel, ttl_seconds=0)
        assert result.node_hosts(result.nodes.rows[0], groups={GROUP}) == []
        hosts[0]["inbound"] = {"configProfileInboundUuid": None}
        result = await reader.read(panel, ttl_seconds=0)
        assert result.hosts.source.availability == "available"
        assert result.node_hosts(result.nodes.rows[0], groups={GROUP}) == []
