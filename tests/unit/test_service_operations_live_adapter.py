"""Offline adapter checks: fake Docker only, no live lock, API or database."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock

import pytest

from tests.support import service_operations_live_adapter as adapter

if TYPE_CHECKING:
    from tests.support.service_operations_live_node import LiveNode


class FakeNode:
    def __init__(self, root: Path, image: str) -> None:
        self.directory = root / "run"
        self.directory.mkdir()
        self.manifest = self.directory / "manifest.json"
        self.prefix = "uc2-" + "a" * 12
        self.name = self.prefix + "-node"
        self.state: dict[str, object] = {
            "run_id": "a" * 32,
            "image": image,
            "containers": [{"name": self.name}],
        }
        self.evidence: dict[str, object] = {"node_image_id": "sha256:original"}
        self.info: dict[str, object] = {
            "Id": "container-id",
            "Name": "/" + self.name,
            "Image": "sha256:original",
            "State": {"Status": "created", "Running": False},
            "RestartCount": 0,
            "Config": {"Image": image, "Labels": {"my-vpn.uc2-run": "a" * 32}},
            "Mounts": [],
        }
        self.base: dict[str, object] = {
            "Id": "sha256:original",
            "Architecture": "arm64",
            "Os": "linux",
            "RepoDigests": ["remnawave/node@" + image.split("@", 1)[1]],
        }
        self.calls: list[tuple[str, ...]] = []
        self.files: dict[str, tuple[bytes, int]] = {}
        self.corrupt: str | None = None
        self.no_execute = False
        self.replaced = False
        self.inspections = 0
        self.save()

    def rows(self, name: str) -> list[dict[str, object]]:
        rows = self.state[name]
        assert isinstance(rows, list)
        return [adapter.object_dict(row) for row in rows]

    def save(self) -> None:
        self.manifest.write_text(json.dumps(self.state))

    async def require_local_docker(self) -> None:
        self.calls.append(("local-context-check",))

    async def docker(self, *args: str) -> str:
        self.calls.append(args)
        if args[0] == "create":
            return "created-by-fake"
        if args[:2] == ("image", "inspect"):
            return json.dumps([self.base])
        if args == ("inspect", self.name):
            self.inspections += 1
            return json.dumps(
                [
                    {
                        **self.info,
                        **({"Id": "replaced"} if self.replaced and self.inspections > 1 else {}),
                    }
                ]
            )
        assert args[0] == "cp", "No startup or other Docker operation is permitted"
        self.copy(args[1], args[2])
        return ""

    def copy(self, source_path: str, destination_path: str) -> None:
        prefix = self.name + ":"
        if source_path.startswith(prefix):
            target = source_path[len(prefix) :]
            data, mode = self.files[target]
            destination = Path(destination_path)
            destination.write_bytes(b"corrupted" if self.corrupt == target else data)
            destination.chmod(0o644 if self.no_execute else mode)
        else:
            assert destination_path.startswith(prefix)
            source = Path(source_path)
            self.files[destination_path[len(prefix) :]] = (
                source.read_bytes(),
                source.stat().st_mode & 0o777,
            )


@pytest.fixture
def prepared(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[FakeNode, Path]:
    manifest = adapter.object_dict(json.loads(adapter.MANIFEST.read_text()))
    directory = tmp_path / "artifacts"
    directory.mkdir()
    for name, entry in adapter.object_dict(manifest["artifacts"]).items():
        data = ("offline-r3-" + name).encode()
        (directory / name).write_bytes(data)
        adapter.object_dict(entry)["sha256"] = hashlib.sha256(data).hexdigest()
    local_manifest = tmp_path / "reviewed-manifest.json"
    local_manifest.write_text(json.dumps(manifest))
    monkeypatch.setattr(adapter, "MANIFEST", local_manifest)
    monkeypatch.setenv("QA_SERVICE_OPERATIONS_LIVE_NODE", "1")
    monkeypatch.setenv(adapter.ADAPTER_ENV, str(directory))
    return FakeNode(tmp_path, str(manifest["base_image"])), directory


def install(node: FakeNode) -> None:
    asyncio.run(
        adapter.install_adapter(cast("LiveNode", node), node.name, str(node.state["image"]))
    )


@pytest.mark.parametrize(("live", "configured"), [(False, False), (False, True), (True, False)])
def test_adapter_is_inert_without_both_explicit_opt_ins(
    monkeypatch: pytest.MonkeyPatch,
    live: bool,
    configured: bool,
) -> None:
    monkeypatch.setenv("QA_SERVICE_OPERATIONS_LIVE_NODE", "1" if live else "0")
    if configured:
        monkeypatch.setenv(adapter.ADAPTER_ENV, "/must-not-read")
    else:
        monkeypatch.delenv(adapter.ADAPTER_ENV, raising=False)
    original_get = adapter.os.environ.get

    def guarded_get(key: str, default: str | None = None) -> str | None:
        if key == adapter.ADAPTER_ENV and not live:
            pytest.fail("Optional adapter environment read before live opt-in")
        return original_get(key, default)

    def forbidden(*args: object, **kwargs: object) -> str:
        raise AssertionError("Disabled adapter must not read files")

    monkeypatch.setattr(adapter.os.environ, "get", guarded_get)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    asyncio.run(adapter.install_adapter(cast("LiveNode", object()), "unused", "unused"))


def test_installs_both_artifacts_only_after_validation_and_records_actual_container_hashes(
    prepared: tuple[FakeNode, Path],
) -> None:
    node, directory = prepared
    image = node.state["image"]
    install(node)
    report = adapter.object_dict(node.evidence["execution_adapter"])
    assert report["status"] == "installed" and report["revision"] == "isolated-poc-r3"
    assert report["base_image_is_patched"] is False and report["base_image"] == image
    assert report["container_hashes_verified_before_start"] is True
    assert report["clients"] == "original_pinned_image_unmodified"
    assert node.state["image"] == image
    expected = {"/opt/app/dist/main.js": "main.js", "/usr/local/bin/xray": "xray-linux-arm64"}
    observed = adapter.object_dict(report["container_artifact_sha256"])
    for target, filename in expected.items():
        data = (directory / filename).read_bytes()
        assert node.files[target][0] == data
        assert observed[target] == hashlib.sha256(data).hexdigest()
    assert node.files["/usr/local/bin/xray"][1] == 0o755
    assert len([call for call in node.calls if call[0] == "cp"]) == 4
    assert node.inspections == 2 and not list(node.directory.glob("adapter-*"))
    assert adapter.object_dict(json.loads(node.manifest.read_text()))["execution_adapter"] == report


def test_r2_manifest_is_rejected_without_touching_recovery_or_docker(
    prepared: tuple[FakeNode, Path],
) -> None:
    node, _ = prepared
    recovery = node.manifest.read_bytes()
    manifest = adapter.object_dict(json.loads(adapter.MANIFEST.read_text()))
    manifest["revision"] = "isolated-poc-r2"
    adapter.MANIFEST.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="revision"):
        install(node)
    assert node.calls == [] and node.files == {}
    assert node.manifest.read_bytes() == recovery


@pytest.mark.parametrize("filename", ["main.js", "xray-linux-arm64"])
@pytest.mark.parametrize("fault", ["missing", "stale", "symlink"])
def test_partial_r2_or_mixed_artifacts_fail_before_any_docker_access(
    prepared: tuple[FakeNode, Path],
    filename: str,
    fault: str,
) -> None:
    node, directory = prepared
    binary = directory / filename
    if fault == "missing":
        binary.unlink()
    elif fault == "stale":
        binary.write_bytes(b"offline-r2-main.js" if filename == "main.js" else b"unreviewed-xray")
    else:
        binary.unlink()
        try:
            binary.symlink_to(
                directory / ("xray-linux-arm64" if filename == "main.js" else "main.js")
            )
        except (NotImplementedError, OSError):
            pytest.skip("Symlinks unavailable on this host")
    with pytest.raises(ValueError):
        install(node)
    assert node.calls == [] and node.files == {}
    report = adapter.object_dict(node.state["execution_adapter"])
    assert report["status"] == "failed" and report["revision"] == "isolated-poc-r3"
    assert adapter.object_dict(json.loads(node.manifest.read_text()))["execution_adapter"] == report
    assert node.manifest.exists() and not list(node.directory.glob("adapter-*"))


@pytest.mark.parametrize(
    "destination",
    [
        "/",
        "/opt",
        "/opt/app/dist/main.js",
        "/usr/local",
        "/usr/local/bin/xray",
        "/usr/local/bin/rw-core",
    ],
)
def test_mounts_cannot_mask_either_execution_artifact_or_core_alias(
    prepared: tuple[FakeNode, Path],
    destination: str,
) -> None:
    node, _ = prepared
    node.info["Mounts"] = [{"Destination": destination}]
    with pytest.raises(ValueError, match="masks"):
        install(node)
    assert not node.files


@pytest.mark.parametrize(
    "fault",
    [
        "running",
        "stopped",
        "restarted",
        "ownership",
        "image",
        "unrecorded",
        "arch",
        "digest",
        "unknown_mounts",
    ],
)
def test_only_original_owned_never_started_arm64_node_is_eligible(
    prepared: tuple[FakeNode, Path],
    fault: str,
) -> None:
    node, _ = prepared
    if fault == "running":
        adapter.object_dict(node.info["State"])["Running"] = True
    elif fault == "stopped":
        adapter.object_dict(node.info["State"])["Status"] = "exited"
    elif fault == "restarted":
        node.info["RestartCount"] = 1
    elif fault == "ownership":
        adapter.object_dict(node.info["Config"])["Labels"] = {"my-vpn.uc2-run": "another-run"}
    elif fault == "image":
        node.info["Image"] = "sha256:other"
    elif fault == "unrecorded":
        node.state["containers"] = []
    elif fault == "arch":
        node.base["Architecture"] = "amd64"
    elif fault == "digest":
        node.base["RepoDigests"] = []
    else:
        node.info["Mounts"] = None
    with pytest.raises(ValueError):
        install(node)
    assert not node.files


@pytest.mark.parametrize("fault", ["bundle_corrupt", "core_corrupt", "mode", "replaced"])
def test_failed_or_partial_container_installation_keeps_failed_manifest_and_never_starts(
    prepared: tuple[FakeNode, Path],
    fault: str,
) -> None:
    node, _ = prepared
    if fault.endswith("corrupt"):
        node.corrupt = (
            "/opt/app/dist/main.js" if fault == "bundle_corrupt" else "/usr/local/bin/xray"
        )
    elif fault == "mode":
        node.no_execute = True
    else:
        node.replaced = True
    with pytest.raises(ValueError):
        install(node)
    report = adapter.object_dict(node.state["execution_adapter"])
    assert (
        report["status"] == "failed" and report["container_hashes_verified_before_start"] is False
    )
    assert report["failure_type"] == "ValueError"
    assert node.manifest.exists() and not list(node.directory.glob("adapter-*"))
    assert all(call[0] != "start" for call in node.calls)


@pytest.mark.parametrize(
    ("live", "suffix"), [(False, "node"), (True, "client-0"), (True, "origin"), (True, "node")]
)
def test_existing_container_hook_only_targets_live_node_and_propagates_failure(
    prepared: tuple[FakeNode, Path],
    monkeypatch: pytest.MonkeyPatch,
    live: bool,
    suffix: str,
) -> None:
    from tests.support.service_operations_live_node import LiveNode

    node, _ = prepared
    monkeypatch.setenv("QA_SERVICE_OPERATIONS_LIVE_NODE", "1" if live else "0")
    hook = AsyncMock(side_effect=ValueError("blocked-start"))
    monkeypatch.setattr(adapter, "install_adapter", hook)

    async def create() -> str:
        return await LiveNode.container(cast(LiveNode, node), suffix, str(node.state["image"]))

    if live and suffix == "node":
        with pytest.raises(ValueError, match="blocked-start"):
            asyncio.run(create())
        hook.assert_awaited_once()
    else:
        assert asyncio.run(create()) == node.prefix + "-" + suffix
        hook.assert_not_awaited()
    assert len(node.calls) == 1 and node.calls[0][0] == "create"


def reproduction_module() -> ModuleType:
    path = Path(__file__).parents[2] / "deploy/node-identity-cancel/reproduce.py"
    spec = importlib.util.spec_from_file_location("uc2_reproduce", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["check"],
        ["build", "--sources", "/unused"],
        ["check", "--sources", "/unused", "--work", "/unused"],
        ["build", "--sources", "/unused", "--work", "/unused", "--artifacts", "/unused"],
    ],
)
def test_reproduction_rejects_ambiguous_arguments_without_any_work(
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
) -> None:
    module = reproduction_module()

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Bad arguments must not run input checks or commands")

    monkeypatch.setattr(module, "check_inputs", forbidden)
    monkeypatch.setattr(module, "command", forbidden)
    monkeypatch.setattr(sys, "argv", ["reproduce.py", *args])
    with pytest.raises(SystemExit) as result:
        module.main()
    assert result.value.code == 2


def test_r3_repository_manifest_preserves_frozen_artifact_patch_and_license_hashes() -> None:
    root = Path(__file__).parents[2] / "deploy/node-identity-cancel"
    manifest = adapter.object_dict(json.loads((root / "manifest.json").read_text()))
    assert manifest["revision"] == "isolated-poc-r3"
    assert manifest["handoff_manifest_sha256"] == (
        "b5a495e8c4688598e9008599fd012c6a68e3fe93ba7a86986bbbab9a4e88b22d"
    )
    assert manifest["independent_build_evidence_sha256"] == (
        "2e61f693065a39a2a1502adb158bebbdd337fdaa246ab825d1788609a23d0a4f"
    )
    artifacts = adapter.object_dict(manifest["artifacts"])
    assert adapter.object_dict(artifacts["main.js"])["sha256"] == (
        "4896c9fa350cf50fe27dda4fcf4cde883a642ef1712bcab7b48b58ea56e61f0d"
    )
    assert adapter.object_dict(artifacts["xray-linux-arm64"])["sha256"] == (
        "25074e2dfad139dfab8d6f4abc89fc16c8c4b2240d78d5a117075076bc897c31"
    )
    sources = adapter.object_dict(manifest["sources"])
    node = adapter.object_dict(sources["node"])
    xray = adapter.object_dict(sources["xray"])
    assert node["version"] == "3.4.2"
    assert node["commit"] == "ea7a835485af81ec464ebbf7acaaa7d6dd486a05"
    assert node["sha256"] == "c8008efb55cc3c569ab9398302649e812711c75d3e4db73a7ad4e03203b25616"
    assert node["patch_sha256"] == (
        "bf1af2716ef8d800385af780d11c016245ddb670659fe5901077d9416a1548b7"
    )
    assert node["locks"] == {
        "package-lock.json": "ee3ef36a0e6c61f3f352753e839e934ed0fdbd2983bcf7567c822640444514ad"
    }
    assert xray["version"] == "v26.7.28"
    assert xray["commit"] == "5ca6f4b7d4dc20a881d4330e498892697627ec0c"
    assert xray["sha256"] == "45de3ead5186fea442b04c662c554a1ffd1d7bd9093a83410f2edabe74fb766e"
    assert xray["patch_sha256"] == (
        "90076c5b3e6d6609b1ef1742e62e57ac4e63ff4e7fceee5c287b9226fb998abf"
    )
    assert xray["locks"] == {
        "go.mod": "3563a7831c81e160549561f54d1fa81aad20b915ebf39bf2164cd93866c21695",
        "go.sum": "33d275a3eae8ea3af29807f45836c1781bceae8bc7c7a88816fcb34b54995351",
    }
    for entry in sources.values():
        source = adapter.object_dict(entry)
        for field in ("patch", "license"):
            assert (
                hashlib.sha256((root / str(source[field])).read_bytes()).hexdigest()
                == (source[field + "_sha256"])
            )
    assert not list(root.rglob("*.tar.gz")) and not list(root.rglob("node_modules"))


@pytest.mark.parametrize("corrupt", [None, "main.js", "xray-linux-arm64"])
def test_build_with_fake_tools_requires_build_dependencies_and_both_output_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    corrupt: str | None,
) -> None:
    module = reproduction_module()
    manifest = adapter.object_dict(json.loads(adapter.MANIFEST.read_text()))
    generated = adapter.object_dict(manifest["generated"])
    generated["sha256"] = hashlib.sha256(b"generated").hexdigest()
    for entry in adapter.object_dict(manifest["artifacts"]).values():
        adapter.object_dict(entry)["sha256"] = hashlib.sha256(b"artifact").hexdigest()
    for entry in adapter.object_dict(manifest["sources"]).values():
        adapter.object_dict(entry)["locks"] = {}
    versions = adapter.object_dict(manifest["toolchain"])
    with zipfile.ZipFile(tmp_path / str(versions["protoc_archive"]), "w") as archive:
        archive.writestr("bin/protoc", b"fake compiler, never executed")
    work = tmp_path / "new-build"
    calls: list[list[str]] = []

    def prepare(manifest: object, sources: Path, destination: Path) -> None:
        (destination / "node/dist").mkdir(parents=True)
        protobuf = destination / "xray" / str(generated["path"])
        protobuf.parent.mkdir(parents=True)
        protobuf.write_bytes(b"generated")

    def command(args: list[str], cwd: Path) -> str:
        assert args[1:] == ["--version"]
        name = "protoc" if Path(args[0]).name == "protoc" else "protoc_gen_go"
        return str(versions[name])

    def fake_run(
        args: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        stdout: object,
        stderr: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        assert env["NODE_ENV"] == "production" and check
        if args[:2] == ["npm", "ci"]:
            assert "--include=dev" in args and "--ignore-scripts" in args
        elif Path(args[0]).name == "protoc":
            output = work / "regenerated" / str(generated["path"])
            output.parent.mkdir(parents=True)
            output.write_bytes(b"generated")
        elif args[:2] == ["go", "build"]:
            Path(args[args.index("-o") + 1]).write_bytes(
                b"partial" if corrupt == "xray-linux-arm64" else b"artifact"
            )
        elif args == ["npm", "run", "build"]:
            (cwd / "dist/main.js").write_bytes(b"partial" if corrupt == "main.js" else b"artifact")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(module, "check_tools", lambda manifest: None)
    monkeypatch.setattr(module, "prepare", prepare)
    monkeypatch.setattr(module, "command", command)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    marker = work / "artifacts/verified-build.json"
    if corrupt is not None:
        with pytest.raises(ValueError, match="mismatched file:") as result:
            module.build(manifest, tmp_path, work)
        assert str(result.value).endswith(corrupt)
        assert not marker.exists()
    else:
        module.build(manifest, tmp_path, work)
        verified = adapter.object_dict(json.loads(marker.read_text()))
        assert verified["protobuf_regenerated"] is True
        assert verified["revision"] == "isolated-poc-r3"
    assert any(args[:2] == ["npm", "ci"] for args in calls)
    changed = [
        "src/common/utils/identity-scope.ts",
        "src/modules/handler/handler.service.ts",
        "src/modules/handler/identity-cancel.ts",
        "src/modules/internal/internal.service.ts",
        "src/modules/xray-core/xray.service.ts",
        "test/identity-fixture.cjs",
        "test/identity-cancel.test.cjs",
        "test/identity-scope.test.cjs",
    ]
    expected_checks = [
        [
            "node",
            "--test",
            "--test-reporter=tap",
            "test/identity-cancel.test.cjs",
            "test/identity-scope.test.cjs",
        ],
        ["npm", "run", "typecheck", "--", "--incremental", "false"],
        ["node_modules/.bin/oxfmt", "--check", *changed],
        ["node_modules/.bin/oxlint", *changed],
        ["npm", "run", "build"],
    ]
    assert calls[-len(expected_checks) :] == expected_checks
