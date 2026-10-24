"""F07: explicit HTTP removal and recovery for an already delivered local service."""

from __future__ import annotations

import asyncio
import hashlib
from typing import TYPE_CHECKING
from uuid import uuid4

from tests.support.exit_replacement_live_node import ExitNode, ledger_totals
from tests.support.node_onboarding_live_node import checked, json_object, one

if TYPE_CHECKING:
    from tests.integration.test_node_onboarding_live_node import OnboardingScenario


def group_preview_evidence(
    preview: dict[str, object],
    node: ExitNode,
    service_id: str,
    before: list[str],
    after: list[str],
) -> dict[str, object]:
    checked(
        preview.get("coverage") == "complete"
        and preview.get("blockers") == []
        and preview.get("remote_authorization_verified") is True,
        "f07_preview_incomplete",
    )
    checked(
        preview.get("affected_service_ids") == [service_id]
        and preview.get("affected_customer_ids") == [1],
        "f07_wrong_affected_services_or_customers",
    )
    direct, reload = json_object(preview["direct"]), json_object(preview["possible_reload"])
    checked(
        direct.get("group_ids") == [node.squad_id]
        and direct.get("node_ids") == [node.node_id]
        and direct.get("profile_ids") == [node.state["onboarding_profile"]]
        and direct.get("service_total") == direct.get("customer_total") == 1
        and direct.get("customer_ids") == [1],
        "f07_wrong_direct_impact",
    )
    service = json_object(one(direct["services"]))
    checked(
        service.get("service_id") == service_id
        and service.get("customer_id") == 1
        and service.get("name") == node.prefix
        and service.get("connection_state") == "ready"
        and all(
            service.get(key) == [node.squad_id]
            for key in ("group_ids", "configured_group_ids", "observed_group_ids")
        ),
        "f07_wrong_direct_service",
    )
    checked(
        reload.get("node_ids") == [node.node_id]
        and reload.get("profile_ids") == [node.state["onboarding_profile"]]
        and reload.get("services") == reload.get("customer_ids") == reload.get("group_ids") == []
        and reload.get("service_total") == reload.get("customer_total") == 0,
        "f07_comparison_group_in_reload_scope",
    )
    current, proposed = json_object(preview["current"]), json_object(preview["proposed"])
    checked(
        current.get("id") == proposed.get("id") == node.squad_id
        and current.get("inbound_ids") == before
        and proposed == {**current, "inbound_ids": after}
        and preview.get("recovery") == "restore_previous_inbounds_and_recheck_profile_nodes",
        "f07_wrong_group_change",
    )
    return {
        key: preview[key]
        for key in (
            "fingerprint",
            "current",
            "proposed",
            "direct",
            "possible_reload",
            "affected_service_ids",
            "affected_customer_ids",
            "recovery",
            "observed_at",
        )
    }


def retained_client(node: ExitNode, port: int) -> dict[str, object]:
    index = node.ports.index(port)
    digest = hashlib.sha256((node.directory / f"client-{index}.json").read_bytes()).hexdigest()
    checked(digest == node.state[f"client_{index}_sha256"], "f07_retained_config_changed")
    return {"client_index": index, "socks_port": port, "config_sha256": digest}


async def exercise_group_change(case: OnboardingScenario, ports: tuple[int, int]) -> None:
    root, other = case.root, case.root.companion
    checked(other is not None and len(case.services) == 2, "f07_requires_two_live_services")
    assert other is not None
    nodes = (root, other)
    originals = [retained_client(node, port) for node, port in zip(nodes, ports, strict=True)]
    rights = [await case.rights(index) for index in (0, 1)]
    totals: list[int] = []
    for index, node in enumerate(nodes):
        service, _ = await case.saved(index)
        up, down = ledger_totals(
            await node.ledger(case.services[index]), expected_peer=await node.internal_ip()
        )
        checked(service.used_bytes == up + down > 0, "f07_missing_existing_usage")
        totals.append(up + down)
    used_before = list(totals)
    evidence: dict[str, object] = {
        "status": "started",
        "clients": originals,
        "rights_before": rights,
        "used_before": used_before,
    }
    case.report("f07_existing_group", evidence)

    async def checkpoint(stage: str) -> None:
        rows_by_service: list[dict[str, object]] = []
        for index, node in enumerate(nodes):
            rows = await node.ledger(case.services[index])
            up, down = ledger_totals(rows, expected_peer=await node.internal_ip())
            checked(up + down == totals[index], "f07_unaccounted_payload")
            service, _ = await case.saved(index)
            checked(service.used_bytes >= used_before[index], "f07_usage_reset")
            await case.meter(index, totals[index])
            checked(await case.rights(index) == rights[index], "f07_service_rights_changed")
            checked(retained_client(node, ports[index]) == originals[index], "f07_client_replaced")
            rows_by_service.append(
                {"service_id": case.services[index], "used_bytes": totals[index], "ledger": rows}
            )
        evidence[stage] = rows_by_service
        case.report("f07_existing_group", evidence)

    inbound = root.state["onboarding_inbound"]
    checked(isinstance(inbound, str), "f07_missing_original_inbound")
    assert isinstance(inbound, str)
    change: dict[str, object] = {
        "operation": "group_inbounds",
        "target_id": root.squad_id,
        "inbound_ids": [],
    }
    preview = await case.http("POST", "/api/admin/console/resources/preview", {"change": change})
    evidence["remove_preview"] = group_preview_evidence(
        preview, root, case.services[0], [inbound], []
    )
    case.report("f07_existing_group", evidence)
    await case.resource_change(root, change, preview=preview)
    removed_operation = case.operation_ids[-1]
    evidence["remove_operation_id"] = removed_operation
    case.report("f07_existing_group", evidence)
    # Panel 3.4.5 queues a profile reload; readback alone is not data-plane evidence.
    await asyncio.sleep(5)
    await root.wait_ready()
    token = uuid4().hex
    evidence["retained_config_rejection"] = await root.rejected(ports[0], token)
    checked(await root.ledger(token) == [], "f07_removed_group_reached_origin")
    await other.exchange(ports[1], case.services[1], b"P")
    totals[1] += 37
    await checkpoint("removed_other_group_still_transfers")

    restore = {**change, "inbound_ids": [inbound]}
    fresh = await case.http("POST", "/api/admin/console/resources/preview", {"change": restore})
    evidence["restore_preview"] = group_preview_evidence(
        fresh, root, case.services[0], [], [inbound]
    )
    checked(fresh["fingerprint"] != preview["fingerprint"], "f07_reused_removal_preview")
    case.report("f07_existing_group", evidence)
    await case.resource_change(root, restore, preview=fresh, recovery_of=removed_operation)
    evidence["restore_operation_id"] = case.operation_ids[-1]
    checked(case.operation_ids[-1] != removed_operation, "f07_reused_removal_operation")
    case.report("f07_existing_group", evidence)
    await asyncio.sleep(5)
    await root.wait_ready()
    for index, node in enumerate(nodes):
        await node.exchange(ports[index], case.services[index], b"P")
        totals[index] += 37
    await checkpoint("restored_original_clients_transfer")
    evidence["status"] = "passed"
    case.report("f07_existing_group", evidence)
