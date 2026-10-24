"""Two disposable r3 paths and a byte-counting origin, restricted to local evidence.

Recover with the same explicit environment:
python -m tests.support.exit_replacement_live_node /tmp/uc2-live-<run>/manifest.json
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from contextlib import suppress
from copy import copy
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.qa.test_remnawave_panel_contract import _panel_service
from tests.support.service_operations_live_adapter import ADAPTER_ENV
from tests.support.service_operations_live_node import (
    IMAGE,
    NETWORK,
    RESOURCE_KEYS,
    LiveNode,
    eventually,
    node_config,
    object_dict,
    private_json,
    require_environment,
)

SCOPE = "isolated_container_network_only; public_fixed_exclusive_egress_not_verified"
ORIGIN = r"""
import asyncio
import json
from contextlib import suppress

rows = []

async def handle(reader, writer):
    row = None
    try:
        header = await reader.readexactly(21)
        op, size, token = header[:1], int.from_bytes(header[1:5], "big"), header[5:].hex()
        assert op in (b"P", b"D", b"U", b"H") and size <= 65536
        row = {"token": token, "op": op.decode(), "peer": writer.get_extra_info("peername")[0],
               "up": 21, "down": 0, "closed": False, "error": None}
        rows.append(row)
        if op == b"U":
            data = await reader.readexactly(size)
            row["up"] += len(data)
            assert data == b"u" * size
            reply = b"K"
        elif op == b"P":
            reply = row["peer"].encode().ljust(16, b" ")
        else:
            reply = b"x" * size
        writer.write(reply)
        await writer.drain()
        row["down"] += len(reply)
        if op == b"H":
            assert await reader.read(1) == b""
    except (OSError, EOFError, AssertionError, asyncio.IncompleteReadError) as exc:
        if row is not None:
            row["error"] = type(exc).__name__
    finally:
        if row is not None:
            row["closed"] = True
        writer.close()
        with suppress(OSError):
            await writer.wait_closed()

async def ledger(reader, writer):
    writer.write(json.dumps(rows).encode())
    await writer.drain()
    writer.close()
    await writer.wait_closed()

async def main():
    data = await asyncio.start_server(handle, "0.0.0.0", 19090)
    control = await asyncio.start_server(ledger, "127.0.0.1", 19091)
    async with data, control:
        await data.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
"""


def require_exit_environment() -> str:
    # The live opt-in check is deliberately first, even before reading a local env file.
    database = require_environment()
    directory = os.environ.get(ADAPTER_ENV)
    if not directory or not Path(directory).is_absolute():
        raise ValueError("Exit replacement requires an explicit absolute r3 artifact directory")
    return database


def ledger_totals(rows: list[dict[str, object]], *, expected_peer: str) -> tuple[int, int]:
    assert rows, "No observed business payload"
    up = down = 0
    for row in rows:
        assert row["closed"] is True and row["error"] is None, "Origin flow remains uncertain"
        assert row["peer"] == expected_peer, "Observed exit differs from the exact local Node"
        sent, received = row["up"], row["down"]
        assert type(sent) is int and type(received) is int and sent >= 21 and received > 0
        up += sent
        down += received
    return up, down


def retained_client(node: LiveNode, port: int, identity: str) -> dict[str, object]:
    """Bind a retained file to the actual service port and credential, never a probe index."""
    assert node.ports.count(port) == 1
    index = node.ports.index(port)
    path = node.directory / f"client-{index}.json"
    fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
    assert fingerprint == node.state[f"client_{index}_sha256"]
    config = object_dict(json.loads(path.read_text()))
    outbounds = config["outbounds"]
    assert isinstance(outbounds, list) and len(outbounds) == 1
    settings = object_dict(object_dict(outbounds[0])["settings"])
    servers = settings["vnext"]
    assert isinstance(servers, list) and len(servers) == 1
    server = object_dict(servers[0])
    assert server["address"] == node.prefix + "-node" and server["port"] == 12080
    users = server["users"]
    assert isinstance(users, list) and len(users) == 1
    assert object_dict(users[0])["id"] == identity, "Retained file is not the service credential"
    return {
        "client_index": index,
        "socks_port": port,
        "config_sha256": fingerprint,
        "credential_sha256": hashlib.sha256(identity.encode()).hexdigest(),
    }


class ExitNode(LiveNode):
    companion: ExitNode | None = None

    async def container(
        self, suffix: str, image: str, *args: str, command: tuple[str, ...] = ()
    ) -> str:
        if suffix == "origin":
            command = ("-u", "-c", ORIGIN)
        return await super().container(suffix, image, *args, command=command)

    async def baseline(self) -> dict[str, object]:
        # Each ordinary LiveNode cleanup still checks the original external inventory.
        # Exclude only exact UUID/name pairs owned by the other half of this same run.
        other = self.companion.rows("resources") if self.companion else []
        result: dict[str, object] = {}
        hashes: dict[str, str] = {}
        for endpoint, (_, key) in RESOURCE_KEYS.items():
            rows = sorted(await self.inventory(endpoint), key=lambda row: str(row["uuid"]))
            owned = {str(row["uuid"]): row["name"] for row in other if row["endpoint"] == endpoint}
            kept = []
            for row in rows:
                if str(row["uuid"]) in owned:
                    assert row[key] == owned[str(row["uuid"])]
                    baseline = object_dict(self.state["baseline"])
                    previous = baseline.get(endpoint, [])
                    assert isinstance(previous, list) and row["uuid"] not in previous
                else:
                    kept.append(row)
            result[endpoint] = [str(UUID(str(row["uuid"]))) for row in kept]
            hashes[endpoint] = hashlib.sha256(json.dumps(kept, sort_keys=True).encode()).hexdigest()
        result["sha256"] = hashes
        return result

    def target(self, *, recover: bool = False) -> ExitNode:
        # Share one advisory lock and panel session, never acquire a second live slot.
        target = copy(self)
        target.directory = self.directory / "target"
        target.manifest = target.directory / "manifest.json"
        if recover:
            target.state = object_dict(json.loads(target.manifest.read_text()))
            assert target.state["parent_run_id"] == self.state["run_id"]
            assert target.state["context"] == self.state["context"]
            assert target.state["image"] == IMAGE
            assert re.fullmatch(r"[0-9a-f]{32}", str(target.state["run_id"]))
        else:
            target.directory.mkdir(mode=0o700)
            target.state = {
                **self.state,
                "run_id": uuid4().hex,
                "parent_run_id": self.state["run_id"],
                "resources": [],
                "containers": [],
                "services": [],
                "schema": None,
            }
        target.prefix = "uc2-" + str(target.state["run_id"])[:12]
        assert target.prefix != self.prefix
        target.ports = []
        target.last_probe = {}
        report = target.directory / "report.json"
        target.evidence = (
            object_dict(json.loads(report.read_text()))
            if recover and report.exists()
            else {
                "run_id": target.state["run_id"],
                "scope": SCOPE,
                "node_image_id": self.evidence.get("node_image_id"),
            }
        )
        target.companion = self
        self.companion = target
        self.state["target_manifest"] = "target/manifest.json"
        target.save()
        self.save()
        return target

    async def setup_target(self) -> None:
        assert self.companion is not None
        self.origin_ip = self.companion.origin_ip
        config = node_config(self.origin_ip)
        inbounds = config["inbounds"]
        assert isinstance(inbounds, list) and len(inbounds) == 1
        # Panel requires inbound tags to be unique across config profiles.
        tag = "UC2_VLESS_" + str(self.state["run_id"])
        object_dict(inbounds[0])["tag"] = tag
        rules = object_dict(config["routing"])["rules"]
        assert isinstance(rules, list)
        for rule in rules:
            object_dict(rule)["inboundTag"] = [tag]
        profile = await self.create_resource(
            "/config-profiles", {"name": self.prefix, "config": config}
        )
        values = await self.api("GET", f"/config-profiles/{profile}/inbounds")
        if isinstance(values, dict):
            values = values.get("inbounds")
        assert isinstance(values, list) and len(values) == 1
        inbound = str(UUID(str(object_dict(values[0])["uuid"])))
        self.squad_id = await self.create_resource(
            "/internal-squads", {"name": self.prefix, "inbounds": [inbound]}
        )
        # The same locally issued Node key is private, never copied into the report.
        source = self.companion.directory / "node.env"
        destination = self.directory / "node.env"
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(source.read_bytes())
        name = await self.container("node", IMAGE, "--env-file", str(destination))
        await self.docker("start", name)
        self.node_id = await self.create_resource(
            "/nodes",
            {
                "name": self.prefix,
                "address": name,
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
                "address": name,
                "port": 12080,
                "inbound": {"configProfileUuid": profile, "configProfileInboundUuid": inbound},
                "nodes": [self.node_id],
                "isDisabled": False,
                "isHidden": False,
                "internalSquads": {"mode": "ALLOW_ONLY", "squads": [self.squad_id]},
            },
        )
        await self.wait_ready()

    async def internal_ip(self) -> str:
        value = await self.docker(
            "inspect",
            "--format",
            '{{(index .NetworkSettings.Networks "' + NETWORK + '").IPAddress}}',
            self.prefix + "-node",
        )
        address = IPv4Address(value)
        assert address.is_private and not address.is_loopback and not address.is_unspecified
        return str(address)

    async def exchange(
        self, port: int, token: str, op: bytes, size: int = 0
    ) -> tuple[bytes, asyncio.StreamReader, asyncio.StreamWriter]:
        assert op in {b"P", b"D", b"U", b"H"} and 0 <= size <= 65536
        reader, writer = await asyncio.wait_for(self.tunnel(port), 4)
        try:
            async with asyncio.timeout(4):
                writer.write(op + size.to_bytes(4, "big") + UUID(token).bytes)
                if op == b"U":
                    writer.write(b"u" * size)
                await writer.drain()
                response = await reader.readexactly(16 if op == b"P" else 1 if op == b"U" else size)
                if op == b"P":
                    assert str(IPv4Address(response.decode().strip())) == await self.internal_ip()
                else:
                    assert response == (b"K" if op == b"U" else b"x" * size)
                if op != b"H":
                    assert await reader.read(1) == b""
                    writer.close()
                    await writer.wait_closed()
                return response, reader, writer
        except BaseException:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()
            raise

    async def ledger(self, token: str) -> list[dict[str, object]]:
        origin = self.companion if "parent_run_id" in self.state else self
        assert origin is not None
        raw = await self.docker(
            "exec",
            origin.prefix + "-origin",
            "python",
            "-c",
            "import socket; s=socket.create_connection(('127.0.0.1',19091),4); "
            "s.settimeout(4); print(s.makefile().read()); s.close()",
        )
        values: object = json.loads(raw)
        assert isinstance(values, list)
        return [object_dict(row) for row in values if object_dict(row)["token"] == token]

    async def rejected(self, port: int, token: str) -> list[dict[str, object]]:
        origin = self.companion if "parent_run_id" in self.state else self
        assert origin is not None
        # Exercise the same data listener directly; the control listener alone is insufficient.
        await self.docker(
            "exec",
            origin.prefix + "-origin",
            "python",
            "-c",
            "import socket,uuid; s=socket.create_connection(('127.0.0.1',19090),4); "
            "s.settimeout(4); s.sendall(b'P'+bytes(4)+uuid.uuid4().bytes); "
            "assert s.makefile('rb').read()==b'127.0.0.1'.ljust(16,b' '); s.close()",
        )
        before = await self.ledger(token)
        probes = []
        for _ in range(3):
            writer = None
            try:
                async with asyncio.timeout(4):
                    reader, writer = await self.tunnel(port)
                    writer.write(b"P" + bytes(4) + UUID(token).bytes)
                    await writer.drain()
                    assert await reader.read(1) == b"", "Retained configuration still transfers"
                probes.append({"socks_ready": True, "outcome": "eof"})
            finally:
                if writer is not None:
                    writer.close()
                    with suppress(OSError):
                        await writer.wait_closed()
        assert await self.ledger(token) == before, "Rejected credentials reached the origin"
        return probes

    async def probe_exit(self) -> dict[str, object]:
        identity = uuid4().hex
        self.remember_service(identity)
        created = await self.panel.create_panel_user(
            username_on_panel="svc_" + identity,
            expire_at=datetime.now(UTC) + timedelta(days=1),
            default_traffic_limit_bytes=65536,
            default_traffic_limit_strategy="NO_RESET",
            specific_squad_uuids=[self.squad_id],
            description="my_vps_obj:service:" + identity,
            status="ACTIVE",
        )
        assert created is not None and not created.get("error")
        remote = object_dict(created.get("response"))
        reference = remote.get("uuid")
        assert isinstance(reference, str) and reference
        port = await self.client(str(remote["vlessUuid"]))
        observations = []
        for _ in range(2):
            payload, _, _ = await self.exchange(port, identity, b"P")
            observations.append(payload.decode().strip())
        assert await self.panel.delete_user_from_panel(reference)

        async def absent() -> bool:
            deleted: bool = await self.panel.get_users_by_filter(username="svc_" + identity) == []
            return deleted

        await eventually(absent, seconds=30)
        rows = await self.ledger(identity)
        assert len(rows) == 2
        ledger_totals(rows, expected_peer=await self.internal_ip())
        return {
            "scope": SCOPE,
            "checked_at": datetime.now(UTC).isoformat(),
            "observed_ips": observations,
            "probe_identity_deleted": True,
            "origin_ledger": rows,
        }


async def cleanup_pair(root: ExitNode) -> None:
    failures = []
    for node in (root.companion, root):
        if node is None:
            continue
        try:
            await node.cleanup()
        except Exception as exc:
            failures.append(type(exc).__name__)
    if failures:
        root.evidence.update({"state": "failed", "cleanup": "failed", "cleanup_errors": failures})
        private_json(root.directory / "report.json", root.evidence)
        raise AssertionError(
            "Scoped exit cleanup incomplete; retain both manifests: " + str(failures)
        )


async def recover(manifest: Path) -> None:
    database = require_exit_environment()
    panel = _panel_service()
    root = ExitNode(panel, manifest)
    try:
        if root.state.get("target_manifest") is not None:
            assert root.state["target_manifest"] == "target/manifest.json"
            root.target(recover=True)
        await root.require_local_docker()
        await cleanup_pair(root)
        schema = root.state.get("schema")
        if schema is not None:
            assert re.fullmatch(r"user_services_test_[0-9a-f]{32}", str(schema))
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

    if len(sys.argv) != 2:
        raise SystemExit("Supply the exact interrupted replacement run's root manifest")
    asyncio.run(recover(Path(sys.argv[1]).resolve()))
