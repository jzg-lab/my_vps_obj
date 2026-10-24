"""R08/A09, F06/UC09: native provider import/update, not GUI certification.

Only the main acceptance window runs this explicit opt-in against the local stand.
This scenario reuses the F06 lock, database migrations and exact recovery cleanup.
"""

from __future__ import annotations

import asyncio
import logging
import os
from uuid import uuid4

import pytest

from tests.integration.test_node_onboarding_live_node import (
    PREVIEW,
    OnboardingScenario,
    run_onboarding,
    string,
)
from tests.support.exit_replacement_live_node import ExitNode, ledger_totals
from tests.support.node_onboarding_live_node import (
    checked,
    json_object,
    require_onboarding_environment,
)
from tests.support.node_onboarding_resource_changes import group_preview_evidence
from tests.support.subscription_client_live import SCOPE, NativeClient, pinned_binary


class NativeSubscriptionScenario(OnboardingScenario):
    async def subscriptions(self, nodes: tuple[ExitNode, ExitNode]) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for index, (node, owner) in enumerate(zip(nodes, (1, 3), strict=True)):
            remote = await self.remote(index)
            response = await self.http(
                "GET", f"/api/services/{self.services[index]}/subscription", actor=owner
            )
            url = string(json_object(response["subscription"])["subscription_url"])
            checked(url == remote.get("subscriptionUrl"), "native_original_url_rewritten")
            rows.append(
                {
                    "url": url,
                    "identity": string(remote["vlessUuid"]),
                    "host": node.prefix + "-node",
                    "node_ip": await node.internal_ip(),
                    "origin_ip": self.root.origin_ip,
                }
            )
        return rows

    async def checkpoint(self, nodes: tuple[ExitNode, ExitNode], totals: list[int]) -> None:
        for index, node in enumerate(nodes):
            rows = await node.ledger(self.services[index])
            up, down = ledger_totals(rows, expected_peer=await node.internal_ip())
            checked(up + down == totals[index], "native_unaccounted_payload")
            await self.meter(index, totals[index])

    async def transfer_native(
        self, native: NativeClient, index: int, totals: list[int], op: str = "P", size: int = 0
    ) -> None:
        receipt = await native.call(
            "exchange", index=index, token=self.services[index], op=op, size=size
        )
        up, down = receipt.get("up"), receipt.get("down")
        checked(type(up) is int and type(down) is int, "native_invalid_payload_receipt")
        assert isinstance(up, int) and isinstance(down, int)
        expected_up = 21 + (size if op == "U" else 0)
        expected_down = 16 if op == "P" else 1 if op == "U" else size
        checked((up, down) == (expected_up, expected_down), "native_payload_receipt_mismatch")
        totals[index] += up + down

    async def published_change(
        self,
        native: NativeClient,
        nodes: tuple[ExitNode, ExitNode],
        originals: list[dict[str, object]],
        totals: list[int],
    ) -> None:
        root = nodes[0]
        change: dict[str, object] = {
            "operation": "host_update",
            "target_id": root.host_id,
            "patch": {"address": await root.internal_ip()},
        }
        preview = await self.http("POST", PREVIEW, {"change": change})
        checked(
            preview.get("affected_service_ids") == [self.services[0]]
            and preview.get("affected_customer_ids") == [1],
            "native_host_impact_mismatch",
        )
        await self.resource_change(root, change, preview=preview)
        operation = self.operation_ids[-1]
        updated = await native.call("refresh", index=0, published_ip=True)
        checked(
            updated["cache_sha256"] != originals[0]["cache_sha256"]
            and updated["endpoint_sha256"] != originals[0]["endpoint_sha256"]
            and all(
                updated[key] == originals[0][key]
                for key in (
                    "url_sha256",
                    "config_sha256",
                    "credential_sha256",
                    "native_proxy_count",
                )
            ),
            "native_provider_did_not_update_original_url",
        )
        checked(
            await native.call("refresh", index=1) == originals[1], "native_other_service_changed"
        )
        for index in (0, 1):
            await self.transfer_native(native, index, totals)
        await self.checkpoint(nodes, totals)
        restore = {**change, "patch": {"address": root.prefix + "-node"}}
        fresh = await self.http("POST", PREVIEW, {"change": restore})
        checked(fresh.get("fingerprint") != preview.get("fingerprint"), "native_stale_host_preview")
        await self.resource_change(root, restore, preview=fresh, recovery_of=operation)
        restored = await native.call("refresh", index=0)
        checked(restored == originals[0], "native_host_recovery_not_original")
        checked(
            await native.call("refresh", index=1) == originals[1], "native_other_service_changed"
        )
        self.report(
            "native_published_host_update",
            {
                "change_operation": operation,
                "recovery_operation": self.operation_ids[-1],
                "before": originals[0],
                "updated": updated,
                "restored": restored,
                "other_provider_unchanged": True,
            },
        )

    async def revoked_then_restored(
        self,
        native: NativeClient,
        nodes: tuple[ExitNode, ExitNode],
        originals: list[dict[str, object]],
        totals: list[int],
    ) -> None:
        root, other = nodes
        inbound = string(root.state["onboarding_inbound"])
        change: dict[str, object] = {
            "operation": "group_inbounds",
            "target_id": root.squad_id,
            "inbound_ids": [],
        }
        preview = await self.http("POST", PREVIEW, {"change": change})
        removed = group_preview_evidence(preview, root, self.services[0], [inbound], [])
        await self.resource_change(root, change, preview=preview)
        operation = self.operation_ids[-1]
        await asyncio.sleep(5)
        await root.wait_ready()
        token = uuid4().hex
        checked(await root.ledger(token) == [], "native_rejection_token_reused")
        probes = [
            await native.call("exchange", index=0, token=token, op="P", denied=True)
            for _ in range(3)
        ]
        checked(await root.ledger(token) == [], "native_unauthorized_origin_payload")
        for index in (0, 1):
            checked(
                await native.call("snapshot", index=index) == originals[index],
                "native_retained_configuration_changed",
            )
        checked((await self.remote(0)).get("status") == "ACTIVE", "native_service_not_active")
        refresh = await native.call("refresh_revoked", index=0)
        self.report("native_authorization_refresh", refresh)
        checked(refresh.get("verified") is True, "native_authorization_refresh_unverified")
        refreshed_token = uuid4().hex
        checked(await root.ledger(refreshed_token) == [], "native_rejection_token_reused")
        refreshed_probes = [
            await native.call("exchange", index=0, token=refreshed_token, op="P", denied=True)
            for _ in range(3)
        ]
        placeholders = refresh.get("placeholders")
        if placeholders is not None:
            names = json_object(placeholders).get("native_proxy_names_sha256")
            checked(isinstance(names, list) and 1 <= len(names) <= 16, "native_placeholder_names")
            assert isinstance(names, list)
            refreshed_probes.extend(
                [
                    await native.call(
                        "probe_placeholder",
                        index=0,
                        name_sha256=string(name),
                        token=refreshed_token,
                    )
                    for name in names
                ]
            )
        checked(await root.ledger(refreshed_token) == [], "native_refreshed_origin_payload")
        checked(
            await native.call("refresh", index=1) == originals[1],
            "native_other_service_changed",
        )
        await self.transfer_native(native, 1, totals)
        await self.checkpoint(nodes, totals)
        checked((await self.remote(1)).get("status") == "ACTIVE", "native_other_service_not_active")
        restore = {**change, "inbound_ids": [inbound]}
        fresh = await self.http("POST", PREVIEW, {"change": restore})
        recovered = group_preview_evidence(fresh, root, self.services[0], [], [inbound])
        checked(fresh["fingerprint"] != preview["fingerprint"], "native_stale_group_preview")
        await self.resource_change(root, restore, preview=fresh, recovery_of=operation)
        await asyncio.sleep(5)
        await root.wait_ready()
        await other.wait_ready()
        for index in (0, 1):
            checked(
                await native.call("refresh", index=index) == originals[index],
                "native_client_changed",
            )
            await self.transfer_native(native, index, totals)
        await self.checkpoint(nodes, totals)
        self.report(
            "native_retained_authorization",
            {
                "remove_preview": removed,
                "restore_preview": recovered,
                "remove_operation": operation,
                "restore_operation": self.operation_ids[-1],
                "retained_native_config_refused": probes,
                "authorization_refresh": refresh,
                "refreshed_native_client_refused": refreshed_probes,
                "unauthorized_origin_rows": [],
                "other_service_transferred": True,
                "original_clients_recovered": True,
            },
        )

    async def exercise(self) -> None:
        await self.client.start_server()
        await self.infrastructure()
        other = self.root.companion
        checked(other is not None, "native_missing_comparison_node")
        assert other is not None
        nodes = (self.root, other)
        for node, owner in zip(nodes, (1, 3), strict=True):
            await self.onboard(node)
            await self.activate(node, owner)
        rights = [await self.rights(index) for index in (0, 1)]
        rows = await self.subscriptions(nodes)
        await self.tls.start()
        native = NativeClient(self.tls)
        await native.install()
        self.report("native_artifact", await native.call("prepare", services=rows))
        self.report("native_negative_tls", await native.call("untrusted"))
        originals = [await native.start(index) for index in (0, 1)]
        self.report("native_import", originals)
        totals = [0, 0]
        for index in (0, 1):
            for op, size in (("P", 0), ("U", 4096), ("D", 8192)):
                await self.transfer_native(native, index, totals, op, size)
        await self.checkpoint(nodes, totals)
        await self.permissions(self.root)
        await self.published_change(native, nodes, originals, totals)
        await self.revoked_then_restored(native, nodes, originals, totals)
        checked(
            [await self.rights(index) for index in (0, 1)] == rights, "native_entitlements_changed"
        )
        self.report(
            "native_acceptance",
            {
                "status": "passed",
                "scope": SCOPE,
                "actual_up_plus_down": totals,
                "native_http_provider_import_and_update": True,
                "gui_compatibility_verified": False,
                "public_dedicated_verified": False,
                "host_trust_or_proxy_modified": False,
                "rights_unchanged": True,
            },
        )


def run_local_native_subscription() -> None:
    if os.environ.get("QA_NATIVE_SUBSCRIPTION_CLIENT") != "1":
        pytest.skip("Requires the main window's explicit native subscription acceptance slot")
    database = require_onboarding_environment()
    pinned_binary()
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        asyncio.run(run_onboarding(database, scenario_type=NativeSubscriptionScenario, scope=SCOPE))
    finally:
        logging.disable(previous)


@pytest.mark.skipif(
    os.environ.get("QA_NATIVE_SUBSCRIPTION_CLIENT") != "1",
    reason="Requires the exclusive native subscription acceptance slot",
)
@pytest.mark.filterwarnings(
    "ignore:It is recommended to use web.RequestKey: aiohttp.web_exceptions.NotAppKeyWarning"
)
def test_native_subscription_import_refresh_usage_and_retained_authorization() -> None:
    run_local_native_subscription()
