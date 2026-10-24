"""Pinned resource payloads and actual transport receipts, with no network."""

import asyncio
import json
import logging
from typing import ClassVar
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pydantic import ValidationError

from bot.services.panel_api_contracts import operation_contract
from bot.services.panel_api_service import PanelApiService
from bot.services.panel_dry_run_api_service import PanelDryRunApiService
from bot.services.resource_operation_panel import dispatch_resource, resource_payload
from bot.services.resource_operations import CHANGE_ADAPTER
from tests.unit.test_admin_console_resource_preview import G1, H1, I1, N1, SECRET
from tests.unit.test_exit_replacement_transport import Reply
from tests.unit.test_resource_operations import CREATED, create_change, live_settings


class ResourceReply(Reply):
    headers: ClassVar[dict[str, str]] = {"Content-Type": "application/json"}


@pytest.mark.parametrize(
    "change,method,path",
    [
        (create_change("node"), "POST", "/nodes"),
        (create_change("host"), "POST", "/hosts"),
        (create_change("group"), "POST", "/internal-squads"),
        (
            {"operation": "group_inbounds", "target_id": G1, "inbound_ids": [I1]},
            "PATCH",
            "/internal-squads",
        ),
        (
            {"operation": "host_update", "target_id": H1, "patch": {"is_disabled": True}},
            "PATCH",
            "/hosts",
        ),
        ({"operation": "node_enable", "target_id": N1}, "POST", f"/nodes/{N1}/actions/enable"),
        ({"operation": "node_disable", "target_id": N1}, "POST", f"/nodes/{N1}/actions/disable"),
        ({"operation": "node_restart", "target_id": N1}, "POST", f"/nodes/{N1}/actions/restart"),
    ],
)
def test_supported_payloads_use_only_pinned_fields(
    change: dict[str, object], method: str, path: str
) -> None:
    typed = CHANGE_ADAPTER.validate_python(change)
    operation, endpoint, payload = resource_payload(typed, "a" * 32)
    assert endpoint == path and operation_contract(operation).method == method
    assert operation_contract(operation).mutation
    if change["operation"] != "node_restart":
        assert not operation_contract(operation).idempotent
    assert SECRET not in str(payload)
    if change["operation"] == "group_create":
        assert payload == {"name": "New group", "inbounds": [I1]}
    if change["operation"] == "host_update":
        assert payload == {"uuid": H1, "isDisabled": True}
        assert typed.model_dump(mode="json")["patch"] == {"is_disabled": True}


@pytest.mark.parametrize(
    "operation,status,body,result",
    [
        ("node_disable", 200, {"response": {"uuid": N1}}, "accepted"),
        ("node_disable", 202, {"response": {"uuid": N1}}, "unknown"),
        ("node_disable", 204, None, "unknown"),
        ("node_disable", 200, {"response": {"uuid": CREATED}}, "unknown"),
        ("node_disable", 200, {"error": True, "response": {"uuid": N1}}, "unknown"),
        ("node_disable", 500, {"password": SECRET}, "unknown"),
        ("node_disable", 403, {"password": SECRET}, "rejected"),
        ("node_restart", 202, {"response": True}, "accepted"),
        ("node_restart", 200, {"response": True}, "unknown"),
        ("node_restart", 202, None, "accepted"),
    ],
)
def test_raw_http_status_and_identity_control_receipt(
    operation: str,
    status: int,
    body: object,
    result: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    panel = PanelApiService(live_settings())
    panel.base_url = "https://panel.invalid/api"
    transport = Mock()
    transport.request.return_value = ResourceReply(
        status, json.dumps(body) if body is not None else ""
    )
    typed = CHANGE_ADAPTER.validate_python({"operation": operation, "target_id": N1})
    with (
        patch.object(panel, "_get_session", AsyncMock(return_value=transport)),
        patch.object(panel, "_prepare_headers", AsyncMock(return_value={"Authorization": SECRET})),
    ):
        receipt = asyncio.run(dispatch_resource(panel, typed, "a" * 32))
    assert receipt.result == result
    transport.request.assert_called_once()
    assert SECRET not in caplog.text and SECRET not in str(receipt)


def test_transport_timeout_is_unknown_without_retry_or_secret(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    panel = PanelApiService(live_settings())
    panel.base_url = "https://panel.invalid/api"
    transport = Mock()
    transport.request.side_effect = TimeoutError(SECRET)
    change = CHANGE_ADAPTER.validate_python(create_change("node"))
    with (
        patch.object(panel, "_get_session", AsyncMock(return_value=transport)),
        patch.object(panel, "_prepare_headers", AsyncMock(return_value={})),
    ):
        assert asyncio.run(dispatch_resource(panel, change, "a" * 32)).result == "unknown"
    transport.request.assert_called_once()
    assert SECRET not in caplog.text


def test_dry_run_blocks_real_client_as_well_as_dry_run_client() -> None:
    settings = live_settings()
    settings.PANEL_WRITE_MODE = "dry_run"
    change = CHANGE_ADAPTER.validate_python(create_change("host"))
    for panel in (PanelApiService(settings), PanelDryRunApiService(settings)):
        with patch.object(panel, "_request_once", AsyncMock()) as request:
            assert asyncio.run(dispatch_resource(panel, change, "a" * 32)).result == "rejected"
            request.assert_not_awaited()


@pytest.mark.parametrize(
    "change",
    [
        create_change("host") | {"group_ids": []},
        create_change("node") | {"port": True},
        create_change("node") | {"address": "https://user:password@node.invalid"},
        create_change("host") | {"privateKey": SECRET},
        {"operation": "host_update", "target_id": H1, "patch": {"port": None}},
    ],
)
def test_invalid_or_secret_fields_are_rejected(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        CHANGE_ADAPTER.validate_python(change)
