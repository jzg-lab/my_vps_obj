"""UC2-SAME-SOURCE-REGRESSION: F04 / UC-04/05 / UA-10/12.

Default: offline observation tests run; the real Node test skips. The main window
owns the exclusive live slot and supplies the existing LiveNode opt-in environment.
Run only ::test_real_node_same_source_service_isolation in that slot. Node 3.4.2's
known sibling disconnect must FAIL, not xfail. No private environment loader here.
Failed runs retain report.json and the original LiveNode recovery manifest; use
python -m tests.support.service_operations_live_node <exact-manifest> to recover.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from ipaddress import IPv4Address
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.services.panel_api_service import PanelApiService
from config.service_periods import as_utc
from tests.integration.test_service_operations_live_node import LiveScenario
from tests.integration.test_user_services_postgres import scenario
from tests.qa.test_remnawave_panel_contract import _panel_service
from tests.support.service_operations_live_node import (
    NETWORK,
    LiveNode,
    StreamResult,
    object_dict,
    private_json,
    require_environment,
)


@dataclass
class StreamObservation:
    received: int = 0
    outcome: str = "reading"
    last_payload_monotonic: float | None = None
    observer_ended_monotonic: float | None = None
    observer_cancelled: bool = False


async def read_stream(
    reader: asyncio.StreamReader,
    observation: StreamObservation,
    started: asyncio.Event,
    *,
    read_timeout: float = 2,
) -> None:
    """Drain throughout the operation; silence is inconclusive, never isolation."""
    try:
        while True:
            data = await asyncio.wait_for(reader.read(65536), read_timeout)
            if not data:
                observation.outcome = "eof"
                return
            if data != b"x" * len(data):
                observation.outcome = "payload_mismatch"
                return
            observation.received += len(data)
            observation.last_payload_monotonic = time.monotonic()
            if observation.received >= 8192:
                started.set()
    except TimeoutError:
        observation.outcome = "stalled"
    except OSError as exc:
        observation.outcome = type(exc).__name__
    except asyncio.CancelledError:
        observation.observer_cancelled = True
        raise
    finally:
        observation.observer_ended_monotonic = time.monotonic()


def assert_continuing(
    observation: StreamObservation,
    *,
    done: bool,
    after_bytes: int,
    requested_at: float,
    checked_at: float,
) -> None:
    assert 0 <= checked_at - requested_at < 45, (
        "Observation exceeded its bound; cannot exclude natural stream completion"
    )
    assert not done and observation.outcome == "reading", "Sibling stream ended or stalled"
    assert not observation.observer_cancelled and observation.observer_ended_monotonic is None
    assert observation.received > after_bytes >= 8192, "No payload after pause"
    assert observation.last_payload_monotonic is not None
    assert 0 <= checked_at - observation.last_payload_monotonic < 2, "No recent sibling payload"


def object_rows(value: object) -> list[dict[str, object]]:
    assert isinstance(value, list), "Expected an observation array (response redacted)"
    return [object_dict(row) for row in value]


class SameSourceNode(LiveNode):
    async def container(
        self, suffix: str, image: str, *args: str, command: tuple[str, ...] = ()
    ) -> str:
        if suffix == "client-0":
            args = (*args, "-p", "127.0.0.1::1081")
        return await super().container(suffix, image, *args, command=command)

    async def client(self, identity: str) -> int:
        if not self.ports:
            return await super().client(identity)
        assert len(self.ports) == 1
        UUID(identity)
        config = object_dict(json.loads((self.directory / "client-0.json").read_text()))
        object_rows(config["inbounds"])[0]["port"] = 1081
        settings = object_dict(object_rows(config["outbounds"])[0]["settings"])
        user = object_rows(object_rows(settings["vnext"])[0]["users"])[0]
        assert user["id"] != identity, "Two distinct service credentials are required"
        user["id"] = identity
        path = self.directory / "client-1.json"
        private_json(path, config)
        name = self.prefix + "-client-0"
        await self.docker("cp", str(path), name + ":/tmp/client-1.json")
        await self.docker("exec", "-d", name, "xray", "run", "-config", "/tmp/client-1.json")
        published = await self.docker("port", name, "1081/tcp")
        assert published.startswith("127.0.0.1:") and "\n" not in published
        port = int(published.rsplit(":", 1)[1])
        assert port != self.ports[0]
        self.ports.append(port)
        self.state["client_1_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.save()
        return port

    async def stream(self, port: int, started: asyncio.Event) -> StreamResult:
        observation = StreamObservation()
        writer: asyncio.StreamWriter | None = None
        try:
            async with asyncio.timeout(25):
                reader, writer = await self.tunnel(port)
                writer.write(b"S" + (2400).to_bytes(4, "big"))
                await writer.drain()
                await read_stream(reader, observation, started)
            assert observation.outcome == "eof", "Target stream did not terminate with valid EOF"
            assert observation.observer_ended_monotonic is not None
            return StreamResult(
                observation.received, observation.outcome, observation.observer_ended_monotonic
            )
        finally:
            if writer is not None:
                writer.close()
                with suppress(OSError, TimeoutError):
                    await asyncio.wait_for(writer.wait_closed(), 2)

    async def source_health(self) -> dict[str, object]:
        name = self.prefix + "-client-0"
        source = str(
            IPv4Address(
                await self.docker(
                    "inspect",
                    "--format",
                    '{{(index .NetworkSettings.Networks "' + NETWORK + '").IPAddress}}',
                    name,
                )
            )
        )
        processes = object_rows(
            json.loads(
                await self.docker(
                    "exec",
                    name,
                    "node",
                    "-e",
                    r"""
const fs = require('fs'); const rows = [];
for (const pid of fs.readdirSync('/proc').filter(p => /^\d+$/.test(p))) {
  try {
    const argv = fs.readFileSync(`/proc/${pid}/cmdline`, 'utf8').split('\0');
    if (argv[0].split('/').pop() === 'xray')
      rows.push({pid: Number(pid), netns: fs.readlinkSync(`/proc/${pid}/ns/net`)});
  } catch (_) {}
}
process.stdout.write(JSON.stringify(rows.sort((a, b) => a.pid - b.pid)));
""",
                )
            )
        )
        containers: list[dict[str, object]] = []
        for row in self.rows("containers"):
            container = str(row["name"])
            assert container in {
                self.prefix + suffix for suffix in ("-origin", "-node", "-client-0")
            }
            info = object_dict(json.loads(await self.docker("inspect", container))[0])
            state = object_dict(info["State"])
            containers.append(
                {
                    "name": container,
                    "id": info["Id"],
                    "restart_count": info["RestartCount"],
                    **{key: state[key] for key in ("Running", "OOMKilled", "StartedAt", "Pid")},
                }
            )
        return {
            "container": name,
            "network": NETWORK,
            "source_ip": source,
            "xray_processes": processes,
            "containers": containers,
        }


def assert_healthy(health: dict[str, object]) -> None:
    processes = object_rows(health["xray_processes"])
    assert len(processes) == 2 and len({row["pid"] for row in processes}) == 2
    for row in processes:
        pid = row["pid"]
        assert type(pid) is int and pid > 0
    namespaces = {row["netns"] for row in processes}
    assert len(namespaces) == 1 and all(
        isinstance(value, str) and value.startswith("net:[") for value in namespaces
    ), "The two Xray processes must share one network namespace"
    assert health["network"] == NETWORK
    assert not IPv4Address(str(health["source_ip"])).is_unspecified
    containers = object_rows(health["containers"])
    assert len(containers) == 3 and len({row["name"] for row in containers}) == 3
    for row in containers:
        assert row["Running"] is True and row["OOMKilled"] is False, "Container stopped or OOM"
        assert type(row["restart_count"]) is int and row["restart_count"] == 0
        assert row["StartedAt"] and row["id"] and row["Pid"]


async def sibling_rights(case: LiveScenario) -> dict[str, object]:
    service, connection = await case.saved(1)
    remote = await case.remote(1)
    assert service.desired_status == "active" and remote["status"] == "ACTIVE"
    assert as_utc(service.expires_at) > datetime.now(UTC)
    assert service.used_bytes < service.quota_bytes
    assert connection.panel_user_uuid and str(remote["uuid"]) == connection.panel_user_uuid
    UUID(str(remote["vlessUuid"]))
    return {
        "desired_status": service.desired_status,
        "revision": service.revision,
        "quota_bytes": service.quota_bytes,
        "expires_at": as_utc(service.expires_at).isoformat(),
        "panel_identity_sha256": hashlib.sha256(connection.panel_user_uuid.encode()).hexdigest(),
        "remote_identity_sha256": hashlib.sha256(str(remote["uuid"]).encode()).hexdigest(),
        "vless_identity_sha256": hashlib.sha256(str(remote["vlessUuid"]).encode()).hexdigest(),
        "remote_status": remote["status"],
        "remote_quota": remote["trafficLimitBytes"],
        "remote_expires_at": remote["expireAt"],
    }


def assert_target_rejected(report: dict[str, object], port: int) -> float:
    pause = object_dict(report["pause"])
    requested = pause["requested_monotonic"]
    assert isinstance(requested, float)
    streams = object_rows(pause["streams"])
    assert len(streams) == 1 and streams[0]["reason"] == "eof"
    received, ended = streams[0]["received"], streams[0]["ended"]
    assert isinstance(received, int) and received >= 8192
    assert isinstance(ended, float) and ended >= requested
    assert pause["retained_configs"] == "rejected"
    probes = object_rows(report["rejected_probes"])
    assert len(probes) == 3
    for probe in probes:
        assert probe["port"] == port and probe["socks_ready"] is True
        reason = probe.get("reason")
        reply = probe.get("socks_reply")
        assert reason in {"IncompleteReadError", "ConnectionResetError", "BrokenPipeError"} or (
            reason == "AssertionError" and type(reply) is int and reply != 0
        ), "Timeout, bad payload or client failure cannot prove retained-config rejection"
    return requested


async def check_isolation(case: LiveScenario, fixture: SameSourceNode) -> None:
    report = fixture.evidence
    report["sibling_rights_before"] = await sibling_rights(case)
    before = await fixture.source_health()
    report["source_before"] = before
    report["source_before_observed_at"] = datetime.now(UTC).isoformat()
    assert_healthy(before)
    observation = StreamObservation()
    task: asyncio.Task[None] | None = None
    writer: asyncio.StreamWriter | None = None
    try:
        async with asyncio.timeout(5):
            reader, writer = await fixture.tunnel(fixture.ports[1])
            writer.write(b"S" + (2400).to_bytes(4, "big"))
            await writer.drain()
        started = asyncio.Event()
        task = asyncio.create_task(read_stream(reader, observation, started))
        await asyncio.wait_for(started.wait(), 5)
        assert not task.done(), "Sibling stream ended before pause"
        report["sibling_initial_bytes"] = observation.received
        pause_call = time.monotonic()
        report["pause_call_monotonic"] = pause_call
        async with asyncio.timeout(30):
            await case.restrict(banned=False)
        report["pause_returned_monotonic"] = time.monotonic()
        after_bytes = observation.received
        report["sibling_bytes_at_pause_return"] = after_bytes
        await asyncio.sleep(3)
        report["sibling_bytes_after_observation"] = observation.received
        report["sibling_rights_after"] = await sibling_rights(case)
        after = await fixture.source_health()
        report["source_after"] = after
        report["source_after_observed_at"] = datetime.now(UTC).isoformat()
        report["sibling_new_connection_usable"] = await fixture.transfer(fixture.ports[1])
        for index in (0, 1):
            path = fixture.directory / f"client-{index}.json"
            assert (
                hashlib.sha256(path.read_bytes()).hexdigest()
                == fixture.state[f"client_{index}_sha256"]
            ), "Retained client configuration changed"
        assert report["sibling_rights_after"] == report["sibling_rights_before"]
        assert_healthy(after)
        assert after == before, "Source IP, namespace, processes or container lifetime changed"
        assert report["sibling_new_connection_usable"] is True
        requested_at = assert_target_rejected(report, fixture.ports[0])
        checked_at = time.monotonic()
        report["checked_monotonic"] = checked_at
        report["sibling_stream_at_check"] = asdict(observation)
        assert 0 <= checked_at - pause_call < 45, "Observation exceeded its bound; inconclusive"
        if observation.outcome in {"eof", "ConnectionResetError", "BrokenPipeError"}:
            assert observation.observer_ended_monotonic is not None
            assert observation.observer_ended_monotonic >= requested_at, (
                "Sibling ended before the pause request; inconclusive"
            )
            report["verdict"] = "sibling_established_stream_cut"
            raise AssertionError("Pausing service0 cut the valid sibling's established stream")
        assert_continuing(
            observation,
            done=task.done(),
            after_bytes=after_bytes,
            requested_at=pause_call,
            checked_at=checked_at,
        )
        report["verdict"] = "isolation_observed"
    finally:
        report["sibling_stream"] = asdict(observation)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if writer is not None:
            writer.close()
            with suppress(OSError, TimeoutError):
                await asyncio.wait_for(writer.wait_closed(), 2)


def run_same_source_regression() -> None:
    require_environment()  # Validate opt-in and targets before scenario can create a schema.
    fixture: SameSourceNode | None = None

    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        nonlocal fixture
        panel = _panel_service()
        try:
            fixture = SameSourceNode(panel)
        except BaseException:
            await panel.close_session()
            raise
        report = fixture.evidence
        report.update({"probe": "UC2-SAME-SOURCE-REGRESSION", "verdict": "inconclusive"})
        print(f"Same-source manifest: {fixture.manifest}", flush=True)
        print(f"Same-source report: {fixture.directory / 'report.json'}", flush=True)
        try:
            async with factory() as session:
                fixture.state["schema"] = await session.scalar(text("SELECT current_schema()"))
                fixture.save()
            squad = await fixture.setup()
            case = LiveScenario(factory, fixture)
            await case.prepare(squad)
            await check_isolation(case, fixture)
            report["state"] = "passed"
        except BaseException as exc:
            report["state"] = "failed"
            report["failure_type"] = type(exc).__name__
            await fixture.capture_failure()
            raise
        finally:
            try:
                cleanup = asyncio.create_task(fixture.cleanup())
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    await cleanup
                    raise
            finally:
                fixture.close_lock()
                await panel.close_session()

    try:
        scenario(run)
    except BaseException as exc:
        if fixture is not None:
            fixture.evidence["state"] = "failed"
            fixture.evidence["failure_type"] = type(exc).__name__
            fixture.evidence["schema_cleanup"] = "scenario failed; recover exact recorded schema"
        raise
    else:
        assert fixture is not None
        fixture.evidence["schema_cleanup"] = "temporary schema dropped by scenario finally"
    finally:
        if fixture is not None:
            private_json(fixture.directory / "report.json", fixture.evidence)
    assert fixture is not None and fixture.evidence["state"] == "passed"
    assert fixture.evidence["cleanup"] == "passed"
    fixture.manifest.unlink()


def test_real_node_same_source_service_isolation() -> None:
    if os.environ.get("QA_SERVICE_OPERATIONS_LIVE_NODE") != "1":
        pytest.skip("Requires explicit exclusive local real Node evidence slot")
    run_same_source_regression()


def test_same_source_defaults_to_skip_before_environment_or_schema_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QA_SERVICE_OPERATIONS_LIVE_NODE", raising=False)

    def forbidden() -> None:
        pytest.fail("Default skip must precede environment, Docker, API and database access")

    monkeypatch.setattr(sys.modules[__name__], "run_same_source_regression", forbidden)
    with pytest.raises(pytest.skip.Exception, match="exclusive local"):
        test_real_node_same_source_service_isolation()


@pytest.mark.parametrize("ending", ["eof", "stalled", "payload_mismatch", "ConnectionResetError"])
def test_stream_observation_never_accepts_a_terminated_or_stalled_stream(ending: str) -> None:
    async def run() -> None:
        reader = asyncio.StreamReader()
        observation = StreamObservation()
        started = asyncio.Event()
        reader.feed_data(b"x" * 8192)
        task = asyncio.create_task(read_stream(reader, observation, started, read_timeout=0.02))
        await asyncio.wait_for(started.wait(), 1)
        requested_at = time.monotonic()
        if ending == "eof":
            reader.feed_eof()
        elif ending == "payload_mismatch":
            reader.feed_data(b"wrong payload")
        elif ending == "ConnectionResetError":
            reader.set_exception(ConnectionResetError("offline reset"))
        await asyncio.wait_for(task, 1)
        assert observation.outcome == ending and observation.received == 8192
        assert observation.observer_ended_monotonic is not None
        assert not observation.observer_cancelled
        with pytest.raises(AssertionError, match="ended or stalled"):
            assert_continuing(
                observation,
                done=task.done(),
                after_bytes=8192,
                requested_at=requested_at,
                checked_at=time.monotonic(),
            )

    asyncio.run(run())


def test_stream_cancellation_is_propagated_and_cannot_count_as_continuity() -> None:
    async def run() -> None:
        reader = asyncio.StreamReader()
        reader.feed_data(b"x" * 8192)
        observation = StreamObservation()
        started = asyncio.Event()
        task = asyncio.create_task(read_stream(reader, observation, started))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert observation.observer_cancelled and observation.observer_ended_monotonic is not None
        with pytest.raises(AssertionError):
            assert_continuing(
                observation,
                done=False,
                after_bytes=8192,
                requested_at=time.monotonic(),
                checked_at=time.monotonic(),
            )

    asyncio.run(run())


def test_stream_continuity_requires_fresh_valid_payload_on_the_original_reader() -> None:
    async def run() -> None:
        reader = asyncio.StreamReader()
        observation = StreamObservation()
        started = asyncio.Event()
        reader.feed_data(b"x" * 8192)
        task = asyncio.create_task(read_stream(reader, observation, started))
        try:
            await asyncio.wait_for(started.wait(), 1)
            after_bytes = observation.received
            requested_at = time.monotonic()
            with pytest.raises(AssertionError, match="No payload after pause"):
                assert_continuing(
                    observation,
                    done=task.done(),
                    after_bytes=after_bytes,
                    requested_at=requested_at,
                    checked_at=time.monotonic(),
                )
            started.clear()
            reader.feed_data(b"x" * 4096)
            await asyncio.wait_for(started.wait(), 1)
            assert_continuing(
                observation,
                done=task.done(),
                after_bytes=after_bytes,
                requested_at=requested_at,
                checked_at=time.monotonic(),
            )
            with pytest.raises(AssertionError, match="exceeded"):
                assert_continuing(
                    observation,
                    done=False,
                    after_bytes=after_bytes,
                    requested_at=requested_at,
                    checked_at=requested_at + 45,
                )
            assert observation.last_payload_monotonic is not None
            with pytest.raises(AssertionError, match="No recent"):
                assert_continuing(
                    observation,
                    done=False,
                    after_bytes=after_bytes,
                    requested_at=requested_at,
                    checked_at=observation.last_payload_monotonic + 2,
                )
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())


@pytest.mark.parametrize(
    "reason", ["IncompleteReadError", "TimeoutError", "payload_mismatch", "ConnectionRefusedError"]
)
def test_retained_config_rejection_requires_transport_evidence(reason: str) -> None:
    report: dict[str, object] = {
        "pause": {
            "requested_monotonic": 10.0,
            "streams": [{"reason": "eof", "received": 8192, "ended": 10.1}],
            "retained_configs": "rejected",
        },
        "rejected_probes": [
            {"port": 12345, "socks_ready": True, "reason": reason} for _ in range(3)
        ],
    }
    if reason == "IncompleteReadError":
        assert assert_target_rejected(report, 12345) == 10.0
    else:
        with pytest.raises(AssertionError, match="cannot prove"):
            assert_target_rejected(report, 12345)


@pytest.mark.parametrize(
    "outcome", ["passed", "failed", "cancelled", "cleanup_failed", "cancel_during_cleanup"]
)
def test_same_source_cleanup_and_recovery_manifest_without_external_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    events: list[str] = []
    panel = cast(PanelApiService, Mock(spec=PanelApiService))
    closed = AsyncMock()
    monkeypatch.setattr(panel, "close_session", closed)
    # Avoid constructing LiveNode: these offline checks must not contend for its live lock.
    fixture = object.__new__(SameSourceNode)
    fixture.panel = panel
    fixture.directory = tmp_path
    fixture.manifest = tmp_path / "manifest.json"
    fixture.state = {"schema": None}
    fixture.evidence = {}
    private_json(fixture.manifest, fixture.state)
    module = sys.modules[__name__]
    monkeypatch.setattr(module, "require_environment", lambda: "offline")
    monkeypatch.setattr(module, "_panel_service", lambda: panel)
    monkeypatch.setattr(module, "SameSourceNode", lambda _: fixture)
    monkeypatch.setattr(fixture, "setup", AsyncMock(return_value="offline-squad"))
    case = Mock(spec=LiveScenario)
    case.prepare = AsyncMock()
    monkeypatch.setattr(module, "LiveScenario", lambda *_: case)
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = "user_services_test_" + "a" * 32
    context = AsyncMock()
    context.__aenter__.return_value = session
    factory = cast(async_sessionmaker[AsyncSession], Mock(return_value=context))

    async def check(_case: LiveScenario, _fixture: SameSourceNode) -> None:
        events.append("check")
        if outcome == "failed":
            raise AssertionError("offline isolation failure")
        if outcome == "cancelled":
            raise asyncio.CancelledError
        fixture.evidence["verdict"] = "isolation_observed"

    async def capture() -> None:
        events.append("capture_failure")

    async def cleanup() -> None:
        events.append("cleanup")
        assert fixture.manifest.exists()
        if outcome == "cancel_during_cleanup":
            owner = next(task for task in asyncio.all_tasks() if task.get_name() == "scenario")
            owner.cancel()
            await asyncio.sleep(0)
        fixture.evidence["cleanup"] = "failed" if outcome == "cleanup_failed" else "passed"
        if outcome == "cleanup_failed":
            raise AssertionError("offline cleanup failure")

    def isolated_scenario(
        run: Callable[[async_sessionmaker[AsyncSession]], Awaitable[None]],
    ) -> None:
        async def execute() -> None:
            owner = asyncio.current_task()
            assert owner is not None
            owner.set_name("scenario")
            await run(factory)

        try:
            asyncio.run(execute())
        finally:
            events.append("schema_finally")

    monkeypatch.setattr(module, "check_isolation", check)
    monkeypatch.setattr(module, "scenario", isolated_scenario)
    monkeypatch.setattr(fixture, "capture_failure", capture)
    monkeypatch.setattr(fixture, "cleanup", cleanup)
    monkeypatch.setattr(fixture, "close_lock", lambda: events.append("unlock"))
    if outcome == "passed":
        run_same_source_regression()
    else:
        error = (
            asyncio.CancelledError
            if outcome in {"cancelled", "cancel_during_cleanup"}
            else AssertionError
        )
        with pytest.raises(error):
            run_same_source_regression()
    assert events == [
        "check",
        *(["capture_failure"] if outcome in {"failed", "cancelled"} else []),
        "cleanup",
        "unlock",
        "schema_finally",
    ]
    closed.assert_awaited_once()
    assert fixture.manifest.exists() is (outcome != "passed")
    report = object_dict(json.loads((tmp_path / "report.json").read_text()))
    assert report["state"] == ("passed" if outcome == "passed" else "failed")
    assert report["cleanup"] == ("failed" if outcome == "cleanup_failed" else "passed")
    if outcome != "passed":
        assert report["failure_type"] == (
            "CancelledError"
            if outcome in {"cancelled", "cancel_during_cleanup"}
            else "AssertionError"
        )
        assert "recover exact" in str(report["schema_cleanup"])
        manifest = object_dict(json.loads(fixture.manifest.read_text()))
        assert manifest["schema"] == "user_services_test_" + "a" * 32
    if os.name != "nt":
        assert (tmp_path / "report.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("fault", ["none", "netns", "pid", "oom", "restart", "stopped"])
def test_same_source_requires_shared_namespace_and_healthy_container_lifetimes(fault: str) -> None:
    processes = [{"pid": 1, "netns": "net:[123]"}, {"pid": 2, "netns": "net:[123]"}]
    containers: list[dict[str, object]] = [
        {
            "name": name,
            "id": name,
            "Running": True,
            "OOMKilled": False,
            "restart_count": 0,
            "StartedAt": "2026-10-24T00:00:00Z",
            "Pid": 123,
        }
        for name in ("origin", "node", "client-0")
    ]
    health: dict[str, object] = {
        "network": NETWORK,
        "source_ip": "172.18.0.2",
        "xray_processes": processes,
        "containers": containers,
    }
    if fault == "netns":
        processes[1]["netns"] = "net:[456]"
    elif fault == "pid":
        processes[1]["pid"] = 1
    elif fault == "oom":
        containers[1]["OOMKilled"] = True
    elif fault == "restart":
        containers[1]["restart_count"] = 1
    elif fault == "stopped":
        containers[0]["Running"] = False
    if fault == "none":
        assert_healthy(health)
    else:
        with pytest.raises(AssertionError):
            assert_healthy(health)


def test_second_identity_reuses_first_client_container_and_preserves_original_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = object.__new__(SameSourceNode)
    fixture.directory = tmp_path
    fixture.manifest = tmp_path / "manifest.json"
    fixture.prefix = "uc2-offline"
    fixture.ports = [12345]
    fixture.state = {"containers": [{"name": fixture.prefix + "-client-0"}]}
    first = "11111111-1111-4111-8111-111111111111"
    second = "22222222-2222-4222-8222-222222222222"
    config: dict[str, object] = {
        "inbounds": [{"port": 1080}],
        "outbounds": [{"settings": {"vnext": [{"users": [{"id": first}]}]}}],
    }
    private_json(tmp_path / "client-0.json", config)
    original = (tmp_path / "client-0.json").read_bytes()
    docker = AsyncMock(side_effect=["", "", "127.0.0.1:12346"])
    monkeypatch.setattr(fixture, "docker", docker)
    assert asyncio.run(fixture.client(second)) == 12346
    assert (tmp_path / "client-0.json").read_bytes() == original
    updated = object_dict(json.loads((tmp_path / "client-1.json").read_text()))
    object_rows(config["inbounds"])[0]["port"] = 1081
    settings = object_dict(object_rows(config["outbounds"])[0]["settings"])
    object_rows(object_rows(settings["vnext"])[0]["users"])[0]["id"] = second
    assert updated == config and fixture.ports == [12345, 12346]
    calls = [entry.args for entry in docker.await_args_list]
    assert calls == [
        ("cp", str(tmp_path / "client-1.json"), "uc2-offline-client-0:/tmp/client-1.json"),
        ("exec", "-d", "uc2-offline-client-0", "xray", "run", "-config", "/tmp/client-1.json"),
        ("port", "uc2-offline-client-0", "1081/tcp"),
    ]
    assert fixture.rows("containers") == [{"name": "uc2-offline-client-0"}]
    assert (
        fixture.state["client_1_sha256"]
        == hashlib.sha256((tmp_path / "client-1.json").read_bytes()).hexdigest()
    )
