"""Bounded native client transport borrowing F06 ownership, TLS and cleanup."""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

from tests.support import subscription_client_observation as observation
from tests.support import subscription_client_runtime as runtime
from tests.support.node_onboarding_live_node import (
    SubscriptionTLS,
    checked,
    json_object,
    require_onboarding_environment,
)
from tests.support.service_operations_live_node import CONTEXT

SCOPE = (
    "native_mihomo_http_provider_local_only; "
    "gui_platform_compatibility_and_public_dedicated_egress_not_verified"
)


def pinned_binary() -> Path:
    checked(
        os.environ.get("QA_NATIVE_SUBSCRIPTION_CLIENT") == "1"
        and os.environ.get("QA_SERVICE_OPERATIONS_LIVE_NODE") == "1",
        "native_explicit_opt_in_required",
    )
    value = os.environ.get(runtime.BINARY_ENV, "")
    path = Path(value)
    checked(bool(value) and path.is_absolute(), "native_explicit_artifact_required")
    checked(runtime.digest(path) == runtime.BINARY_SHA256, "native_binary_digest_mismatch")
    checked(
        runtime.digest(path.with_name(path.name + ".gz")) == runtime.ARCHIVE_SHA256,
        "native_archive_digest_mismatch",
    )
    return path


class NativeClient:
    def __init__(self, tls: SubscriptionTLS) -> None:
        self.tls = tls

    async def install(self) -> None:
        require_onboarding_environment()
        binary = await asyncio.to_thread(pinned_binary)
        await self.tls.inspect_owned(running=True)
        self.tls.save(native_client={"scope": SCOPE, "binary_sha256": runtime.BINARY_SHA256})
        await self.tls.node.docker(
            "exec",
            self.tls.name,
            "python",
            "-c",
            "from pathlib import Path; Path('/tmp/subscription-client').mkdir(mode=0o700)",
        )
        for source, name in ((binary, "mihomo"), (Path(runtime.__file__), "runtime.py")):
            await self.tls.node.docker(
                "cp", str(source), self.tls.name + ":" + str(runtime.BASE / name)
            )
        await self.tls.node.docker(
            "cp",
            observation.__file__,
            self.tls.name + ":" + str(runtime.TLS / "subscription_client_observation.py"),
        )

    async def call(self, action: str, **values: object) -> dict[str, object]:
        require_onboarding_environment()
        await self.tls.inspect_owned(running=True)
        payload = json.dumps({"action": action, **values}).encode()
        checked(len(payload) <= runtime.LIMIT, "native_request_too_large")
        # stdin avoids placing subscription credentials in Docker arguments or host files.
        process = await asyncio.create_subprocess_exec(
            "docker",
            "--context",
            CONTEXT,
            "exec",
            "-i",
            self.tls.name,
            "python",
            str(runtime.BASE / "runtime.py"),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(payload), timeout=45)
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise
        checked(len(stdout) <= runtime.LIMIT, "native_response_too_large")
        try:
            response = json_object(json.loads(stdout))
        except (ValueError, TypeError):
            raise runtime.NativeEvidenceError("native_runtime_response_invalid") from None
        if process.returncode != 0 or response.get("ok") is not True:
            code = response.get("failure_code")
            if not isinstance(code, str) or not re.fullmatch(r"native_[a-z_]{1,80}", code):
                code = "native_runtime_failed"
            raise runtime.NativeEvidenceError(code)
        return json_object(response.get("evidence"))

    async def start(self, index: int) -> dict[str, object]:
        checked(type(index) is int and index in (0, 1), "native_invalid_index")
        await self.call("register", index=index)
        await self.tls.node.docker(
            "exec",
            "-d",
            self.tls.name,
            "python",
            str(runtime.BASE / "runtime.py"),
            "serve",
            str(index),
        )
        return await self.call("refresh", index=index)
