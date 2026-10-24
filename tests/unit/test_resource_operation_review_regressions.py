"""Creation evidence must preserve ownership; resource gates must not starve revocation."""

from typing import cast
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from bot.app.web.admin_console_resource_operation_schemas import ConsoleResourceOperationOut
from bot.services.resource_operation_panel import creation_marker
from bot.services.resource_operation_runner import run_pending_resource_operation
from bot.services.service_provisioning import ServiceProvisioningWorker
from db.dal.service_delivery_dal import request_service_revocation
from db.dal.user_services_dal import ServiceConflict, save_plan
from db.service_models import ServiceConnection, UserService
from tests.unit.test_admin_console_resource_preview import G1
from tests.unit.test_resource_operations import (
    CREATED,
    ResourceOperationDatabaseCase,
    create_change,
)
from tests.unit.test_service_provisioning import panel_fixture
from tests.unit.test_user_services import sample_terms


class ResourceOperationReviewRegressions(ResourceOperationDatabaseCase):
    async def _lost_host_create(self) -> ConsoleResourceOperationOut:
        operation = await self.submit(create_change("host"))
        self.lose_reply = True
        await run_pending_resource_operation(self.sessions, self.panel)
        await run_pending_resource_operation(self.sessions, self.panel)
        current = await self.output(operation.id)
        assert current.status == "unknown" and current.gate_active
        assert len(current.attempts) == 1 and current.attempts[0].receipt == "unknown"
        assert current.observation is not None
        assert current.observation.configuration == "matched"
        assert current.observation.correlation == "creation_marker"
        assert current.observation.values is not None
        assert current.observation.values.id == CREATED
        created = next(row for row in self.rows("/hosts") if row["uuid"] == CREATED)
        tags = created["tags"]
        assert isinstance(tags, list) and creation_marker(operation.id, host=True) in tags
        self.writes.assert_awaited_once()
        return current

    async def _reject_foreign_evidence(
        self, before: ConsoleResourceOperationOut, result: str, target: str
    ) -> None:
        with pytest.raises(ServiceConflict, match=r"^resource_evidence_invalid$"):
            await self.evidence(before.id, result, target=target)
        after = await self.output(before.id)
        assert after.status == "unknown" and after.gate_active
        assert after.target_id == before.target_id
        assert after.version == before.version and after.attempts == before.attempts
        assert after.evidence == [] and not after.can_retry
        self.writes.assert_awaited_once()

    async def test_absent_foreign_uuid_cannot_disprove_a_known_created_host(self) -> None:
        operation = await self._lost_host_create()
        foreign = str(UUID(int=902))
        assert all(row["uuid"] != foreign for row in self.rows("/hosts"))
        await self._reject_foreign_evidence(operation, "not_applied", foreign)

    async def test_partial_evidence_cannot_claim_an_unmarked_foreign_host(self) -> None:
        operation = await self._lost_host_create()
        foreign = str(UUID(int=902))
        created = next(row for row in self.rows("/hosts") if row["uuid"] == CREATED)
        self.rows("/hosts").append(
            {**created, "uuid": foreign, "remark": "Unrelated new host", "tags": []}
        )
        await self._reject_foreign_evidence(operation, "partial", foreign)

    async def test_unknown_resource_gate_cannot_starve_the_51st_revocation(self) -> None:
        async with self.sessions.begin() as session:
            self.plan = await save_plan(
                session, terms=sample_terms(squad_uuids=[G1]), enabled=True, actor_id=1
            )
        service_ids: list[str] = []
        for index in range(51):
            service, _, _ = await self.activate(f"awaiting-resource-{index}")
            service_ids.append(service.id)
        # Every attempt is NULL, so the final UUID is outside the worker's first batch.
        victim_id = max(service_ids)
        operation = await self.submit()
        self.lose_reply = True
        await run_pending_resource_operation(self.sessions, self.panel)
        before = await self.output(operation.id)
        assert before.status == "unknown" and before.gate_active
        self.writes.assert_awaited_once()

        async with self.sessions.begin() as session:
            victim = await session.get(UserService, victim_id)
            assert victim is not None
            await request_service_revocation(
                session,
                service_id=victim_id,
                user_id=1,
                actor_id=1,
                expected_revision=victim.revision,
                idempotency_key="cancel-last",
                reason="Requested cancellation",
            )
        panel, users = panel_fixture()
        worker = ServiceProvisioningWorker(cast(sessionmaker, self.sessions), panel)
        await worker.tick()
        await worker.tick()

        current = await self.output(operation.id)
        assert current.status == "unknown" and current.gate_active
        assert current.attempts == before.attempts
        self.writes.assert_awaited_once()
        panel.create_panel_user.assert_not_awaited()
        panel.update_user_status_on_panel.assert_not_awaited()
        panel.delete_user_from_panel.assert_not_awaited()
        assert users == {}
        async with self.sessions() as session:
            connection = await session.get(ServiceConnection, victim_id)
            assert connection is not None and connection.revoke_requested_at is not None
            assert connection.state == "revoked", (
                "Two worker ticks must reach revocation despite 50 gate-blocked preparations",
                connection.state,
                connection.attempted_at,
                panel.get_users_by_filter.await_count,
            )
            assert connection.revoked_at is not None and not connection.sync_pending
            remaining = list(
                await session.scalars(
                    select(ServiceConnection).where(
                        ServiceConnection.service_id.in_(service_ids),
                        ServiceConnection.service_id != victim_id,
                    )
                )
            )
            assert len(remaining) == 50
            assert all(row.state == "pending" and row.panel_user_uuid is None for row in remaining)
        panel.get_users_by_filter.assert_awaited_once_with(username=f"svc_{victim_id}")
