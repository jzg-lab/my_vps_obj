"""Offline proof boundaries for an actual native fetch after authorization removal."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from aiohttp.test_utils import make_mocked_request

from tests.support import node_onboarding_live_node as bridge
from tests.support import subscription_client_observation as observation
from tests.support import subscription_client_runtime as runtime
from tests.unit.test_node_onboarding_live_support import no_environment as no_environment
from tests.unit.test_node_onboarding_live_support import transport
from tests.unit.test_subscription_client_runtime import setup_client


def observed_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    receipts = tmp_path / "observations"
    receipts.mkdir(mode=0o700)
    monkeypatch.setattr(observation, "OBSERVATIONS", receipts)
    directory = tmp_path / "tls"
    directory.mkdir(mode=0o700)
    # Exercise the real callback using the same container-sibling module name.
    (directory / "subscription_client_observation.py").write_bytes(
        Path(observation.__file__).read_bytes()
    )
    monkeypatch.setitem(sys.modules, "subscription_client_observation", observation)
    return directory


@pytest.mark.parametrize(
    "body,kind,expected",
    [
        (b"", "text/plain", True),
        (b"\r\n \t", "text/plain", True),
        (base64.b64encode(b"\n \r"), "text/plain", True),
        (b"", "text/html", False),
        (b"<html>login</html>", "text/html", False),
        (b"invalid profile", "text/plain", False),
        (b"vless://private", "text/plain", False),
        (base64.b64encode(b"vless://private"), "text/plain", False),
    ],
)
def test_empty_source_is_not_html_or_malformed_subscription(
    body: bytes, kind: str, expected: bool
) -> None:
    assert observation.empty_subscription(body, kind) is expected


@pytest.mark.parametrize(
    "body,status", [(b"", 200), (b"unchanged private body", 200), (b"unavailable", 503)]
)
def test_bridge_records_exact_attempt_without_rewriting_body_or_publishing_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    body: bytes,
    status: int,
) -> None:
    directory = observed_directory(tmp_path, monkeypatch)
    marker = uuid4().hex
    url = "https://127.0.0.1:3010/private%2Ftoken?q=%2f"
    runtime.private_json(directory / "request.json", {"url": url, "native_observation": marker})
    _, session = transport(monkeypatch, body=body, status=status)
    request = make_mocked_request(
        "GET", "/private%2Ftoken?q=%2f", headers={"Host": bridge.LOCAL_AUTHORITY}
    )
    result = asyncio.run(bridge.proxy_subscription(request, directory))
    assert result.status == status and result.body == body
    receipt_file = observation.OBSERVATIONS / (marker + ".json")
    receipt = runtime.read_json(receipt_file)
    assert receipt == {
        "attempt": marker,
        "url_sha256": hashlib.sha256(url.encode()).hexdigest(),
        "upstream_status": status,
        "body_bytes": len(body),
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "empty_subscription": not body,
    }
    assert receipt_file.stat().st_mode & 0o777 == 0o600
    assert "private" not in receipt_file.read_text()
    assert session.get.call_args.kwargs["allow_redirects"] is False
    assert str(session.get.call_args.args[0]) == bridge.UPSTREAM + request.raw_path


def test_observer_is_inert_without_registered_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = observed_directory(tmp_path, monkeypatch)
    runtime.private_json(directory / "request.json", {"url": "https://127.0.0.1:3010/private"})
    transport(monkeypatch, body=b"actual-body")
    request = make_mocked_request("GET", "/private", headers={"Host": bridge.LOCAL_AUTHORITY})
    response = asyncio.run(bridge.proxy_subscription(request, directory))
    assert response.status == 200 and response.body == b"actual-body"
    assert list(observation.OBSERVATIONS.iterdir()) == []


@pytest.mark.parametrize("failure", ["foreign_path", "invalid_nonce", "repeated", "symlink"])
def test_observation_scope_and_one_fetch_receipt_are_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    directory = observed_directory(tmp_path, monkeypatch)
    marker = "../private" if failure == "invalid_nonce" else uuid4().hex
    runtime.private_json(
        directory / "request.json",
        {
            "url": "https://127.0.0.1:3010/private",
            "native_observation": marker,
        },
    )
    _, session = transport(monkeypatch, body=b"original")
    request = make_mocked_request(
        "GET",
        "/wrong" if failure == "foreign_path" else "/private",
        headers={"Host": bridge.LOCAL_AUTHORITY},
    )
    if failure == "symlink":
        outside = tmp_path / "outside"
        outside.write_bytes(b"untouched")
        (observation.OBSERVATIONS / (marker + ".json")).symlink_to(outside)
    if failure == "repeated":
        assert asyncio.run(bridge.proxy_subscription(request, directory)).status == 200
        original_receipt = (observation.OBSERVATIONS / (marker + ".json")).read_bytes()
    response = asyncio.run(bridge.proxy_subscription(request, directory))
    assert response.status == 502
    if failure == "foreign_path":
        session.get.assert_not_called()
    if failure == "symlink":
        assert (tmp_path / "outside").read_bytes() == b"untouched"
    if failure == "repeated":
        assert (observation.OBSERVATIONS / (marker + ".json")).read_bytes() == original_receipt


@pytest.mark.parametrize(
    "case",
    [
        "retained",
        "empty_field",
        "cleared",
        "cleared_memory_only",
        "cleared_memory_success",
        "bad_status",
        "network_error",
        "unknown_error",
        "nonempty_source",
        "source_failure",
        "html_source",
        "fallback_direct",
        "changed_cache",
        "changed_config",
    ],
)
def test_native_revocation_requires_real_empty_fetch_and_records_actual_cache_behavior(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    row = setup_client(tmp_path, monkeypatch)
    directory = observed_directory(tmp_path, monkeypatch)
    monkeypatch.setattr(runtime, "TLS", directory)
    monkeypatch.setattr(runtime, "ready", Mock())
    cached = tmp_path / "0" / "provider.txt"
    initial_cache = cached.read_bytes()
    updated = False

    def api(index: int, method: str, path: str) -> tuple[int, bytes]:
        nonlocal updated
        assert (index, path) == (0, "/providers/proxies/service")
        if method == "GET":
            proxies = (
                []
                if updated and case in {"cleared", "cleared_memory_only", "cleared_memory_success"}
                else [
                    {
                        "name": "COMPATIBLE"
                        if updated and case == "fallback_direct"
                        else "test node",
                        "type": "Direct" if updated and case == "fallback_direct" else "Vless",
                    }
                ]
            )
            return 200, json.dumps({"proxies": proxies}).encode()
        assert method == "PUT"
        updated = True
        registration = runtime.read_json(directory / "request.json")
        assert registration["url"] == row["url"]
        assert isinstance(registration["native_observation"], str)
        parts = urlsplit(str(row["url"]))
        request = make_mocked_request(
            "GET", parts.path + "?" + parts.query, headers={"Host": bridge.LOCAL_AUTHORITY}
        )
        source = b"still authorized private URI" if case == "nonempty_source" else b""
        response = Mock(
            status=503 if case == "source_failure" else 200,
            headers={"Content-Type": "text/html" if case == "html_source" else "text/plain"},
        )
        observation.record_response(directory, request, source, response)
        if case == "cleared":
            cached.unlink()
        if case == "changed_cache":
            cached.write_bytes(b"changed native cache")
        if case == "changed_config":
            runtime.private_json(tmp_path / "0" / "config.json", {"changed": True})
        message = (
            "connection refused private-url"
            if case == "network_error"
            else "unexpected private-url"
            if case == "unknown_error"
            else "file must have a `proxies` field"
            if case == "empty_field"
            else "provider need one proxy at least"
        )
        return (
            (204, b"")
            if case in {"cleared", "cleared_memory_success"}
            else (
                500 if case == "bad_status" else 503,
                json.dumps({"message": message}).encode(),
            )
        )

    monkeypatch.setattr(runtime, "api", api)
    result = runtime.refresh_revoked(0)
    assert result["verified"] is (
        case in {"retained", "empty_field", "cleared", "cleared_memory_only"}
    )
    assert result["controller_status"] == (
        204
        if case in {"cleared", "cleared_memory_success"}
        else 500
        if case == "bad_status"
        else 503
    )
    assert result["cache_behavior"] == (
        "removed" if case == "cleared" else "changed" if case == "changed_cache" else "retained"
    )
    assert result["loaded_proxy_metadata_behavior"] == (
        "cleared"
        if case in {"cleared", "cleared_memory_only", "cleared_memory_success"}
        else "changed"
        if case == "fallback_direct"
        else "retained"
    )
    assert runtime.read_json(directory / "request.json") == {"url": row["url"]}
    assert "private" not in json.dumps(result) and str(row["identity"]) not in json.dumps(result)
    assert "old_configuration_retained" not in result
    if case not in {"cleared", "changed_cache"}:
        assert cached.read_bytes() == initial_cache


@pytest.mark.parametrize("failure", ["no_fetch", "wrong_attempt", "wrong_url"])
def test_native_revocation_cannot_reuse_stale_or_absent_fetch_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    row = setup_client(tmp_path, monkeypatch)
    directory = observed_directory(tmp_path, monkeypatch)
    monkeypatch.setattr(runtime, "TLS", directory)
    monkeypatch.setattr(runtime, "ready", Mock())

    def api(index: int, method: str, path: str) -> tuple[int, bytes]:
        if method == "GET":
            return 200, b'{"proxies":[{"name":"test node","type":"Vless"}]}'
        registration = runtime.read_json(directory / "request.json")
        marker = str(registration["native_observation"])
        if failure != "no_fetch":
            runtime.private_json(
                observation.OBSERVATIONS / (marker + ".json"),
                {
                    "attempt": uuid4().hex if failure == "wrong_attempt" else marker,
                    "url_sha256": "wrong"
                    if failure == "wrong_url"
                    else hashlib.sha256(str(row["url"]).encode()).hexdigest(),
                    "upstream_status": 200,
                    "empty_subscription": True,
                },
            )
        return 503, b'{"message":"provider need one proxy at least"}'

    monkeypatch.setattr(runtime, "api", api)
    with pytest.raises((runtime.NativeEvidenceError, FileNotFoundError)):
        runtime.refresh_revoked(0)
    assert runtime.read_json(directory / "request.json") == {"url": row["url"]}
