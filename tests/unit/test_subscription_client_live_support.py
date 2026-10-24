"""Offline ownership checks; keep a distinct module name from live acceptance."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from tests.support import subscription_client_live as live
from tests.support import subscription_client_runtime as runtime
from tests.support.node_onboarding_live_node import SubscriptionTLS
from tests.unit.test_node_onboarding_live_support import OfflineNode
from tests.unit.test_node_onboarding_live_support import fixture_node as fixture_node
from tests.unit.test_node_onboarding_live_support import no_environment as no_environment


def test_opt_out_precedes_environment_artifacts_and_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.integration import test_subscription_client_live as acceptance

    monkeypatch.delenv("QA_NATIVE_SUBSCRIPTION_CLIENT", raising=False)
    forbidden = Mock(side_effect=AssertionError("Opt-out touched environment"))
    for name in ("require_onboarding_environment", "pinned_binary", "run_onboarding"):
        monkeypatch.setattr(acceptance, name, forbidden)
    with pytest.raises(pytest.skip.Exception):
        acceptance.run_local_native_subscription()
    forbidden.assert_not_called()


def test_runner_default_preserves_original_f06_scenario() -> None:
    from tests.integration.test_node_onboarding_live_node import OnboardingScenario, run_onboarding
    from tests.support.exit_replacement_live_node import SCOPE

    signature = inspect.signature(run_onboarding)
    assert signature.parameters["scenario_type"].default is OnboardingScenario
    assert signature.parameters["scope"].default == SCOPE


def test_pinned_artifact_requires_two_opt_ins_before_file_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QA_NATIVE_SUBSCRIPTION_CLIENT", raising=False)
    forbidden = Mock(side_effect=AssertionError("Must not inspect artifacts"))
    monkeypatch.setattr(runtime, "digest", forbidden)
    with pytest.raises(ValueError, match="native_explicit_opt_in_required"):
        live.pinned_binary()
    forbidden.assert_not_called()


@pytest.mark.parametrize("corrupt", [None, "binary", "archive", "symlink"])
def test_artifact_digest_checks_both_binary_and_release_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    corrupt: str | None,
) -> None:
    binary = tmp_path / "mihomo"
    binary.write_bytes(b"pinned binary")
    archive = tmp_path / "mihomo.gz"
    archive.write_bytes(b"pinned archive")
    monkeypatch.setenv("QA_NATIVE_SUBSCRIPTION_CLIENT", "1")
    monkeypatch.setenv("QA_SERVICE_OPERATIONS_LIVE_NODE", "1")
    monkeypatch.setenv(runtime.BINARY_ENV, str(binary))
    monkeypatch.setattr(runtime, "BINARY_SHA256", hashlib.sha256(binary.read_bytes()).hexdigest())
    monkeypatch.setattr(runtime, "ARCHIVE_SHA256", hashlib.sha256(archive.read_bytes()).hexdigest())
    if corrupt == "binary":
        binary.write_bytes(b"changed")
    elif corrupt == "archive":
        archive.write_bytes(b"changed")
    elif corrupt == "symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(binary)
        monkeypatch.setenv(runtime.BINARY_ENV, str(alias))
    if corrupt is None:
        assert live.pinned_binary() == binary
    else:
        with pytest.raises(ValueError):
            live.pinned_binary()


@pytest.mark.parametrize("fail", [False, True])
def test_runtime_secrets_use_stdin_not_argv_or_host_files(
    fixture_node: OfflineNode,
    monkeypatch: pytest.MonkeyPatch,
    fail: bool,
) -> None:
    monkeypatch.setattr(live, "require_onboarding_environment", lambda: "unused")
    tls = SubscriptionTLS(fixture_node)
    inspected = AsyncMock(return_value={})
    monkeypatch.setattr(tls, "inspect_owned", inspected)
    process = Mock(returncode=1 if fail else 0)
    response = (
        {"ok": False, "failure_type": "ValueError"}
        if fail
        else {"ok": True, "evidence": {"safe": True}}
    )
    process.communicate = AsyncMock(return_value=(json.dumps(response).encode(), b"secret stderr"))
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    native = live.NativeClient(tls)
    if fail:
        with pytest.raises(ValueError, match="native_runtime_failed"):
            asyncio.run(native.call("prepare", services=[{"secret": "private-url"}]))
    else:
        assert asyncio.run(native.call("prepare", services=[{"secret": "private-url"}])) == {
            "safe": True
        }
    args = spawn.call_args.args
    assert "private-url" not in repr(args) and "private-url" not in repr(spawn.call_args.kwargs)
    assert args[:6] == ("docker", "--context", live.CONTEXT, "exec", "-i", tls.name)
    assert json.loads(process.communicate.call_args.args[0])["services"] == [
        {"secret": "private-url"}
    ]
    inspected.assert_awaited_once_with(running=True)
    assert not tls.directory.exists()


def test_transport_cancellation_reaps_docker_exec(
    fixture_node: OfflineNode,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live, "require_onboarding_environment", lambda: "unused")
    tls = SubscriptionTLS(fixture_node)
    monkeypatch.setattr(tls, "inspect_owned", AsyncMock())
    process = Mock(returncode=None)
    process.communicate = AsyncMock(side_effect=asyncio.CancelledError())
    process.wait = AsyncMock()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(live.NativeClient(tls).call("register", index=0))
    process.kill.assert_called_once()
    process.wait.assert_awaited_once()


def test_native_install_and_recovery_keep_existing_tls_cleanup_guards(
    fixture_node: OfflineNode,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(live, "require_onboarding_environment", lambda: "unused")
    monkeypatch.setattr(live, "pinned_binary", lambda: tmp_path / "mihomo")
    tls = SubscriptionTLS(fixture_node)
    asyncio.run(tls.start())
    before = set(tls.directory.iterdir())
    original_docker = fixture_node.docker
    copied = AsyncMock(return_value="")
    monkeypatch.setattr(fixture_node, "docker", copied)
    inspected = AsyncMock(return_value={})
    monkeypatch.setattr(tls, "inspect_owned", inspected)
    asyncio.run(live.NativeClient(tls).install())
    assert set(tls.directory.iterdir()) == before
    assert tls.scope()["native_client"] == {
        "scope": live.SCOPE,
        "binary_sha256": runtime.BINARY_SHA256,
    }
    assert len(copied.await_args_list) == 4
    assert all(
        "--mount" not in call.args and "-p" not in call.args for call in copied.await_args_list
    )
    destinations = [call.args[-1] for call in copied.await_args_list if call.args[0] == "cp"]
    assert destinations == [
        tls.name + ":/tmp/subscription-client/mihomo",
        tls.name + ":/tmp/subscription-client/runtime.py",
        tls.name + ":/tmp/onboarding-tls/subscription_client_observation.py",
    ]
    monkeypatch.setattr(fixture_node, "docker", original_docker)
    asyncio.run(SubscriptionTLS(fixture_node).cleanup())
    assert not tls.directory.exists() and tls.scope()["status"] == "cleaned"
