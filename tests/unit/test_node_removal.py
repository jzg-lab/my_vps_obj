"""Unassociated-node removal uses confirmed intents and fresh absence readback."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from bot.app.web.admin_console_resource_operation_schemas import ConsoleResourceOperationStartBody
from bot.services.resource_operation_reconciliation import reconcile_resource_operation
from bot.services.resource_operation_runner import run_pending_resource_operation
from bot.services.resource_operations import CHANGE_ADAPTER, start_resource_operation
from bot.services.resource_preview_panel import read_preview_inventory
from db.dal.user_services_dal import ServiceConflict
from tests.unit.test_admin_console_resource_preview import (
    I3,
    N1,
    N2,
    N3,
    P2,
    build_resource_preview,
    fixture_rows,
    inventory_fixture,
    panel_fixture,
)
from tests.unit.test_resource_operations import ResourceOperationDatabaseCase


@pytest.mark.parametrize("implicit,disabled", [(False, False), (True, False), (True, True)])
def test_removal_blocks_explicit_and_implicit_hosts_including_disabled(
    implicit: bool, disabled: bool
) -> None:
    payloads = inventory_fixture()
    hosts = payloads["/hosts"]
    assert isinstance(hosts, list)
    hosts[0]["nodes"] = [] if implicit else [N1]
    hosts[0]["isDisabled"] = disabled
    hosts[0]["isHidden"] = True
    panel, _ = panel_fixture(payloads)
    inventory = asyncio.run(read_preview_inventory(panel))
    preview = build_resource_preview(
        CHANGE_ADAPTER.validate_python({"operation": "node_delete", "target_id": N1}),
        inventory,
        [],
    )
    assert "node_has_related_hosts" in preview.blockers
    assert [host.name for host in preview.related_hosts] == ["Host"]
    assert preview.fingerprint is None and preview.proposed is None


def test_removal_blocks_potential_services_even_without_a_host() -> None:
    panel, _ = panel_fixture(inventory_fixture())
    preview = build_resource_preview(
        CHANGE_ADAPTER.validate_python({"operation": "node_delete", "target_id": N2}),
        asyncio.run(read_preview_inventory(panel)),
        fixture_rows(),
    )
    assert preview.related_hosts == []
    assert "node_has_related_services" in preview.blockers
    assert preview.direct.service_total == 1
    assert preview.affected_customer_ids == [22]
    assert preview.fingerprint is None


class NodeRemovalTests(ResourceOperationDatabaseCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.queued = False
        self.fail_readback = False
        self.writes = AsyncMock(side_effect=self.delete_write)
        self.panel._request_once = self.writes

    def remove_node(self) -> None:
        self.rows("/nodes")[:] = [row for row in self.rows("/nodes") if row["uuid"] != N3]
        for profile in self.rows("/config-profiles", "configProfiles"):
            nodes = profile["nodes"]
            assert isinstance(nodes, list)
            profile["nodes"] = [node for node in nodes if node["uuid"] != N3]

    async def delete_write(self, method: str, path: str, **kwargs: object) -> dict[str, object]:
        assert method == "DELETE" and path == f"/nodes/{N3}"
        assert "json" not in kwargs
        if not self.queued:
            self.remove_node()
        if self.fail_readback:
            self.payloads["/nodes"] = TimeoutError("inventory unavailable")
        if self.lose_reply:
            raise TimeoutError("response lost")
        return {"status_code": 204}

    async def test_removal_confirms_absence_and_preserves_other_nodes(self) -> None:
        operation = await self.submit({"operation": "node_delete", "target_id": N3})
        await run_pending_resource_operation(self.sessions, self.panel)
        result = await self.output(operation.id)
        assert result.status == "succeeded" and not result.gate_active
        assert result.observation is not None
        assert result.observation.configuration == "matched"
        assert result.observation.values is None and result.observation.runtime == "unverified"
        assert result.preview.proposed is None
        assert result.preview.recovery == "node_removal_requires_manual_onboarding"
        assert {row["uuid"] for row in self.rows("/nodes")} == {N1, N2}
        await run_pending_resource_operation(self.sessions, self.panel)
        self.writes.assert_awaited_once()

    async def test_host_added_after_confirmation_blocks_dispatch(self) -> None:
        operation = await self.submit({"operation": "node_delete", "target_id": N3})
        self.rows("/hosts").append(
            {
                **self.rows("/hosts")[0],
                "uuid": "00000000-0000-0000-0000-000000000999",
                "nodes": [N3],
                "inbound": {"configProfileUuid": P2, "configProfileInboundUuid": I3},
            }
        )
        await run_pending_resource_operation(self.sessions, self.panel)
        result = await self.output(operation.id)
        assert result.status == "failed" and result.error_code == "resource_sources_incomplete"
        self.writes.assert_not_awaited()

    async def test_queued_acknowledgement_waits_for_absence_before_success(self) -> None:
        self.queued = True
        operation = await self.submit({"operation": "node_delete", "target_id": N3})
        await run_pending_resource_operation(self.sessions, self.panel)
        result = await self.output(operation.id)
        assert result.status == "unknown" and result.gate_active
        self.remove_node()
        async with self.sessions.begin() as session:
            accepted = await reconcile_resource_operation(
                session, self.panel, result.id, expected_version=result.version
            )
            assert accepted.operation.status == "succeeded"
        self.writes.assert_awaited_once()

    async def test_lost_delete_reply_keeps_guard_even_if_registration_is_absent(self) -> None:
        self.lose_reply = True
        operation = await self.submit({"operation": "node_delete", "target_id": N3})
        await run_pending_resource_operation(self.sessions, self.panel)
        result = await self.output(operation.id)
        assert result.status == "unknown" and result.gate_active
        async with self.sessions.begin() as session:
            accepted = await reconcile_resource_operation(
                session, self.panel, result.id, expected_version=result.version
            )
            assert accepted.operation.status == "unknown" and accepted.operation.gate_active
        await run_pending_resource_operation(self.sessions, self.panel)
        self.writes.assert_awaited_once()
        with pytest.raises(ServiceConflict):
            async with self.sessions.begin() as session:
                await start_resource_operation(
                    session,
                    self.panel,
                    actor_id=1,
                    body=ConsoleResourceOperationStartBody(
                        change=operation.change,
                        expected_fingerprint=operation.preview.fingerprint or "a" * 64,
                        idempotency_key="second",
                    ),
                )

    async def test_failed_readback_cannot_prove_removal(self) -> None:
        self.fail_readback = True
        operation = await self.submit({"operation": "node_delete", "target_id": N3})
        await run_pending_resource_operation(self.sessions, self.panel)
        result = await self.output(operation.id)
        assert result.status == "unknown" and result.gate_active
        assert result.observation is not None
        assert result.observation.configuration == "unavailable"
        self.writes.assert_awaited_once()
