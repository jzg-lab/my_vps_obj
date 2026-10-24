"""Offline TLS/manifest checkpoint: real crypto, no sockets, locks, Docker or DB."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import socket
import ssl
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from aiohttp.test_utils import make_mocked_request

from tests.support import exit_replacement_live_node as exits
from tests.support import node_onboarding_live_node as harness
from tests.support import service_operations_live_node as shared


@pytest.fixture(autouse=True)
def no_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    forbidden = Mock(side_effect=AssertionError("Offline checkpoint touched live infrastructure"))
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "bind", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(shared, "_read_env", forbidden)


def certificates(directory: Path, material: harness.TLSMaterial) -> None:
    directory.mkdir(mode=0o700)
    for filename, payload in (
        ("ca.pem", material.ca),
        ("server.pem", material.certificate),
        ("server.key", material.key),
    ):
        harness.private_bytes(directory / filename, payload)


def handshake(client_context: ssl.SSLContext, server_context: ssl.SSLContext) -> None:
    client_in, client_out, server_in, server_out = (ssl.MemoryBIO() for _ in range(4))
    client = client_context.wrap_bio(client_in, client_out, server_hostname="127.0.0.1")
    server = server_context.wrap_bio(server_in, server_out, server_side=True)
    finished = set()
    for _ in range(100):
        for index, peer in enumerate((client, server)):
            try:
                peer.do_handshake()
                finished.add(index)
            except ssl.SSLWantReadError:
                pass
        for outgoing, incoming in ((client_out, server_in), (server_out, client_in)):
            if outgoing.pending:
                incoming.write(outgoing.read())
        if len(finished) == 2:
            assert client.version() in {"TLSv1.2", "TLSv1.3"}
            assert client.getpeercert()
            client.write(b"strict-tls-payload")
            server_in.write(client_out.read())
            assert server.read() == b"strict-tls-payload"
            return
    pytest.fail("TLS BIO handshake did not finish")


def assert_ca_scope(context: ssl.SSLContext, ca: bytes) -> None:
    # Some Python distributions preload explicitly distrusted certificates too.
    baseline = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    assert set(context.get_ca_certs(binary_form=True)) == {
        *baseline.get_ca_certs(binary_form=True),
        ssl.PEM_cert_to_DER_cert(ca.decode("ascii")),
    }


def test_real_tls_validates_ca_ip_san_and_transmits_without_sockets(tmp_path: Path) -> None:
    material = harness.tls_material()
    directory = tmp_path / "tls"
    certificates(directory, material)
    client = harness.client_context(material.ca)
    assert client.verify_mode == ssl.CERT_REQUIRED and client.check_hostname
    assert_ca_scope(client, material.ca)
    handshake(client, harness.server_context(directory))
    assert directory.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in directory.iterdir())


@pytest.mark.parametrize("case", ["unknown_ca", "wrong_ip_san"])
def test_real_tls_rejects_untrusted_ca_and_wrong_san(tmp_path: Path, case: str) -> None:
    material = harness.tls_material(address="127.0.0.2" if case == "wrong_ip_san" else "127.0.0.1")
    directory = tmp_path / "tls"
    certificates(directory, material)
    ca = harness.tls_material().ca if case == "unknown_ca" else material.ca
    with pytest.raises(ssl.SSLCertVerificationError):
        handshake(harness.client_context(ca), harness.server_context(directory))


def test_opt_in_precedes_environment_and_manifest_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("QA_SERVICE_OPERATIONS_LIVE_NODE", raising=False)
    forbidden = Mock(side_effect=AssertionError("Opt-out must precede environment access"))
    monkeypatch.setattr(exits, "require_exit_environment", forbidden)
    node = OfflineNode(tmp_path / "root")
    tls = harness.SubscriptionTLS(node)
    for operation in (
        harness.require_onboarding_environment,
        lambda: asyncio.run(tls.start()),
        lambda: asyncio.run(tls.fetch("not-a-url", target=node, identity="secret")),
        lambda: asyncio.run(tls.cleanup()),
        lambda: asyncio.run(harness.recover(tmp_path / "missing.json")),
    ):
        with pytest.raises(ValueError, match="Explicit QA_SERVICE_OPERATIONS_LIVE_NODE"):
            operation()
    forbidden.assert_not_called()
    assert node.calls == []
    assert "onboarding_tls" not in node.state
    assert not tls.directory.exists()


def test_opt_in_reuses_mandatory_adapter_and_local_environment_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QA_SERVICE_OPERATIONS_LIVE_NODE", "1")
    guard = Mock(side_effect=ValueError("mandatory reviewed adapter missing"))
    monkeypatch.setattr(exits, "require_exit_environment", guard)
    with pytest.raises(ValueError, match="mandatory reviewed adapter missing"):
        harness.require_onboarding_environment()
    guard.assert_called_once_with()


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:3010/secret",
        "https://example.com/secret",
        "https://127.0.0.1:3011/secret",
        "https://localhost:3010/secret",
        "https://user:password@127.0.0.1:3010/secret",
        "https://127.0.0.1:3010/secret#fragment",
        "https://127.0.0.1:3010/secret#",
        "https://127.0.0.1:3010//other/path",
        "https://127.0.0.1:3010/secret\\path",
        "https://127.0.0.1:3010/secret\npath",
        "https://127.0.0.1:3010/secret path",
        "https://127.0.0.1:3010/secret\x00path",
        "https://127.0.0.1:3010",
        "https://127.0.0.1:3010/" + "x" * 4096,
    ],
)
def test_url_rejects_nonlocal_or_ambiguous_targets_without_echoing_secrets(url: str) -> None:
    with pytest.raises(harness.SubscriptionEvidenceError) as error:
        harness.subscription_target(url)
    assert "secret" not in str(error.value) and url not in str(error.value)


def test_original_encoded_path_query_are_not_rewritten() -> None:
    target = "/path%2Ftoken?first=%2f%2B&token=opaque%3D&first=second"
    assert harness.subscription_target("https://127.0.0.1:3010" + target) == target


def uri(host: str, identity: str, *, port: int = 12080, options: str = "") -> bytes:
    return f"vless://{identity}@{host}:{port}?type=tcp&security=none{options}#local".encode()


def outbound(host: str, identity: str) -> dict[str, object]:
    return {
        "protocol": "vless",
        "settings": {"vnext": [{"address": host, "port": 12080, "users": [{"id": identity}]}]},
        "streamSettings": {"network": "tcp", "security": "none"},
    }


@pytest.mark.parametrize("form", ["uri", "base64", "json_object", "json_list"])
def test_supported_subscription_extracts_actual_endpoint_and_identity(form: str) -> None:
    identity, host = str(uuid4()), "uc2-owned-node"
    body = uri(host, identity)
    if form == "base64":
        body = base64.b64encode(body)
    elif form.startswith("json"):
        config = {"outbounds": [outbound(host, identity), {"protocol": "freedom"}]}
        body = json.dumps([config] if form == "json_list" else config).encode()
    result = harness.subscription_outbound(
        body, "text/plain", host=host, port=12080, identity=identity
    )
    server = harness.json_object(harness.one(harness.json_object(result["settings"])["vnext"]))
    assert server == {
        "address": host,
        "port": 12080,
        "users": [{"id": identity, "encryption": "none"}],
    }
    assert result["streamSettings"] == {"network": "tcp", "security": "none"}


@pytest.mark.parametrize("mismatch", ["identity", "host", "port"])
def test_subscription_cannot_supply_another_service_or_endpoint(mismatch: str) -> None:
    identity, host = str(uuid4()), "uc2-owned-node"
    body = uri(
        "uc2-foreign-node" if mismatch == "host" else host,
        str(uuid4()) if mismatch == "identity" else identity,
        port=12081 if mismatch == "port" else 12080,
    )
    with pytest.raises(harness.SubscriptionEvidenceError, match="unexpected_subscription") as error:
        harness.subscription_outbound(body, "text/plain", host=host, port=12080, identity=identity)
    assert identity not in str(error.value)


@pytest.mark.parametrize(
    "body,content_type,code",
    [
        (b"<html>token-secret</html>", "text/plain", "html_not_subscription"),
        (b"token-secret", "text/html; charset=utf-8", "html_not_subscription"),
        (
            base64.b64encode(b"<!doctype html><html>secret</html>"),
            "text/plain",
            "html_not_subscription",
        ),
        (b"", "text/plain", "subscription_size"),
        (b"x" * (harness.MAX_BODY + 1), "text/plain", "subscription_size"),
        (b"\xffsecret", "text/plain", "invalid_subscription_payload"),
        (b'{"outbounds": [], "outbounds": []}', "application/json", "duplicate_subscription_key"),
        (
            b'{"outbounds": [{"protocol":"shadowsocks"}]}',
            "application/json",
            "unsupported_proxy_protocol",
        ),
        (b'{"outbounds": []}', "application/json", "expected_one_subscription_target"),
    ],
)
def test_subscription_rejects_html_malformed_or_unsupported_payloads(
    body: bytes, content_type: str, code: str
) -> None:
    with pytest.raises(harness.SubscriptionEvidenceError, match=code):
        harness.subscription_outbound(
            body, content_type, host="owned", port=12080, identity=str(uuid4())
        )


@pytest.mark.parametrize(
    "options", ["&security=tls", "&type=ws", "&sni=secret", "&flow=xtls-rprx-vision", "&foo=secret"]
)
def test_subscription_rejects_unimplemented_uri_options(options: str) -> None:
    identity = str(uuid4())
    with pytest.raises(harness.SubscriptionEvidenceError, match="unsupported_vless_options"):
        harness.subscription_outbound(
            uri("owned", identity, options=options),
            "text/plain",
            host="owned",
            port=12080,
            identity=identity,
        )


@pytest.mark.parametrize(
    "change,code",
    [
        ({"mux": {"enabled": True}}, "unsupported_vless_fields"),
        ({"streamSettings": {"network": "ws"}}, "unsupported_vless_transport"),
        ({"streamSettings": {"security": "tls"}}, "unsupported_vless_transport"),
        (
            {"streamSettings": {"tcpSettings": {"header": {"type": "http"}}}},
            "unsupported_tcp_header",
        ),
        ({"settings": {"vnext": [], "extra": True}}, "unsupported_vless_settings"),
    ],
)
def test_subscription_json_does_not_silently_drop_unsupported_proxy_fields(
    change: dict[str, object], code: str
) -> None:
    identity = str(uuid4())
    body = json.dumps({"outbounds": [outbound("owned", identity) | change]}).encode()
    with pytest.raises(harness.SubscriptionEvidenceError, match=code):
        harness.subscription_outbound(
            body, "application/json", host="owned", port=12080, identity=identity
        )


def test_diagnostics_do_not_store_subscription_or_private_material() -> None:
    identity = str(uuid4())
    body = uri("owned", identity)
    proof = harness.diagnostics(body, "text/plain; secret=opaque", 200)
    assert proof == {
        "http_status": 200,
        "body_bytes": len(body),
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "body_kind": "vless_uri",
    }
    assert identity not in json.dumps(proof) and "opaque" not in json.dumps(proof)
    assert "PRIVATE KEY" not in repr(harness.tls_material())
    assert identity not in repr(harness.FetchedSubscription(outbound("owned", identity), proof))


def test_private_files_reject_overwrite_and_symlink(tmp_path: Path) -> None:
    path = tmp_path / "secret"
    harness.private_bytes(path, b"original")
    with pytest.raises(FileExistsError):
        harness.private_bytes(path, b"replacement")
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(FileExistsError):
        harness.private_bytes(link, b"replacement")
    assert path.read_bytes() == b"original"


def transport(
    monkeypatch: pytest.MonkeyPatch, *, body: bytes, status: int = 200
) -> tuple[Mock, Mock]:
    async def chunks(size: int):
        for offset in range(0, len(body), size):
            yield body[offset : offset + size]

    response = Mock(status=status, headers={"Content-Type": "text/plain"})
    response.content.iter_chunked = chunks
    context = AsyncMock()
    context.__aenter__.return_value = response
    session = Mock()
    session.get.return_value = context
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    factory = Mock(return_value=session_context)
    monkeypatch.setattr(harness.aiohttp, "ClientSession", factory)
    return factory, session


def test_proxy_fixed_upstream_preserves_path_and_never_forwards_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = "/opaque%2Fsecret?q=%2f%2B&x=1"
    url = "https://127.0.0.1:3010" + target
    harness.private_bytes(tmp_path / "request.json", json.dumps({"url": url}).encode())
    factory, session = transport(monkeypatch, body=b"actual-subscription")
    request = make_mocked_request(
        "GET",
        target,
        headers={
            "Host": harness.LOCAL_AUTHORITY,
            "Authorization": "Bearer secret",
            "Cookie": "private=secret",
            "X-Forwarded-For": "203.0.113.99, secret",
            "X-Forwarded-Proto": "http",
        },
    )
    response = asyncio.run(harness.proxy_subscription(request, tmp_path))
    assert response.status == 200 and response.body == b"actual-subscription"
    assert str(session.get.call_args.args[0]) == harness.UPSTREAM + target
    assert factory.call_args.kwargs["trust_env"] is False
    assert session.get.call_args.kwargs == {
        "headers": {
            "User-Agent": harness.USER_AGENT,
            "Accept": "*/*",
            "Accept-Encoding": "identity",
            "Host": harness.LOCAL_AUTHORITY,
            "X-Forwarded-Proto": "https",
            "X-Forwarded-For": "127.0.0.1",
        },
        "allow_redirects": False,
    }


@pytest.mark.parametrize(
    "host,target", [("other:3010", "/secret"), (harness.LOCAL_AUTHORITY, "/other")]
)
def test_proxy_does_not_contact_upstream_for_unregistered_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, host: str, target: str
) -> None:
    harness.private_bytes(
        tmp_path / "request.json", json.dumps({"url": "https://127.0.0.1:3010/secret"}).encode()
    )
    factory, _ = transport(monkeypatch, body=b"unused")
    request = make_mocked_request("GET", target, headers={"Host": host})
    response = asyncio.run(harness.proxy_subscription(request, tmp_path))
    assert response.status == 502 and response.text == "local_subscription_proxy_failed"
    factory.assert_not_called()


@pytest.mark.parametrize(
    "status,body,expected", [(302, b"redirect", 302), (200, b"x" * (harness.MAX_BODY + 1), 502)]
)
def test_proxy_never_follows_redirects_and_bounds_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int, body: bytes, expected: int
) -> None:
    harness.private_bytes(tmp_path / "request.json", b'{"url":"https://127.0.0.1:3010/secret"}')
    _, session = transport(monkeypatch, body=body, status=status)
    request = make_mocked_request("GET", "/secret", headers={"Host": harness.LOCAL_AUTHORITY})
    response = asyncio.run(harness.proxy_subscription(request, tmp_path))
    assert response.status == expected
    assert session.get.call_args.kwargs["allow_redirects"] is False


def test_container_fetch_uses_original_url_and_ca_without_proxy_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    material = harness.tls_material()
    directory = tmp_path / "tls"
    certificates(directory, material)
    url = "https://127.0.0.1:3010/secret%2Ftoken?q=%2f"
    harness.private_bytes(directory / "request.json", json.dumps({"url": url}).encode())
    factory, session = transport(monkeypatch, body=b"subscription-bytes")
    asyncio.run(harness.fetch_in_container(directory))
    assert str(session.get.call_args.args[0]) == url
    context = session.get.call_args.kwargs["ssl"]
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert_ca_scope(context, material.ca)
    assert session.get.call_args.kwargs["allow_redirects"] is False
    assert factory.call_args.kwargs["trust_env"] is False
    result = json.loads((directory / "response.json").read_bytes())
    assert result["tls_verified"] is True
    assert base64.b64decode(result["body_base64"]) == b"subscription-bytes"


def test_fetch_transport_error_records_class_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "tls"
    certificates(directory, harness.tls_material())
    harness.private_bytes(directory / "request.json", b'{"url":"https://127.0.0.1:3010/secret"}')
    factory, _ = transport(monkeypatch, body=b"unused")
    factory.side_effect = ssl.SSLCertVerificationError("https://secret:password@private.invalid/")
    asyncio.run(harness.fetch_in_container(directory))
    assert json.loads((directory / "response.json").read_bytes()) == {
        "tls_verified": False,
        "failure_type": "SSLCertVerificationError",
    }


def test_proxy_listens_only_on_namespace_loopback_and_cleans_up_on_cancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "tls"
    certificates(directory, harness.tls_material())
    runner = Mock(setup=AsyncMock(), cleanup=AsyncMock())
    runner_factory = Mock(return_value=runner)
    site = Mock(start=AsyncMock())
    site_factory = Mock(return_value=site)
    monkeypatch.setattr(harness.web, "AppRunner", runner_factory)
    monkeypatch.setattr(harness.web, "TCPSite", site_factory)

    async def run() -> None:
        task = asyncio.create_task(harness.serve(directory))
        await asyncio.sleep(0)
        assert (directory / "ready.json").is_file()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert site_factory.call_args.args == (runner, "127.0.0.1", 3010)
    assert isinstance(site_factory.call_args.kwargs["ssl_context"], ssl.SSLContext)
    assert runner_factory.call_args.kwargs == {"access_log": None}
    runner.cleanup.assert_awaited_once_with()


class OfflineNode(shared.LiveNode):
    """Exercise real manifest/container bookkeeping with only Docker transport replaced."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        directory.mkdir(mode=0o700)
        self.manifest = directory / "manifest.json"
        self.state = {
            "run_id": uuid4().hex,
            "context": shared.CONTEXT,
            "image": shared.IMAGE,
            "resources": [],
            "services": [],
            "containers": [],
            "baseline": {},
            "schema": None,
        }
        self.prefix = "uc2-" + str(self.state["run_id"])[:12]
        self.evidence = {"state": "not_run"}
        self.ports = []
        self.calls: list[tuple[str, ...]] = []
        self.info: dict[str, object] | None = None
        self.failure: str | None = None
        self.cancel = False
        self.body = b""
        self.content_type = "text/plain"
        self.response_status = 200
        self.tls_verified = True
        self.companion: OfflineNode | None = None
        self.save()

    async def docker(self, *args: str) -> str:
        self.calls.append(args)
        if args[0] == self.failure:
            raise RuntimeError("transport failed with secret URL that must not be logged")
        if args[0] == "context":
            return "unix:///offline/.colima/my-vps-obj/docker.sock"
        if args[0] == "create":
            name = args[args.index("--name") + 1]
            saved = json.loads(self.manifest.read_bytes())
            assert {"name": name} in saved["containers"]
            assert saved["onboarding_tls"]["status"] == "preparing"
            self.info = {
                "Id": "offline-container-id",
                "Name": "/" + name,
                "Config": {
                    "Image": harness.CLIENT_IMAGE,
                    "Labels": {"my-vpn.uc2-run": self.state["run_id"]},
                },
                "HostConfig": {
                    "NetworkMode": shared.NETWORK,
                    "PortBindings": {},
                    "Memory": 128 * 1024 * 1024,
                    "PidsLimit": 64,
                },
                "NetworkSettings": {"Networks": {shared.NETWORK: {}}},
                "Mounts": [],
                "State": {"Running": False},
            }
            return "offline-container-id"
        if args[0] == "inspect":
            assert self.info is not None
            return json.dumps([self.info])
        if args[0] == "start":
            assert self.info is not None
            self.info["State"] = {"Running": True}
        elif args[0] == "ps":
            assert args == (
                "ps",
                "-aq",
                "--filter",
                "name=^/" + self.prefix + "-" + harness.CLIENT_SUFFIX + "$",
            )
            return "offline-container-id" if self.info else ""
        elif args[0] == "rm":
            assert args == ("rm", "-f", self.prefix + "-" + harness.CLIENT_SUFFIX)
            self.info = None
        elif args[0] == "cp" and args[1].endswith(":/tmp/onboarding-tls/response.json"):
            harness.private_bytes(
                Path(args[2]),
                json.dumps(
                    {
                        "status": self.response_status,
                        "content_type": self.content_type,
                        "body_base64": base64.b64encode(self.body).decode(),
                        "tls_verified": self.tls_verified,
                    }
                ).encode(),
            )
        elif args[0] == "exec":
            if args[-1] == "fetch" and self.cancel:
                raise asyncio.CancelledError()
            if "ready.json" in args[-1]:
                return "True"
        else:
            assert args[0] in {"cp", "start"}
        return ""


@pytest.fixture
def fixture_node(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> OfflineNode:
    monkeypatch.setattr(harness, "require_onboarding_environment", lambda: "offline-db")
    return OfflineNode(tmp_path / "root")


def test_start_records_intent_bounds_container_and_cleanup_is_repeatable(
    fixture_node: OfflineNode,
) -> None:
    tls = harness.SubscriptionTLS(fixture_node)
    asyncio.run(tls.start())
    assert tls.scope()["status"] == "ready"
    assert tls.scope()["container_id"] == "offline-container-id"
    create = next(call for call in fixture_node.calls if call[0] == "create")
    for flag, value in (
        ("--memory", "128m"),
        ("--memory-swap", "128m"),
        ("--pids-limit", "64"),
        ("--network", shared.NETWORK),
        ("--label", "my-vpn.uc2-run=" + str(fixture_node.state["run_id"])),
    ):
        assert create[create.index(flag) + 1] == value
    assert "--pull=never" in create
    assert not {"-p", "--publish", "-P", "--publish-all", "-v", "--mount", "--privileged"} & set(
        create
    )
    for name, digest in harness.json_object(tls.scope()["file_sha256"]).items():
        assert hashlib.sha256((tls.directory / name).read_bytes()).hexdigest() == digest
        assert (tls.directory / name).stat().st_mode & 0o777 == 0o600
    assert tls.directory.stat().st_mode & 0o777 == 0o700
    asyncio.run(tls.cleanup())
    asyncio.run(tls.cleanup())
    assert tls.scope()["status"] == "cleaned" and not tls.directory.exists()
    assert fixture_node.manifest.exists()
    assert fixture_node.info is None


@pytest.mark.parametrize("failure", ["create", "cp", "start"])
def test_partial_start_retains_recoverable_manifest(
    fixture_node: OfflineNode, failure: str
) -> None:
    tls = harness.SubscriptionTLS(fixture_node)
    fixture_node.failure = failure
    with pytest.raises(RuntimeError):
        asyncio.run(tls.start())
    assert tls.scope()["status"] == "failed"
    assert fixture_node.manifest.exists() and tls.directory.exists()
    assert "secret URL" not in fixture_node.manifest.read_text()
    fixture_node.failure = None
    recovered = harness.SubscriptionTLS(fixture_node)
    asyncio.run(recovered.cleanup())
    assert recovered.scope()["status"] == "cleaned"


def test_cleanup_failure_preserves_manifest_and_retry(fixture_node: OfflineNode) -> None:
    tls = harness.SubscriptionTLS(fixture_node)
    asyncio.run(tls.start())
    fixture_node.failure = "rm"
    with pytest.raises(RuntimeError):
        asyncio.run(tls.cleanup())
    assert tls.scope()["status"] == "cleanup_failed"
    assert tls.directory.exists() and fixture_node.manifest.exists()
    fixture_node.failure = None
    asyncio.run(harness.SubscriptionTLS(fixture_node).cleanup())
    assert tls.scope()["status"] == "cleaned"


@pytest.mark.parametrize("foreign", ["label", "id", "network", "mount", "ports", "memory"])
def test_foreign_or_unbounded_container_is_never_deleted(
    fixture_node: OfflineNode, foreign: str
) -> None:
    tls = harness.SubscriptionTLS(fixture_node)
    asyncio.run(tls.start())
    assert fixture_node.info is not None
    if foreign == "id":
        fixture_node.info["Id"] = "replacement-container"
    elif foreign == "label":
        fixture_node.info["Config"] = {
            "Image": harness.CLIENT_IMAGE,
            "Labels": {"my-vpn.uc2-run": uuid4().hex},
        }
    elif foreign == "mount":
        fixture_node.info["Mounts"] = [{"Source": "/private"}]
    else:
        field, value = {
            "network": ("NetworkMode", "host"),
            "ports": ("PortBindings", {"3010/tcp": [{}]}),
            "memory": ("Memory", 0),
        }[foreign]
        fixture_node.info["HostConfig"] = harness.json_object(fixture_node.info["HostConfig"]) | {
            field: value
        }
    with pytest.raises(harness.SubscriptionEvidenceError):
        asyncio.run(tls.cleanup())
    assert not any(call[0] == "rm" for call in fixture_node.calls)
    assert tls.scope()["status"] == "cleanup_failed" and tls.directory.exists()


@pytest.mark.parametrize("foreign", ["preexisting", "symlink", "unknown_file"])
def test_cleanup_does_not_delete_foreign_directory_or_file(
    fixture_node: OfflineNode, tmp_path: Path, foreign: str
) -> None:
    tls = harness.SubscriptionTLS(fixture_node)
    if foreign == "preexisting":
        tls.directory.mkdir()
        with pytest.raises(FileExistsError):
            asyncio.run(tls.start())
        assert tls.scope()["directory_created"] is False
    else:
        asyncio.run(tls.start())
        if foreign == "symlink":
            private = tmp_path / "private"
            private.write_bytes(b"do-not-delete")
            (tls.directory / "request.json").symlink_to(private)
        else:
            (tls.directory / "unowned.txt").write_bytes(b"do-not-delete")
    with pytest.raises(harness.SubscriptionEvidenceError):
        asyncio.run(tls.cleanup())
    assert tls.directory.exists() and fixture_node.manifest.exists()
    if foreign == "symlink":
        assert (tmp_path / "private").read_bytes() == b"do-not-delete"


def test_fetch_validates_actual_service_and_can_fetch_another_service(
    fixture_node: OfflineNode,
) -> None:
    tls = harness.SubscriptionTLS(fixture_node)
    asyncio.run(tls.start())
    for _ in range(2):
        identity = str(uuid4())
        url = "https://127.0.0.1:3010/" + str(uuid4())
        fixture_node.body = uri(fixture_node.prefix + "-node", identity)
        result = asyncio.run(tls.fetch(url, target=fixture_node, identity=identity))
        assert result.evidence["status"] == "verified"
        assert result.evidence["http_status"] == 200 and result.evidence["tls_verified"] is True
        assert result.evidence["url_sha256"] == hashlib.sha256(url.encode()).hexdigest()
        assert str(fixture_node.body) not in (fixture_node.directory / "report.json").read_text()
        assert not (tls.directory / "request.json").exists()
        assert not (tls.directory / "response.json").exists()
        assert identity not in fixture_node.manifest.read_text()
        assert url not in repr(fixture_node.calls) and identity not in repr(fixture_node.calls)
    asyncio.run(tls.cleanup())


@pytest.mark.parametrize("failure", ["html", "wrong_identity", "tls", "redirect", "cancel"])
def test_failed_fetch_retains_private_recovery_state_and_safe_diagnostics(
    fixture_node: OfflineNode, failure: str
) -> None:
    tls = harness.SubscriptionTLS(fixture_node)
    asyncio.run(tls.start())
    identity = str(uuid4())
    fixture_node.body = uri(
        fixture_node.prefix + "-node", str(uuid4()) if failure == "wrong_identity" else identity
    )
    fixture_node.tls_verified = failure != "tls"
    fixture_node.response_status = 302 if failure == "redirect" else 200
    fixture_node.cancel = failure == "cancel"
    if failure == "html":
        fixture_node.body = b"<html>subscription-secret</html>"
    error = asyncio.CancelledError if failure == "cancel" else harness.SubscriptionEvidenceError
    with pytest.raises(error):
        asyncio.run(
            tls.fetch("https://127.0.0.1:3010/secret", target=fixture_node, identity=identity)
        )
    assert tls.scope()["status"] == "failed"
    assert (tls.directory / "request.json").exists() and fixture_node.manifest.exists()
    report = (fixture_node.directory / "report.json").read_text()
    assert (
        "subscription-secret" not in report and "/secret" not in report and identity not in report
    )
    assert json.loads(report)["onboarding_tls"]["status"] == "failed"
    fixture_node.cancel = False
    asyncio.run(harness.SubscriptionTLS(fixture_node).cleanup())
    assert not tls.directory.exists()


@pytest.mark.parametrize("field", ["run_id", "container", "directory"])
def test_foreign_manifest_fails_before_docker_cleanup(
    fixture_node: OfflineNode, field: str
) -> None:
    tls = harness.SubscriptionTLS(fixture_node)
    asyncio.run(tls.start())
    fixture_node.state["onboarding_tls"] = tls.scope() | {field: "foreign"}
    calls = len(fixture_node.calls)
    with pytest.raises(harness.SubscriptionEvidenceError, match="foreign_tls_manifest"):
        asyncio.run(tls.cleanup())
    assert len(fixture_node.calls) == calls
    assert fixture_node.manifest.exists() and tls.directory.exists()


def test_parent_directory_symlink_is_preserved(fixture_node: OfflineNode, tmp_path: Path) -> None:
    tls = harness.SubscriptionTLS(fixture_node)
    asyncio.run(tls.start())
    original = tmp_path / "original"
    tls.directory.rename(original)
    tls.directory.symlink_to(original, target_is_directory=True)
    with pytest.raises(harness.SubscriptionEvidenceError, match="foreign_tls_directory"):
        asyncio.run(tls.cleanup())
    assert tls.directory.is_symlink() and (original / "server.key").exists()
    assert fixture_node.manifest.exists()


@pytest.mark.parametrize("failure", [None, "tls", "pair", "schema", "cancel"])
def test_recovery_orders_tls_pair_schema_and_retains_both_manifests_until_success(
    fixture_node: OfflineNode, monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    import sqlalchemy.ext.asyncio as sqlalchemy_asyncio

    from tests.qa import test_remnawave_panel_contract as contract

    tls = harness.SubscriptionTLS(fixture_node)
    asyncio.run(tls.start())
    companion = OfflineNode(fixture_node.directory / "target")
    fixture_node.companion = companion
    fixture_node.state["target_manifest"] = "target/manifest.json"
    fixture_node.state["schema"] = "user_services_test_" + uuid4().hex
    fixture_node.save()
    panel = Mock()
    panel.close_session = AsyncMock()
    monkeypatch.setattr(contract, "_panel_service", Mock(return_value=panel))
    constructor = Mock(return_value=fixture_node)
    monkeypatch.setattr(exits, "ExitNode", constructor)
    target = Mock(return_value=companion)
    monkeypatch.setattr(fixture_node, "target", target, raising=False)
    close_lock = Mock()
    monkeypatch.setattr(fixture_node, "close_lock", close_lock)
    events: list[str] = []

    async def pair(root: shared.LiveNode) -> None:
        assert root is fixture_node
        assert tls.scope()["status"] == "cleaned" and not tls.directory.exists()
        assert fixture_node.info is None
        events.append("pair")
        if failure == "pair":
            raise RuntimeError("pair cleanup interrupted")
        if failure == "cancel":
            raise asyncio.CancelledError()

    pair_mock = AsyncMock(side_effect=pair)
    monkeypatch.setattr(exits, "cleanup_pair", pair_mock)

    async def execute(statement: object) -> None:
        assert str(statement) == f'DROP SCHEMA IF EXISTS "{fixture_node.state["schema"]}" CASCADE'
        assert events == ["pair"]
        assert fixture_node.manifest.exists() and companion.manifest.exists()
        events.append("schema")
        if failure == "schema":
            raise RuntimeError("schema cleanup interrupted")

    connection = Mock(execute=AsyncMock(side_effect=execute))
    transaction = AsyncMock()
    transaction.__aenter__.return_value = connection
    engine = Mock(begin=Mock(return_value=transaction), dispose=AsyncMock())
    engine_factory = Mock(return_value=engine)
    monkeypatch.setattr(sqlalchemy_asyncio, "create_async_engine", engine_factory)
    fixture_node.failure = "rm" if failure == "tls" else None
    if failure is None:
        asyncio.run(harness.recover(fixture_node.manifest))
        assert events == ["pair", "schema"]
        engine.dispose.assert_awaited_once_with()
        assert not fixture_node.manifest.exists() and not companion.manifest.exists()
    else:
        error = asyncio.CancelledError if failure == "cancel" else RuntimeError
        with pytest.raises(error):
            asyncio.run(harness.recover(fixture_node.manifest))
        assert fixture_node.manifest.exists() and companion.manifest.exists()
        if failure == "tls":
            pair_mock.assert_not_called()
        if failure != "schema":
            engine_factory.assert_not_called()
        else:
            engine.dispose.assert_awaited_once_with()
    constructor.assert_called_once_with(panel, fixture_node.manifest)
    target.assert_called_once_with(recover=True)
    close_lock.assert_called_once_with()
    panel.close_session.assert_awaited_once_with()


def test_integration_default_skip_precedes_app_database_and_live_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.integration import test_node_onboarding_live_node as acceptance

    monkeypatch.delenv("QA_SERVICE_OPERATIONS_LIVE_NODE", raising=False)
    forbidden = Mock(side_effect=AssertionError("Opt-out touched environment"))
    for name in (
        "require_onboarding_environment",
        "run_onboarding",
        "create_async_engine",
        "ExitNode",
    ):
        monkeypatch.setattr(acceptance, name, forbidden)
    with pytest.raises(pytest.skip.Exception):
        acceptance.run_local_onboarding()
    forbidden.assert_not_called()


def test_client_runs_returned_outbound_verbatim_with_existing_cleanup_limits(
    fixture_node: OfflineNode,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands = AsyncMock(side_effect=["created", "copied", "started", "127.0.0.1:19000"])
    monkeypatch.setattr(fixture_node, "docker", commands)
    actual = outbound(fixture_node.prefix + "-node", str(uuid4()))
    port = asyncio.run(harness.subscription_client(fixture_node, actual))
    assert port == 19000 and fixture_node.ports == [19000]
    path = fixture_node.directory / "client-0.json"
    assert json.loads(path.read_bytes())["outbounds"] == [actual]
    assert fixture_node.state["client_0_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    create, copy, start, published = [call.args for call in commands.await_args_list]
    assert create[0] == "create" and shared.IMAGE in create
    assert create[create.index("--memory") + 1] == "128m"
    assert create[create.index("-p") + 1] == "127.0.0.1::1080"
    assert (
        copy[0] == "cp" and copy[1] == str(path) and start[0] == "start" and published[0] == "port"
    )
    fixture_node.ports.append(19001)
    with pytest.raises(
        harness.SubscriptionEvidenceError, match="client_outside_existing_cleanup_scope"
    ):
        asyncio.run(harness.subscription_client(fixture_node, actual))
    assert commands.await_count == 4
