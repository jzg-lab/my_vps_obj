"""Private, container-only Mihomo control; subscription bytes never become test-built proxies.

Copied beside the pinned binary, not installed on the host. The enclosing owned
SubscriptionTLS container is the process and secret cleanup boundary.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import BinaryIO
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import ProxyHandler, Request, build_opener
from uuid import UUID, uuid4

BASE = Path("/tmp/subscription-client")
TLS = Path("/tmp/onboarding-tls")
VERSION = "1.19.33"
BINARY_SHA256 = "8c73570d9a5f388bc2f58eee0b347ccfab84fb3cf1a0f8f2cf5eac7005fbcdc0"
ARCHIVE_SHA256 = "ba408b317080ee265c46cb923a50018c1b82cbd708551cdd46a1e3e307396187"
BINARY_ENV = "QA_NATIVE_SUBSCRIPTION_MIHOMO_BINARY"
USER_AGENT = "my-vpn-uc07-local-acceptance/1.0"
LIMIT = 2 * 1024 * 1024


class NativeEvidenceError(ValueError):
    """Fixed diagnostic code only, never native logs, URLs or credentials."""


def check(condition: bool, code: str) -> None:
    if not condition:
        raise NativeEvidenceError(code)


def obj(value: object) -> dict[str, object]:
    check(isinstance(value, dict), "native_invalid_object")
    assert isinstance(value, dict)
    check(all(isinstance(key, str) for key in value), "native_invalid_keys")
    return {str(key): item for key, item in value.items()}


def text(value: object) -> str:
    check(isinstance(value, str) and bool(value), "native_invalid_string")
    assert isinstance(value, str)
    return value


def digest(path: Path) -> str:
    check(path.is_file() and not path.is_symlink(), "native_unsafe_file")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def private_json(path: Path, value: object) -> None:
    temporary = path.with_name(path.name + ".new")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(value, stream)
    check(not path.is_symlink(), "native_unsafe_file")
    temporary.replace(path)


def original_url(value: object) -> str:
    url = text(value)
    check(
        len(url) <= 4096 and not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url),
        "native_invalid_url",
    )
    parts = urlsplit(url)
    check(
        parts.scheme == "https"
        and parts.netloc == "127.0.0.1:3010"
        and parts.path.startswith("/")
        and not parts.path.startswith("//")
        and "#" not in url
        and "\\" not in url,
        "native_nonlocal_url",
    )
    return url


def private_ip(value: object) -> str:
    address = ipaddress.IPv4Address(text(value))
    check(
        address.is_private
        and not address.is_loopback
        and not address.is_unspecified
        and not address.is_multicast,
        "native_nonprivate_target",
    )
    return str(address)


def descriptor(value: object) -> dict[str, object]:
    row = obj(value)
    check(
        set(row) == {"url", "identity", "host", "node_ip", "origin_ip"},
        "native_invalid_descriptor",
    )
    original_url(row["url"])
    UUID(text(row["identity"]))
    check(re.fullmatch(r"uc2-[0-9a-f]{12}-node", text(row["host"])) is not None, "native_host")
    private_ip(row["node_ip"])
    private_ip(row["origin_ip"])
    return row


def config(url: str, index: int, secret: str) -> dict[str, object]:
    check(type(index) is int and index in (0, 1, 2), "native_invalid_index")
    return {
        "socks-port": 10800 + index,
        "allow-lan": False,
        "bind-address": "127.0.0.1",
        "external-controller": f"127.0.0.1:{19080 + index}",
        "secret": secret,
        "mode": "rule",
        "log-level": "silent",
        "ipv6": False,
        "dns": {"enable": False},
        "tun": {"enable": False},
        "geo-auto-update": False,
        "profile": {"store-selected": False, "store-fake-ip": False},
        "proxies": [],
        "proxy-providers": {
            "service": {
                "type": "http",
                "url": original_url(url),
                "path": "./provider.txt",
                "interval": 0,
                "proxy": "DIRECT",
                "header": {"User-Agent": [USER_AGENT]},
                "health-check": {"enable": False},
            }
        },
        "proxy-groups": [{"name": "service", "type": "select", "use": ["service"]}],
        "rules": ["MATCH,service"],
    }


def process_env(directory: Path, *, trusted: bool) -> dict[str, str]:
    # Both trust controls are process-private. No inherited HTTP proxy or CA overrides.
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(directory),
        "SSL_CERT_FILE": str(TLS / "ca.pem" if trusted else BASE / "empty.pem"),
        "SSL_CERT_DIR": str(BASE / "empty-certs"),
        "DISABLE_EMBED_CA": "1",
        "GOMAXPROCS": "2",
        "GOMEMLIMIT": "24MiB",
        "GOGC": "50",
    }


def prepare(values: object) -> dict[str, object]:
    check(isinstance(values, list) and len(values) == 2, "native_requires_two_services")
    assert isinstance(values, list)
    rows = [descriptor(value) for value in values]
    for key in ("url", "identity", "host", "node_ip"):
        check(rows[0][key] != rows[1][key], "native_services_not_distinct")
    check(rows[0]["origin_ip"] == rows[1]["origin_ip"], "native_origin_changed")
    check(digest(BASE / "mihomo") == BINARY_SHA256, "native_binary_mismatch")
    (BASE / "mihomo").chmod(0o700)
    (BASE / "observations").mkdir(mode=0o700)
    (BASE / "empty-certs").mkdir(mode=0o700)
    fd = os.open(BASE / "empty.pem", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    for index, row in enumerate([*rows, rows[0]]):
        directory = BASE / str(index)
        directory.mkdir(mode=0o700)
        private_json(directory / "descriptor.json", row)
        private_json(
            directory / "config.json", config(text(row["url"]), index, secrets.token_hex(32))
        )
    return {"binary_sha256": BINARY_SHA256, "version": VERSION, "prepared": True}


def read_json(path: Path) -> dict[str, object]:
    check(not path.is_symlink() and path.stat().st_size <= LIMIT, "native_unsafe_file")
    return obj(json.loads(path.read_bytes()))


def register(index: int) -> dict[str, object]:
    row = descriptor(read_json(BASE / str(index) / "descriptor.json"))
    # Exactly one original URL is exposed at a time; periodic provider updates are disabled.
    private_json(TLS / "request.json", {"url": row["url"]})
    return {"url_sha256": hashlib.sha256(text(row["url"]).encode()).hexdigest()}


def api(index: int, method: str, path: str, *, selection: str | None = None) -> tuple[int, bytes]:
    check(method in {"GET", "PUT"}, "native_controller_method")
    check(
        path in {"/version", "/providers/proxies/service", "/proxies/service"},
        "native_controller_path",
    )
    check(
        (selection is None and (method == "GET" or path == "/providers/proxies/service"))
        or (
            method == "PUT"
            and path == "/proxies/service"
            and isinstance(selection, str)
            and 0 < len(selection) <= 512
        ),
        "native_controller_selection",
    )
    saved = read_json(BASE / str(index) / "config.json")
    request = Request(
        f"http://127.0.0.1:{19080 + index}" + path,
        method=method,
        data=json.dumps({"name": selection}).encode() if selection is not None else None,
        headers={
            "Authorization": "Bearer " + text(saved["secret"]),
            "Content-Type": "application/json",
        },
    )
    try:
        response = build_opener(ProxyHandler({})).open(request, timeout=10)
    except HTTPError as exc:
        response = exc
    with response:
        body = response.read(LIMIT + 1)
        check(len(body) <= LIMIT, "native_controller_oversize")
        return int(response.code), body


def ready(index: int) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            status, body = api(index, "GET", "/version")
            check(status == 200, "native_version_http")
            check(obj(json.loads(body)).get("version") == "v" + VERSION, "native_version_mismatch")
            return
        except (URLError, OSError):
            time.sleep(0.2)
    raise NativeEvidenceError("native_controller_not_ready")


def command(index: int) -> list[str]:
    directory = BASE / str(index)
    return [str(BASE / "mihomo"), "-d", str(directory), "-f", str(directory / "config.json")]


def untrusted() -> dict[str, object]:
    register(2)
    directory = BASE / "2"
    check(not (directory / "provider.txt").exists(), "native_negative_cache_exists")
    with subprocess.Popen(
        command(2),
        env=process_env(directory, trusted=False),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ) as process:
        try:
            ready(2)
            status, body = api(2, "PUT", "/providers/proxies/service")
            check(
                status == 503 and b"x509: certificate signed by unknown authority" in body,
                "native_negative_not_certificate_refusal",
            )
            check(not (directory / "provider.txt").exists(), "native_untrusted_cache_written")
        finally:
            process.kill()
            process.wait(timeout=5)
    return {
        "controller_status": 503,
        "untrusted_ca_refused": True,
        "provider_cache_written": False,
        "core_stopped": True,
    }


def cache_evidence(body: bytes, row: dict[str, object], *, published_ip: bool) -> dict[str, object]:
    """Assert native-owned cache content only; never pass parsed proxies to the core."""
    check(0 < len(body) <= LIMIT, "native_cache_size")
    source = body.decode("utf-8").strip()
    if not source.startswith("vless://"):
        source = base64.b64decode("".join(source.split()), validate=True).decode("utf-8").strip()
    check(source.startswith("vless://") and len(source.splitlines()) == 1, "native_cache_format")
    uri = urlsplit(source)
    expected_host = text(row["node_ip"] if published_ip else row["host"])
    check(
        uri.scheme == "vless"
        and uri.hostname == expected_host
        and uri.port == 12080
        and uri.password is None
        and UUID(text(uri.username)) == UUID(text(row["identity"])),
        "native_cache_identity_or_resource_mismatch",
    )
    options = parse_qs(uri.query, keep_blank_values=True, strict_parsing=True)
    allowed = {
        "type": {"tcp"},
        "security": {"none"},
        "encryption": {"none"},
        "headerType": {"none"},
        "flow": {""},
    }
    check(
        set(options) <= set(allowed)
        and all(len(value) == 1 and value[0] in allowed[key] for key, value in options.items()),
        "native_cache_transport_mismatch",
    )
    return {
        "cache_sha256": hashlib.sha256(body).hexdigest(),
        "credential_sha256": hashlib.sha256(text(row["identity"]).encode()).hexdigest(),
        "endpoint_sha256": hashlib.sha256(f"{expected_host}:12080".encode()).hexdigest(),
        "proxy_name_sha256": hashlib.sha256(unquote(uri.fragment).encode()).hexdigest(),
    }


def snapshot(index: int, *, published_ip: bool = False) -> dict[str, object]:
    directory = BASE / str(index)
    row = descriptor(read_json(directory / "descriptor.json"))
    cached = directory / "provider.txt"
    check(cached.is_file() and not cached.is_symlink(), "native_provider_cache_missing")
    check(cached.stat().st_size <= LIMIT, "native_cache_size")
    evidence = cache_evidence(cached.read_bytes(), row, published_ip=published_ip)
    status, body = api(index, "GET", "/providers/proxies/service")
    check(status == 200, "native_provider_not_loaded")
    provider = obj(json.loads(body))
    proxies = provider.get("proxies")
    check(isinstance(proxies, list) and len(proxies) == 1, "native_provider_count")
    assert isinstance(proxies, list)
    proxy = obj(proxies[0])
    check(text(proxy.get("type")).lower() == "vless", "native_provider_wrong_type")
    check(
        hashlib.sha256(text(proxy.get("name")).encode()).hexdigest()
        == evidence["proxy_name_sha256"],
        "native_provider_name_mismatch",
    )
    return {
        **evidence,
        "config_sha256": digest(directory / "config.json"),
        "url_sha256": hashlib.sha256(text(row["url"]).encode()).hexdigest(),
        "native_proxy_count": 1,
        "native_proxy_type": "vless",
    }


def refresh(index: int, *, published_ip: bool = False) -> dict[str, object]:
    register(index)
    ready(index)
    status, _ = api(index, "PUT", "/providers/proxies/service")
    check(status == 204, "native_refresh_failed")
    return snapshot(index, published_ip=published_ip)


def provider_state(index: int) -> dict[str, object]:
    """Observe loaded state even when the core clears or retains an invalid update."""
    directory = BASE / str(index)
    cached = directory / "provider.txt"
    check(not cached.is_symlink(), "native_unsafe_file")
    status, body = api(index, "GET", "/providers/proxies/service")
    check(status == 200, "native_provider_not_loaded")
    proxies = obj(json.loads(body)).get("proxies")
    check(isinstance(proxies, list) and len(proxies) <= 16, "native_provider_count")
    assert isinstance(proxies, list)
    loaded = [obj(proxy) for proxy in proxies]
    return {
        "cache_present": cached.exists(),
        "cache_sha256": digest(cached) if cached.exists() else None,
        "config_sha256": digest(directory / "config.json"),
        "proxies": [
            {
                "name_sha256": hashlib.sha256(text(proxy.get("name")).encode()).hexdigest(),
                "type": text(proxy.get("type")).lower(),
            }
            for proxy in loaded
        ],
    }


def placeholder_names(index: int) -> list[str]:
    """Inspect native cache against Remnawave 3.4.5 createFallbackHosts/buildVlessLink."""
    directory = BASE / str(index)
    row = descriptor(read_json(directory / "descriptor.json"))
    cached = directory / "provider.txt"
    check(
        cached.is_file() and not cached.is_symlink() and 0 < cached.stat().st_size <= LIMIT,
        "native_placeholder_cache_missing",
    )
    body = cached.read_bytes()
    if not body.startswith(b"vless://"):
        body = base64.b64decode(body, validate=True)
    lines = body.decode("utf-8").splitlines()
    check(1 <= len(lines) <= 16, "native_placeholder_count")
    names: list[str] = []
    for line in lines:
        check(
            not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in line),
            "native_placeholder_uri",
        )
        uri = urlsplit(line)
        check(
            uri.scheme == "vless"
            and uri.netloc == "00000000-0000-0000-0000-000000000000@0.0.0.0:1"
            and not uri.path
            and parse_qs(uri.query, keep_blank_values=True, strict_parsing=True)
            == {"encryption": ["none"], "type": ["tcp"], "security": ["none"]},
            "native_placeholder_not_pinned_fallback",
        )
        check(
            UUID(text(uri.username)) != UUID(text(row["identity"]))
            and uri.hostname not in {row["host"], row["node_ip"]}
            and uri.port != 12080,
            "native_revoked_credentials_retained",
        )
        name = unquote(uri.fragment, errors="strict")
        check(
            0 < len(name) <= 512
            and name not in names
            and name not in {"DIRECT", "REJECT", "COMPATIBLE", "service"}
            and not any(ord(c) < 32 or ord(c) == 127 for c in name),
            "native_placeholder_name",
        )
        names.append(name)
    return names


def placeholder_metadata(names: list[str]) -> list[dict[str, str]]:
    return [
        {"name_sha256": hashlib.sha256(name.encode()).hexdigest(), "type": "vless"}
        for name in names
    ]


def refresh_revoked(index: int) -> dict[str, object]:
    before = snapshot(index)
    loaded_before = provider_state(index)
    register(index)
    ready(index)
    row = descriptor(read_json(BASE / str(index) / "descriptor.json"))
    marker = uuid4().hex
    private_json(TLS / "request.json", {"url": row["url"], "native_observation": marker})
    try:
        status, body = api(index, "PUT", "/providers/proxies/service")
        receipt = read_json(BASE / "observations" / (marker + ".json"))
        check(
            receipt.get("attempt") == marker and receipt.get("url_sha256") == before["url_sha256"],
            "native_refresh_receipt_mismatch",
        )
        after = provider_state(index)
        message = ""
        if status == 503:
            with suppress(ValueError, TypeError):
                message = text(obj(json.loads(body)).get("message"))
        # Pinned core parser errors, not a blanket acceptance of any failed update.
        empty_error = message in {
            "provider need one proxy at least",
            "file must have a `proxies` field",
        }
        rejected_empty = status == 503 and empty_error
        source_empty = (
            receipt.get("upstream_status") == 200 and receipt.get("empty_subscription") is True
        )
        retained = after["proxies"] == loaded_before["proxies"]
        cleared = after["proxies"] == []
        empty_cache = not after["cache_present"] or after["cache_sha256"] == receipt.get(
            "body_sha256"
        )
        known_empty_cache = empty_cache or after["cache_sha256"] == loaded_before["cache_sha256"]
        placeholders: dict[str, object] | None = None
        if (
            status == 204
            and receipt.get("upstream_status") == 200
            and receipt.get("empty_subscription") is False
        ):
            names = placeholder_names(index)
            check(
                after["cache_sha256"] == receipt.get("body_sha256")
                and after["cache_sha256"] != before["cache_sha256"]
                and after["proxies"] == placeholder_metadata(names),
                "native_placeholder_source_or_provider_mismatch",
            )
            placeholders = {
                "contract": "remnawave_3_4_5_no_hosts_fallback",
                "native_proxy_names_sha256": [
                    entry["name_sha256"] for entry in placeholder_metadata(names)
                ],
                "source_matches_native_cache": True,
                "revoked_identity_absent": True,
                "revoked_endpoint_absent": True,
            }
        accepted = after["config_sha256"] == before["config_sha256"] and (
            placeholders is not None
            or (
                source_empty
                and known_empty_cache
                and (
                    (rejected_empty and (retained or cleared))
                    or (status == 204 and cleared and empty_cache)
                )
            )
        )
        return {
            "verified": accepted,
            "controller_status": status,
            "controller_error": "empty_provider"
            if rejected_empty
            else "none"
            if status == 204
            else "unrecognized",
            "controller_body_sha256": hashlib.sha256(body).hexdigest(),
            "source": receipt,
            "before": loaded_before,
            "after": after,
            "placeholders": placeholders,
            "cache_behavior": "retained"
            if after["cache_sha256"] == loaded_before["cache_sha256"]
            else "removed"
            if not after["cache_present"]
            else "changed",
            "loaded_proxy_metadata_behavior": "retained"
            if retained
            else "cleared"
            if cleared
            else "changed",
        }
    finally:
        register(index)


def probe_placeholder(index: int, name_sha256: str, token: str) -> dict[str, object]:
    names = placeholder_names(index)
    before = provider_state(index)
    check(before["proxies"] == placeholder_metadata(names), "native_placeholder_provider_changed")
    matches = [name for name in names if hashlib.sha256(name.encode()).hexdigest() == name_sha256]
    check(len(matches) == 1, "native_placeholder_selection")
    status, _ = api(index, "PUT", "/proxies/service", selection=matches[0])
    check(status == 204, "native_placeholder_select_failed")
    status, body = api(index, "GET", "/proxies/service")
    selected = obj(json.loads(body))
    check(
        status == 200
        and selected.get("type") == "Selector"
        and selected.get("now") == matches[0]
        and selected.get("all") == names,
        "native_placeholder_selection_unconfirmed",
    )
    result = exchange(index, token, "P", 0, denied=True)
    check(provider_state(index) == before, "native_placeholder_state_changed")
    return {"name_sha256": name_sha256, "selected": True, **result}


def exact(stream: BinaryIO, size: int) -> bytes:
    value = stream.read(size)
    check(value is not None and len(value) == size, "native_socks_short_reply")
    return value


def exchange(index: int, token: str, op: str, size: int, *, denied: bool) -> dict[str, object]:
    row = descriptor(read_json(BASE / str(index) / "descriptor.json"))
    check(op in {"P", "D", "U"} and type(size) is int and 0 <= size <= 65536, "native_payload")
    check(not denied or (op == "P" and size == 0), "native_rejection_payload")
    token_bytes = UUID(token).bytes
    with socket.create_connection(("127.0.0.1", 10800 + index), timeout=4) as sock:
        sock.settimeout(4)
        with sock.makefile("rb") as reader:
            sock.sendall(b"\x05\x01\x00")
            check(exact(reader, 2) == b"\x05\x00", "native_socks_not_ready")
            target = ipaddress.IPv4Address(text(row["origin_ip"])).packed
            sock.sendall(b"\x05\x01\x00\x01" + target + (19090).to_bytes(2, "big"))
            reply = exact(reader, 4)
            check(reply[0] == 5 and reply[2] == 0, "native_invalid_socks_reply")
            if reply[1] != 0:
                check(denied and 1 <= reply[1] <= 8, "native_proxy_connect_failed")
                return {"socks_ready": True, "outcome": "socks_refused"}
            check(reply[3] in {1, 3, 4}, "native_socks_address_type")
            address_size = 4 if reply[3] == 1 else 16 if reply[3] == 4 else exact(reader, 1)[0]
            exact(reader, address_size + 2)
            sock.sendall(op.encode() + size.to_bytes(4, "big") + token_bytes)
            if op == "U":
                sock.sendall(b"u" * size)
            if denied:
                try:
                    received = reader.read(1)
                except ConnectionResetError:
                    received = b""
                check(received == b"", "native_unauthorized_payload_received")
                return {"socks_ready": True, "outcome": "eof"}
            expected = (
                text(row["node_ip"]).encode().ljust(16, b" ")
                if op == "P"
                else b"K"
                if op == "U"
                else b"x" * size
            )
            check(exact(reader, len(expected)) == expected, "native_wrong_origin_payload")
            check(reader.read(1) == b"", "native_origin_not_closed")
    return {"up": 21 + (size if op == "U" else 0), "down": len(expected)}


def dispatch(request: dict[str, object]) -> dict[str, object]:
    action = request.get("action")
    if action == "prepare":
        return prepare(request.get("services"))
    if action == "untrusted":
        return untrusted()
    index = request.get("index")
    check(type(index) is int and index in (0, 1), "native_invalid_index")
    assert isinstance(index, int)
    if action == "register":
        return register(index)
    if action == "refresh_revoked":
        return refresh_revoked(index)
    if action == "probe_placeholder":
        return probe_placeholder(
            index, text(request.get("name_sha256")), text(request.get("token"))
        )
    if action in {"snapshot", "refresh"}:
        published = request.get("published_ip", False)
        check(type(published) is bool, "native_invalid_endpoint_mode")
        assert isinstance(published, bool)
        return (snapshot if action == "snapshot" else refresh)(index, published_ip=published)
    if action == "exchange":
        denied, size = request.get("denied", False), request.get("size", 0)
        check(type(denied) is bool and type(size) is int, "native_payload")
        assert isinstance(denied, bool) and isinstance(size, int)
        return exchange(
            index, text(request.get("token")), text(request.get("op")), size, denied=denied
        )
    raise NativeEvidenceError("native_unknown_action")


def main() -> None:
    check(os.environ.get("QA_SERVICE_OPERATIONS_LIVE_NODE") == "1", "native_explicit_opt_in")
    check(BASE.is_dir() and not BASE.is_symlink(), "native_private_directory_missing")
    os.umask(0o077)
    if len(sys.argv) == 3 and sys.argv[1] == "serve":
        check(sys.argv[2] in {"0", "1"}, "native_invalid_index")
        index = int(sys.argv[2])
        check(digest(BASE / "mihomo") == BINARY_SHA256, "native_binary_mismatch")
        with open(os.devnull, "wb") as quiet:
            os.dup2(quiet.fileno(), 1)
            os.dup2(quiet.fileno(), 2)
        os.execve(BASE / "mihomo", command(index), process_env(BASE / str(index), trusted=True))
    check(len(sys.argv) == 1, "native_runtime_arguments")
    raw = sys.stdin.buffer.read(LIMIT + 1)
    check(len(raw) <= LIMIT, "native_request_size")
    print(json.dumps({"ok": True, "evidence": dispatch(obj(json.loads(raw)))}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "failure_type": type(exc).__name__,
                    "failure_code": str(exc)
                    if isinstance(exc, NativeEvidenceError)
                    else "native_runtime_failed",
                }
            )
        )
        raise SystemExit(1) from None
