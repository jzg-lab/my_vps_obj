"""Offline native boundary tests; no real client, Docker, socket or database IO."""

from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest

from tests.support import subscription_client_runtime as runtime
from tests.unit.test_node_onboarding_live_support import no_environment as no_environment


def service() -> dict[str, object]:
    return {
        "url": "https://127.0.0.1:3010/private%2Ftoken?q=%2f",
        "identity": str(uuid4()),
        "host": "uc2-0123456789ab-node",
        "node_ip": "172.19.0.20",
        "origin_ip": "172.19.0.10",
    }


def subscription(row: dict[str, object], *, published: bool = False) -> bytes:
    host = row["node_ip"] if published else row["host"]
    uri = (
        f"vless://{row['identity']}@{host}:12080?type=tcp&security=none&encryption=none#test%20node"
    )
    return base64.b64encode(uri.encode())


def setup_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    monkeypatch.setattr(runtime, "BASE", tmp_path)
    directory = tmp_path / "0"
    directory.mkdir()
    row = service()
    runtime.private_json(directory / "descriptor.json", row)
    runtime.private_json(directory / "config.json", runtime.config(str(row["url"]), 0, "private"))
    (directory / "provider.txt").write_bytes(subscription(row))
    return row


def test_config_contains_only_native_url_provider_and_no_test_constructed_proxies() -> None:
    url = str(service()["url"])
    config = runtime.config(url, 0, "private")
    provider = runtime.obj(runtime.obj(config["proxy-providers"])["service"])
    assert provider["url"] == url
    assert provider["type"] == "http" and provider["interval"] == 0
    assert provider["header"] == {"User-Agent": [runtime.USER_AGENT]}
    assert config["proxies"] == [] and config["rules"] == ["MATCH,service"]
    assert config["proxy-groups"] == [{"name": "service", "type": "select", "use": ["service"]}]
    assert config["bind-address"] == "127.0.0.1" and config["allow-lan"] is False
    assert config["external-controller"] == "127.0.0.1:19080"
    assert config["tun"] == {"enable": False} and config["dns"] == {"enable": False}
    assert "skip-cert-verify" not in json.dumps(config)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:3010/secret",
        "https://other/secret",
        "https://127.0.0.1:3010//other",
        "https://user:password@127.0.0.1:3010/secret",
        "https://127.0.0.1:3010/secret#fragment",
        "https://127.0.0.1:3010/secret\n",
        "https://127.0.0.1:3010/\\secret",
    ],
)
def test_nonlocal_or_ambiguous_url_refused(url: str) -> None:
    with pytest.raises(runtime.NativeEvidenceError):
        runtime.config(url, 0, "private")


def test_private_process_trust_never_inherits_host_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://private-proxy")
    monkeypatch.setenv("SSL_CERT_FILE", "/private-host-ca")
    monkeypatch.setenv("DISABLE_SYSTEM_CA", "1")
    trusted = runtime.process_env(runtime.BASE / "0", trusted=True)
    negative = runtime.process_env(runtime.BASE / "2", trusted=False)
    assert trusted["SSL_CERT_FILE"] == "/tmp/onboarding-tls/ca.pem"
    assert negative["SSL_CERT_FILE"] == "/tmp/subscription-client/empty.pem"
    for env in (trusted, negative):
        assert env["SSL_CERT_DIR"] == "/tmp/subscription-client/empty-certs"
        assert env["DISABLE_EMBED_CA"] == "1"
        assert "DISABLE_SYSTEM_CA" not in env
        assert "HTTPS_PROXY" not in env and "HTTP_PROXY" not in env
        assert env["GOMAXPROCS"] == "2" and env["GOMEMLIMIT"] == "24MiB"


def test_cache_is_inspection_only_and_compared_to_native_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = setup_client(tmp_path, monkeypatch)
    observed = {"proxies": [{"name": "test node", "type": "Vless"}]}
    api = Mock(return_value=(200, json.dumps(observed).encode()))
    monkeypatch.setattr(runtime, "api", api)
    result = runtime.snapshot(0)
    assert result["native_proxy_type"] == "vless" and result["native_proxy_count"] == 1
    assert result["credential_sha256"] == hashlib.sha256(str(row["identity"]).encode()).hexdigest()
    assert result["cache_sha256"] == hashlib.sha256(subscription(row)).hexdigest()
    assert "private" not in json.dumps(result) and str(row["identity"]) not in json.dumps(result)
    api.assert_called_once_with(0, "GET", "/providers/proxies/service")


@pytest.mark.parametrize("change", ["identity", "host", "node_ip", "protocol", "extra", "html"])
def test_wrong_cached_identity_resources_and_formats_rejected(change: str) -> None:
    row = service()
    wrong = dict(row)
    if change in {"identity", "host", "node_ip"}:
        wrong[change] = {
            "identity": str(uuid4()),
            "host": "uc2-ffffffffffff-node",
            "node_ip": "172.19.0.30",
        }[change]
    body = subscription(wrong, published=change == "node_ip")
    if change == "protocol":
        body = base64.b64decode(body).replace(b"type=tcp", b"type=ws")
    elif change == "extra":
        body = base64.b64decode(body) + b"\n" + base64.b64decode(subscription(row))
    elif change == "html":
        body = b"<html>private login</html>"
    with pytest.raises(ValueError):
        runtime.cache_evidence(body, row, published_ip=change == "node_ip")


@pytest.mark.parametrize(
    "proxies",
    [
        [],
        [{"type": "Direct", "name": "COMPATIBLE"}],
        [{"type": "Vless", "name": "wrong"}],
        [{"type": "Vless", "name": "test node"}] * 2,
    ],
)
def test_native_loaded_proxy_must_match_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    proxies: list[dict[str, str]],
) -> None:
    setup_client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        runtime, "api", Mock(return_value=(200, json.dumps({"proxies": proxies}).encode()))
    )
    with pytest.raises(runtime.NativeEvidenceError):
        runtime.snapshot(0)


def test_refresh_fetches_registered_original_url_before_inspection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = setup_client(tmp_path, monkeypatch)
    tls = tmp_path / "tls"
    tls.mkdir()
    monkeypatch.setattr(runtime, "TLS", tls)
    order: list[str] = []
    monkeypatch.setattr(runtime, "ready", lambda index: order.append("ready"))

    def api(index: int, method: str, path: str) -> tuple[int, bytes]:
        assert runtime.read_json(tls / "request.json") == {"url": row["url"]}
        assert (index, method, path) == (0, "PUT", "/providers/proxies/service")
        order.append("native-update")
        return 204, b""

    def snapshot(index: int, *, published_ip: bool) -> dict[str, object]:
        assert index == 0 and published_ip is True
        order.append("native-cache-inspection")
        return {"verified": True}

    monkeypatch.setattr(runtime, "api", api)
    monkeypatch.setattr(runtime, "snapshot", snapshot)
    assert runtime.refresh(0, published_ip=True) == {"verified": True}
    assert order == ["ready", "native-update", "native-cache-inspection"]


@pytest.mark.parametrize(
    "negative",
    [
        "certificate",
        "network",
        "success",
        "cached",
        "startup",
        "wrong_500",
        "wrong_502",
        "wrong_504",
        "wrong_400",
    ],
)
def test_negative_control_requires_certificate_refusal_and_always_reaps_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    negative: str,
) -> None:
    monkeypatch.setattr(runtime, "BASE", tmp_path)
    (tmp_path / "2").mkdir()
    monkeypatch.setattr(runtime, "register", Mock())
    ready = Mock(
        side_effect=runtime.NativeEvidenceError("unready") if negative == "startup" else None
    )
    monkeypatch.setattr(runtime, "ready", ready)
    process = Mock()
    process.__enter__ = Mock(return_value=process)
    process.__exit__ = Mock(return_value=False)
    popen = Mock(return_value=process)
    monkeypatch.setattr(runtime.subprocess, "Popen", popen)

    def response(*args: object) -> tuple[int, bytes]:
        if negative == "cached":
            (tmp_path / "2" / "provider.txt").write_bytes(b"private")
        return (
            (204, b"")
            if negative == "success"
            else (
                int(negative.removeprefix("wrong_")) if negative.startswith("wrong_") else 503,
                b"connection refused"
                if negative == "network"
                else b"x509: certificate signed by unknown authority (private URL omitted)",
            )
        )

    monkeypatch.setattr(runtime, "api", response)
    if negative == "certificate":
        assert runtime.untrusted() == {
            "controller_status": 503,
            "untrusted_ca_refused": True,
            "provider_cache_written": False,
            "core_stopped": True,
        }
    else:
        with pytest.raises(runtime.NativeEvidenceError):
            runtime.untrusted()
    process.kill.assert_called_once()
    process.wait.assert_called_once_with(timeout=5)
    assert popen.call_args.kwargs["env"]["SSL_CERT_FILE"] == str(tmp_path / "empty.pem")


def test_private_writes_do_not_follow_symlinks(tmp_path: Path) -> None:
    original = tmp_path / "original"
    original.write_text("unchanged")
    link = tmp_path / "request.json"
    link.symlink_to(original)
    with pytest.raises(runtime.NativeEvidenceError, match="native_unsafe_file"):
        runtime.private_json(link, {"secret": "private"})
    assert original.read_text() == "unchanged"


def test_prepare_creates_private_container_only_profiles_and_keeps_original_urls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime, "BASE", tmp_path)
    binary = tmp_path / "mihomo"
    binary.write_bytes(b"offline fixture")
    monkeypatch.setattr(runtime, "BINARY_SHA256", hashlib.sha256(binary.read_bytes()).hexdigest())
    first = service()
    second = {
        **service(),
        "url": "https://127.0.0.1:3010/another-private-token",
        "host": "uc2-fedcba987654-node",
        "node_ip": "172.19.0.21",
    }
    assert runtime.prepare([first, second])["prepared"] is True
    for index, row in enumerate((first, second, first)):
        directory = tmp_path / str(index)
        assert directory.stat().st_mode & 0o777 == 0o700
        assert runtime.read_json(directory / "descriptor.json") == row
        config = runtime.read_json(directory / "config.json")
        provider = runtime.obj(runtime.obj(config["proxy-providers"])["service"])
        assert provider["url"] == row["url"] and config["proxies"] == []
        assert all(path.stat().st_mode & 0o777 == 0o600 for path in directory.iterdir())
    assert binary.stat().st_mode & 0o777 == 0o700
    with pytest.raises(FileExistsError):
        runtime.prepare([first, second])


@pytest.mark.parametrize("key", ["url", "identity", "host", "node_ip"])
def test_prepare_refuses_service_identity_or_resource_aliasing_before_binary_io(
    monkeypatch: pytest.MonkeyPatch,
    key: str,
) -> None:
    first = service()
    second = {
        **service(),
        "url": "https://127.0.0.1:3010/another-private-token",
        "host": "uc2-fedcba987654-node",
        "node_ip": "172.19.0.21",
    }
    second[key] = first[key]
    forbidden = Mock(side_effect=AssertionError("Must reject before file IO"))
    monkeypatch.setattr(runtime, "digest", forbidden)
    with pytest.raises(runtime.NativeEvidenceError, match="native_services_not_distinct"):
        runtime.prepare([first, second])
    forbidden.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "shell", "index": 0},
        {"action": "register", "index": True},
        {"action": "snapshot", "index": -1},
        {"action": "snapshot", "index": 0, "published_ip": "yes"},
    ],
)
def test_unknown_commands_and_ambiguous_types_refused(payload: dict[str, object]) -> None:
    with pytest.raises(runtime.NativeEvidenceError):
        runtime.dispatch(payload)


@pytest.mark.parametrize("op,size", [("P", 0), ("U", 4096), ("D", 8192)])
def test_socks_business_payload_and_byte_receipts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    op: str,
    size: int,
) -> None:
    row = setup_client(tmp_path, monkeypatch)
    expected = (
        str(row["node_ip"]).encode().ljust(16, b" ")
        if op == "P"
        else b"K"
        if op == "U"
        else b"x" * size
    )
    received = b"\x05\x00" + b"\x05\x00\x00\x01" + bytes(6) + expected
    sock = Mock()
    sock.__enter__ = Mock(return_value=sock)
    sock.__exit__ = Mock(return_value=False)
    sock.makefile.return_value = io.BytesIO(received)
    connection = Mock(return_value=sock)
    monkeypatch.setattr(runtime.socket, "create_connection", connection)
    token = uuid4()
    result = runtime.exchange(0, str(token), op, size, denied=False)
    assert result == {"up": 21 + (size if op == "U" else 0), "down": len(expected)}
    connection.assert_called_once_with(("127.0.0.1", 10800), timeout=4)
    sent = [call.args[0] for call in sock.sendall.call_args_list]
    assert sent[0] == b"\x05\x01\x00"
    assert sent[1] == b"\x05\x01\x00\x01\xac\x13\x00\x0a" + (19090).to_bytes(2, "big")
    assert sent[2] == op.encode() + size.to_bytes(4, "big") + token.bytes
    if op == "U":
        assert sent[3] == b"u" * size


@pytest.mark.parametrize("outcome", ["refused", "eof", "payload", "dead_socks", "timeout"])
def test_rejection_requires_ready_socks_and_no_payload_not_timeout_or_dead_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    setup_client(tmp_path, monkeypatch)
    reply = b"\x05\x00" + b"\x05\x00\x00\x01" + bytes(6)
    if outcome == "refused":
        reply = b"\x05\x00\x05\x01\x00\x01"
    elif outcome == "payload":
        reply += b"unexpected successful payload"
    elif outcome == "dead_socks":
        reply = b""
    sock = Mock()
    sock.__enter__ = Mock(return_value=sock)
    sock.__exit__ = Mock(return_value=False)
    sock.makefile.return_value = io.BytesIO(reply)
    if outcome == "timeout":
        reader = Mock()
        reader.__enter__ = Mock(return_value=reader)
        reader.__exit__ = Mock(return_value=False)
        reader.read.side_effect = [b"\x05\x00", b"\x05\x00\x00\x01", bytes(6), TimeoutError()]
        sock.makefile.return_value = reader
    monkeypatch.setattr(runtime.socket, "create_connection", Mock(return_value=sock))
    if outcome in {"refused", "eof"}:
        result = runtime.exchange(0, str(uuid4()), "P", 0, denied=True)
        assert result == {
            "socks_ready": True,
            "outcome": "socks_refused" if outcome == "refused" else "eof",
        }
    else:
        with pytest.raises((runtime.NativeEvidenceError, TimeoutError)):
            runtime.exchange(0, str(uuid4()), "P", 0, denied=True)


def test_runtime_file_imports_standalone_without_repository(
    tmp_path: Path,
) -> None:
    import builtins
    import runpy

    path = tmp_path / "runtime.py"
    path.write_bytes(Path(runtime.__file__).read_bytes())
    original = builtins.__import__

    def isolated_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        assert name.split(".")[0] not in {"tests", "bot", "db", "config"}
        return original(name, globals, locals, fromlist, level)

    loaded = runpy.run_path(
        str(path),
        run_name="native_standalone",
        init_globals={
            "__builtins__": {**vars(builtins), "__import__": isolated_import},
        },
    )
    assert callable(loaded["dispatch"]) and loaded["VERSION"] == "1.19.33"
