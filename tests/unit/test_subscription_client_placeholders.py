"""Offline pinned no-Host semantics; fixtures never supply proxies to a real core."""

from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import quote, urlsplit
from uuid import uuid4

import pytest
from aiohttp.test_utils import make_mocked_request

from tests.support import node_onboarding_live_node as bridge
from tests.support import subscription_client_observation as observation
from tests.support import subscription_client_runtime as runtime
from tests.unit.test_node_onboarding_live_support import no_environment as no_environment
from tests.unit.test_subscription_client_authorization import observed_directory
from tests.unit.test_subscription_client_runtime import setup_client, subscription

NAMES = ["No hosts found", "No published nodes", "Contact administrator", "Refresh later"]
PREFIX = "vless://00000000-0000-0000-0000-000000000000@0.0.0.0:1"
PARAMS = "?encryption=none&type=tcp&security=none"


def placeholder_body(names: list[str] = NAMES) -> bytes:
    # Mirrors 3.4.5 createFallbackHosts + XrayGeneratorService; labels are only fixtures.
    return "\n".join(PREFIX + PARAMS + "#" + quote(name, safe="") for name in names).encode()


@pytest.mark.parametrize("encoded", [False, True])
@pytest.mark.parametrize("count", [1, 4, 16])
def test_pinned_placeholders_are_inspected_without_rewriting_native_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, encoded: bool, count: int
) -> None:
    row = setup_client(tmp_path, monkeypatch)
    names = [f"No hosts {index}" for index in range(count)]
    body = placeholder_body(names)
    if encoded:
        body = base64.b64encode(body)
    cached = tmp_path / "0" / "provider.txt"
    cached.write_bytes(body)
    assert runtime.placeholder_names(0) == names
    assert cached.read_bytes() == body
    assert runtime.read_json(tmp_path / "0" / "descriptor.json") == row


@pytest.mark.parametrize(
    "fault",
    [
        "service_identity",
        "foreign_identity",
        "service_host",
        "service_ip",
        "port",
        "protocol",
        "encryption",
        "security",
        "transport",
        "extra",
        "duplicate_param",
        "missing_param",
        "path",
        "mixed_authorized",
        "invalid_base64",
        "html",
        "yaml",
        "empty",
        "duplicate_name",
        "reserved_name",
        "empty_name",
        "control_name",
        "oversized_name",
        "oversized_count",
        "symlink",
        "missing_cache",
    ],
)
def test_arbitrary_changed_subscription_is_not_a_no_hosts_placeholder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    row = setup_client(tmp_path, monkeypatch)
    cached = tmp_path / "0" / "provider.txt"
    body = placeholder_body()
    substitutions = {
        "service_identity": (
            b"00000000-0000-0000-0000-000000000000",
            str(row["identity"]).encode(),
        ),
        "foreign_identity": (b"00000000-0000-0000-0000-000000000000", str(uuid4()).encode()),
        "service_host": (b"0.0.0.0", str(row["host"]).encode()),
        "service_ip": (b"0.0.0.0", str(row["node_ip"]).encode()),
        "port": (b":1?", b":12080?"),
        "protocol": (b"vless://", b"trojan://"),
        "encryption": (b"encryption=none", b"encryption=other"),
        "security": (b"security=none", b"security=tls"),
        "transport": (b"type=tcp", b"type=ws"),
        "extra": (b"type=tcp", b"type=tcp&sni=other"),
        "duplicate_param": (b"type=tcp", b"type=tcp&type=tcp"),
        "missing_param": (b"encryption=none&", b""),
        "path": (b":1?", b":1/other?"),
    }
    if fault in substitutions:
        body = body.replace(*substitutions[fault])
    if fault == "mixed_authorized":
        body += b"\n" + base64.b64decode(subscription(row))
    if fault in {"invalid_base64", "html", "yaml", "empty"}:
        body = {
            "invalid_base64": b"%invalid",
            "html": b"<html>error</html>",
            "yaml": b"proxies: []",
            "empty": b"",
        }[fault]
    if fault in {
        "duplicate_name",
        "reserved_name",
        "empty_name",
        "control_name",
        "oversized_name",
        "oversized_count",
    }:
        names = {
            "duplicate_name": ["same", "same"],
            "reserved_name": ["DIRECT"],
            "empty_name": [""],
            "control_name": ["bad\nname"],
            "oversized_name": ["a" * 513],
            "oversized_count": [str(index) for index in range(17)],
        }[fault]
        body = placeholder_body(names)
    cached.write_bytes(body)
    if fault in {"symlink", "missing_cache"}:
        cached.unlink()
    if fault == "symlink":
        outside = tmp_path / "outside"
        outside.write_bytes(body)
        cached.symlink_to(outside)
    with pytest.raises(ValueError):
        runtime.placeholder_names(0)


@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "source_mismatch",
        "loaded_extra",
        "loaded_wrong_name",
        "loaded_direct",
        "wrong_status",
        "source_failure",
        "changed_config",
    ],
)
def test_refresh_requires_original_url_exact_source_cache_and_loaded_placeholder_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    row = setup_client(tmp_path, monkeypatch)
    directory = observed_directory(tmp_path, monkeypatch)
    monkeypatch.setattr(runtime, "TLS", directory)
    monkeypatch.setattr(runtime, "ready", Mock())
    cached = tmp_path / "0" / "provider.txt"
    body = base64.b64encode(placeholder_body())
    updated = False

    def api(index: int, method: str, path: str) -> tuple[int, bytes]:
        nonlocal updated
        assert (index, path) == (0, "/providers/proxies/service")
        if method == "GET":
            proxies = (
                [{"name": name, "type": "Vless"} for name in NAMES]
                if updated
                else [{"name": "test node", "type": "Vless"}]
            )
            if updated and case == "loaded_extra":
                proxies.append({"name": "test node", "type": "Vless"})
            if updated and case == "loaded_wrong_name":
                proxies[0]["name"] = "different"
            if updated and case == "loaded_direct":
                proxies[0]["type"] = "Direct"
            return 200, json.dumps({"proxies": proxies}).encode()
        assert method == "PUT"
        registration = runtime.read_json(directory / "request.json")
        assert registration["url"] == row["url"]
        target = urlsplit(str(row["url"]))
        request = make_mocked_request(
            "GET", target.path + "?" + target.query, headers={"Host": bridge.LOCAL_AUTHORITY}
        )
        observation.record_response(
            directory,
            request,
            body,
            Mock(
                status=503 if case == "source_failure" else 200,
                headers={"Content-Type": "text/plain"},
            ),
        )
        cached.write_bytes(
            body if case != "source_mismatch" else base64.b64encode(placeholder_body(["unrelated"]))
        )
        if case == "changed_config":
            runtime.private_json(tmp_path / "0" / "config.json", {"changed": True})
        updated = True
        return (500, b"{}") if case == "wrong_status" else (204, b"")

    monkeypatch.setattr(runtime, "api", api)
    if case in {"source_mismatch", "loaded_extra", "loaded_wrong_name", "loaded_direct"}:
        with pytest.raises(
            runtime.NativeEvidenceError, match="native_placeholder_source_or_provider_mismatch"
        ):
            runtime.refresh_revoked(0)
    else:
        result = runtime.refresh_revoked(0)
        assert result["verified"] is (case == "valid")
        assert result["cache_behavior"] == "changed"
        if case == "valid":
            expected = [hashlib.sha256(name.encode()).hexdigest() for name in NAMES]
            assert result["placeholders"] == {
                "contract": "remnawave_3_4_5_no_hosts_fallback",
                "native_proxy_names_sha256": expected,
                "source_matches_native_cache": True,
                "revoked_identity_absent": True,
                "revoked_endpoint_absent": True,
            }
        encoded_result = json.dumps(result)
        assert "private" not in encoded_result and str(row["identity"]) not in encoded_result
        assert all(name not in encoded_result for name in NAMES)
        assert cached.read_bytes() == body
    assert runtime.read_json(directory / "request.json") == {"url": row["url"]}


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "unknown_name",
        "select_failure",
        "wrong_selected",
        "extra_selected",
        "payload_received",
        "state_changed",
    ],
)
def test_each_placeholder_is_natively_selected_rechecked_and_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    setup_client(tmp_path, monkeypatch)
    (tmp_path / "0" / "provider.txt").write_bytes(base64.b64encode(placeholder_body()))
    state: dict[str, object] = {
        "proxies": runtime.placeholder_metadata(NAMES),
        "cache_sha256": "same",
    }
    monkeypatch.setattr(runtime, "provider_state", Mock(return_value=state))
    selected_name: str | None = None

    def api(
        index: int, method: str, path: str, *, selection: str | None = None
    ) -> tuple[int, bytes]:
        nonlocal selected_name
        assert (index, path) == (0, "/proxies/service")
        if method == "PUT":
            assert selection in NAMES
            selected_name = selection
            return (500, b"") if fault == "select_failure" else (204, b"")
        assert method == "GET" and selection is None
        return 200, json.dumps(
            {
                "type": "Selector",
                "now": "other" if fault == "wrong_selected" else selected_name,
                "all": [*NAMES, "DIRECT"] if fault == "extra_selected" else NAMES,
            }
        ).encode()

    def exchange(index: int, token: str, op: str, size: int, *, denied: bool) -> dict[str, object]:
        assert (index, token, op, size, denied) == (0, "test-token", "P", 0, True)
        if fault == "payload_received":
            raise runtime.NativeEvidenceError("native_unauthorized_payload_received")
        if fault == "state_changed":
            monkeypatch.setattr(
                runtime, "provider_state", Mock(return_value={**state, "cache_sha256": "changed"})
            )
        return {"socks_ready": True, "outcome": "eof"}

    monkeypatch.setattr(runtime, "api", api)
    exchange_mock = Mock(side_effect=exchange)
    monkeypatch.setattr(runtime, "exchange", exchange_mock)
    for name in NAMES:
        sha = hashlib.sha256(name.encode()).hexdigest()
        if fault == "none":
            assert runtime.probe_placeholder(0, sha, "test-token") == {
                "name_sha256": sha,
                "selected": True,
                "socks_ready": True,
                "outcome": "eof",
            }
        else:
            with pytest.raises(runtime.NativeEvidenceError):
                runtime.probe_placeholder(
                    0, "unknown" if fault == "unknown_name" else sha, "test-token"
                )
            break
    if fault in {"unknown_name", "select_failure", "wrong_selected", "extra_selected"}:
        exchange_mock.assert_not_called()
    if fault == "none":
        assert exchange_mock.call_count == len(NAMES)


def test_controller_selection_transport_is_fixed_and_does_not_include_proxies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup_client(tmp_path, monkeypatch)
    stream = io.BytesIO(b"")
    response = Mock(code=204)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read = stream.read
    opener = Mock()
    opener.open.return_value = response
    monkeypatch.setattr(runtime, "build_opener", Mock(return_value=opener))
    assert runtime.api(0, "PUT", "/proxies/service", selection=NAMES[0]) == (204, b"")
    request = opener.open.call_args.args[0]
    assert request.full_url == "http://127.0.0.1:19080/proxies/service"
    assert json.loads(request.data) == {"name": NAMES[0]}
    assert request.get_header("Content-type") == "application/json"
    for method, path, selection in [
        ("PUT", "/configs", "x"),
        ("PUT", "/providers/proxies/service", "x"),
        ("PUT", "/proxies/other", "x"),
        ("GET", "/proxies/service", "x"),
        ("PUT", "/proxies/service", None),
        ("PUT", "/proxies/service", ""),
    ]:
        with pytest.raises(runtime.NativeEvidenceError):
            runtime.api(0, method, path, selection=selection)
    assert opener.open.call_count == 1
