"""Offline onboarding initialization and F07 evidence boundaries; no live environment."""

from __future__ import annotations

import asyncio
import hashlib
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
import sqlalchemy.ext.asyncio as sql

from bot.app.web.admin_api_impl.auth import admin_auth_middleware
from bot.app.web.cache_headers import api_no_store_middleware
from bot.app.web.context import PANEL_SERVICE, SESSION_FACTORY, SETTINGS
from bot.app.web.webapp.assets import _csrf_protection_middleware
from bot.app.web.webapp_auth import verify_webapp_session_token
from bot.services.resource_operation_panel import resource_writes_enabled
from config.settings import Settings
from tests.integration.test_node_onboarding_live_node import OnboardingScenario
from tests.qa import test_remnawave_panel_contract as panel_fixture
from tests.support.exit_replacement_live_node import ExitNode
from tests.support.node_onboarding_live_node import (
    SubscriptionEvidenceError,
    resolve_onboarding_cleanup,
)
from tests.support.node_onboarding_resource_changes import group_preview_evidence, retained_client
from tests.support.service_operations_live_node import private_json
from tests.support.settings_stub import SettingsStub


@pytest.fixture(autouse=True)
def no_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    import fcntl

    forbidden = Mock(side_effect=AssertionError("Offline test touched live infrastructure"))
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "bind", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(fcntl, "flock", forbidden)


@pytest.fixture
def node(tmp_path: Path) -> ExitNode:
    # Only the inert fixture state is needed; never acquire the shared live lock.
    result = object.__new__(ExitNode)
    result.directory = tmp_path
    result.manifest = tmp_path / "manifest.json"
    result.prefix = "uc2-offline"
    result.state = {
        "onboarding_profile": str(uuid4()),
        "onboarding_inbound": str(uuid4()),
    }
    result.squad_id, result.node_id = str(uuid4()), str(uuid4())
    result.ports = []
    result.evidence = {}
    return result


@pytest.mark.filterwarnings(
    "ignore:It is recommended to use web.RequestKey: aiohttp.web_exceptions.NotAppKeyWarning"
)
def test_full_scenario_initializes_real_settings_and_keeps_live_panel_policy(
    node: ExitNode,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        panel_fixture, "_read_env", lambda _: {"REMNAWAVE_DEV_API_TOKEN": "offline"}
    )
    monkeypatch.setenv("QA_REMNAWAVE_API_URL", "http://127.0.0.1:3000/api")
    monkeypatch.delenv("QA_REMNAWAVE_API_TOKEN", raising=False)
    monkeypatch.setenv("ADMIN_IDS", "1,3")

    async def initialize() -> None:
        node.panel = panel_fixture._panel_service()
        previous = node.panel.settings
        assert isinstance(previous, SettingsStub) and not hasattr(previous, "model_copy")
        previous_values = vars(previous).copy()
        panel_configuration = node.panel.panel_settings
        factory = sql.async_sessionmaker()
        case = OnboardingScenario(factory, node)
        try:
            assert isinstance(case.settings, Settings)
            assert case.panel is node.panel and case.panel.settings is case.settings
            assert case.settings.panel_settings == panel_configuration
            assert case.panel.base_url == "http://127.0.0.1:3000/api"
            assert case.panel.api_key == "offline"
            assert case.panel._session is None
            assert resource_writes_enabled(case.panel) is True
            assert case.settings.PANEL_WRITE_MODE == "live"
            for name in (
                "PANEL_ALL_USERS_CACHE_TTL_SECONDS",
                "PANEL_USER_CACHE_TTL_SECONDS",
                "PANEL_DEVICES_CACHE_TTL_SECONDS",
            ):
                assert getattr(case.settings, name) == previous_values[name] == 0
            assert vars(previous) == previous_values
            assert case.settings.ADMIN_IDS_STR == "" and case.settings.REDIS_URL is None
            assert case.settings.ADMIN_PANEL_STATS_CACHE_TTL_SECONDS == 0
            assert case.settings.WEBAPP_SESSION_SECRET != previous.WEBAPP_SESSION_SECRET
            app = case.client.app
            assert app[SETTINGS] is case.settings and app[PANEL_SERVICE] is case.panel
            assert app[SESSION_FACTORY] is factory
            assert list(app.middlewares) == [
                api_no_store_middleware,
                _csrf_protection_middleware,
                admin_auth_middleware,
            ]
            paths = {route.resource.canonical for route in app.router.routes() if route.resource}
            assert {
                "/api/admin/console/resources/operations",
                "/api/admin/console/nodes/onboarding/deployment",
                "/api/services/{service_id}/subscription",
            } <= paths
            for owner, header in case.headers.items():
                token = header["Authorization"].removeprefix("Bearer ")
                assert verify_webapp_session_token(case.settings, token) == owner
        finally:
            await case.client.close()
            await node.panel.close_session()

    asyncio.run(initialize())


def preview(node: ExitNode, service: str) -> dict[str, object]:
    values = {
        "kind": "group",
        "id": node.squad_id,
        "name": node.prefix,
        "inbound_ids": [node.state["onboarding_inbound"]],
    }
    return {
        "coverage": "complete",
        "blockers": [],
        "remote_authorization_verified": True,
        "affected_service_ids": [service],
        "affected_customer_ids": [1],
        "fingerprint": "a" * 64,
        "observed_at": "2026-10-24T00:00:00Z",
        "current": values,
        "proposed": {**values, "inbound_ids": []},
        "recovery": "restore_previous_inbounds_and_recheck_profile_nodes",
        "direct": {
            "group_ids": [node.squad_id],
            "node_ids": [node.node_id],
            "profile_ids": [node.state["onboarding_profile"]],
            "service_total": 1,
            "customer_total": 1,
            "customer_ids": [1],
            "services": [
                {
                    "service_id": service,
                    "customer_id": 1,
                    "name": node.prefix,
                    "connection_state": "ready",
                    "group_ids": [node.squad_id],
                    "configured_group_ids": [node.squad_id],
                    "observed_group_ids": [node.squad_id],
                }
            ],
        },
        "possible_reload": {
            "group_ids": [],
            "node_ids": [node.node_id],
            "profile_ids": [node.state["onboarding_profile"]],
            "services": [],
            "customer_ids": [],
            "service_total": 0,
            "customer_total": 0,
        },
    }


def test_f07_projects_exact_existing_customer_service_and_restore_values(node: ExitNode) -> None:
    service = uuid4().hex
    before = [str(node.state["onboarding_inbound"])]
    value = preview(node, service)
    value["unused_secret"] = "must-not-be-reported"
    proof = group_preview_evidence(value, node, service, before, [])
    assert "unused_secret" not in proof
    assert proof["affected_service_ids"] == [service] and proof["affected_customer_ids"] == [1]
    value["current"], value["proposed"] = value["proposed"], value["current"]
    group_preview_evidence(value, node, service, [], before)


@pytest.mark.parametrize(
    "fault",
    [
        "extra_service",
        "wrong_customer",
        "missing_authorization",
        "partial",
        "wrong_service_owner",
        "extra_reload_group",
        "changed_group_name",
        "wrong_original_inbound",
    ],
)
def test_f07_rejects_inexact_impact_or_restore_scope(node: ExitNode, fault: str) -> None:
    service = uuid4().hex
    value = preview(node, service)
    if fault == "extra_service":
        value["affected_service_ids"] = [service, uuid4().hex]
    elif fault == "wrong_customer":
        value["affected_customer_ids"] = [3]
    elif fault == "missing_authorization":
        value["remote_authorization_verified"] = False
    elif fault == "partial":
        value["coverage"] = "partial"
    elif fault == "wrong_service_owner":
        direct = value["direct"]
        assert isinstance(direct, dict)
        direct["services"][0]["customer_id"] = 3
    elif fault == "extra_reload_group":
        reload = value["possible_reload"]
        assert isinstance(reload, dict)
        reload["group_ids"] = [str(uuid4())]
    else:
        target = value["proposed" if fault == "changed_group_name" else "current"]
        assert isinstance(target, dict)
        target["name" if fault == "changed_group_name" else "inbound_ids"] = "other"
    with pytest.raises(SubscriptionEvidenceError, match="f07_"):
        group_preview_evidence(value, node, service, [str(node.state["onboarding_inbound"])], [])


def test_f07_hashes_the_retained_service_index_and_port_not_an_earlier_probe(
    node: ExitNode,
) -> None:
    node.ports = [19001, 19002]
    private_json(node.directory / "client-0.json", {"probe": True})
    private_json(node.directory / "client-1.json", {"retained_service": True})
    path = node.directory / "client-1.json"
    node.state["client_1_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    proof = retained_client(node, 19002)
    assert proof["client_index"] == 1 and proof["socks_port"] == 19002
    private_json(node.directory / "client-0.json", {"probe": "changed"})
    assert retained_client(node, 19002) == proof
    private_json(path, {"retained_service": "changed"})
    with pytest.raises(SubscriptionEvidenceError, match="f07_retained_config_changed"):
        retained_client(node, 19002)


@pytest.mark.parametrize("outcome", ["uuid", "pending", "rejected", "unknown"])
def test_offline_http_cleanup_never_adopts_an_unknown_creation(
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    identity = str(uuid4())
    resource = {
        "endpoint": "/nodes",
        "name": "uc2-offline",
        "uuid": None,
        "operation_id": uuid4().hex,
    }
    root = Mock(spec=ExitNode)
    root.companion = None
    root.prefix = "uc2-offline"
    root.state = {"onboarding_http": True, "schema": "user_services_test_" + uuid4().hex}
    root.rows.return_value = [resource]
    operation = SimpleNamespace(
        request={"name": root.prefix},
        operation="node_create",
        target_id=identity if outcome == "uuid" else None,
        attempt_count=0 if outcome == "pending" else 1,
        attempts=[{"receipt": "rejected" if outcome == "rejected" else "unknown"}],
    )
    session = Mock(get=AsyncMock(return_value=operation))
    context = AsyncMock()
    context.__aenter__.return_value = session
    engine = Mock(dispose=AsyncMock())
    factory = Mock(return_value=engine)
    monkeypatch.setattr(sql, "create_async_engine", factory)
    monkeypatch.setattr(sql, "async_sessionmaker", Mock(return_value=Mock(return_value=context)))
    if outcome == "unknown":
        with pytest.raises(SubscriptionEvidenceError, match="unresolved_http_creation"):
            asyncio.run(resolve_onboarding_cleanup(root, "offline-transport"))
        assert resource["uuid"] is None
        root.save.assert_not_called()
    else:
        asyncio.run(resolve_onboarding_cleanup(root, "offline-transport"))
        assert root.state["resources"] == ([resource] if outcome == "uuid" else [])
        assert resource["uuid"] == (identity if outcome == "uuid" else None)
        root.save.assert_called_once()
    assert (
        factory.call_args.kwargs["connect_args"]["server_settings"]["search_path"]
        == root.state["schema"]
    )
    engine.dispose.assert_awaited_once_with()
