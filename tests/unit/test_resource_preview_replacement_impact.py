"""Replacement impact reads use batched fakes, with no database or HTTP server."""

from datetime import UTC, datetime
from typing import cast
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web import admin_console_resource_routes
from bot.app.web.admin_console_nodes_panel import NodeInventoryReader
from bot.app.web.admin_console_resource_schemas import (
    ConsoleResourcePreviewBody,
    ConsoleResourcePreviewOut,
    ResourceSourceOut,
)
from bot.services.resource_preview import build_resource_preview
from bot.services.resource_preview_authorizations import (
    PreviewAuthorizations,
    read_preview_authorizations,
)
from bot.services.resource_preview_panel import read_preview_inventory
from db.dal.admin_console_nodes_dal import (
    ServiceResourceRows,
    read_service_resources,
    service_group_ids,
)
from db.models import User
from db.service_models import (
    DedicatedExit,
    ServiceConnection,
    ServiceOperationExecution,
    ServiceOrder,
    UserService,
)
from tests.unit.test_admin_console_resource_preview import (
    G1,
    G2,
    G3,
    H1,
    I2,
    N1,
    N2,
    N3,
    SECRET,
    fixture_rows,
    inventory_fixture,
    panel_fixture,
)
from tests.unit.test_user_services import sample_terms


class ReplacementImpactTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        service, connection, _, user = fixture_rows()[0]
        assert connection is not None
        self.service = service
        self.connection = connection
        self.user: User | None = user
        service.terms = sample_terms(
            resource_type="dedicated", squad_uuids=[], resource_pool="private"
        ).model_dump(mode="json")
        self.old = DedicatedExit(
            id="a" * 32,
            service_id=service.id,
            hold_order_id=None,
            squad_uuid=G1,
            resource_pool="private",
            enabled=True,
            verified_at=datetime.now(UTC),
            revision=1,
        )
        self.candidate = DedicatedExit(
            id="b" * 32,
            service_id=None,
            hold_order_id="c" * 32,
            squad_uuid=G2,
            resource_pool="private",
            enabled=False,
            verified_at=None,
            revision=2,
        )
        self.current: DedicatedExit | None = self.old
        self.exits = [self.old, self.candidate]
        self.order = ServiceOrder(
            id="c" * 32,
            service_id=service.id,
            user_id=99,
            request_owner_id=99,
            kind="replace_exit",
            request={
                "replacement": {
                    "expected_revision": 1,
                    "old_exit_id": self.old.id,
                    "new_exit_id": self.candidate.id,
                    "expected_old_exit_revision": 1,
                    "expected_new_exit_revision": 2,
                    "resource_fingerprint": "d" * 64,
                    "reason": SECRET,
                }
            },
        )
        connection.replacement_order_id = self.order.id
        self.execution = ServiceOperationExecution(
            id="d" * 32,
            service_id=service.id,
            order_id=self.order.id,
            phase="exit_replace",
            status="pending",
        )
        self.records: list[tuple[ServiceOrder | None, ServiceOperationExecution | None]] = [
            (self.order, self.execution)
        ]
        self.observed = {UUID(G1)}

    async def read(
        self, *, group_ids: set[str] | None = None, service_id: str | None = None
    ) -> ServiceResourceRows:
        raw_rows: list[
            tuple[UserService, ServiceConnection | None, DedicatedExit | None, User | None]
        ] = [(self.service, self.connection, self.current, self.user)]
        session = Mock(spec=AsyncSession)
        session.execute = AsyncMock(side_effect=[raw_rows, self.records])
        session.scalars = AsyncMock(return_value=self.exits)
        rows = await read_service_resources(
            cast(AsyncSession, session), group_ids=group_ids, service_id=service_id
        )
        assert session.execute.await_count == 2
        assert session.scalars.await_count == 1
        session.get.assert_not_called()
        session.flush.assert_not_called()
        session.commit.assert_not_called()
        queries = [call.args[0] for call in session.execute.await_args_list]
        assert "LEFT OUTER JOIN users" in str(queries[0].compile(dialect=postgresql.dialect()))
        assert "exit_replace" in str(
            queries[1].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
        )
        if service_id is not None:
            service_sql = str(
                queries[0].compile(
                    dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
                )
            )
            assert f"WHERE user_services.id = '{service_id}'" in service_sql
            order_sql = str(
                queries[1].compile(
                    dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
                )
            )
            assert f"service_orders.service_id = '{service_id}'" in order_sql
            assert f"service_operation_executions.service_id = '{service_id}'" in order_sql
            exit_sql = str(
                session.scalars.await_args.args[0].compile(
                    dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
                )
            )
            assert "WHERE" in exit_sql and f"service_id = '{service_id}'" in exit_sql
            assert "dedicated_exits.hold_order_id IS NOT NULL" not in exit_sql
        return rows

    async def preview(
        self, change: dict[str, object], rows: ServiceResourceRows | None = None
    ) -> ConsoleResourcePreviewOut:
        if rows is None:
            rows = await self.read()
        panel, _ = panel_fixture(inventory_fixture())
        return build_resource_preview(
            ConsoleResourcePreviewBody.model_validate({"change": change}).change,
            await read_preview_inventory(panel),
            rows,
            authorizations=PreviewAuthorizations(
                {self.service.id: self.observed},
                ResourceSourceOut(
                    source="authorizations", availability="available", observed_at=datetime.now(UTC)
                ),
            ),
        )

    def complete_binding(self) -> None:
        self.old.service_id = None
        self.old.hold_order_id = self.order.id
        self.candidate.service_id = self.service.id
        self.candidate.hold_order_id = None
        self.candidate.enabled = True
        self.candidate.verified_at = datetime.now(UTC)
        self.current = self.candidate
        self.connection.replacement_order_id = None
        self.execution.status = "succeeded"
        self.observed = {UUID(G2)}

    async def test_candidate_node_lists_actual_owner_without_granting_candidate(self) -> None:
        rows = await self.read(group_ids={G2})
        assert len(rows) == 1 and rows[0][0].id == self.service.id
        assert rows[0][2] is self.old
        assert rows[0][3].user_id == 11
        assert service_group_ids(self.service, self.old) == {G1}
        assert service_group_ids(self.service, self.candidate) == set()
        result = await self.preview({"operation": "node_disable", "target_id": N2})
        assert result.coverage == "partial" and result.fingerprint is None
        assert result.affected_service_ids == [self.service.id]
        assert result.affected_customer_ids == [11]
        assert not result.remote_authorization_verified
        service = result.direct.services[0]
        assert service.group_ids == [G1, G2]
        assert service.configured_group_ids == [G1]
        assert service.observed_group_ids == [G1]
        assert SECRET not in result.model_dump_json()

    async def test_retained_old_exit_survives_success_and_cleared_gate(self) -> None:
        self.complete_binding()
        rows = await self.read(group_ids={G1})
        assert len(rows) == 1 and rows[0][2] is self.candidate
        assert service_group_ids(self.service, self.old) == set()
        result = await self.preview({"operation": "node_restart", "target_id": N1})
        assert "replacement_resource_held" in result.blockers
        assert result.direct.service_total == 1 and result.direct.customer_total == 1
        assert result.direct.services[0].configured_group_ids == [G2]
        assert result.direct.services[0].observed_group_ids == [G2]

    async def test_terminal_success_does_not_block_unrelated_current_resource(self) -> None:
        self.complete_binding()
        result = await self.preview({"operation": "node_disable", "target_id": N2})
        assert result.coverage == "complete" and result.fingerprint
        assert result.affected_service_ids == [self.service.id]

    async def test_known_hold_does_not_block_unrelated_resource(self) -> None:
        result = await self.preview({"operation": "node_restart", "target_id": N3})
        assert result.coverage == "complete" and result.fingerprint
        assert result.affected_service_ids == [] and result.blockers == []
        assert await self.read(group_ids={G3}) == []

    async def test_candidate_hold_appears_in_profile_reload_impact(self) -> None:
        result = await self.preview(
            {"operation": "group_inbounds", "target_id": G1, "inbound_ids": [I2]}
        )
        assert result.possible_reload.group_ids == [G2]
        assert result.possible_reload.services[0].service_id == self.service.id
        assert result.coverage == "partial"

    async def test_host_impact_includes_retained_exit_with_no_current_authorization(self) -> None:
        self.complete_binding()
        result = await self.preview(
            {"operation": "host_update", "target_id": H1, "patch": {"is_disabled": True}}
        )
        assert result.direct.group_ids == [G1]
        assert result.affected_service_ids == [self.service.id]
        assert result.coverage == "partial" and result.fingerprint is None

    async def test_reclaimed_resource_stops_blocking(self) -> None:
        self.complete_binding()
        self.old.hold_order_id = None
        self.records = []
        result = await self.preview(
            {"operation": "host_update", "target_id": H1, "patch": {"is_disabled": True}}
        )
        assert result.coverage == "complete" and result.fingerprint
        assert result.affected_service_ids == []
        assert await self.read(group_ids={G1}) == []

    async def test_revoked_identity_does_not_remove_held_resource_impact(self) -> None:
        self.complete_binding()
        self.connection.state = "revoked"
        self.observed = set()
        rows = await self.read(group_ids={G1})
        assert len(rows) == 1
        result = await self.preview({"operation": "node_disable", "target_id": N1})
        assert result.coverage == "partial" and self.service.id in result.affected_service_ids

    async def test_multiple_holds_do_not_duplicate_service_or_remote_lookups(self) -> None:
        self.complete_binding()
        self.current = None
        self.candidate.service_id = None
        self.candidate.hold_order_id = self.order.id
        rows = await self.read()
        assert len(rows) == 1 and len(rows.replacement_impacts) == 2
        panel, _ = panel_fixture(inventory_fixture())
        await read_preview_authorizations(panel, rows)
        cast(AsyncMock, panel.get_user_by_uuid_lookup).assert_awaited_once()
        result = await self.preview({"operation": "node_restart", "target_id": N1}, rows)
        assert result.direct.service_total == 1 and result.direct.customer_ids == [11]
        assert "duplicate_service_binding" not in result.blockers

    async def test_archived_hold_keeps_real_service_id_without_account_zero(self) -> None:
        self.complete_binding()
        self.service.user_id = None
        self.user = None
        rows = await self.read()
        assert not rows and rows.replacement_impacts[0].customer_id is None
        result = await self.preview({"operation": "node_disable", "target_id": N1}, rows)
        assert result.coverage == "partial"
        assert result.affected_service_ids == [self.service.id]
        assert result.affected_customer_ids == [] and result.direct.customer_total == 0
        assert result.direct.service_total == 1
        assert "replacement_customer_unavailable" in result.blockers
        assert result.direct.services == []  # The current public schema requires an owner.

    async def test_missing_user_does_not_fall_back_to_order_owner(self) -> None:
        self.complete_binding()
        self.user = None
        result = await self.preview({"operation": "node_disable", "target_id": N1})
        assert result.affected_service_ids == [self.service.id]
        assert result.affected_customer_ids == []
        assert "replacement_customer_unavailable" in result.blockers

    async def test_orphan_hold_is_unknown_for_its_group_not_a_fake_empty_success(self) -> None:
        self.connection.replacement_order_id = None
        self.records = []
        result = await self.preview({"operation": "node_disable", "target_id": N2})
        assert result.coverage == "partial" and result.fingerprint is None
        assert "replacement_service_unconfirmed" in result.blockers
        assert result.affected_service_ids == [] and result.affected_customer_ids == []
        unrelated = await self.preview({"operation": "node_restart", "target_id": N3})
        assert unrelated.coverage == "complete"

    async def test_unlocatable_hold_blocks_unknown_scope(self) -> None:
        self.connection.replacement_order_id = None
        self.records = []
        self.candidate.squad_uuid = "invalid-group"
        result = await self.preview({"operation": "node_restart", "target_id": N3})
        assert result.coverage == "partial"
        assert "replacement_scope_unconfirmed" in result.blockers
        rows = await self.read(group_ids=set())
        assert rows.replacement_impacts[0].unknown_scope

    async def test_missing_gate_order_never_means_no_replacement(self) -> None:
        self.records = []
        self.candidate.hold_order_id = None
        result = await self.preview({"operation": "node_restart", "target_id": N3})
        assert result.coverage == "partial" and result.fingerprint is None
        assert "replacement_state_invalid" in result.blockers
        assert result.affected_service_ids == [self.service.id]

    async def test_pending_execution_without_gate_is_still_potential_impact(self) -> None:
        self.connection.replacement_order_id = None
        self.candidate.hold_order_id = None
        result = await self.preview({"operation": "node_disable", "target_id": N2})
        assert result.coverage == "partial"
        assert "replacement_state_invalid" in result.blockers
        assert result.affected_service_ids == [self.service.id]

    async def test_exit_replace_execution_without_order_is_explicitly_unknown(self) -> None:
        self.connection.replacement_order_id = None
        self.candidate.hold_order_id = None
        self.execution.order_id = None
        self.records = [(None, self.execution)]
        result = await self.preview({"operation": "node_restart", "target_id": N3})
        assert result.coverage == "partial"
        assert "replacement_state_invalid" in result.blockers

    async def test_invalid_request_and_missing_exit_fail_closed(self) -> None:
        for invalid in ("request", "exit"):
            with self.subTest(invalid=invalid):
                if invalid == "request":
                    self.order.request = {}
                else:
                    self.setUp()
                    self.exits.remove(self.candidate)
                result = await self.preview({"operation": "node_restart", "target_id": N3})
                assert result.coverage == "partial"
                assert "replacement_scope_unconfirmed" in result.blockers

    async def test_hold_and_current_binding_corruption_does_not_grant_access(self) -> None:
        self.old.hold_order_id = self.order.id
        assert service_group_ids(self.service, self.old) == set()
        result = await self.preview({"operation": "node_restart", "target_id": N1})
        assert "replacement_state_invalid" in result.blockers

    async def test_service_filter_keeps_corrupt_hold_on_its_current_binding(self) -> None:
        self.old.hold_order_id = self.order.id
        self.connection.replacement_order_id = None
        self.records = []
        rows = await self.read(service_id=self.service.id)
        assert rows.replacement_impacts
        assert "replacement_state_invalid" in rows.replacement_impacts[0].blockers
        assert service_group_ids(self.service, rows[0][2]) == set()
        self.records = [(self.order, self.execution)]
        self.order.service_id = "f" * 32
        rows = await self.read(service_id=self.service.id)
        assert rows.replacement_impacts
        assert all(impact.service_id == self.service.id for impact in rows.replacement_impacts)

    async def test_missing_service_is_not_reported_as_a_real_customer(self) -> None:
        self.connection.replacement_order_id = None
        self.execution.status = "succeeded"
        self.order.service_id = "f" * 32
        self.execution.service_id = self.order.service_id
        result = await self.preview({"operation": "node_disable", "target_id": N2})
        assert result.coverage == "partial"
        assert "replacement_service_unconfirmed" in result.blockers
        assert result.affected_service_ids == [] and result.affected_customer_ids == []

    async def test_service_specific_read_preserves_current_binding_only(self) -> None:
        rows = await self.read(service_id=self.service.id)
        assert len(rows) == 1 and rows[0][2] is self.old
        assert len(rows.replacement_impacts) == 2
        missing = await self.read(service_id="f" * 32)
        assert not missing and missing.replacement_impacts == []

    async def test_plain_rows_with_gate_cannot_claim_complete(self) -> None:
        panel, _ = panel_fixture(inventory_fixture())
        assert self.user is not None
        result = build_resource_preview(
            ConsoleResourcePreviewBody.model_validate(
                {"change": {"operation": "node_restart", "target_id": N3}}
            ).change,
            await read_preview_inventory(panel),
            [(self.service, self.connection, self.old, self.user)],
            authorizations=PreviewAuthorizations(
                {self.service.id: self.observed},
                ResourceSourceOut(
                    source="authorizations", availability="available", observed_at=datetime.now(UTC)
                ),
            ),
        )
        assert "replacement_scope_unconfirmed" in result.blockers
        assert result.coverage == "partial"

    async def test_node_coverage_uses_scoped_metadata_before_pagination(self) -> None:
        panel, _ = panel_fixture(inventory_fixture())
        inventory = await NodeInventoryReader().read(panel, ttl_seconds=0)
        affected = await self.read(group_ids={G2})
        assert inventory.coverage == "complete"
        assert inventory.scope_coverage(affected) == "partial"
        unrelated = await self.read(group_ids={G3})
        assert inventory.scope_coverage(unrelated) == "complete"
        self.complete_binding()
        self.user = None
        archived = await self.read(group_ids={G1})
        assert archived == [] and inventory.scope_coverage(archived) == "partial"
        inventory.nodes.source.availability = "stale"
        assert inventory.scope_coverage(affected) == "stale"

    async def test_existing_resource_read_and_preview_consumers_keep_metadata(self) -> None:
        rows = await self.read()
        session = Mock(spec=AsyncSession)
        session.scalar = AsyncMock(return_value=None)
        context = AsyncMock()
        context.__aenter__.return_value = session
        request = Mock()
        with (
            patch.object(
                admin_console_resource_routes,
                "get_session_factory",
                return_value=Mock(return_value=context),
            ),
            patch.object(
                admin_console_resource_routes, "read_service_resources", return_value=rows
            ),
        ):
            loaded, archived = await admin_console_resource_routes._read_services(request)
        assert loaded is rows and not archived
        panel, _ = panel_fixture(inventory_fixture())
        change = ConsoleResourcePreviewBody.model_validate(
            {"change": {"operation": "node_disable", "target_id": N2}}
        ).change
        with (
            patch.object(admin_console_resource_routes, "get_panel_service", return_value=panel),
            patch.object(
                admin_console_resource_routes, "_read_services", return_value=(loaded, False)
            ),
        ):
            result = await admin_console_resource_routes._stable_preview(request, change)
        assert result.coverage == "partial" and result.fingerprint is None
        assert result.affected_service_ids == [self.service.id]
        assert result.direct.services[0].configured_group_ids == [G1]
        assert "replacement_resource_held" in result.blockers
