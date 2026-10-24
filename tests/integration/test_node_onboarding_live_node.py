"""UC-07/08 F06, UA-16: real HTTP onboarding and subscription-driven local traffic.

Only raw profiles/inbounds and the controlled origin are advanced fixture setup.
Node, group, Host, plan, activation and delivery use real product HTTP handlers.
The main window owns live execution; default collection never accesses the stand.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from secrets import token_hex
from uuid import UUID, uuid4

import pytest
from aiohttp import ClientTimeout, DummyCookieJar, web
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.app.web.admin_api_impl.auth import admin_auth_middleware
from bot.app.web.cache_headers import api_no_store_middleware
from bot.app.web.context import PANEL_SERVICE, SESSION_FACTORY, SETTINGS
from bot.app.web.webapp.assets import _csrf_protection_middleware
from bot.app.web.webapp.routes import setup_subscription_webapp_routes
from bot.app.web.webapp_auth import create_webapp_session_token
from bot.services.resource_operation_runner import (
    run_pending_resource_operation,
    run_resource_operation,
)
from bot.services.service_delivery import deliver_service_identity
from bot.services.service_exit_replacement import observed_groups
from bot.services.service_provisioning import provision_service_identity
from bot.services.service_usage_sync import synchronize_service_usage, usage_counters
from config.service_periods import as_utc
from config.settings import Settings
from db.auth_models import AccountRole
from db.migrator.chain_0118_resource_operations import _upgrade as upgrade_resources
from db.migrator.chain_0119_account_operations import _upgrade as upgrade_account_operations
from db.models import Base, User
from tests.integration import test_user_services_postgres as pg
from tests.integration.test_service_operations_live_node import LiveScenario
from tests.qa.test_remnawave_panel_contract import _panel_service
from tests.support.exit_replacement_live_node import SCOPE, ExitNode, cleanup_pair, ledger_totals
from tests.support.node_onboarding_live_node import (
    SubscriptionTLS,
    checked,
    json_object,
    one,
    private_bytes,
    require_onboarding_environment,
    resolve_onboarding_cleanup,
    subscription_client,
)
from tests.support.node_onboarding_resource_changes import exercise_group_change
from tests.support.service_operations_live_node import (
    IMAGE,
    NETWORK,
    PROJECT_ENV,
    RESOURCE_KEYS,
    eventually,
    node_config,
    private_json,
)
from tests.unit.test_user_services import sample_terms

OPERATIONS = "/api/admin/console/resources/operations"
DEPLOYMENT = "/api/admin/console/nodes/onboarding/deployment"
PREVIEW = "/api/admin/console/resources/preview"


def string(value: object) -> str:
    checked(isinstance(value, str) and bool(value), "expected_nonempty_string")
    assert isinstance(value, str)
    return value


class OnboardingScenario(LiveScenario):
    def __init__(self, factory: async_sessionmaker[AsyncSession], root: ExitNode) -> None:
        super().__init__(factory, root)
        self.root = root
        self.tls = SubscriptionTLS(root)
        self.settings = Settings(
            **{
                **vars(self.panel.settings),
                "_env_file": None,
                "POSTGRES_USER": "unused_injected_session_factory",
                "POSTGRES_PASSWORD": "unused_injected_session_factory",
                "TELEGRAM_ENABLED": False,
                "ADMIN_IDS": "",
                "WEBAPP_SESSION_SECRET": token_hex(32),
                "REDIS_URL": None,
                "ADMIN_PANEL_STATS_CACHE_TTL_SECONDS": 0,
            }
        )
        checked(self.settings.panel_settings == self.panel.panel_settings, "panel_settings_changed")
        # The real resource runner requires Settings, including its live-write policy.
        self.panel.settings = self.settings
        self.headers = {
            user: {"Authorization": "Bearer " + create_webapp_session_token(self.settings, user)}
            for user in (1, 2, 3)
        }
        app = web.Application(
            middlewares=[
                api_no_store_middleware,
                _csrf_protection_middleware,
                admin_auth_middleware,
            ]
        )
        app[SETTINGS], app[SESSION_FACTORY], app[PANEL_SERVICE] = (
            self.settings,
            self.sessions,
            self.panel,
        )
        setup_subscription_webapp_routes(app)
        self.client = TestClient(
            TestServer(app, host="127.0.0.1"),
            cookie_jar=DummyCookieJar(),
            trust_env=False,
            timeout=ClientTimeout(total=60),
        )
        self.operation_ids: list[str] = []

    def report(self, name: str, values: object) -> None:
        self.root.evidence[name] = values
        private_json(self.root.directory / "report.json", self.root.evidence)

    async def http(
        self,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
        *,
        actor: int | None = 2,
        status: int = 200,
    ) -> dict[str, object]:
        checked(path.startswith("/api/") and "://" not in path, "nonlocal_product_path")
        async with self.client.request(
            method,
            path,
            json=body,
            headers=self.headers[actor] if actor is not None else {},
            allow_redirects=False,
        ) as response:
            if response.status != status:
                self.report(
                    "last_http_failure", {"method": method, "path": path, "status": response.status}
                )
            checked(response.status == status, "product_http_status_" + str(response.status))
            result = json_object(await response.json())
            checked(result.get("ok") is (status == 200), "product_http_envelope")
            checked("no-store" in response.headers.get("Cache-Control", ""), "product_http_cache")
            return result

    async def resource_change(
        self,
        node: ExitNode,
        change: dict[str, object],
        *,
        endpoint: str | None = None,
        preview: dict[str, object] | None = None,
        recovery_of: str | None = None,
    ) -> str:
        if preview is None:
            preview = await self.http("POST", PREVIEW, {"change": change})
        self.report(
            "last_preview",
            {
                key: preview.get(key)
                for key in (
                    "coverage",
                    "blockers",
                    "fingerprint",
                    "affected_service_ids",
                    "affected_customer_ids",
                )
            },
        )
        checked(
            preview.get("coverage") == "complete" and preview.get("blockers") == [],
            "resource_preview_incomplete",
        )
        proposed = json_object(preview.get("proposed"))
        if endpoint is not None:
            checked(proposed.get("id") is None, "creation_already_has_identity")
            checked(
                not any(
                    row.get(RESOURCE_KEYS[endpoint][1]) == node.prefix
                    for row in await node.inventory(endpoint)
                ),
                "resource_already_exists",
            )
        body: dict[str, object] = {
            "change": change,
            "expected_fingerprint": string(preview.get("fingerprint")),
            "idempotency_key": uuid4().hex,
        }
        if recovery_of is not None:
            body["recovery_of"] = recovery_of
        accepted = await self.http("POST", OPERATIONS, body)
        operation = json_object(accepted["operation"])
        operation_id = string(operation["id"])
        self.operation_ids.append(operation_id)
        self.root.state["resource_operation_ids"] = self.operation_ids
        self.root.save()
        confirmed = json_object(operation["preview"])
        checked(
            all(
                confirmed[key] == preview[key]
                for key in ("fingerprint", "affected_service_ids", "affected_customer_ids")
            )
            and operation["recovery_of"] == recovery_of,
            "resource_confirmation_changed",
        )
        checked(
            operation["status"] == "pending"
            and operation["attempts"] == []
            and operation["gate_active"] is True,
            "submission_executed_without_worker",
        )
        resource: dict[str, object] | None = None
        if endpoint is not None:
            resource = {
                "endpoint": endpoint,
                "name": node.prefix,
                "uuid": None,
                "operation_id": operation_id,
            }
            node.state["resources"] = [*node.rows("resources"), resource]
            node.save()
            checked(
                not any(
                    row.get(RESOURCE_KEYS[endpoint][1]) == node.prefix
                    for row in await node.inventory(endpoint)
                ),
                "pending_created_remote_resource",
            )
        # Both entrypoints are real: the scoped pending worker selects this sole pending row.
        await run_pending_resource_operation(self.factory, self.panel)

        async def completed() -> bool:
            nonlocal operation
            operation = await self.http("GET", OPERATIONS + "/" + operation_id)
            if resource is not None and operation.get("target_id") is not None:
                resource["uuid"] = str(UUID(string(operation["target_id"])))
                node.save()
            self.report(
                "last_resource_operation",
                {
                    key: operation.get(key)
                    for key in (
                        "id",
                        "status",
                        "target_id",
                        "attempts",
                        "error_code",
                        "gate_active",
                        "observation",
                    )
                },
            )
            checked(
                operation["status"] not in {"failed", "unknown", "superseded"},
                "resource_worker_requires_reconciliation",
            )
            return operation["status"] == "succeeded"

        await eventually(completed, seconds=30)
        attempts = operation["attempts"]
        checked(
            operation["gate_active"] is False and isinstance(attempts, list) and len(attempts) == 1,
            "resource_operation_not_completed",
        )
        observation = json_object(operation.get("observation"))
        checked(
            observation.get("configuration") == "matched"
            and observation.get("runtime") == "unverified",
            "configuration_receipt_not_runtime",
        )
        target = str(UUID(string(operation["target_id"])))
        # A succeeded operation is not dispatched again by the actual worker.
        await run_resource_operation(self.factory, self.panel, operation_id)
        retry = await self.http("GET", OPERATIONS + "/" + operation_id)
        checked(retry["attempts"] == operation["attempts"], "terminal_operation_redispatched")
        duplicate = await self.http("POST", OPERATIONS, body)
        checked(
            duplicate.get("duplicate") is True
            and json_object(duplicate["operation"])["id"] == operation_id,
            "resource_idempotency",
        )
        return target

    async def infrastructure(self) -> None:
        root = self.root
        await root.require_local_docker()
        baseline = await root.baseline()
        checked(baseline["/nodes"] == [] and baseline["/hosts"] == [], "local_stand_not_empty")
        root.state.update(
            {
                "baseline": baseline,
                "env_sha256": hashlib.sha256(PROJECT_ENV.read_bytes()).hexdigest(),
                "onboarding_http": True,
            }
        )
        root.save()
        image = json_object(one(json.loads(await root.docker("image", "inspect", IMAGE))))
        digests = image.get("RepoDigests")
        checked(
            isinstance(digests, list)
            and any(
                isinstance(item, str) and item.endswith("@" + IMAGE.split("@", 1)[1])
                for item in digests
            ),
            "pinned_node_image_missing",
        )
        root.evidence.update({"node_image_id": image["Id"], "node_image_digest": IMAGE})
        await root.docker("network", "inspect", NETWORK)
        origin = await root.container("origin", "my-vps-obj-backend:dev", "--entrypoint", "python")
        await root.docker("start", origin)
        root.origin_ip = await root.docker(
            "inspect",
            "--format",
            '{{(index .NetworkSettings.Networks "' + NETWORK + '").IPAddress}}',
            origin,
        )
        root.target()
        checked(root.companion is not None, "missing_comparison_fixture")
        self.report(
            "fixture_boundary",
            {
                "advanced_maintenance_only": ["controlled_origin", "raw_profile", "raw_inbound"],
                "http_created": ["node", "group", "host", "plan", "service", "delivery"],
                "scope": SCOPE,
                "origin_ip": root.origin_ip,
                "public_dedicated_verified": False,
                "third_party_client_import_verified": False,
            },
        )

    async def onboard(self, node: ExitNode) -> None:
        node.origin_ip = self.root.origin_ip
        config = node_config(node.origin_ip)
        tag = "UC07_VLESS_" + string(node.state["run_id"])
        config["inbounds"] = [json_object(one(config["inbounds"])) | {"tag": tag}]
        routing = json_object(config["routing"])
        rules = routing["rules"]
        checked(isinstance(rules, list), "invalid_fixture_routing")
        assert isinstance(rules, list)
        routing["rules"] = [json_object(row) | {"inboundTag": [tag]} for row in rules]
        config["routing"] = routing
        profile = await node.create_resource(
            "/config-profiles", {"name": node.prefix, "config": config}
        )
        values = await node.api("GET", f"/config-profiles/{profile}/inbounds")
        if isinstance(values, dict):
            values = values.get("inbounds")
        inbound = str(UUID(string(json_object(one(values))["uuid"])))
        node.state.update({"onboarding_profile": profile, "onboarding_inbound": inbound})
        node.save()
        node.squad_id = await self.resource_change(
            node,
            {"operation": "group_create", "name": node.prefix, "inbound_ids": []},
            endpoint="/internal-squads",
        )
        await self.resource_change(
            node,
            {"operation": "group_inbounds", "target_id": node.squad_id, "inbound_ids": [inbound]},
        )
        deployment = await self.http("POST", DEPLOYMENT, {"management_port": 2222})
        checked(
            deployment.get("installation_performed") is False
            and deployment.get("recorded_node_version") == "3.4.2",
            "deployment_not_scoped",
        )
        secret = string(deployment.get("secret_key"))
        checked("\n" not in secret and "\r" not in secret, "invalid_deployment_secret")
        env = node.directory / "node.env"
        private_bytes(env, ("NODE_PORT=2222\nSECRET_KEY=" + secret + "\n").encode())
        name = await node.container("node", IMAGE, "--env-file", str(env))
        await node.docker("start", name)
        node.node_id = await self.resource_change(
            node,
            {
                "operation": "node_create",
                "name": node.prefix,
                "address": name,
                "port": 2222,
                "profile_id": profile,
                "inbound_ids": [inbound],
            },
            endpoint="/nodes",
        )
        await node.wait_ready()
        node.host_id = await self.resource_change(
            node,
            {
                "operation": "host_create",
                "name": node.prefix,
                "address": name,
                "port": 12080,
                "profile_id": profile,
                "inbound_id": inbound,
                "node_ids": [node.node_id],
                "group_mode": "ALLOW_ONLY",
                "group_ids": [node.squad_id],
                "is_disabled": False,
                "is_hidden": True,
            },
            endpoint="/hosts",
        )
        await self.resource_change(
            node,
            {"operation": "host_update", "target_id": node.host_id, "patch": {"is_hidden": False}},
        )
        await node.wait_ready()
        self.report(
            "onboarded_" + node.prefix,
            {
                "node_uuid": node.node_id,
                "group_uuid": node.squad_id,
                "host_uuid": node.host_id,
                "inbound_uuid": inbound,
                "profile_uuid": profile,
                "internal_ip": await node.internal_ip(),
                "node_ready": node.evidence.get("node_ready_before_services"),
                "adapter": node.evidence.get("execution_adapter"),
            },
        )

    async def activate(self, node: ExitNode, owner: int) -> int:
        terms = sample_terms(
            name=node.prefix, quota_bytes=64 * 1024 * 1024, squad_uuids=[node.squad_id]
        ).model_dump(mode="json")
        result = await self.http(
            "POST", "/api/admin/service-plans", {"terms": terms, "enabled": True}
        )
        plan = json_object(result["plan"])
        result = await self.http(
            "POST",
            "/api/admin/services",
            {
                "user_id": owner,
                "plan_id": plan["id"],
                "expected_revision": plan["revision"],
                "idempotency_key": uuid4().hex,
            },
        )
        service_id = string(json_object(result["service"])["id"])
        index = len(self.services)
        self.services.append(service_id)
        node.remember_service(service_id)
        await provision_service_identity(self.sessions, service_id, self.panel)
        await synchronize_service_usage(self.sessions, service_id, self.panel)
        service, connection = await self.saved(index)
        checked(connection.state == "pending" and service.used_bytes == 0, "service_not_prepared")
        await self.http(
            "POST",
            f"/api/admin/services/{service_id}/deliver",
            {
                "user_id": owner,
                "expected_revision": service.revision,
                "idempotency_key": uuid4().hex,
            },
        )
        await deliver_service_identity(self.sessions, service_id, self.panel)
        service, connection = await self.saved(index)
        remote = await self.remote(index)
        checked(
            connection.state == "ready"
            and not connection.sync_pending
            and remote.get("status") == "ACTIVE",
            "service_not_delivered",
        )
        checked(observed_groups(remote) == {node.squad_id}, "wrong_service_authorization")
        self.report(
            "service_" + service_id,
            {
                "owner": owner,
                "plan_id": plan["id"],
                "squad_id": node.squad_id,
                "state": connection.state,
                "credential_sha256": hashlib.sha256(
                    string(remote["vlessUuid"]).encode()
                ).hexdigest(),
            },
        )
        return index

    async def subscription(
        self, index: int, node: ExitNode, owner: int
    ) -> tuple[int, dict[str, object]]:
        remote = await self.remote(index)
        response = await self.http(
            "GET", f"/api/services/{self.services[index]}/subscription", actor=owner
        )
        url = string(json_object(response["subscription"])["subscription_url"])
        checked(url == remote.get("subscriptionUrl"), "product_subscription_url_rewritten")
        fetched = await self.tls.fetch(url, target=node, identity=string(remote["vlessUuid"]))
        port = await subscription_client(node, fetched.outbound)
        self.report(
            "subscription_" + self.services[index],
            {
                **fetched.evidence,
                "client_index": node.ports.index(port),
                "socks_port": port,
                "config_sha256": node.state[f"client_{node.ports.index(port)}_sha256"],
            },
        )
        return port, fetched.outbound

    async def meter(self, index: int, expected: int) -> None:
        async def reconciled() -> bool:
            await synchronize_service_usage(self.sessions, self.services[index], self.panel)
            service, connection = await self.saved(index)
            checked(
                connection.usage_error is None
                and connection.cycle_cutover_bytes is None
                and (connection.usage_lifetime_offset or 0) == 0,
                "usage_not_authoritative",
            )
            checked(
                service.used_bytes <= expected and (connection.usage_raw_bytes or 0) <= expected,
                "usage_exceeds_accounted_payload",
            )
            matches: bool = (
                service.used_bytes
                == connection.usage_total_bytes
                == connection.usage_raw_bytes
                == expected
            )
            return matches

        await eventually(reconciled)
        service, connection = await self.saved(index)
        checked(
            usage_counters(await self.remote(index)) == (expected, expected), "panel_meter_mismatch"
        )
        self.report(
            "meter_" + self.services[index],
            {
                "expected_up_plus_down": expected,
                "used_bytes": service.used_bytes,
                "raw_bytes": connection.usage_raw_bytes,
                "total_bytes": connection.usage_total_bytes,
                "observed_at": as_utc(service.last_usage_sync_at).isoformat()
                if service.last_usage_sync_at
                else None,
            },
        )

    async def rights(self, index: int) -> dict[str, object]:
        service, connection = await self.saved(index)
        remote = await self.remote(index)
        return {
            "service_id": service.id,
            "owner": service.user_id,
            "terms": service.terms,
            "plan_id": service.plan_id,
            "plan_revision": service.plan_revision,
            "quota_bytes": service.quota_bytes,
            "desired_status": service.desired_status,
            "starts_at": as_utc(service.starts_at).isoformat(),
            "expires_at": as_utc(service.expires_at).isoformat(),
            "identity_sha256": hashlib.sha256(
                string(connection.panel_user_uuid).encode()
            ).hexdigest(),
            "credential_sha256": hashlib.sha256(string(remote["vlessUuid"]).encode()).hexdigest(),
            "groups": sorted(observed_groups(remote)),
            "remote_status": remote["status"],
            "remote_quota": remote["trafficLimitBytes"],
            "remote_expiry": remote["expireAt"],
        }

    async def transfer(self, index: int, node: ExitNode, port: int) -> int:
        token = self.services[index]
        for op, size in ((b"P", 0), (b"U", 8192), (b"D", 12288)):
            await node.exchange(port, token, op, size)
        rows = await node.ledger(token)
        up, down = ledger_totals(rows, expected_peer=await node.internal_ip())
        checked(
            len(rows) == 3 and up + down == 21 * 3 + 8192 + 12288 + 16 + 1,
            "origin_payload_count_mismatch",
        )
        await self.meter(index, up + down)
        self.report("payload_" + token, {"ledger": rows, "upload": up, "download": down})
        return up + down

    async def permissions(self, node: ExitNode) -> None:
        before = await self.http("GET", OPERATIONS)
        paths: list[tuple[str, str, dict[str, object] | None]] = [
            ("GET", OPERATIONS, None),
            ("GET", OPERATIONS + "/" + self.operation_ids[0], None),
            (
                "POST",
                OPERATIONS,
                {
                    "change": {"operation": "node_disable", "target_id": node.node_id},
                    "expected_fingerprint": "0" * 64,
                    "idempotency_key": uuid4().hex,
                },
            ),
            ("POST", DEPLOYMENT, {"management_port": 2222}),
            (
                "POST",
                PREVIEW,
                {
                    "change": {
                        "operation": "group_inbounds",
                        "target_id": node.squad_id,
                        "inbound_ids": [],
                    }
                },
            ),
        ]
        for actor, status in ((None, 401), (1, 403), (3, 403)):
            for method, path, body in paths:
                await self.http(method, path, body, actor=actor, status=status)
        after = await self.http("GET", OPERATIONS)
        checked(before == after, "unauthorized_management_changed_operations")
        await self.http(
            "GET", f"/api/services/{self.services[0]}/subscription", actor=3, status=404
        )
        await self.http(
            "GET", f"/api/services/{self.services[1]}/subscription", actor=1, status=404
        )
        self.report(
            "http_authorization",
            {
                "anonymous": 401,
                "service_owners": 403,
                "cross_owner_subscription": 404,
                "operation_history_unchanged": True,
            },
        )

    async def metrics(self, node: ExitNode) -> None:
        from bot.app.web.admin_console_nodes_schemas import ConsoleNodeDetailOut

        for attempt in range(7):
            value = await self.http("GET", f"/api/admin/console/nodes/{node.node_id}")
            detail = ConsoleNodeDetailOut.model_validate(value)
            system = detail.node.system.model_dump(mode="json")
            present = any(
                value is not None
                for key, value in system.items()
                if key not in {"sampled_at", "invalid_fields"}
            )
            checked(detail.node.system.sampled_at is None, "node_sample_time_was_invented")
            self.report(
                "uc09_node_metrics",
                {
                    "node_id": node.node_id,
                    "status": "observed" if present else "unverified_system_missing",
                    "attempts": attempt + 1,
                    "source_path": "/api/admin/console/nodes/{id}",
                    "system": system,
                    "sources": [row.model_dump(mode="json") for row in detail.sources],
                    "observed_at": detail.node.observed_at.isoformat()
                    if detail.node.observed_at
                    else None,
                    "observation_basis": detail.node.observation_basis,
                    "online_status": detail.node.status,
                    "users_online": detail.node.users_online,
                    "users_online_quality": detail.node.users_online_quality,
                    "online_scope": detail.node.online_scope,
                    "sample_freshness": "unknown",
                    "panel_host_stats_used": False,
                },
            )
            if present:
                return
            if attempt < 6:
                await asyncio.sleep(5)

    async def exercise(self) -> None:
        await self.client.start_server()
        await self.infrastructure()
        other = self.root.companion
        checked(other is not None, "missing_comparison_node")
        assert other is not None
        for node in (self.root, other):
            await self.onboard(node)
        checked(await self.root.internal_ip() != await other.internal_ip(), "egress_not_distinct")
        for node, owner in ((self.root, 1), (other, 3)):
            await self.activate(node, owner)
        rights = [await self.rights(index) for index in (0, 1)]
        await self.tls.start()
        port, _ = await self.subscription(0, self.root, 1)
        other_port, other_outbound = await self.subscription(1, other, 3)
        total = await self.transfer(0, self.root, port)
        other_total = await self.transfer(1, other, other_port)
        await self.permissions(self.root)
        # A valid, paid-up second service deliberately targets the first group's listener.
        hostile = json.loads(json.dumps(other_outbound))
        hostile["settings"]["vnext"][0]["address"] = self.root.prefix + "-node"
        rejected_port = await subscription_client(self.root, hostile)
        token = uuid4().hex
        rejected = await self.root.rejected(rejected_port, token)
        self.report(
            "cross_group_rejection",
            {
                "attempts": rejected,
                "origin_rows": await self.root.ledger(token),
                "other_service_active_before_and_after": True,
            },
        )
        for index, node, current_port, expected in (
            (0, self.root, port, total),
            (1, other, other_port, other_total),
        ):
            checked(
                (await self.remote(index)).get("status") == "ACTIVE",
                "comparison_service_not_active",
            )
            await node.exchange(current_port, self.services[index], b"P")
            await self.meter(index, expected + 37)
            checked(await self.rights(index) == rights[index], "service_rights_or_identity_changed")
            checked(
                hashlib.sha256((node.directory / "client-0.json").read_bytes()).hexdigest()
                == node.state["client_0_sha256"],
                "delivered_client_config_changed",
            )
        self.report("unchanged_rights", rights)
        await self.metrics(self.root)
        await exercise_group_change(self, (port, other_port))


async def run_onboarding(
    database: str,
    *,
    scenario_type: type[OnboardingScenario] = OnboardingScenario,
    scope: str = SCOPE,
) -> None:
    panel = _panel_service()
    root = ExitNode(panel)
    root.evidence["scope"] = scope
    schema = "user_services_test_" + uuid4().hex
    root.state["schema"] = schema
    root.save()
    print(f"Local F06 manifest: {root.manifest}", flush=True)
    admin = create_async_engine(database)
    engine = create_async_engine(
        database, connect_args={"server_settings": {"search_path": schema}}
    )
    case: OnboardingScenario | None = None
    passed = False
    try:
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        async with engine.begin() as connection:
            # Reuse the PG fixture's idempotent migrations, retaining this schema on failure.
            migrated = {
                "service_plans",
                "service_orders",
                "user_services",
                "service_connections",
                "dedicated_exits",
                "dedicated_exit_audit",
                "account_access_sync",
                "service_usage_periods",
                "service_plan_quota_changes",
                "service_operation_executions",
                "resource_operations",
            }
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(
                    conn,
                    tables=[
                        table for table in Base.metadata.sorted_tables if table.name not in migrated
                    ],
                )
            )
            for migration in (
                pg._upgrade,
                pg.upgrade_history,
                pg.upgrade_access,
                pg.upgrade_provisioning,
                pg.upgrade_changes,
                pg.upgrade_usage,
                pg.upgrade_entitlements,
                pg.upgrade_delivery,
                pg.upgrade_revocation_evidence,
                pg.upgrade_executions,
                pg.upgrade_exit_replacement,
                upgrade_resources,
                upgrade_account_operations,
            ):
                await connection.run_sync(migration)
        factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        async with factory.begin() as session:
            session.add_all([User(user_id=1), User(user_id=2), User(user_id=3)])
            await session.flush()
            session.add(AccountRole(user_id=2, role="admin"))
        case = scenario_type(factory, root)
        await case.exercise()
        root.evidence["state"] = "passed"
        passed = True
    except BaseException as exc:
        root.evidence.update({"state": "failed", "failure_type": type(exc).__name__})
        if case:
            case.report(
                "failure",
                {"type": type(exc).__name__, "message": "F06 stopped; private manifest retained"},
            )
        raise
    finally:
        try:
            if case:
                await case.client.close()

            async def cleanup() -> None:
                if root.state.get("onboarding_tls") is not None:
                    await SubscriptionTLS(root).cleanup()
                await resolve_onboarding_cleanup(root, database)
                await root.require_local_docker()
                await cleanup_pair(root)

            cleanup_task = asyncio.create_task(cleanup())
            try:
                await asyncio.shield(cleanup_task)
            except asyncio.CancelledError:
                passed = False
                await cleanup_task
                raise
            if passed:
                async with admin.begin() as connection:
                    await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
                root.evidence["schema_cleanup"] = "passed"
                if root.companion:
                    root.companion.manifest.unlink()
                root.manifest.unlink()
            else:
                root.evidence["schema_cleanup"] = "retained_for_recovery"
        except BaseException as exc:
            root.evidence.update(
                {"state": "failed", "cleanup": "failed", "cleanup_failure_type": type(exc).__name__}
            )
            raise
        finally:
            private_json(root.directory / "report.json", root.evidence)
            await engine.dispose()
            await admin.dispose()
            root.close_lock()
            await panel.close_session()
    print(f"Local F06 report: {root.directory / 'report.json'}", flush=True)


def run_local_onboarding() -> None:
    if os.environ.get("QA_SERVICE_OPERATIONS_LIVE_NODE") != "1":
        pytest.skip("Requires the exclusive opt-in local F06 slot")
    database = require_onboarding_environment()
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        asyncio.run(run_onboarding(database))
    finally:
        logging.disable(previous)


@pytest.mark.skipif(
    os.environ.get("QA_SERVICE_OPERATIONS_LIVE_NODE") != "1",
    reason="Requires the exclusive opt-in local F06 slot",
)
@pytest.mark.filterwarnings(
    "ignore:It is recommended to use web.RequestKey: aiohttp.web_exceptions.NotAppKeyWarning"
)
def test_real_http_onboarding_subscription_usage_and_group_isolation() -> None:
    run_local_onboarding()
