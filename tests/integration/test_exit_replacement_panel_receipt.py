"""Opt-in local control-plane proof; no claim about stopped flows or dedicated egress."""

import asyncio
import hashlib
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from bot.services.service_exit_replacement_panel import dispatch_patch, prepare_patch
from tests.qa.test_remnawave_panel_contract import _panel_service
from tests.support.service_operations_live_node import (
    PROJECT_ENV,
    LiveNode,
    object_dict,
    require_environment,
)


@pytest.mark.skipif(
    os.environ.get("QA_SERVICE_OPERATIONS_LIVE_NODE") != "1",
    reason="Requires the exclusive opt-in local panel verification slot",
)
def test_local_panel_accepts_exact_replacement_patch_receipts() -> None:
    require_environment()

    async def run() -> None:
        panel = _panel_service()
        fixture = LiveNode(panel)
        print(f"Replacement receipt manifest: {fixture.manifest}", flush=True)
        try:
            await fixture.require_local_docker()
            baseline = await fixture.baseline()
            assert baseline["/nodes"] == [] and baseline["/hosts"] == []
            fixture.state["baseline"] = baseline
            fixture.state["env_sha256"] = hashlib.sha256(PROJECT_ENV.read_bytes()).hexdigest()
            identity = uuid4().hex
            fixture.remember_service(identity)
            description = "my_vps_obj:service:" + identity
            expires = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=123000)
            created = await panel.create_panel_user(
                username_on_panel="svc_" + identity,
                expire_at=expires,
                default_traffic_limit_bytes=8192,
                default_traffic_limit_strategy="NO_RESET",
                specific_squad_uuids=[],
                description=description,
                status="DISABLED",
            )
            assert created is not None and not created.get("error")
            remote = object_dict(created.get("response"))
            reference = remote.get("uuid")
            assert isinstance(reference, str) and reference
            fixture.evidence["scope"] = "Panel 3.4.5 receipts only; no Node or egress proof"
            receipts: list[dict[str, object]] = []
            for status in ("DISABLED", "ACTIVE", "DISABLED"):
                payload: dict[str, object] = {
                    "status": status,
                    "activeInternalSquads": [],
                    "externalSquadUuid": None,
                    "expireAt": expires.isoformat(timespec="milliseconds"),
                    "trafficLimitBytes": 4096,
                    "trafficLimitStrategy": "NO_RESET",
                }
                prepared = await prepare_patch(panel, reference, payload)
                receipt = await dispatch_patch(panel, prepared)
                assert receipt is not None, "A synchronous exact response was not accepted"
                observed = await panel.get_user_by_uuid(reference, use_cache=False)
                assert observed is not None and observed.get("description") == description
                assert observed.get("status") == status
                assert observed.get("trafficLimitBytes") == 4096
                assert observed.get("activeInternalSquads") == []
                receipts.append({"status": status, "receipt_sha256": receipt})
            fixture.evidence["receipts"] = receipts
            fixture.evidence["state"] = "passed"
        except BaseException as exc:
            fixture.evidence["state"] = "failed"
            fixture.evidence["failure_type"] = type(exc).__name__
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
        fixture.manifest.unlink()
        print(f"Replacement receipt report: {fixture.directory / 'report.json'}", flush=True)

    asyncio.run(run())
