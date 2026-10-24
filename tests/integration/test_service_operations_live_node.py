"""UA-10/11/12/13 evidence on one disposable local Node, never enabled in CI.

The main window owns the exclusive live slot. Explicit environment required:
QA_SERVICE_OPERATIONS_LIVE_NODE=1 DOCKER_CONTEXT=colima-my-vps-obj
QA_ENV_FILE=<checkout>/.env.project-dev QA_REMNAWAVE_API_URL=http://127.0.0.1:3000/api
CORE_PERFORMANCE_TEST_DATABASE_URL=<local project asyncpg URL>
Run only this file; the existing Node-free panel tests must not run concurrently.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker

from bot.app.web.admin_api_impl.auth import admin_auth_middleware
from bot.app.web.admin_console_nodes_routes import setup_admin_console_nodes_routes
from bot.app.web.context import PANEL_SERVICE, SESSION_FACTORY, SETTINGS
from bot.app.web.webapp_auth import create_webapp_session_token
from bot.services import service_change_sync
from bot.services.account_access_sync import set_account_ban, synchronize_account_access
from bot.services.panel_api_service import PanelApiService
from bot.services.service_delivery import deliver_service_identity
from bot.services.service_diagnostics import service_diagnostics
from bot.services.service_panel_state import ServiceEntitlementPanel
from bot.services.service_provisioning import provision_service_identity
from bot.services.service_usage_sync import synchronize_service_usage
from config.service_changes import ServiceChange
from config.service_periods import as_utc
from config.settings import Settings
from db.auth_models import AccountRole
from db.dal.service_changes_dal import change_service
from db.dal.service_delivery_dal import request_service_delivery
from db.dal.service_operations_dal import retry_execution
from db.dal.user_services_dal import activate_service, save_plan
from db.models import User
from db.service_models import (
    ServiceConnection,
    ServiceOperationExecution,
    ServiceOrder,
    UserService,
)
from tests.integration.test_user_services_postgres import scenario
from tests.qa.test_remnawave_panel_contract import _panel_service
from tests.support import service_operations_live_node as node_harness
from tests.support.service_operations_live_node import (
    CONTEXT,
    LiveNode,
    eventually,
    object_dict,
    private_json,
    require_environment,
    validate_local_targets,
)
from tests.unit.test_user_services import sample_terms


@pytest.mark.parametrize(
    ("panel", "database", "context"),
    [
        ("http://example.com:3000/api", "postgresql+asyncpg://localhost/test", CONTEXT),
        ("http://localhost:3000/api", "postgresql+asyncpg://example.com/test", CONTEXT),
        ("http://localhost:3000/api", "postgresql+asyncpg://localhost/test", "default"),
        ("http://localhost:3000/api?redirect=prod", "postgresql+asyncpg://localhost/test", CONTEXT),
        (
            "http://localhost:3000/api",
            "postgresql+asyncpg://localhost/test?options=unsafe",
            CONTEXT,
        ),
    ],
)
def test_live_evidence_rejects_nonlocal_or_ambiguous_targets(
    panel: str, database: str, context: str
) -> None:
    with pytest.raises(ValueError, match="isolated loopback"):
        validate_local_targets(panel, database, context)


def test_live_evidence_manifest_is_private_and_needs_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "manifest.json"
    private_json(manifest, {"run_id": "example"})
    # Windows mode bits do not express ACLs; the live Colima fixture requires POSIX.
    if os.name != "nt":
        assert manifest.stat().st_mode & 0o777 == 0o600
    assert json.loads(manifest.read_text()) == {"run_id": "example"}
    monkeypatch.delenv("QA_SERVICE_OPERATIONS_LIVE_NODE", raising=False)
    with pytest.raises(ValueError, match="Explicit"):
        require_environment()


@pytest.mark.parametrize("origin", ["172.18.0.13", "10.20.30.40"])
def test_live_node_config_allows_only_origin_tcp_port(origin: str) -> None:
    config = node_harness.node_config(origin)
    outbounds = cast(list[dict[str, object]], config["outbounds"])
    assert len(outbounds) == 2
    assert outbounds[0]["tag"] == "DIRECT" and outbounds[0]["protocol"] == "freedom"
    assert outbounds[0]["settings"] == {
        "finalRules": [
            {"action": "allow", "network": "tcp", "ip": [origin + "/32"], "port": "19090"},
            {"action": "block"},
        ]
    }
    assert outbounds[1] == {"tag": "BLOCK", "protocol": "blackhole"}
    assert object_dict(config["routing"])["rules"] == [
        {
            "type": "field",
            "inboundTag": ["UC2_VLESS"],
            "network": "tcp",
            "ip": [origin + "/32"],
            "port": "19090",
            "outboundTag": "DIRECT",
        },
        {"type": "field", "inboundTag": ["UC2_VLESS"], "outboundTag": "BLOCK"},
    ]


def _offline_node(tmp_path: Path) -> LiveNode:
    manifest = tmp_path / "manifest.json"
    private_json(
        manifest,
        {
            "run_id": uuid4().hex,
            "context": CONTEXT,
            "image": node_harness.IMAGE,
            "resources": [],
            "containers": [],
            "services": [],
            "baseline": {},
            "schema": None,
        },
    )
    return LiveNode(cast(PanelApiService, Mock(spec=PanelApiService)), manifest)


@pytest.mark.parametrize(
    ("present", "changes"),
    [
        (False, {}),
        (True, {"uuid": "another-node"}),
        (True, {"isConnected": False}),
        (True, {"isConnecting": True}),
        (True, {"isDisabled": True}),
        (True, {"isConnected": 1}),
        (True, {"isConnecting": None}),
        (True, {"isDisabled": None}),
    ],
)
@pytest.mark.skipif(sys.platform == "win32", reason="Colima fixture uses a POSIX advisory lock")
def test_node_readiness_waits_for_exact_connected_enabled_node(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, present: bool, changes: dict[str, object]
) -> None:
    async def run() -> None:
        fixture = _offline_node(tmp_path)
        fixture.node_id = str(uuid4())
        flags = {"isConnected": True, "isConnecting": False, "isDisabled": False}
        ready = {
            "uuid": fixture.node_id,
            **flags,
            "raw_config": "SHOULD_NOT_APPEAR",
        }
        inventory = AsyncMock(side_effect=[[{**ready, **changes}] if present else [], [ready]])
        sleep = AsyncMock()
        monkeypatch.setattr(fixture, "inventory", inventory)
        monkeypatch.setattr(node_harness.asyncio, "sleep", sleep)
        try:
            before = datetime.now(UTC)
            await fixture.wait_ready()
            assert inventory.await_count == 2
            inventory.assert_awaited_with("/nodes")
            sleep.assert_awaited_once_with(1)
            evidence = dict(object_dict(fixture.evidence["node_ready_before_services"]))
            observed_at = evidence.pop("observed_at")
            assert before <= datetime.fromisoformat(str(observed_at)) <= datetime.now(UTC)
            assert evidence == {"node_uuid": fixture.node_id, **flags}
        finally:
            fixture.close_lock()

    asyncio.run(run())


@pytest.mark.parametrize(
    ("suffix", "memory", "pids"),
    [("node", "384m", "128"), ("client-0", "128m", "64"), ("origin", "96m", "32")],
)
@pytest.mark.skipif(sys.platform == "win32", reason="Colima fixture uses a POSIX advisory lock")
def test_all_live_containers_have_memory_pids_and_log_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str, memory: str, pids: str
) -> None:
    async def run() -> None:
        fixture = _offline_node(tmp_path)
        docker = AsyncMock(return_value="created")
        monkeypatch.setattr(fixture, "docker", docker)
        try:
            name = await fixture.container(suffix, node_harness.IMAGE)
            docker.assert_awaited_once()
            assert docker.await_args is not None
            args = docker.await_args.args
            assert args[0] == "create" and "--pull=never" in args
            for flag, expected in (
                ("--memory", memory),
                ("--memory-swap", memory),
                ("--pids-limit", pids),
                ("--log-driver", "json-file"),
            ):
                assert args[args.index(flag) + 1] == expected
            assert args.count("--log-opt") == 2
            assert "max-size=1m" in args and "max-file=1" in args
            assert ("--cap-add" in args) is (suffix == "node")
            if suffix == "node":
                assert args[args.index("--cap-add") + 1] == "NET_ADMIN"
            assert fixture.rows("containers") == [{"name": name}]
        finally:
            fixture.close_lock()

    asyncio.run(run())


@pytest.mark.parametrize("borrowed", [False, True])
@pytest.mark.skipif(sys.platform == "win32", reason="Colima fixture uses a POSIX advisory lock")
def test_manifest_cleanup_recovers_lost_create_response_but_never_deletes_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, borrowed: bool
) -> None:
    async def run() -> None:
        env = tmp_path / "project.env"
        env.write_text("PANEL_WRITE_MODE=dry_run\n")
        monkeypatch.setattr(node_harness, "PROJECT_ENV", env)
        fixture = _offline_node(tmp_path)
        reference = str(uuid4())
        baseline: dict[str, object] = {
            endpoint: ([reference] if endpoint == "/nodes" and borrowed else [])
            for endpoint in node_harness.RESOURCE_KEYS
        }
        fixture.state.update(
            {
                "baseline": baseline,
                "env_sha256": hashlib.sha256(env.read_bytes()).hexdigest(),
                "resources": [{"endpoint": "/nodes", "name": fixture.prefix, "uuid": None}],
                "containers": [{"name": fixture.prefix + "-origin"}],
            }
        )
        fixture.save()
        secret = fixture.directory / "node.env"
        secret.write_text("DO_NOT_REPORT_SECRET")
        present = [{"uuid": reference, "name": fixture.prefix}]
        inventory = AsyncMock(side_effect=[present, present, []])
        api = AsyncMock()
        removed: list[str] = []

        async def docker(*args: str) -> str:
            if args[0] == "ps":
                return "owned-container" if not removed else ""
            if args[0] == "inspect":
                return str(fixture.state["run_id"])
            assert args == ("rm", "-f", fixture.prefix + "-origin")
            removed.append(args[-1])
            return ""

        monkeypatch.setattr(fixture, "inventory", inventory)
        monkeypatch.setattr(fixture, "api", api)
        monkeypatch.setattr(fixture, "docker", docker)
        monkeypatch.setattr(fixture, "baseline", AsyncMock(return_value=baseline))
        try:
            if borrowed:
                with pytest.raises(AssertionError, match="Scoped cleanup incomplete"):
                    await fixture.cleanup()
                api.assert_not_awaited()
            else:
                await fixture.cleanup()
                api.assert_awaited_once_with("DELETE", "/nodes/" + reference)
            assert removed == [fixture.prefix + "-origin"]
            assert fixture.manifest.exists() and not secret.exists()
            report = (fixture.directory / "report.json").read_text()
            assert "DO_NOT_REPORT_SECRET" not in report
            errors = object_dict(json.loads(report))["cleanup_errors"]
            assert bool(errors) is borrowed
        finally:
            fixture.close_lock()

    asyncio.run(run())


@pytest.mark.parametrize(
    ("reference", "owned"),
    [("62", True), ("11111111-1111-4111-8111-111111111111", True), ("63", False)],
)
@pytest.mark.skipif(sys.platform == "win32", reason="Colima fixture uses a POSIX advisory lock")
def test_identity_cleanup_keeps_numeric_and_legacy_refs_and_checks_ownership(
    tmp_path: Path, reference: str, owned: bool
) -> None:
    async def run() -> None:
        fixture = _offline_node(tmp_path)
        identity = "a" * 32
        fixture.remember_service(identity)
        lookup = AsyncMock(
            side_effect=[
                [
                    {
                        "uuid": reference,
                        "username": "svc_" + identity,
                        "description": "my_vps_obj:service:" + identity
                        if owned
                        else "another service",
                    }
                ],
                [],
            ]
        )
        delete = AsyncMock(return_value=True)
        with (
            patch.object(fixture.panel, "get_users_by_filter", lookup),
            patch.object(fixture.panel, "delete_user_from_panel", delete),
        ):
            try:
                if owned:
                    await fixture.cleanup()
                    delete.assert_awaited_once_with(reference)
                    assert lookup.await_count == 2
                else:
                    with pytest.raises(AssertionError, match="Scoped cleanup incomplete"):
                        await fixture.cleanup()
                    delete.assert_not_awaited()
            finally:
                fixture.close_lock()

    asyncio.run(run())


@pytest.mark.skipif(sys.platform == "win32", reason="Colima fixture uses a POSIX advisory lock")
def test_failure_diagnostics_keep_probe_oom_exit_and_error_types_without_raw_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def run() -> None:
        fixture = _offline_node(tmp_path)
        name = fixture.prefix + "-node"
        fixture.state["containers"] = [{"name": name}]
        fixture.last_probe = {
            "port": 12345,
            "socks_ready": True,
            "stage": "payload_read",
            "reason": "IncompleteReadError",
            "raw_config": "SHOULD_NOT_APPEAR",
        }
        calls: list[tuple[str, ...]] = []

        def docker_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            command = tuple(args[3:])
            calls.append(command)
            if command[0] == "inspect":
                return subprocess.CompletedProcess(
                    args,
                    0,
                    stdout=json.dumps(
                        {
                            "Running": False,
                            "OOMKilled": True,
                            "ExitCode": 137,
                            "Status": "exited",
                            "Error": "SHOULD_NOT_APPEAR",
                        }
                    ),
                    stderr="SHOULD_NOT_APPEAR",
                )
            assert command[0] in {"logs", "exec"}
            if command[0] == "exec":
                return subprocess.CompletedProcess(
                    args, 0, stdout="invalid request user id: SHOULD_NOT_APPEAR", stderr=""
                )
            return subprocess.CompletedProcess(
                args,
                0,
                stdout="",
                stderr=(
                    "invalid user SHOULD_NOT_APPEAR; "
                    "blocked target SHOULD_NOT_APPEAR; out of memory"
                ),
            )

        monkeypatch.setattr(node_harness.subprocess, "run", docker_run)
        try:
            await fixture.capture_failure()
            report = (fixture.directory / "report.json").read_text()
            assert "SHOULD_NOT_APPEAR" not in report
            assert object_dict(fixture.evidence["last_probe"])["reason"] == "IncompleteReadError"
            containers = cast(list[dict[str, object]], fixture.evidence["failure_containers"])
            assert containers == [
                {
                    "name": name,
                    "state": {"Running": False, "OOMKilled": True, "ExitCode": 137},
                    "status": "exited",
                    "log_error_types": ["invalid_user", "out_of_memory", "xray_target_blocked"],
                    "kernel_error_types": ["invalid_request", "request_identity_rejected"],
                }
            ]
            assert calls[0] == (
                "inspect",
                "--format",
                "{{json .State}}",
                name,
            )
            assert calls[1] == ("logs", "--tail", "40", name)
        finally:
            fixture.close_lock()

    asyncio.run(run())


class LiveScenario:
    def __init__(self, factory: async_sessionmaker[AsyncSession], fixture: LiveNode) -> None:
        self.factory = factory
        self.sessions = cast(sessionmaker, factory)
        self.fixture = fixture
        self.panel = fixture.panel
        self.services: list[str] = []

    async def saved(self, index: int) -> tuple[UserService, ServiceConnection]:
        async with self.factory() as session:
            service = await session.get(UserService, self.services[index])
            connection = await session.get(ServiceConnection, self.services[index])
            assert service and connection
            return service, connection

    async def remote(self, index: int) -> dict[str, object]:
        _, connection = await self.saved(index)
        assert connection.panel_user_uuid
        result = await self.panel.get_user_by_uuid_lookup(connection.panel_user_uuid)
        assert result.get("ok") is True
        return object_dict(result["user"])

    async def operation(self, operation_id: str) -> ServiceOperationExecution:
        async with self.factory() as session:
            result = await session.get(ServiceOperationExecution, operation_id)
            assert result
            return result

    async def change(self, index: int, action: str, key: str) -> str:
        async with self.factory.begin() as session:
            service = await session.get(UserService, self.services[index])
            assert service
            _, order, duplicate = await change_service(
                session,
                service_id=service.id,
                user_id=1,
                actor_id=2,
                expected_revision=service.revision,
                idempotency_key=key,
                change=ServiceChange.model_validate(
                    {
                        "action": action,
                        **(
                            {"days": 1, "price": "0", "currency": "CNY"}
                            if action == "renew"
                            else {}
                        ),
                    }
                ),
            )
            assert not duplicate
            operation = await session.scalar(
                select(ServiceOperationExecution).where(
                    ServiceOperationExecution.order_id == order.id
                )
            )
            assert isinstance(operation, ServiceOperationExecution)
            assert operation.status == "pending"
            assert operation.attempt_count == 0 and operation.attempted_at is None
            identity = operation.id
            assert isinstance(identity, str)
            return identity

    async def synchronize(self, index: int, operation_id: str) -> None:
        await service_change_sync.synchronize_service_change(
            self.sessions, self.services[index], self.panel
        )
        operation = await self.operation(operation_id)
        assert operation.status == "succeeded" and operation.completed_at
        assert operation.attempt_count >= 1 and operation.attempted_at
        assert operation.first_failed_at is None
        self.fixture.evidence["operation_" + operation_id] = {
            "phase": operation.phase,
            "target_revision": operation.target_revision,
            "status": operation.status,
            "attempt_count": operation.attempt_count,
            "attempted_at": operation.attempted_at.isoformat(),
            "completed_at": operation.completed_at.isoformat(),
        }

    async def prepare(self, squad: str) -> None:
        async with self.factory.begin() as session:
            session.add(AccountRole(user_id=2, role="admin"))
            plan = await save_plan(
                session,
                terms=sample_terms(quota_bytes=64 * 1024 * 1024, squad_uuids=[squad]),
                enabled=True,
                actor_id=2,
            )
            for key in ("first", "second"):
                service, _, _ = await activate_service(
                    session,
                    user_id=1,
                    actor_id=2,
                    plan_id=plan.id,
                    expected_revision=1,
                    idempotency_key=key,
                )
                self.services.append(service.id)
                self.fixture.remember_service(service.id)
        for index, service_id in enumerate(self.services):
            await provision_service_identity(self.sessions, service_id, self.panel)
            await synchronize_service_usage(self.sessions, service_id, self.panel)
            async with self.factory.begin() as session:
                await request_service_delivery(
                    session,
                    service_id=service_id,
                    user_id=1,
                    actor_id=2,
                    expected_revision=1,
                    idempotency_key="deliver:" + service_id,
                )
            await deliver_service_identity(self.sessions, service_id, self.panel)
            _, connection = await self.saved(index)
            assert connection.state == "ready" and not connection.sync_pending
            remote = await self.remote(index)
            assert remote["status"] == "ACTIVE"
            port = await self.fixture.client(str(remote["vlessUuid"]))
            await eventually(partial(self.fixture.transfer, port))

    async def associations(self, expected_status: str) -> None:
        settings = Settings(
            BOT_TOKEN="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
            POSTGRES_USER="unused",
            POSTGRES_PASSWORD="unused",
            ADMINS=[],
            ADMIN_PANEL_STATS_CACHE_TTL_SECONDS=0,
            _env_file=None,
        )
        app = web.Application(middlewares=[admin_auth_middleware])
        app[SETTINGS] = settings
        app[SESSION_FACTORY] = self.sessions
        app[PANEL_SERVICE] = self.panel
        setup_admin_console_nodes_routes(app)
        headers = {"Authorization": "Bearer " + create_webapp_session_token(settings, 2)}
        async with TestClient(TestServer(app)) as client:

            async def observed() -> bool:
                response = await client.get(
                    f"/api/admin/console/nodes/{self.fixture.node_id}", headers=headers
                )
                assert response.status == 200
                body = object_dict(await response.json())
                node = object_dict(body["node"])
                if node["status"] != expected_status:
                    return False
                assert body["associations_complete"] is True
                assert body["service_total"] == 2 and body["customer_total"] == 1
                assert {
                    object_dict(row)["id"] for row in cast(list[object], body["services"])
                } == set(self.services)
                assert {
                    object_dict(row)["user_id"] for row in cast(list[object], body["services"])
                } == {1}
                assert node["observed_at"] and node["profile_id"] and node["inbound_ids"]
                assert {object_dict(row)["id"] for row in cast(list[object], body["hosts"])} == {
                    self.fixture.host_id
                }
                self.fixture.evidence["node_" + expected_status] = body
                return True

            await eventually(observed)
            for service_id in self.services:
                response = await client.get(
                    f"/api/admin/console/services/{service_id}/resources", headers=headers
                )
                assert response.status == 200
                body = object_dict(await response.json())
                assert body["coverage"] == "complete"
                assert body["configured_group_ids"] == [self.fixture.squad_id]
                assert {object_dict(row)["id"] for row in cast(list[object], body["nodes"])} == {
                    self.fixture.node_id
                }
                assert {object_dict(row)["id"] for row in cast(list[object], body["hosts"])} == {
                    self.fixture.host_id
                }
                assert body["remote_authorization_verified"] is False

    async def restrict(self, *, banned: bool) -> None:
        indices = (0, 1) if banned else (0,)
        rights = [await self.saved(index) for index in indices]
        tasks = []
        try:
            for index in indices:
                started = asyncio.Event()
                tasks.append(
                    asyncio.create_task(self.fixture.stream(self.fixture.ports[index], started))
                )
                await asyncio.wait_for(started.wait(), 5)
            started_at = time.monotonic()
            if banned:
                async with self.factory.begin() as session:
                    await set_account_ban(session, user_id=1, actor_id=2, banned=True)
                async with self.factory() as session:
                    job = await synchronize_account_access(session, 1, self.panel)
                    assert job and not job.pending and job.attempted_at
                    self.fixture.evidence["account_access_sync"] = {
                        "pending": job.pending,
                        "attempted_at": job.attempted_at.isoformat(),
                        "last_error": job.last_error,
                    }
            else:
                operation_id = await self.change(0, "pause", "pause")
                await self.synchronize(0, operation_id)
            confirmed_at = time.monotonic()
            results = await asyncio.wait_for(asyncio.gather(*tasks), 20)
            assert all(
                result.received > 0 and result.reason != "timeout" and result.ended >= started_at
                for result in results
            )
            for index, (before, previous) in zip(indices, rights, strict=True):
                await self.fixture.blocked(self.fixture.ports[index])
                service, connection = await self.saved(index)
                assert service.expires_at == before.expires_at
                assert service.quota_bytes == before.quota_bytes
                assert service.used_bytes >= before.used_bytes
                assert connection.panel_user_uuid == previous.panel_user_uuid
                async with self.factory() as session:
                    user = await session.get(User, 1)
                    diagnostic = await service_diagnostics(
                        service, connection, None, user, self.panel
                    )
                assert diagnostic.remote.status in {"DISABLED", "LIMITED", "EXPIRED"}
                assert diagnostic.remote.observed_at and diagnostic.target_access == "disabled"
                assert diagnostic.data_plane_verified is False
            if not banned:
                assert await self.fixture.transfer(self.fixture.ports[1])
            self.fixture.evidence["ban" if banned else "pause"] = {
                "requested_monotonic": started_at,
                "confirmed_monotonic": confirmed_at,
                "streams": [asdict(result) for result in results],
                "retained_configs": "rejected",
                "observed_at": datetime.now(UTC).isoformat(),
            }
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def unban(self) -> None:
        # Keep the second service paused: unban must not override service-level restrictions.
        operation_id = await self.change(1, "pause", "pause-before-unban")
        await self.synchronize(1, operation_id)
        async with self.factory.begin() as session:
            await set_account_ban(session, user_id=1, actor_id=2, banned=False)
        async with self.factory() as session:
            job = await synchronize_account_access(session, 1, self.panel)
            assert job and not job.pending
        await eventually(lambda: self.fixture.transfer(self.fixture.ports[0]))
        await self.fixture.blocked(self.fixture.ports[1])
        operation_id = await self.change(1, "resume", "resume-after-unban")
        await self.synchronize(1, operation_id)
        await eventually(lambda: self.fixture.transfer(self.fixture.ports[1]))
        self.fixture.evidence["unban"] = (
            "active service restored; paused service remained blocked until resume"
        )

    async def race(self) -> None:
        before, connection = await self.saved(0)
        pause = await self.change(0, "pause", "race-pause")
        entered, release = asyncio.Event(), asyncio.Event()
        original = service_change_sync._synchronize_saved_change

        async def gated(
            factory: sessionmaker,
            service_id: str,
            panel: ServiceEntitlementPanel,
            intent: tuple[int | None, int],
        ) -> bool:
            entered.set()
            await release.wait()
            result = await original(factory, service_id, panel, intent)
            assert isinstance(result, bool)
            return result

        task = None
        try:
            with patch.object(service_change_sync, "_synchronize_saved_change", gated):
                task = asyncio.create_task(
                    service_change_sync.synchronize_service_change(
                        self.sessions, self.services[0], self.panel
                    )
                )
                await asyncio.wait_for(entered.wait(), 10)
                pending = await self.operation(pause)
                assert (
                    pending.status == "unknown"
                    and pending.attempt_count == 1
                    and pending.attempted_at
                )
                renew = await self.change(0, "renew", "race-renew")
                release.set()
                await task
            assert (await self.operation(pause)).status == "superseded"
            await self.synchronize(0, renew)
            after, current = await self.saved(0)
            assert after.revision == before.revision + 2 and after.desired_status == "paused"
            assert as_utc(after.expires_at) == as_utc(before.expires_at) + timedelta(days=1)
            assert (
                current.panel_user_uuid == connection.panel_user_uuid
                and after.quota_bytes == before.quota_bytes
            )
            await self.fixture.blocked(self.fixture.ports[0])
            assert await self.fixture.transfer(self.fixture.ports[1])
            resume = await self.change(0, "resume", "race-resume")
            await self.synchronize(0, resume)
            await eventually(lambda: self.fixture.transfer(self.fixture.ports[0]))
            self.fixture.evidence["race"] = (
                "in-flight pause superseded by one renewal; latest paused intent enforced"
            )
        finally:
            release.set()
            if task is not None:
                await asyncio.gather(task, return_exceptions=True)

    async def unknown_retry(self) -> None:
        before, connection = await self.saved(0)
        remote_before = await self.remote(0)
        renewal = await self.change(0, "renew", "uncertain-renew")
        wrote = False

        async def lose_local_result(
            session: AsyncSession,
            user: User,
            service: UserService,
            saved_connection: ServiceConnection,
            *,
            confirmed: bool,
        ) -> None:
            nonlocal wrote
            assert confirmed and not saved_connection.sync_pending
            observed = await self.remote(0)
            assert observed["uuid"] == remote_before["uuid"]
            assert as_utc(
                datetime.fromisoformat(str(observed["expireAt"]).replace("Z", "+00:00"))
            ).isoformat(timespec="milliseconds") == as_utc(service.expires_at).isoformat(
                timespec="milliseconds"
            )
            wrote = True
            raise RuntimeError("Injected loss of local finalization after real remote read-back")

        with (
            patch.object(service_change_sync, "record_entitlement_result", lose_local_result),
            pytest.raises(RuntimeError, match="Injected loss"),
        ):
            await service_change_sync.synchronize_service_change(
                self.sessions, self.services[0], self.panel
            )
        assert wrote
        unknown = await self.operation(renewal)
        assert unknown.status == "unknown" and unknown.attempt_count == 1 and unknown.attempted_at
        assert unknown.first_failed_at is None and unknown.completed_at is None
        for expected_duplicate in (False, True):
            async with self.factory.begin() as session:
                operation, _, duplicate = await retry_execution(
                    session,
                    service_id=self.services[0],
                    operation_id=renewal,
                    user_id=1,
                    actor_id=2,
                    expected_revision=before.revision + 1,
                    idempotency_key="retry-uncertain-renew",
                )
                assert duplicate is expected_duplicate and operation.status == "unknown"
                assert (
                    operation.attempted_at == unknown.attempted_at and operation.attempt_count == 1
                )
        await self.synchronize(0, renewal)
        result = await self.operation(renewal)
        assert result.attempt_count == 2 and result.first_failed_at is None
        after, current = await self.saved(0)
        remote_after = await self.remote(0)
        assert after.revision == before.revision + 1
        assert as_utc(after.expires_at) == as_utc(before.expires_at) + timedelta(days=1)
        assert current.panel_user_uuid == connection.panel_user_uuid
        assert after.quota_bytes == before.quota_bytes and after.used_bytes >= before.used_bytes
        assert remote_after["uuid"] == remote_before["uuid"]
        assert remote_after["trafficLimitBytes"] == remote_before["trafficLimitBytes"]
        original_identity = hashlib.sha256(str(remote_before["vlessUuid"]).encode()).digest()
        retried_identity = hashlib.sha256(str(remote_after["vlessUuid"]).encode()).digest()
        assert retried_identity == original_identity
        async with self.factory() as session:
            for key in ("uncertain-renew", "retry-uncertain-renew"):
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(ServiceOrder)
                        .where(ServiceOrder.idempotency_key == key)
                    )
                    == 1
                )
        assert await self.fixture.transfer(self.fixture.ports[0])
        self.fixture.evidence["unknown_retry"] = {
            "operation_id": renewal,
            "attempt_count": result.attempt_count,
            "unknown_attempted_at": unknown.attempted_at.isoformat(),
            "completed_at": result.completed_at.isoformat() if result.completed_at else None,
            "first_failed_at": None,
            "renewal_orders": 1,
            "retry_orders": 1,
        }


@pytest.mark.filterwarnings(
    "ignore:It is recommended to use web.RequestKey: aiohttp.web_exceptions.NotAppKeyWarning"
)
@pytest.mark.skipif(
    os.environ.get("QA_SERVICE_OPERATIONS_LIVE_NODE") != "1",
    reason="Requires explicit exclusive local real Node evidence slot",
)
def test_real_node_service_operations_and_retained_configurations() -> None:
    require_environment()  # Must run before scenario creates its temporary schema.
    fixture: LiveNode | None = None

    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        nonlocal fixture
        panel = _panel_service()
        fixture = LiveNode(panel)
        print(f"Local Node evidence manifest: {fixture.manifest}", flush=True)
        try:
            async with factory() as session:
                fixture.state["schema"] = await session.scalar(text("SELECT current_schema()"))
                fixture.save()
            squad = await fixture.setup()
            scenario_run = LiveScenario(factory, fixture)
            await scenario_run.prepare(squad)
            await scenario_run.associations("online")
            await scenario_run.restrict(banned=False)
            resume = await scenario_run.change(0, "resume", "resume")
            await scenario_run.synchronize(0, resume)
            await eventually(lambda: fixture.transfer(fixture.ports[0]))
            await scenario_run.race()
            await scenario_run.unknown_retry()
            await scenario_run.restrict(banned=True)
            await scenario_run.unban()
            await fixture.docker("stop", fixture.prefix + "-node")
            await scenario_run.associations("offline")
            await fixture.docker("start", fixture.prefix + "-node")
            await eventually(lambda: fixture.transfer(fixture.ports[0]))
            await scenario_run.associations("online")
            for index in (0, 1):
                path = fixture.directory / f"client-{index}.json"
                assert (
                    hashlib.sha256(path.read_bytes()).hexdigest()
                    == fixture.state[f"client_{index}_sha256"]
                )
            fixture.evidence["state"] = "passed"
        except BaseException as exc:
            fixture.evidence["state"] = "failed"
            fixture.evidence["failure_type"] = type(exc).__name__
            await fixture.capture_failure()
            raise
        finally:
            try:
                cleanup = asyncio.create_task(fixture.cleanup())
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    await cleanup
                    raise
            finally:
                fixture.close_lock()
                await panel.close_session()

    scenario(run)
    assert fixture is not None
    fixture.evidence["schema_cleanup"] = "temporary schema dropped by scenario finally"
    private_json(fixture.directory / "report.json", fixture.evidence)
    fixture.manifest.unlink()
