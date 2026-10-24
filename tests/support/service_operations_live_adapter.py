"""Explicit opt-in r3 overrides for a newly created disposable Node only."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from tests.support.service_operations_live_node import LiveNode

MANIFEST = Path(__file__).parents[2] / "deploy/node-identity-cancel/manifest.json"
ADAPTER_ENV = "QA_SERVICE_OPERATIONS_ADAPTER_DIR"


def object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("Expected adapter object (response redacted)")
    return cast(dict[str, object], value)


def first_object(raw: str) -> dict[str, object]:
    values: object = json.loads(raw)
    if not isinstance(values, list) or len(values) != 1:
        raise ValueError("Expected exactly one adapter inspection result")
    return object_dict(values[0])


def verify_container(
    info: dict[str, object],
    fixture: LiveNode,
    name: str,
    image: str,
    destinations: list[str],
) -> None:
    if name != fixture.prefix + "-node" or info["Name"] != "/" + name:
        raise ValueError("Only the exact disposable Node can receive the adapter")
    if {"name": name} not in fixture.rows("containers"):
        raise ValueError("Disposable Node is absent from the recovery manifest")
    state = object_dict(info["State"])
    config = object_dict(info["Config"])
    labels = object_dict(config["Labels"])
    if state["Status"] != "created" or state["Running"] is not False or info["RestartCount"] != 0:
        raise ValueError("Adapter installation requires a never-started Node")
    if (
        config["Image"] != image
        or info["Image"] != fixture.evidence["node_image_id"]
        or labels.get("my-vpn.uc2-run") != fixture.state["run_id"]
    ):
        raise ValueError("Disposable Node image or ownership mismatch")
    mounts = info["Mounts"]
    if not isinstance(mounts, list):
        raise ValueError("Cannot establish container mount inventory")
    for item in mounts:
        mount = PurePosixPath(str(object_dict(item)["Destination"]))
        if not mount.is_absolute() or ".." in mount.parts:
            raise ValueError("Ambiguous container mount")
        if any(PurePosixPath(path).is_relative_to(mount) for path in destinations):
            raise ValueError("A mount masks an adapter execution path")


async def install_adapter(fixture: LiveNode, name: str, image: str) -> None:
    # Neither optional environment lookup nor file/Docker access precedes explicit live opt-in.
    if os.environ.get("QA_SERVICE_OPERATIONS_LIVE_NODE") != "1":
        return
    directory = os.environ.get(ADAPTER_ENV)
    if directory is None:
        return
    source = Path(directory)
    if not directory or not source.is_absolute():
        raise ValueError("Adapter directory must be an explicit absolute local path")
    manifest = object_dict(json.loads(MANIFEST.read_text()))
    if (
        manifest["schema"] != 1
        or manifest["revision"] != "isolated-poc-r3"
        or image != manifest["base_image"]
        or image != fixture.state["image"]
    ):
        raise ValueError("Adapter revision or original pinned base image mismatch")
    artifacts = object_dict(manifest["artifacts"])
    if set(artifacts) != {"main.js", "xray-linux-arm64"}:
        raise ValueError("The reviewed r3 Node / unchanged Xray pair is mandatory")
    destinations = ["/opt/app/dist/main.js", "/usr/local/bin/xray", "/usr/local/bin/rw-core"]
    report: dict[str, object] = {
        "kind": "prestart_disposable_node_override",
        "revision": manifest["revision"],
        "base_image": image,
        "base_image_is_patched": False,
        "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        "sources": manifest["sources"],
        "toolchain": manifest["toolchain"],
        "target": manifest["target"],
        "clients": "original_pinned_image_unmodified",
        "scope": manifest["scope"],
        "status": "installing",
        "container_hashes_verified_before_start": False,
    }
    fixture.state["execution_adapter"] = report
    fixture.evidence["execution_adapter"] = report
    fixture.save()
    try:
        with tempfile.TemporaryDirectory(prefix="adapter-", dir=fixture.directory) as temporary:
            staged = Path(temporary)
            expected: dict[str, str] = {}
            for filename, entry in artifacts.items():
                artifact = object_dict(entry)
                local = source / filename
                if local.is_symlink() or not local.is_file():
                    raise ValueError("Missing or non-regular adapter artifact: " + filename)
                data = local.read_bytes()
                sha256 = hashlib.sha256(data).hexdigest()
                if sha256 != artifact["sha256"]:
                    raise ValueError("Unreviewed or stale adapter artifact: " + filename)
                destination = artifact["destination"]
                if destination != destinations[0 if filename == "main.js" else 1]:
                    raise ValueError("Unexpected adapter destination")
                (staged / filename).write_bytes(data)
                (staged / filename).chmod(0o644 if filename == "main.js" else 0o755)
                expected[filename] = sha256
            report["artifact_sha256"] = expected
            await fixture.require_local_docker()
            base = first_object(await fixture.docker("image", "inspect", image))
            if (
                base["Architecture"] != "arm64"
                or base["Os"] != "linux"
                or base["Id"] != fixture.evidence["node_image_id"]
            ):
                raise ValueError("Reviewed adapter requires the pinned Linux ARM64 base image")
            repo_digests = base["RepoDigests"]
            if not isinstance(repo_digests, list) or not any(
                isinstance(value, str) and value.endswith("@" + image.split("@", 1)[1])
                for value in repo_digests
            ):
                raise ValueError("Pinned base image digest is absent")
            before = first_object(await fixture.docker("inspect", name))
            verify_container(before, fixture, name, image, destinations)
            observed: dict[str, str] = {}
            for filename, entry in artifacts.items():
                artifact = object_dict(entry)
                target = name + ":" + str(artifact["destination"])
                await fixture.docker("cp", str(staged / filename), target)
                returned = staged / ("verified-" + filename)
                await fixture.docker("cp", target, str(returned))
                if returned.is_symlink() or not returned.is_file():
                    raise ValueError("Container adapter artifact is not a regular file")
                sha256 = hashlib.sha256(returned.read_bytes()).hexdigest()
                if sha256 != expected[filename]:
                    raise ValueError("Actual container adapter checksum mismatch: " + filename)
                if filename == "xray-linux-arm64" and returned.stat().st_mode & 0o111 != 0o111:
                    raise ValueError("Container Xray artifact is not executable")
                observed[str(artifact["destination"])] = sha256
            after = first_object(await fixture.docker("inspect", name))
            verify_container(after, fixture, name, image, destinations)
            if before["Id"] != after["Id"]:
                raise ValueError("Disposable Node was replaced during adapter installation")
            report.update(
                {
                    "status": "installed",
                    "container_artifact_sha256": observed,
                    "container_hashes_verified_before_start": True,
                }
            )
    except BaseException as exc:
        report.update({"status": "failed", "failure_type": type(exc).__name__})
        raise
    finally:
        fixture.save()
