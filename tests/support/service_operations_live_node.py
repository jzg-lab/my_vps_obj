"""Opt-in, manifest-scoped local Node fixture; never changes the default stack.

Recovery after an interrupted run (same opt-in and local environment as the test):
python -m tests.support.service_operations_live_node /tmp/uc2-live-<run>/manifest.json
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from ipaddress import IPv4Address
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from bot.services.panel_api_service import PanelApiService
from tests.qa.test_remnawave_panel_contract import _panel_service, _read_env

CONTEXT = "colima-my-vps-obj"
NETWORK = "my-vps-obj-dev-network"
IMAGE = (
    "remnawave/node:3.4.2@sha256:1f97485b4bc7e4944f1ae95cc57d176376813b0022e9567b705f384f1a2e909d"
)
PROJECT_ENV = Path(__file__).resolve().parents[2] / ".env.project-dev"
RESOURCE_KEYS = {
    "/nodes": ("nodes", "name"),
    "/hosts": ("hosts", "remark"),
    "/internal-squads": ("internalSquads", "name"),
    "/config-profiles": ("configProfiles", "name"),
}
ORIGIN = """
import asyncio
async def handle(reader, writer):
    try:
        op = await reader.readexactly(1)
        size = int.from_bytes(await reader.readexactly(4), 'big')
        if op == b'D':
            writer.write(b'x' * min(size, 65536))
            await writer.drain()
        elif op == b'S':
            for _ in range(min(size, 2400)):
                writer.write(b'x' * 4096)
                await writer.drain()
                await asyncio.sleep(.05)
    except (OSError, asyncio.IncompleteReadError):
        pass
    finally:
        writer.close()
        await writer.wait_closed()
async def main():
    async with await asyncio.start_server(handle, '0.0.0.0', 19090) as server:
        await server.serve_forever()
asyncio.run(main())
"""


def node_config(origin_ip: str) -> dict[str, object]:
    origin = str(IPv4Address(origin_ip)) + "/32"
    return {
        "log": {"loglevel": "info"},
        "inbounds": [
            {
                "tag": "UC2_VLESS",
                "listen": "0.0.0.0",
                "port": 12080,
                "protocol": "vless",
                "settings": {"clients": [], "decryption": "none"},
                "streamSettings": {"network": "tcp", "security": "none"},
            }
        ],
        "outbounds": [
            {
                "tag": "DIRECT",
                "protocol": "freedom",
                "settings": {
                    # Xray 26.7.28 blocks private VLESS targets after routing by default.
                    "finalRules": [
                        {"action": "allow", "network": "tcp", "ip": [origin], "port": "19090"},
                        {"action": "block"},
                    ]
                },
            },
            {"tag": "BLOCK", "protocol": "blackhole"},
        ],
        "routing": {
            "rules": [
                {
                    "type": "field",
                    "inboundTag": ["UC2_VLESS"],
                    "network": "tcp",
                    "ip": [origin],
                    "port": "19090",
                    "outboundTag": "DIRECT",
                },
                {"type": "field", "inboundTag": ["UC2_VLESS"], "outboundTag": "BLOCK"},
            ]
        },
    }


def validate_local_targets(panel_url: str, database_url: str, context: str) -> None:
    """Fail before creating a schema, invoking Docker, or contacting the panel."""
    panel = urlsplit(panel_url)
    database = make_url(database_url)
    loopbacks = {"127.0.0.1", "::1", "localhost"}
    if (
        context != CONTEXT
        or panel.scheme != "http"
        or panel.hostname not in loopbacks
        or panel.port != 3000
        or panel.path.rstrip("/") != "/api"
        or panel.username is not None
        or panel.query
        or panel.fragment
        or database.drivername != "postgresql+asyncpg"
        or database.host not in loopbacks
        or database.query
    ):
        raise ValueError("Live Node evidence requires the isolated loopback project targets")


def require_environment() -> str:
    if os.environ.get("QA_SERVICE_OPERATIONS_LIVE_NODE") != "1":
        raise ValueError("Explicit QA_SERVICE_OPERATIONS_LIVE_NODE=1 is required")
    if Path(os.environ.get("QA_ENV_FILE", "")).resolve() != PROJECT_ENV.resolve():
        raise ValueError("QA_ENV_FILE must identify this checkout's project development file")
    database_url = os.environ.get("CORE_PERFORMANCE_TEST_DATABASE_URL", "")
    validate_local_targets(
        os.environ.get("QA_REMNAWAVE_API_URL", ""),
        database_url,
        os.environ.get("DOCKER_CONTEXT", ""),
    )
    env = _read_env(PROJECT_ENV)
    database = make_url(database_url)
    if (
        env.get("PANEL_WRITE_MODE", "dry_run") != "dry_run"
        or database.port != int(env.get("DEV_POSTGRES_PORT", "6768"))
        or database.database != env.get("POSTGRES_DB")
        or database.username != env.get("POSTGRES_USER")
        or database.password != env.get("POSTGRES_PASSWORD")
    ):
        raise ValueError(
            "Disposable schema must use the local project DB; default mode stays dry_run"
        )
    return database_url


def private_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(".new")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")
    temporary.replace(path)


def object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise AssertionError("Expected a JSON object (sensitive response omitted)")
    return cast(dict[str, object], value)


def log_error_types(raw: str) -> list[str]:
    lowered = raw.lower()
    return sorted(
        {
            category
            for marker, category in (
                ("out of memory", "out_of_memory"),
                ("panic:", "panic"),
                ("invalid user", "invalid_user"),
                ("invalid account", "invalid_account"),
                ("failed to read request header", "request_header_rejected"),
                ("user already exists", "duplicate_user"),
                ("failed to add user", "add_user_failed"),
                ("error adding users", "add_user_failed"),
                ("handler not found", "inbound_handler_missing"),
                ("invalid request", "invalid_request"),
                ("invalid request user id", "request_identity_rejected"),
                ("invalid request address", "request_address_invalid"),
                ("invalid request version", "request_version_invalid"),
                ("failed to read request version", "request_version_missing"),
                ("failed to decode request header addons", "request_addons_invalid"),
                ("is rejected since the client flow is empty", "client_flow_missing"),
                ("is not able to use the flow", "client_flow_mismatch"),
                ("connection refused", "connection_refused"),
                ("connection reset", "connection_reset"),
                ("timeout", "timeout"),
                ("blocked target", "xray_target_blocked"),
                ("failed to build final rule", "xray_final_rule_invalid"),
                ("failed to open connection", "outbound_connect_failed"),
                ("permission denied", "permission_denied"),
                ("cap_net_admin is not available", "connection_drop_capability_missing"),
            )
            if marker in lowered
        }
    )


async def eventually(check: Callable[[], Awaitable[bool]], *, seconds: int = 60) -> None:
    deadline = time.monotonic() + seconds
    while True:
        if await check():
            return
        if time.monotonic() >= deadline:
            raise AssertionError("Local Node observation did not converge within the test deadline")
        await asyncio.sleep(1)


@dataclass
class StreamResult:
    received: int
    reason: str
    ended: float


class LiveNode:
    def __init__(self, panel: PanelApiService, manifest: Path | None = None) -> None:
        if os.name == "nt":
            raise RuntimeError("The live Colima fixture requires a POSIX advisory lock")
        import fcntl

        self.panel = panel
        self.directory = manifest.parent if manifest else Path(tempfile.mkdtemp(prefix="uc2-live-"))
        self.manifest = manifest or self.directory / "manifest.json"
        self.state = (
            object_dict(json.loads(self.manifest.read_text()))
            if manifest
            else {
                "run_id": uuid4().hex,
                "context": CONTEXT,
                "image": IMAGE,
                "resources": [],
                "containers": [],
                "services": [],
                "baseline": {},
                "schema": None,
            }
        )
        assert self.state["context"] == CONTEXT and self.state["image"] == IMAGE
        assert re.fullmatch(r"[0-9a-f]{32}", str(self.state["run_id"]))
        self.prefix = "uc2-" + str(self.state["run_id"])[:12]
        self.ports: list[int] = []
        self.origin_ip = ""
        self.last_probe: dict[str, object] = {}
        report = self.directory / "report.json"
        self.evidence: dict[str, object] = (
            object_dict(json.loads(report.read_text()))
            if manifest and report.exists()
            else {"run_id": self.state["run_id"], "state": "not_run"}
        )
        self.lock = (Path(tempfile.gettempdir()) / "my-vpn-uc2-live-node.lock").open("a+")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self.lock.close()
            raise
        self.save()

    def save(self) -> None:
        private_json(self.manifest, self.state)

    def rows(self, name: str) -> list[dict[str, object]]:
        values = self.state[name]
        assert isinstance(values, list)
        return [object_dict(value) for value in values]

    async def docker(self, *args: str) -> str:
        def execute() -> str:
            result = subprocess.run(
                ["docker", "--context", CONTEXT, *args], capture_output=True, text=True, timeout=45
            )
            if result.returncode:
                raise AssertionError(f"Scoped Docker {args[0]} failed (output redacted)")
            output = result.stdout + result.stderr if args[0] == "logs" else result.stdout
            return output.strip()

        return await asyncio.to_thread(execute)

    async def api(self, method: str, endpoint: str, payload: object = None) -> object:
        response = await self.panel._request(
            method,
            endpoint,
            log_full_response=False,
            **({"json": payload} if payload is not None else {}),
        )
        if not response or response.get("error"):
            raise AssertionError(f"Scoped panel {method} failed (response redacted)")
        return response.get("response")

    async def inventory(self, endpoint: str) -> list[dict[str, object]]:
        result = await self.api("GET", endpoint)
        if isinstance(result, dict):
            body = object_dict(result)
            result = body.get(RESOURCE_KEYS[endpoint][0])
            if not isinstance(result, list) or ("total" in body and body["total"] != len(result)):
                raise AssertionError("Cannot establish a complete local resource inventory")
        assert isinstance(result, list)
        return [object_dict(value) for value in result]

    async def baseline(self) -> dict[str, object]:
        result: dict[str, object] = {}
        fingerprints: dict[str, str] = {}
        for endpoint in RESOURCE_KEYS:
            rows = sorted(await self.inventory(endpoint), key=lambda row: str(row["uuid"]))
            result[endpoint] = [str(UUID(str(row["uuid"]))) for row in rows]
            fingerprints[endpoint] = hashlib.sha256(
                json.dumps(rows, sort_keys=True).encode()
            ).hexdigest()
        result["sha256"] = fingerprints
        return result

    async def require_local_docker(self) -> None:
        socket_url = await self.docker(
            "context", "inspect", CONTEXT, "--format", "{{.Endpoints.docker.Host}}"
        )
        assert socket_url.startswith("unix://") and socket_url.endswith(
            "/.colima/my-vps-obj/docker.sock"
        ), "Refusing a Docker context that does not point at the local project Colima socket"

    async def create_resource(self, endpoint: str, payload: dict[str, object]) -> str:
        row: dict[str, object] = {
            "endpoint": endpoint,
            "name": payload[RESOURCE_KEYS[endpoint][1]],
            "uuid": None,
        }
        rows = self.rows("resources")
        rows.append(row)
        self.state["resources"] = rows
        self.save()
        result = object_dict(await self.api("POST", endpoint, payload))
        row["uuid"] = str(UUID(str(result["uuid"])))
        self.save()
        return str(row["uuid"])

    async def container(
        self, suffix: str, image: str, *args: str, command: tuple[str, ...] = ()
    ) -> str:
        name = self.prefix + "-" + suffix
        rows = self.rows("containers")
        rows.append({"name": name})
        self.state["containers"] = rows
        self.save()
        kind = "client" if suffix.startswith("client-") else suffix
        memory, pids = {
            "node": ("384m", "128"),
            "client": ("128m", "64"),
            "origin": ("96m", "32"),
        }[kind]
        await self.docker(
            "create",
            "--pull=never",
            "--memory",
            memory,
            "--memory-swap",
            memory,
            "--pids-limit",
            pids,
            "--log-driver",
            "json-file",
            "--log-opt",
            "max-size=1m",
            "--log-opt",
            "max-file=1",
            "--name",
            name,
            "--label",
            "my-vpn.uc2-run=" + str(self.state["run_id"]),
            "--network",
            NETWORK,
            # Node 3.4.2 requires this within its bridge namespace to close existing sockets.
            *(("--cap-add", "NET_ADMIN") if kind == "node" else ()),
            *args,
            image,
            *command,
        )
        if suffix == "node" and os.environ.get("QA_SERVICE_OPERATIONS_LIVE_NODE") == "1":
            from tests.support.service_operations_live_adapter import install_adapter

            await install_adapter(self, name, image)
        return name

    async def setup(self) -> str:
        assert self.panel.base_url and self.panel.settings.PANEL_WRITE_MODE == "live"
        await self.require_local_docker()
        baseline = await self.baseline()
        assert baseline["/nodes"] == [] and baseline["/hosts"] == []
        self.state["baseline"] = baseline
        self.state["env_sha256"] = hashlib.sha256(PROJECT_ENV.read_bytes()).hexdigest()
        self.save()
        # Inspect only: missing/pinned images must be supplied by the main window.
        image = object_dict(json.loads(await self.docker("image", "inspect", IMAGE))[0])
        assert IMAGE.split("@", 1)[1] in " ".join(cast(list[str], image["RepoDigests"]))
        self.evidence["node_image_id"] = image["Id"]
        self.evidence["node_image_digest"] = IMAGE
        await self.docker("network", "inspect", NETWORK)
        origin = await self.container(
            "origin",
            "my-vps-obj-backend:dev",
            "--entrypoint",
            "python",
            command=("-u", "-c", ORIGIN),
        )
        await self.docker("start", origin)
        self.origin_ip = (
            await self.docker(
                "inspect",
                "--format",
                '{{(index .NetworkSettings.Networks "' + NETWORK + '").IPAddress}}',
                origin,
            )
        ).strip()
        assert re.fullmatch(r"\d+\.\d+\.\d+\.\d+", self.origin_ip)
        profile = await self.create_resource(
            "/config-profiles", {"name": self.prefix, "config": node_config(self.origin_ip)}
        )
        inbounds = await self.api("GET", f"/config-profiles/{profile}/inbounds")
        if isinstance(inbounds, dict):
            inbounds = inbounds.get("inbounds")
        assert isinstance(inbounds, list) and len(inbounds) == 1
        inbound = str(UUID(str(object_dict(inbounds[0])["uuid"])))
        squad = await self.create_resource(
            "/internal-squads", {"name": self.prefix, "inbounds": [inbound]}
        )
        secret = object_dict(await self.api("GET", "/keygen"))["secretKey"]
        assert isinstance(secret, str) and secret and "\n" not in secret
        env_path = self.directory / "node.env"
        descriptor = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            handle.write("NODE_PORT=2222\nSECRET_KEY=" + secret + "\n")
        node_name = await self.container("node", IMAGE, "--env-file", str(env_path))
        await self.docker("start", node_name)
        self.node_id = await self.create_resource(
            "/nodes",
            {
                "name": self.prefix,
                "address": node_name,
                "port": 2222,
                "consumptionMultiplier": 1,
                "nodeConsumptionMultiplier": 1,
                "configProfile": {"activeConfigProfileUuid": profile, "activeInbounds": [inbound]},
            },
        )
        self.host_id = await self.create_resource(
            "/hosts",
            {
                "remark": self.prefix,
                "address": node_name,
                "port": 12080,
                "inbound": {"configProfileUuid": profile, "configProfileInboundUuid": inbound},
                "nodes": [self.node_id],
                "isDisabled": False,
                "isHidden": False,
                "internalSquads": {"mode": "ALLOW_ONLY", "squads": [squad]},
            },
        )
        self.squad_id = squad
        self.evidence["xray_version"] = (
            await self.docker("exec", node_name, "xray", "version")
        ).splitlines()[0]
        await self.wait_ready()
        return squad

    async def wait_ready(self) -> None:
        async def ready() -> bool:
            rows = await self.inventory("/nodes")
            node = next((row for row in rows if row.get("uuid") == self.node_id), {})
            self.evidence["node_ready_before_services"] = {
                "node_uuid": self.node_id,
                "observed_at": datetime.now(UTC).isoformat(),
                **{
                    key: node.get(key) if isinstance(node.get(key), bool) else None
                    for key in ("isConnected", "isConnecting", "isDisabled")
                },
            }
            return (
                node.get("isConnected") is True
                and node.get("isConnecting") is False
                and node.get("isDisabled") is False
            )

        await eventually(ready)

    def remember_service(self, service_id: str) -> None:
        assert re.fullmatch(r"[0-9a-f]{32}", service_id)
        rows = self.rows("services")
        rows.append({"id": service_id})
        self.state["services"] = rows
        self.save()

    async def client(self, identity: str) -> int:
        UUID(identity)
        index = len(self.ports)
        path = self.directory / f"client-{index}.json"
        private_json(
            path,
            {
                "log": {"loglevel": "info"},
                "inbounds": [
                    {
                        "listen": "0.0.0.0",
                        "port": 1080,
                        "protocol": "socks",
                        "settings": {"auth": "noauth", "udp": False},
                    }
                ],
                "outbounds": [
                    {
                        "protocol": "vless",
                        "settings": {
                            "vnext": [
                                {
                                    "address": self.prefix + "-node",
                                    "port": 12080,
                                    "users": [{"id": identity, "encryption": "none"}],
                                }
                            ]
                        },
                        "streamSettings": {"network": "tcp", "security": "none"},
                    }
                ],
            },
        )
        name = await self.container(
            "client-" + str(index),
            IMAGE,
            "-p",
            "127.0.0.1::1080",
            "--entrypoint",
            "xray",
            command=("run", "-config", "/tmp/client.json"),
        )
        await self.docker("cp", str(path), name + ":/tmp/client.json")
        await self.docker("start", name)
        published = await self.docker("port", name, "1080/tcp")
        assert published.startswith("127.0.0.1:") and "\n" not in published
        port = int(published.rsplit(":", 1)[1])
        self.ports.append(port)
        self.state[f"client_{index}_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.save()
        return port

    async def tunnel(self, port: int) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        try:
            self.last_probe["stage"] = "socks_handshake"
            writer.write(b"\x05\x01\x00")
            await writer.drain()
            assert await reader.readexactly(2) == b"\x05\x00"
            self.last_probe["socks_ready"] = True
            self.last_probe["stage"] = "proxy_connect"
            host = self.origin_ip.encode("ascii")
            writer.write(
                b"\x05\x01\x00\x03" + bytes([len(host)]) + host + (19090).to_bytes(2, "big")
            )
            await writer.drain()
            response = await reader.readexactly(4)
            self.last_probe["socks_reply"] = response[1]
            assert response[1] == 0, "SOCKS connection rejected"
            size = (
                4
                if response[3] == 1
                else 16
                if response[3] == 4
                else (await reader.readexactly(1))[0]
            )
            await reader.readexactly(size + 2)
            self.last_probe["stage"] = "payload_read"
            return reader, writer
        except BaseException:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()
            raise

    async def transfer(self, port: int) -> bool:
        writer = None
        self.last_probe = {
            "socks_ready": False,
            "port": port,
            "stage": "client_connect",
            "observed_at": datetime.now(UTC).isoformat(),
        }
        try:
            async with asyncio.timeout(4):
                reader, writer = await self.tunnel(port)
                writer.write(b"D" + (1024).to_bytes(4, "big"))
                await writer.drain()
                success = await reader.readexactly(1024) == b"x" * 1024
                self.last_probe["stage"] = "payload_complete" if success else "payload_mismatch"
                return success
        except (OSError, EOFError, asyncio.IncompleteReadError, AssertionError) as exc:
            self.last_probe["reason"] = type(exc).__name__
            return False
        finally:
            if writer is not None:
                writer.close()
                with suppress(OSError):
                    await writer.wait_closed()

    async def blocked(self, port: int) -> None:
        # Prove the origin and local SOCKS listener still work before accepting a rejection.
        await self.docker(
            "exec",
            self.prefix + "-origin",
            "python",
            "-c",
            "import socket; s=socket.create_connection(('127.0.0.1',19090),4); "
            "s.sendall(b'D'+(1).to_bytes(4,'big')); assert s.recv(1)==b'x'; s.close()",
        )
        probes = []
        for _ in range(3):
            assert not await self.transfer(port), (
                "Retained disabled configuration still transfers payload"
            )
            assert self.last_probe["socks_ready"], "Client failure cannot prove identity rejection"
            probes.append(dict(self.last_probe))
        self.evidence.setdefault("rejected_probes", [])
        recorded = self.evidence["rejected_probes"]
        assert isinstance(recorded, list)
        recorded.extend(probes)

    async def stream(self, port: int, started: asyncio.Event) -> StreamResult:
        received = 0
        writer = None
        reason = "eof"
        try:
            async with asyncio.timeout(25):
                reader, writer = await self.tunnel(port)
                writer.write(b"S" + (2400).to_bytes(4, "big"))
                await writer.drain()
                while data := await reader.read(65536):
                    received += len(data)
                    started.set()
        except TimeoutError:
            reason = "timeout"
        except (OSError, EOFError, asyncio.IncompleteReadError) as exc:
            reason = type(exc).__name__
        finally:
            if writer is not None:
                writer.close()
                with suppress(OSError):
                    await writer.wait_closed()
        return StreamResult(received, reason, time.monotonic())

    async def capture_failure(self) -> None:
        self.evidence["last_probe"] = {
            key: value
            for key, value in self.last_probe.items()
            if key in {"port", "stage", "reason", "socks_ready", "socks_reply", "observed_at"}
        }
        containers: list[dict[str, object]] = []
        self.evidence["failure_containers"] = containers
        try:
            async with asyncio.timeout(15):
                for container in self.rows("containers"):
                    name = str(container["name"])
                    assert name.startswith(self.prefix + "-")
                    observation: dict[str, object] = {"name": name}
                    containers.append(observation)
                    try:
                        state = object_dict(
                            json.loads(
                                await self.docker("inspect", "--format", "{{json .State}}", name)
                            )
                        )
                        observation["state"] = {
                            key: state.get(key) if type(state.get(key)) is expected else None
                            for key, expected in (
                                ("Running", bool),
                                ("OOMKilled", bool),
                                ("ExitCode", int),
                            )
                        }
                        status = state.get("Status")
                        observation["status"] = (
                            status
                            if status
                            in (
                                "created",
                                "running",
                                "paused",
                                "restarting",
                                "removing",
                                "exited",
                                "dead",
                            )
                            else "unknown"
                        )
                        observation["log_error_types"] = log_error_types(
                            await self.docker("logs", "--tail", "40", name)
                        )
                        if name.endswith("-node"):
                            observation["kernel_error_types"] = log_error_types(
                                await self.docker(
                                    "exec",
                                    name,
                                    "node",
                                    "-e",
                                    "const fs=require('fs');process.stdout.write("
                                    "fs.readFileSync('/var/log/xray/current','utf8')"
                                    ".split('\\n').slice(-40).join('\\n'));",
                                )
                            )
                    except Exception as exc:
                        observation["diagnostic_error"] = type(exc).__name__
        except Exception as exc:
            self.evidence["failure_diagnostics_error"] = type(exc).__name__
        private_json(self.directory / "report.json", self.evidence)

    async def cleanup(self) -> None:
        errors: list[str] = []
        # Continue independent cleanup after a failure; leave manifest for exact recovery.
        for service in self.rows("services"):
            identity = str(service["id"])
            assert re.fullmatch(r"[0-9a-f]{32}", identity)
            try:
                users = await self.panel.get_users_by_filter(username="svc_" + identity)
                assert users is not None
                for user in users:
                    assert user.get("username") == "svc_" + identity
                    assert user.get("description") == "my_vps_obj:service:" + identity
                    # Panel 3.x normalizes numeric ids into this historical uuid key.
                    reference = user.get("uuid")
                    assert isinstance(reference, str) and reference.strip()
                    assert await self.panel.delete_user_from_panel(reference)

                async def identity_absent(service_id: str = identity) -> bool:
                    observed = await self.panel.get_users_by_filter(username="svc_" + service_id)
                    return isinstance(observed, list) and len(observed) == 0

                await eventually(identity_absent, seconds=30)
            except Exception:
                errors.append("identity:" + identity)
        for resource in reversed(self.rows("resources")):
            endpoint = str(resource["endpoint"])
            assert endpoint in RESOURCE_KEYS and str(resource["name"]) == self.prefix
            try:
                rows = await self.inventory(endpoint)
                matches = [
                    row for row in rows if row.get(RESOURCE_KEYS[endpoint][1]) == self.prefix
                ]
                assert len(matches) <= 1
                for row in matches:
                    ref = str(UUID(str(row["uuid"])))
                    baseline = object_dict(self.state["baseline"])
                    assert ref not in cast(list[str], baseline[endpoint])
                    assert resource["uuid"] in (None, ref)
                    resource["uuid"] = ref
                    self.save()
                    await self.api("DELETE", endpoint + "/" + ref)

                    async def resource_absent(path: str = endpoint, target: str = ref) -> bool:
                        return all(str(row["uuid"]) != target for row in await self.inventory(path))

                    # Node DELETE acknowledges the queued stop/delete job, not its completion.
                    await eventually(resource_absent, seconds=30)
            except Exception:
                errors.append(endpoint + ":" + str(resource["uuid"]))
        for container in reversed(self.rows("containers")):
            name = str(container["name"])
            assert name.startswith(self.prefix + "-")
            try:
                existing = await self.docker("ps", "-aq", "--filter", "name=^/" + name + "$")
                if existing:
                    label = await self.docker(
                        "inspect", "--format", '{{index .Config.Labels "my-vpn.uc2-run"}}', name
                    )
                    assert label == self.state["run_id"]
                    await self.docker("rm", "-f", name)
                assert not await self.docker("ps", "-aq", "--filter", "name=^/" + name + "$")
            except Exception:
                errors.append("container:" + name)
        for path in self.directory.iterdir():
            if path.name in {"node.env", "origin.py", "client-0.json", "client-1.json"}:
                path.unlink()
        if self.state["baseline"]:
            try:
                assert await self.baseline() == self.state["baseline"]
                assert (
                    hashlib.sha256(PROJECT_ENV.read_bytes()).hexdigest() == self.state["env_sha256"]
                )
            except Exception:
                errors.append("baseline_changed")
        self.evidence["cleanup_errors"] = errors
        self.evidence["cleanup"] = "failed" if errors else "passed"
        if errors:
            self.evidence["state"] = "failed"
        private_json(self.directory / "report.json", self.evidence)
        if errors:
            raise AssertionError(
                f"Scoped cleanup incomplete; retain {self.manifest}: " + ", ".join(errors)
            )

    def close_lock(self) -> None:
        self.lock.close()


async def recover(manifest: Path) -> None:
    database_url = require_environment()
    panel = _panel_service()
    fixture = LiveNode(panel, manifest)
    try:
        await fixture.require_local_docker()
        await fixture.cleanup()
        schema = fixture.state.get("schema")
        if schema is not None:
            assert re.fullmatch(r"user_services_test_[0-9a-f]{32}", str(schema))
            engine = create_async_engine(database_url)
            try:
                async with engine.begin() as connection:
                    await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            finally:
                await engine.dispose()
        fixture.evidence["schema_cleanup"] = "exact recorded temporary schema removed"
        private_json(fixture.directory / "report.json", fixture.evidence)
        fixture.manifest.unlink()
    finally:
        fixture.close_lock()
        await panel.close_session()


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        raise SystemExit("Supply the exact interrupted run's manifest path")
    asyncio.run(recover(Path(sys.argv[1]).resolve()))
