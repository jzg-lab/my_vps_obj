"""F06 local HTTPS subscription checkpoint; no environment access on import.

The same file runs inside the disposable subscription client container. This
checkpoint does not claim pending HTTP resource operations have been executed.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import json
import logging
import os
import ssl
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import aiohttp
from aiohttp import web
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from yarl import URL

if TYPE_CHECKING:
    from tests.support.service_operations_live_node import LiveNode

LOCAL_AUTHORITY = "127.0.0.1:3010"
UPSTREAM = "http://remnawave-subscription-page:3010"
CLIENT_IMAGE = "my-vps-obj-backend:dev"
CLIENT_SUFFIX = "client-subscription"
DIRECTORY = "onboarding-tls"
CONTAINER_DIRECTORY = Path("/tmp/onboarding-tls")
MAX_BODY = 2 * 1024 * 1024
USER_AGENT = "my-vpn-uc07-local-acceptance/1.0"
FILES = ("ca.pem", "server.pem", "server.key", "runtime.py", "request.json", "response.json")
FAILURE_CODES = {
    "ClientConnectorCertificateError": "certificate_rejected",
    "ClientConnectorSSLError": "tls_failed",
    "SSLCertVerificationError": "certificate_rejected",
    "ClientConnectorDNSError": "upstream_dns_failed",
    "ClientConnectorError": "upstream_connection_failed",
    "ServerDisconnectedError": "upstream_disconnected",
    "ClientPayloadError": "upstream_payload_failed",
    "TimeoutError": "transport_timeout",
    "SubscriptionEvidenceError": "proxy_guard_rejected",
    "NameError": "runtime_name_missing",
    "ImportError": "runtime_import_failed",
    "ModuleNotFoundError": "runtime_import_failed",
    "UnexpectedError": "unexpected_failure",
}


class SubscriptionEvidenceError(ValueError):
    """Only fixed diagnostic codes belong in exceptions; never URLs or payloads."""


def require_onboarding_environment() -> str:
    if os.environ.get("QA_SERVICE_OPERATIONS_LIVE_NODE") != "1":
        raise ValueError("Explicit QA_SERVICE_OPERATIONS_LIVE_NODE=1 is required")
    from tests.support.exit_replacement_live_node import require_exit_environment

    return require_exit_environment()


def checked(condition: bool, code: str) -> None:
    if not condition:
        raise SubscriptionEvidenceError(code)


def json_object(value: object) -> dict[str, object]:
    checked(isinstance(value, dict), "invalid_json_object")
    assert isinstance(value, dict)
    checked(all(isinstance(key, str) for key in value), "invalid_json_keys")
    return {str(key): item for key, item in value.items()}


def unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        checked(key not in result, "duplicate_subscription_key")
        result[key] = value
    return result


def subscription_target(url: str) -> str:
    checked(
        len(url) <= 4096
        and not any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in url),
        "invalid_subscription_url",
    )
    try:
        parts = urlsplit(url)
        valid = (
            parts.scheme == "https"
            and parts.netloc == LOCAL_AUTHORITY
            and parts.port == 3010
            and parts.username is None
            and parts.password is None
            and "#" not in url
            and parts.path.startswith("/")
            and not parts.path.startswith("//")
            and "\\" not in url
        )
    except ValueError:
        raise SubscriptionEvidenceError("invalid_subscription_url") from None
    checked(valid, "subscription_outside_local_tls")
    return parts.path + ("?" + parts.query if parts.query else "")


@dataclass(frozen=True, repr=False)
class TLSMaterial:
    ca: bytes = field(repr=False)
    certificate: bytes = field(repr=False)
    key: bytes = field(repr=False)


def tls_material(*, address: str = "127.0.0.1") -> TLSMaterial:
    now = datetime.now(UTC)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "UC07 temporary local CA")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(issuer)
        .issuer_name(issuer)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(False, False, False, False, False, True, True, False, False),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), False)
        .sign(ca_key, hashes.SHA256())
    )
    key = ec.generate_private_key(ec.SECP256R1())
    certificate = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "UC07 local TLS")]))
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(address))]), False
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
        .add_extension(
            x509.KeyUsage(True, False, False, False, False, False, False, False, False),
            critical=True,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), False
        )
        .sign(ca_key, hashes.SHA256())
    )
    # The CA private key never leaves memory; only this run's leaf key is persisted.
    return TLSMaterial(
        ca.public_bytes(serialization.Encoding.PEM),
        certificate.public_bytes(serialization.Encoding.PEM),
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )


def private_bytes(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)


def server_context(directory: Path) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(directory / "server.pem", directory / "server.key")
    return context


def client_context(ca: bytes) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_verify_locations(cadata=ca.decode("ascii"))
    checked(context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED, "tls_not_strict")
    return context


def payload_kind(body: bytes, content_type: str) -> str:
    prefix = body.lstrip()[:128].lower()
    if "text/html" in content_type.lower() or prefix.startswith((b"<!doctype html", b"<html")):
        return "html"
    if prefix.startswith((b"[", b"{")):
        return "json"
    if prefix.startswith(b"vless://"):
        return "vless_uri"
    return "unknown"


def diagnostics(body: bytes, content_type: str, status: int) -> dict[str, object]:
    return {
        "http_status": status,
        "body_bytes": len(body),
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "body_kind": payload_kind(body, content_type),
    }


def one(values: object) -> object:
    checked(isinstance(values, list) and len(values) == 1, "expected_one_subscription_target")
    assert isinstance(values, list)
    return values[0]


def subscription_outbound(
    body: bytes, content_type: str, *, host: str, port: int, identity: str
) -> dict[str, object]:
    """Extract only the actual subscription's one supported VLESS/TCP/no-TLS proxy."""
    checked(0 < len(body) <= MAX_BODY, "subscription_size")
    checked(payload_kind(body, content_type) != "html", "html_not_subscription")
    try:
        source = body.decode("utf-8").strip()
        if not source.startswith(("{", "[", "vless://")):
            source = (
                base64.b64decode("".join(source.split()), validate=True).decode("utf-8").strip()
            )
        checked(payload_kind(source.encode(), "") != "html", "html_not_subscription")
        if source.startswith("vless://"):
            checked(len(source.splitlines()) == 1, "expected_one_subscription_target")
            uri = urlsplit(source)
            options = parse_qs(uri.query, keep_blank_values=True, strict_parsing=True)
            allowed = {
                "type": {"tcp"},
                "security": {"none"},
                "encryption": {"none"},
                "headerType": {"none"},
                "flow": {""},
            }
            checked(
                set(options) <= set(allowed)
                and all(
                    len(value) == 1 and value[0] in allowed[key] for key, value in options.items()
                ),
                "unsupported_vless_options",
            )
            checked(uri.password is None and uri.path in ("", "/"), "unsupported_vless_uri")
            server: dict[str, object] = {"address": uri.hostname, "port": uri.port}
            user: dict[str, object] = {"id": uri.username, "encryption": "none"}
        else:
            raw: object = json.loads(source, object_pairs_hook=unique_keys)
            config = json_object(one(raw) if isinstance(raw, list) else raw)
            outbounds = config.get("outbounds")
            checked(isinstance(outbounds, list), "unsupported_subscription_format")
            assert isinstance(outbounds, list)
            rows = [json_object(value) for value in outbounds]
            checked(
                all(row.get("protocol") in {"vless", "freedom", "blackhole"} for row in rows),
                "unsupported_proxy_protocol",
            )
            outbound = json_object(one([row for row in rows if row.get("protocol") == "vless"]))
            checked(
                set(outbound) <= {"tag", "protocol", "settings", "streamSettings"},
                "unsupported_vless_fields",
            )
            settings = json_object(outbound.get("settings"))
            checked(set(settings) == {"vnext"}, "unsupported_vless_settings")
            server = json_object(one(settings["vnext"]))
            checked(set(server) == {"address", "port", "users"}, "unsupported_vless_server")
            user = json_object(one(server["users"]))
            checked(set(user) <= {"id", "encryption", "flow"}, "unsupported_vless_user")
            stream = json_object(outbound.get("streamSettings", {}))
            checked(
                set(stream) <= {"network", "security", "tcpSettings"}, "unsupported_vless_transport"
            )
            checked(
                stream.get("network", "tcp") == "tcp" and stream.get("security", "none") == "none",
                "unsupported_vless_transport",
            )
            checked(
                stream.get("tcpSettings", {}) in ({}, {"header": {"type": "none"}}),
                "unsupported_tcp_header",
            )
        checked(
            server.get("address") == host
            and type(server.get("port")) is int
            and server["port"] == port,
            "unexpected_subscription_endpoint",
        )
        checked(
            user.get("encryption", "none") == "none" and user.get("flow", "") == "",
            "unsupported_vless_user",
        )
        observed_identity = user.get("id")
        checked(isinstance(observed_identity, str), "invalid_subscription_identity")
        assert isinstance(observed_identity, str)
        checked(UUID(observed_identity) == UUID(identity), "unexpected_subscription_identity")
    except SubscriptionEvidenceError:
        raise
    except (ValueError, TypeError, KeyError):
        raise SubscriptionEvidenceError("invalid_subscription_payload") from None
    return {
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": server["address"],
                    "port": server["port"],
                    "users": [{"id": observed_identity, "encryption": "none"}],
                }
            ]
        },
        "streamSettings": {"network": "tcp", "security": "none"},
    }


async def bounded_body(response: aiohttp.ClientResponse) -> bytes:
    body = bytearray()
    async for chunk in response.content.iter_chunked(65536):
        body.extend(chunk)
        checked(len(body) <= MAX_BODY, "subscription_size")
    return bytes(body)


def load_request(directory: Path) -> tuple[str, str]:
    value: object = json.loads((directory / "request.json").read_bytes())
    request = json_object(value)
    url = request.get("url")
    checked(isinstance(url, str), "invalid_subscription_url")
    assert isinstance(url, str)
    return url, subscription_target(url)


async def proxy_subscription(request: web.Request, directory: Path) -> web.Response:
    try:
        _, target = load_request(directory)
        checked(
            request.host == LOCAL_AUTHORITY and request.raw_path == target,
            "unregistered_subscription_path",
        )
        async with (
            aiohttp.ClientSession(
                trust_env=False, timeout=aiohttp.ClientTimeout(total=20)
            ) as session,
            session.get(
                URL(UPSTREAM + target, encoded=True),
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "*/*",
                    "Accept-Encoding": "identity",
                    "Host": LOCAL_AUTHORITY,
                    "X-Forwarded-Proto": "https",
                    "X-Forwarded-For": "127.0.0.1",
                },
                allow_redirects=False,
            ) as response,
        ):
            body = await bounded_body(response)
            if (directory / "subscription_client_observation.py").is_file():
                from subscription_client_observation import record_response

                record_response(directory, request, body, response)
            return web.Response(
                status=response.status,
                body=body,
                headers={
                    "Content-Type": response.headers.get(
                        "Content-Type", "application/octet-stream"
                    ),
                    "Cache-Control": "no-store",
                },
            )
    except Exception as exc:
        kind = type(exc).__name__
        return web.Response(
            status=502,
            text="local_subscription_proxy_failed",
            headers={"X-UC07-Proxy-Failure": kind if kind in FAILURE_CODES else "UnexpectedError"},
        )


async def serve(directory: Path) -> None:
    async def proxy(request: web.Request) -> web.Response:
        return await proxy_subscription(request, directory)

    app = web.Application(client_max_size=4096)
    app.router.add_get("/{path:.*}", proxy, allow_head=False)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", 3010, ssl_context=server_context(directory)).start()
        private_bytes(directory / "ready.json", b'{"ready":true}')
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


async def fetch_in_container(directory: Path) -> None:
    result: dict[str, object]
    try:
        url, _ = load_request(directory)
        context = client_context((directory / "ca.pem").read_bytes())
        async with (
            aiohttp.ClientSession(
                trust_env=False, timeout=aiohttp.ClientTimeout(total=25)
            ) as session,
            session.get(
                URL(url, encoded=True),
                ssl=context,
                headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
                allow_redirects=False,
            ) as response,
        ):
            body = await bounded_body(response)
            content_type = response.headers.get("Content-Type", "")
            result = {
                "tls_verified": True,
                "status": response.status,
                "content_type": content_type,
                "body_base64": base64.b64encode(body).decode("ascii"),
            }
            kind = response.headers.get("X-UC07-Proxy-Failure")
            if response.status == 502 and kind in FAILURE_CODES:
                result["proxy_failure_type"] = kind
    except Exception as exc:
        result = {"tls_verified": False, "failure_type": type(exc).__name__}
    private_bytes(directory / "response.json", json.dumps(result).encode())


@dataclass(frozen=True, repr=False)
class FetchedSubscription:
    outbound: dict[str, object] = field(repr=False)
    evidence: dict[str, object]


async def subscription_client(node: LiveNode, outbound: dict[str, object]) -> int:
    """Run the parsed subscription outbound verbatim in the existing bounded client."""
    require_onboarding_environment()
    from tests.support.service_operations_live_node import IMAGE, private_json

    index = len(node.ports)
    checked(index in (0, 1), "client_outside_existing_cleanup_scope")
    path = node.directory / f"client-{index}.json"
    checked(not path.exists(), "client_config_already_exists")
    private_json(
        path,
        {
            "log": {"loglevel": "warning"},
            "inbounds": [
                {
                    "listen": "0.0.0.0",
                    "port": 1080,
                    "protocol": "socks",
                    "settings": {"auth": "noauth", "udp": False},
                }
            ],
            "outbounds": [outbound],
        },
    )
    node.state[f"client_{index}_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    node.save()
    name = await node.container(
        f"client-{index}",
        IMAGE,
        "-p",
        "127.0.0.1::1080",
        "--entrypoint",
        "xray",
        command=("run", "-config", "/tmp/client.json"),
    )
    await node.docker("cp", str(path), name + ":/tmp/client.json")
    await node.docker("start", name)
    published = await node.docker("port", name, "1080/tcp")
    checked(published.startswith("127.0.0.1:") and "\n" not in published, "nonlocal_client_port")
    port = int(published.rsplit(":", 1)[1])
    checked(0 < port < 65536, "invalid_client_port")
    node.ports.append(port)
    return port


async def resolve_onboarding_cleanup(root: LiveNode, database: str) -> None:
    """Never adopt an uncertain HTTP creation by name; use its durable attempt UUID."""
    import re

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from db.resource_operation_models import ResourceOperation

    nodes = [root, getattr(root, "companion", None)]
    if not any(node and node.state.get("onboarding_http") for node in nodes):
        return
    if all(
        resource.get("uuid") is not None
        for node in nodes
        if node
        for resource in node.rows("resources")
    ):
        return
    schema = root.state.get("schema")
    checked(
        isinstance(schema, str)
        and re.fullmatch(r"user_services_test_[0-9a-f]{32}", schema) is not None,
        "foreign_schema",
    )
    engine = create_async_engine(
        database, connect_args={"server_settings": {"search_path": schema}}
    )
    try:
        async with async_sessionmaker(engine)() as session:
            for node in nodes:
                if node is None:
                    continue
                resources = node.rows("resources")
                for resource in list(resources):
                    operation_id = resource.get("operation_id")
                    if operation_id is None:
                        checked(
                            resource.get("endpoint") == "/config-profiles",
                            "untracked_http_resource",
                        )
                        continue
                    operation = await session.get(ResourceOperation, operation_id)
                    checked(operation is not None, "missing_resource_operation")
                    assert operation is not None
                    checked(
                        operation.request.get("name") == node.prefix, "foreign_resource_operation"
                    )
                    checked(
                        resource["endpoint"]
                        == {
                            "node_create": "/nodes",
                            "group_create": "/internal-squads",
                            "host_create": "/hosts",
                        }.get(operation.operation),
                        "foreign_resource_operation",
                    )
                    if operation.target_id is not None:
                        identity = str(UUID(operation.target_id))
                        checked(resource["uuid"] in (None, identity), "changed_resource_uuid")
                        resource["uuid"] = identity
                    elif operation.attempt_count == 0 or (
                        operation.attempts and operation.attempts[-1].get("receipt") == "rejected"
                    ):
                        resources.remove(resource)
                    else:
                        raise SubscriptionEvidenceError(
                            "unresolved_http_creation_retain_schema_and_manifest"
                        )
                node.state["resources"] = resources
                node.save()
    finally:
        await engine.dispose()


class SubscriptionTLS:
    """Borrow the existing fixture lock and record everything in its exact manifest."""

    def __init__(self, node: LiveNode) -> None:
        self.node = node
        self.directory = node.directory / DIRECTORY
        self.name = node.prefix + "-" + CLIENT_SUFFIX

    def scope(self) -> dict[str, object]:
        scope = json_object(self.node.state.get("onboarding_tls"))
        checked(
            scope.get("run_id") == self.node.state["run_id"]
            and scope.get("container") == self.name
            and scope.get("directory") == DIRECTORY
            and self.name == "uc2-" + str(self.node.state["run_id"])[:12] + "-" + CLIENT_SUFFIX,
            "foreign_tls_manifest",
        )
        return scope

    def save(self, **values: object) -> None:
        self.node.state["onboarding_tls"] = {**self.scope(), **values}
        self.node.save()

    def report(self, values: dict[str, object]) -> None:
        from tests.support.service_operations_live_node import private_json

        self.node.evidence["onboarding_tls"] = values
        private_json(self.node.directory / "report.json", self.node.evidence)

    async def inspect_owned(self, *, running: bool | None = None) -> dict[str, object]:
        from tests.support.service_operations_live_node import NETWORK

        scope = self.scope()
        checked({"name": self.name} in self.node.rows("containers"), "tls_container_not_recorded")
        raw: object = json.loads(await self.node.docker("inspect", self.name))
        info = json_object(one(raw))
        config = json_object(info.get("Config"))
        host = json_object(info.get("HostConfig"))
        network = json_object(info.get("NetworkSettings"))
        state = json_object(info.get("State"))
        labels = json_object(config.get("Labels"))
        checked(
            info.get("Name") == "/" + self.name
            and labels.get("my-vpn.uc2-run") == self.node.state["run_id"]
            and config.get("Image") == CLIENT_IMAGE
            and host.get("NetworkMode") == NETWORK
            and set(json_object(network.get("Networks"))) == {NETWORK}
            and not host.get("PortBindings")
            and not info.get("Mounts")
            and host.get("Memory") == 128 * 1024 * 1024
            and host.get("PidsLimit") == 64,
            "foreign_or_unbounded_tls_container",
        )
        if scope.get("container_id") is not None:
            checked(info.get("Id") == scope["container_id"], "replaced_tls_container")
        if running is not None:
            checked(state.get("Running") is running, "unexpected_tls_container_state")
        return info

    async def start(self) -> None:
        require_onboarding_environment()
        from tests.support.service_operations_live_node import eventually

        checked("onboarding_tls" not in self.node.state, "tls_manifest_already_exists")
        checked("parent_run_id" not in self.node.state, "tls_requires_root_manifest")
        self.node.state["onboarding_tls"] = {
            "run_id": self.node.state["run_id"],
            "container": self.name,
            "directory": DIRECTORY,
            "directory_created": False,
            "status": "preparing",
        }
        self.node.save()
        try:
            self.directory.mkdir(mode=0o700)
            self.save(directory_created=True)
            material = tls_material()
            payloads = {
                "ca.pem": material.ca,
                "server.pem": material.certificate,
                "server.key": material.key,
                "runtime.py": await asyncio.to_thread(Path(__file__).read_bytes),
            }
            for filename, data in payloads.items():
                private_bytes(self.directory / filename, data)
            self.save(
                file_sha256={
                    key: hashlib.sha256(value).hexdigest() for key, value in payloads.items()
                }
            )
            await self.node.require_local_docker()
            name = await self.node.container(
                CLIENT_SUFFIX,
                CLIENT_IMAGE,
                "--entrypoint",
                "python",
                "-e",
                "QA_SERVICE_OPERATIONS_LIVE_NODE=1",
                command=("-u", str(CONTAINER_DIRECTORY / "runtime.py"), "serve"),
            )
            checked(name == self.name, "unexpected_tls_container_name")
            info = await self.inspect_owned(running=False)
            checked(
                isinstance(info.get("Id"), str) and bool(info["Id"]), "missing_tls_container_id"
            )
            self.save(container_id=info["Id"])
            await self.node.docker(
                "cp", str(self.directory), self.name + ":" + str(CONTAINER_DIRECTORY)
            )
            await self.node.docker("start", self.name)

            async def ready() -> bool:
                return (
                    await self.node.docker(
                        "exec",
                        self.name,
                        "python",
                        "-c",
                        "from pathlib import Path; "
                        "print(Path('/tmp/onboarding-tls/ready.json').is_file())",
                    )
                    == "True"
                )

            await eventually(ready, seconds=30)
            await self.inspect_owned(running=True)
            self.save(status="ready")
            self.report(
                {
                    "status": "ready",
                    "scope": "container_loopback_tls_only",
                    "ca_sha256": hashlib.sha256(material.ca).hexdigest(),
                    "host_trust_modified": False,
                }
            )
        except BaseException as exc:
            self.save(status="failed", failure_type=type(exc).__name__)
            raise

    async def fetch(self, url: str, *, target: LiveNode, identity: str) -> FetchedSubscription:
        require_onboarding_environment()
        subscription_target(url)
        checked(
            self.scope().get("status") in {"ready", "fetched"}, "tls_checkpoint_requires_recovery"
        )
        checked(
            target is self.node or target is getattr(self.node, "companion", None),
            "foreign_subscription_target",
        )
        await self.inspect_owned(running=True)
        evidence: dict[str, object] = {
            "url_sha256": hashlib.sha256(url.encode()).hexdigest(),
            "tls_verified": False,
        }
        try:
            private_bytes(self.directory / "request.json", json.dumps({"url": url}).encode())
            await self.node.docker(
                "cp",
                str(self.directory / "request.json"),
                self.name + ":" + str(CONTAINER_DIRECTORY / "request.json"),
            )
            await self.node.docker(
                "exec", self.name, "python", str(CONTAINER_DIRECTORY / "runtime.py"), "fetch"
            )
            await self.node.docker(
                "cp",
                self.name + ":" + str(CONTAINER_DIRECTORY / "response.json"),
                str(self.directory / "response.json"),
            )
            response_file = self.directory / "response.json"
            checked(
                not response_file.is_symlink() and response_file.stat().st_size <= MAX_BODY * 2,
                "unsafe_subscription_response_file",
            )
            response_file.chmod(0o600)
            raw: object = json.loads(response_file.read_bytes())
            response = json_object(raw)
            for field_name, prefix in (
                ("failure_type", "transport"),
                ("proxy_failure_type", "proxy"),
            ):
                kind = response.get(field_name)
                if isinstance(kind, str) and kind in FAILURE_CODES:
                    evidence[prefix + "_failure_type"] = kind
                    evidence[prefix + "_failure_code"] = FAILURE_CODES[kind]
            checked(response.get("tls_verified") is True, "subscription_tls_failed")
            evidence["tls_verified"] = True
            status, content_type, encoded = (
                response.get("status"),
                response.get("content_type"),
                response.get("body_base64"),
            )
            checked(
                type(status) is int and isinstance(content_type, str) and isinstance(encoded, str),
                "invalid_subscription_response",
            )
            assert (
                isinstance(status, int)
                and isinstance(content_type, str)
                and isinstance(encoded, str)
            )
            body = base64.b64decode(encoded, validate=True)
            evidence.update(diagnostics(body, content_type, status))
            checked(status == 200, "subscription_http_status")
            outbound = subscription_outbound(
                body, content_type, host=target.prefix + "-node", port=12080, identity=identity
            )
            evidence.update(
                {
                    "status": "verified",
                    "protocol": "vless_tcp_no_tls",
                    "credential_sha256": hashlib.sha256(identity.encode()).hexdigest(),
                }
            )
            await self.node.docker(
                "exec",
                self.name,
                "python",
                "-c",
                "from pathlib import Path; p=Path('/tmp/onboarding-tls'); "
                "[(p/n).unlink() for n in ('request.json','response.json')]",
            )
            for filename in ("request.json", "response.json"):
                (self.directory / filename).unlink()
            self.save(status="fetched")
            return FetchedSubscription(outbound, evidence)
        except BaseException as exc:
            code = str(exc) if isinstance(exc, SubscriptionEvidenceError) else type(exc).__name__
            evidence.update({"status": "failed", "failure_code": code})
            self.save(status="failed", failure_type=type(exc).__name__)
            if not isinstance(exc, Exception):
                raise
            raise SubscriptionEvidenceError("subscription_checkpoint_failed") from None
        finally:
            self.report(evidence)

    async def cleanup(self) -> None:
        require_onboarding_environment()
        self.scope()
        try:
            await self.node.require_local_docker()
            existing = await self.node.docker("ps", "-aq", "--filter", "name=^/" + self.name + "$")
            if existing:
                await self.inspect_owned()
                await self.node.docker("rm", "-f", self.name)
            checked(
                not await self.node.docker("ps", "-aq", "--filter", "name=^/" + self.name + "$"),
                "tls_container_cleanup_incomplete",
            )
            checked(not self.directory.is_symlink(), "foreign_tls_directory")
            if self.directory.exists():
                checked(self.scope().get("directory_created") is True, "unowned_tls_directory")
                paths = list(self.directory.iterdir())
                checked(
                    all(
                        path.name in FILES and not path.is_symlink() and path.is_file()
                        for path in paths
                    ),
                    "foreign_tls_file",
                )
                for path in paths:
                    path.unlink()
                self.directory.rmdir()
            self.save(status="cleaned")
        except BaseException as exc:
            self.save(status="cleanup_failed", failure_type=type(exc).__name__)
            raise


async def recover(manifest: Path) -> None:
    database = require_onboarding_environment()
    import re

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests.qa.test_remnawave_panel_contract import _panel_service
    from tests.support.exit_replacement_live_node import ExitNode, cleanup_pair

    panel = _panel_service()
    root = ExitNode(panel, manifest)
    try:
        if root.state.get("target_manifest") is not None:
            checked(
                root.state["target_manifest"] == "target/manifest.json", "foreign_target_manifest"
            )
            root.target(recover=True)
        if root.state.get("onboarding_tls") is not None:
            await SubscriptionTLS(root).cleanup()
        await resolve_onboarding_cleanup(root, database)
        await root.require_local_docker()
        await cleanup_pair(root)
        schema = root.state.get("schema")
        if schema is not None:
            checked(
                isinstance(schema, str)
                and re.fullmatch(r"user_services_test_[0-9a-f]{32}", schema) is not None,
                "foreign_schema",
            )
            engine = create_async_engine(database)
            try:
                async with engine.begin() as connection:
                    await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            finally:
                await engine.dispose()
        if root.companion:
            root.companion.manifest.unlink()
        root.manifest.unlink()
    finally:
        root.close_lock()
        await panel.close_session()


if __name__ == "__main__":
    import sys

    logging.disable(logging.CRITICAL)
    try:
        checked(
            os.environ.get("QA_SERVICE_OPERATIONS_LIVE_NODE") == "1",
            "explicit_live_opt_in_required",
        )
        if len(sys.argv) == 3 and sys.argv[1] == "recover":
            asyncio.run(recover(Path(sys.argv[2]).resolve()))
        else:
            checked(
                len(sys.argv) == 2 and sys.argv[1] in {"serve", "fetch"}, "invalid_runtime_action"
            )
            asyncio.run(
                serve(CONTAINER_DIRECTORY)
                if sys.argv[1] == "serve"
                else fetch_in_container(CONTAINER_DIRECTORY)
            )
    except Exception:
        raise SystemExit("Local subscription runtime failed; inspect sanitized report") from None
