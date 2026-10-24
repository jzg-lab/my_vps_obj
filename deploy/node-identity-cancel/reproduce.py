"""Offline checks by default; explicit build uses a fresh directory outside the repo."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parent


def object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("Expected a manifest object")
    return cast(dict[str, object], value)


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def verify(path: Path, expected: object) -> None:
    if path.is_symlink() or not path.is_file() or digest(path) != expected:
        raise ValueError(f"Missing, non-regular or mismatched file: {path.name}")


def command(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def check_inputs(manifest: dict[str, object], sources: Path) -> None:
    for entry in object_dict(manifest["sources"]).values():
        source = object_dict(entry)
        verify(sources / str(source["archive"]), source["sha256"])
        verify(ROOT / str(source["patch"]), source["patch_sha256"])
        verify(ROOT / str(source["license"]), source["license_sha256"])
    tools = object_dict(manifest["toolchain"])
    verify(sources / str(tools["protoc_archive"]), tools["protoc_sha256"])


def prepare(manifest: dict[str, object], sources: Path, work: Path) -> None:
    for name, entry in object_dict(manifest["sources"]).items():
        source = object_dict(entry)
        root = str(source["root"])
        with tarfile.open(sources / str(source["archive"]), "r:gz") as archive:
            if any(Path(item.name).parts[0] != root for item in archive.getmembers()):
                raise ValueError("Archive does not have the pinned source root")
            archive.extractall(work, filter="data")
        tree = work / name
        (work / root).rename(tree)
        verify(tree / str(source["upstream_license"]), source["license_sha256"])
        for file, sha256 in object_dict(source["locks"]).items():
            verify(tree / file, sha256)
        patch = str(ROOT / str(source["patch"]))
        command(["git", "apply", "--check", patch], tree)
        command(["git", "apply", patch], tree)
    generated = object_dict(manifest["generated"])
    verify(work / "xray" / str(generated["path"]), generated["sha256"])


def check_artifacts(manifest: dict[str, object], directory: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name, entry in object_dict(manifest["artifacts"]).items():
        artifact = object_dict(entry)
        verify(directory / name, artifact["sha256"])
        hashes[name] = digest(directory / name)
    return hashes


def check_tools(manifest: dict[str, object]) -> None:
    versions = object_dict(manifest["toolchain"])
    for name, args in (
        ("go", ["go", "version"]),
        ("node", ["node", "--version"]),
        ("npm", ["npm", "--version"]),
    ):
        if command(args, ROOT, {**os.environ, "GOTOOLCHAIN": "local"}) != versions[name]:
            raise ValueError(f"Pinned {name} version/host required; no automatic upgrade")


def build(manifest: dict[str, object], sources: Path, work: Path) -> None:
    check_tools(manifest)
    work.mkdir()  # An existing/partial workspace must never become a fresh successful build.
    prepare(manifest, sources, work)
    tools = object_dict(manifest["toolchain"])
    protoc = work / "protoc"
    with zipfile.ZipFile(sources / str(tools["protoc_archive"])) as archive:
        archive.extractall(protoc)
    compiler = protoc / "bin/protoc"
    compiler.chmod(0o755)
    if command([str(compiler), "--version"], work) != tools["protoc"]:
        raise ValueError("Unexpected protoc version")
    env = {
        **os.environ,
        "GOTOOLCHAIN": "local",
        "GOPATH": str(work / "go"),
        "GOCACHE": str(work / "go-cache"),
        "GOBIN": str(work / "bin"),
        "GOFLAGS": "",
        "NODE_ENV": "production",
    }
    logs = work / "logs"
    logs.mkdir()

    def run(label: str, args: list[str], cwd: Path, extra: dict[str, str] | None = None) -> None:
        with (logs / (label + ".log")).open("w") as output:
            subprocess.run(
                args,
                cwd=cwd,
                env={**env, **(extra or {})},
                stdout=output,
                stderr=subprocess.STDOUT,
                check=True,
            )

    run("generator-install", ["go", "install", str(tools["protoc_gen_go_module"])], work)
    plugin = work / "bin/protoc-gen-go"
    if command([str(plugin), "--version"], work) != tools["protoc_gen_go"]:
        raise ValueError("Unexpected protoc-gen-go version")
    generated = object_dict(manifest["generated"])
    regenerated = work / "regenerated"
    regenerated.mkdir()
    run(
        "protobuf-regenerate",
        [
            str(compiler),
            "--plugin=protoc-gen-go=" + str(plugin),
            "--go_out=" + str(regenerated),
            "--go_opt=paths=source_relative",
            str(generated["proto"]),
        ],
        work / "xray",
    )
    verify(regenerated / str(generated["path"]), generated["sha256"])
    if (regenerated / str(generated["path"])).read_bytes() != (
        work / "xray" / str(generated["path"])
    ).read_bytes():
        raise ValueError("Generated protobuf differs from the frozen patch")
    run(
        "go-tests",
        [
            "go",
            "test",
            "-race",
            "-count=1",
            "-timeout=90s",
            "-json",
            "./proxy/vless/inbound",
            "./proxy/vless/encoding",
            "./common/mux",
            "./app/proxyman/command",
        ],
        work / "xray",
    )
    run(
        "go-repeat",
        [
            "go",
            "test",
            "-race",
            "-count=20",
            "-timeout=90s",
            "-json",
            "-run",
            "^TestIdentityCancel",
            "./proxy/vless/inbound",
            "./common/mux",
            "./app/proxyman/command",
        ],
        work / "xray",
    )
    artifacts = work / "artifacts"
    artifacts.mkdir()
    run(
        "xray-build",
        [
            "go",
            "build",
            "-trimpath",
            "-buildvcs=false",
            "-ldflags",
            "-s -w -buildid= -X github.com/xtls/xray-core/core.build=uc2-identity-cancel",
            "-o",
            str(artifacts / "xray-linux-arm64"),
            "./main",
        ],
        work / "xray",
        {"CGO_ENABLED": "0", "GOOS": "linux", "GOARCH": "arm64"},
    )
    node = work / "node"
    run(
        "npm-ci",
        [
            "npm",
            "ci",
            "--include=dev",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
            "--cache",
            str(work / "npm-cache"),
        ],
        node,
    )
    run(
        "node-tests",
        [
            "node",
            "--test",
            "--test-reporter=tap",
            "test/identity-cancel.test.cjs",
            "test/identity-scope.test.cjs",
        ],
        node,
    )
    run("node-types", ["npm", "run", "typecheck", "--", "--incremental", "false"], node)
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
    run("node-format", ["node_modules/.bin/oxfmt", "--check", *changed], node)
    run("node-lint", ["node_modules/.bin/oxlint", *changed], node)
    run("node-build", ["npm", "run", "build"], node)
    shutil.copyfile(node / "dist/main.js", artifacts / "main.js")
    hashes = check_artifacts(manifest, artifacts)
    for name, entry in object_dict(manifest["sources"]).items():
        for file, sha256 in object_dict(object_dict(entry)["locks"]).items():
            verify(work / name / file, sha256)
    (artifacts / "verified-build.json").write_text(
        json.dumps(
            {
                "revision": manifest["revision"],
                "manifest_sha256": digest(ROOT / "manifest.json"),
                "toolchain": tools,
                "artifact_sha256": hashes,
                "protobuf_regenerated": True,
            },
            indent=2,
        )
        + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("check", "build"))
    parser.add_argument(
        "--sources",
        type=Path,
        required=True,
        help="Local directory with the three pinned archives; no archive downloads",
    )
    parser.add_argument(
        "--artifacts", type=Path, help="Also check the pinned r3 Node / unchanged Xray pair"
    )
    parser.add_argument(
        "--work", type=Path, help="New, nonexistent build directory outside the repo"
    )
    args = parser.parse_args()
    if args.mode == "build" and (args.work is None or args.artifacts is not None):
        parser.error("build requires --work and does not accept --artifacts")
    if args.mode == "check" and args.work is not None:
        parser.error("check does not accept --work")
    manifest = object_dict(json.loads((ROOT / "manifest.json").read_text()))
    sources = Path(args.sources).resolve()
    work = Path(args.work).resolve() if args.work is not None else None
    if work is not None and (work.exists() or work.is_relative_to(ROOT.parents[1])):
        parser.error("--work must be nonexistent and outside the repository")
    check_inputs(manifest, sources)
    if args.mode == "check":
        with tempfile.TemporaryDirectory(prefix="uc2-adapter-check-") as directory:
            prepare(manifest, sources, Path(directory))
        if args.artifacts is not None:
            check_artifacts(manifest, Path(args.artifacts))
        print(
            "PASS: archives, locks, exact patches, licenses and frozen protobuf hash checked; "
            "no build"
        )
    else:
        assert work is not None
        build(manifest, sources, work)
        print("PASS: r3 Node / unchanged Xray pair reproduced; protobuf regenerated; tests passed")


if __name__ == "__main__":
    main()
