"""Real SQLite impact ownership and confirm checks with offline inventory responses."""

from copy import deepcopy
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import event, select

from bot.app.web.admin_console_exit_replacement_schemas import ConsoleExitReplacementConfirmBody
from bot.services.resource_preview_panel import digest
from bot.services.service_exit_replacement import current_state
from bot.services.service_exit_replacement_commands import confirm_replacement
from bot.services.service_exit_replacement_topology import (
    ReplacementTopology,
    read_replacement_topology,
)
from db.dal.user_services_dal import ServiceConflict, activate_service, save_plan
from db.service_models import DedicatedExitAudit, ServiceConnection, UserService
from tests.unit.test_admin_console_resource_preview import P1, inventory_fixture, uid
from tests.unit.test_service_exit_replacement_runner import RunnerDatabaseTestCase
from tests.unit.test_user_services import sample_terms

RELOAD_GROUP, RELOAD_INBOUND = uid(4), uid(204)


def related_inventory() -> dict[str, object]:
    payloads = inventory_fixture()
    groups, profiles = payloads["/internal-squads"], payloads["/config-profiles"]
    assert isinstance(groups, dict) and isinstance(profiles, dict)
    groups["total"] += 1
    groups["internalSquads"].append(
        {
            "uuid": RELOAD_GROUP,
            "name": "Other group on the same profile",
            "inbounds": [{"uuid": RELOAD_INBOUND}],
        }
    )
    profiles["configProfiles"][0]["inbounds"].append(
        {"uuid": RELOAD_INBOUND, "profileUuid": P1, "tag": "reload"}
    )
    return payloads


def pre_customer_digest(value: object) -> str:
    if isinstance(value, dict) and "service_impacts" in value:
        value = dict(value)
        impacts = value.pop("service_impacts")
        assert isinstance(impacts, list)
        value["services"] = [
            {key: field for key, field in impact.items() if key != "customer_id"}
            for impact in impacts
        ]
    result = digest(value)
    assert isinstance(result, str)
    return result


class ExitReplacementImpactCustomersTests(RunnerDatabaseTestCase):
    async def asyncSetUp(self) -> None:
        with patch(
            "tests.unit.test_service_exit_replacement_runner.inventory_fixture",
            side_effect=related_inventory,
        ):
            await super().asyncSetUp()

    async def prepare(
        self, service: UserService, *, ready: bool = False
    ) -> tuple[AsyncMock, dict[str, object]]:
        # Seed the affected service before the parent fixture captures its initial scope.
        self.reload_service = await self.add_reload_service("Reload customer service", user_id=2)
        return await super().prepare(service, ready=ready)

    async def add_reload_service(self, name: str, *, user_id: int = 2) -> UserService:
        async with self.sessions.begin() as session:
            plan = await save_plan(
                session,
                terms=sample_terms(name=name, squad_uuids=[RELOAD_GROUP]),
                enabled=True,
                actor_id=1,
            )
            service, _, _ = await activate_service(
                session,
                user_id=user_id,
                actor_id=1,
                plan_id=plan.id,
                expected_revision=1,
                idempotency_key="impact:" + plan.id,
            )
            return service

    async def topology(self) -> ReplacementTopology:
        async with self.sessions() as session:
            state = await self.state(session)
            result = await read_replacement_topology(
                session, self.panel, state.old_exit, state.new_exit, service_id=self.service.id
            )
            assert not session.new and not session.dirty and not session.deleted
            return result

    async def test_reload_lists_current_customers_and_stored_service_names(self) -> None:
        other = await self.add_reload_service("Another customer service", user_id=1)
        topology = await self.topology()
        assert topology.public.coverage == "complete"
        impacts = {item.service_id: item for item in topology.public.impacts}
        assert set(impacts) == {self.reload_service.id, other.id}
        assert impacts[self.reload_service.id].customer_id == 2
        assert impacts[self.reload_service.id].service_name == "Reload customer service"
        assert impacts[other.id].customer_id == 1
        assert impacts[other.id].service_name == "Another customer service"
        assert all(
            item.kind == "possible_reload" and item.group_ids == [RELOAD_GROUP]
            for item in impacts.values()
        )
        assert not self.writes

    async def test_external_identity_never_gets_a_guessed_customer_or_name(self) -> None:
        self.extra_remote_users.append(
            {
                "uuid": "external-identity",
                "activeInternalSquads": [RELOAD_GROUP],
                "username": "NOT_A_LOCAL_SERVICE_NAME",
                "password": "PRIVATE_TEST_PASSWORD",
            }
        )
        topology = await self.topology()
        assert topology.public.coverage == "complete"
        external = [item for item in topology.public.impacts if item.service_id is None]
        assert len(external) == 1
        assert external[0].model_dump() == {
            "service_id": None,
            "customer_id": None,
            "service_name": None,
            "group_ids": [RELOAD_GROUP],
            "kind": "possible_reload",
        }
        assert "NOT_A_LOCAL_SERVICE_NAME" not in topology.public.model_dump_json()
        assert "PRIVATE_TEST_PASSWORD" not in topology.public.model_dump_json()

    async def test_names_are_display_only_and_do_not_invalidate_confirmation(self) -> None:
        before = await self.topology()
        await self.tick()
        await self.attest()
        async with self.sessions.begin() as session:
            service = await session.get(UserService, self.reload_service.id)
            assert service
            service.terms = service.terms | {"name": "Renamed service"}
        after = await self.topology()
        assert (before.old_scope, before.new_scope) == (after.old_scope, after.new_scope)
        assert before.public.resource_fingerprint == after.public.resource_fingerprint
        assert after.public.impacts[0].service_name == "Renamed service"
        await self.confirm()
        assert (await self.progress()).stage == "switching"

    async def test_ownership_change_rejects_old_confirmation_without_rewriting_history(
        self,
    ) -> None:
        await self.tick()
        await self.attest()
        await self.confirm()
        before = await self.topology()
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.progress.stop_audit_id and state.progress.verification_audit_id
            assert self.fingerprint
            body = ConsoleExitReplacementConfirmBody(
                user_id=1,
                operation_id=self.operation.id,
                expected_revision=state.service.revision,
                expected_operation_version=state.progress.version,
                expected_old_exit_revision=state.old_exit.revision,
                expected_new_exit_revision=state.new_exit.revision,
                expected_resource_fingerprint=self.fingerprint,
                old_stop_audit_id=state.progress.stop_audit_id,
                candidate_verify_audit_id=state.progress.verification_audit_id,
                confirm_replace_and_request_restore=True,
                idempotency_key="confirm",
            )
            request_before = deepcopy(state.order.request)
            progress_before = deepcopy(state.execution.replacement_progress)
            audits_before = {
                row.id: deepcopy(row.evidence)
                for row in await session.scalars(select(DedicatedExitAudit))
            }
        async with self.sessions.begin() as session:
            service = await session.get(UserService, self.reload_service.id)
            assert service
            service.user_id = 1
        after = await self.topology()
        assert after.public.coverage == "complete"
        assert after.public.impacts[0].customer_id == 1
        assert before.public.resource_fingerprint != after.public.resource_fingerprint
        with pytest.raises(ServiceConflict, match="exit_replacement_scope_changed"):
            async with self.sessions.begin() as session:
                await confirm_replacement(
                    session, self.panel, service_id=self.service.id, actor_id=1, body=body
                )
        async with self.sessions() as session:
            state = await self.state(session)
            assert state.order.request == request_before
            assert state.execution.replacement_progress == progress_before
            assert {
                row.id: row.evidence for row in await session.scalars(select(DedicatedExitAudit))
            } == audits_before

    async def test_archived_held_service_keeps_known_name_but_not_historical_owner(self) -> None:
        await self.tick()
        await self.attest()
        await self.confirm()
        for _ in range(4):
            await self.tick()
        async with self.sessions.begin() as session:
            state = await current_state(
                session, self.service.id, self.operation.id, allow_terminal=True
            )
            assert state.progress.stage == "completed"
            assert state.old_exit.hold_order_id == state.order.id
            state.service.user_id = None
            state.service.desired_status = "cancelled"
            state.connection.state = "revoked"
            state.connection.revoked_at = datetime.now(UTC)
            state.connection.sync_pending = False
            assert state.order.request_owner_id == 1
            old, new = state.old_exit, state.new_exit
        async with self.sessions() as session:
            topology = await read_replacement_topology(
                session, self.panel, old, new, service_id=self.reload_service.id
            )
            impacts = [
                item for item in topology.public.impacts if item.service_id == self.service.id
            ]
            assert impacts and all(item.customer_id is None for item in impacts)
            assert all(item.service_name == self.service.terms["name"] for item in impacts)
            assert any(item.group_ids == [old.squad_uuid] for item in impacts)
        async with self.sessions.begin() as session:
            archived = await session.get(UserService, self.service.id)
            assert archived
            archived.terms = {key: value for key, value in archived.terms.items() if key != "name"}
        async with self.sessions() as session:
            topology = await read_replacement_topology(
                session, self.panel, old, new, service_id=self.reload_service.id
            )
            impacts = [
                item for item in topology.public.impacts if item.service_id == self.service.id
            ]
            assert impacts and all(
                item.customer_id is None and item.service_name is None for item in impacts
            )

    async def test_pre_customer_fingerprints_are_rejected_even_with_empty_impacts(self) -> None:
        for empty in (False, True):
            with self.subTest(empty=empty):
                if empty:
                    async with self.sessions.begin() as session:
                        connection = await session.get(ServiceConnection, self.reload_service.id)
                        assert connection
                        connection.state = "revoked"
                current = await self.topology()
                assert current.public.coverage == "complete"
                assert bool(current.public.impacts) is not empty
                with patch(
                    "bot.services.service_exit_replacement_topology.digest",
                    side_effect=pre_customer_digest,
                ):
                    previous = await self.topology()
                assert previous.public.resource_fingerprint
                with pytest.raises(ServiceConflict, match="exit_replacement_scope_changed"):
                    current.require(previous.public.resource_fingerprint)

    async def test_labels_use_one_batch_query_independent_of_service_count(self) -> None:
        async def capture() -> list[str]:
            statements: list[str] = []

            def collect(
                _connection: object,
                _cursor: object,
                statement: str,
                _parameters: object,
                _context: object,
                _executemany: bool,
            ) -> None:
                statements.append(" ".join(statement.split()))

            event.listen(self.engine.sync_engine, "before_cursor_execute", collect)
            try:
                await self.topology()
            finally:
                event.remove(self.engine.sync_engine, "before_cursor_execute", collect)
            assert all(statement.startswith("SELECT") for statement in statements)
            labels = [
                statement
                for statement in statements
                if statement.startswith(
                    "SELECT user_services.id, users.user_id, user_services.terms"
                )
            ]
            assert len(labels) == 1
            assert "LEFT OUTER JOIN users" in labels[0] and "user_services.id IN" in labels[0]
            return statements

        before = await capture()
        for number in range(5):
            await self.add_reload_service(f"Additional service {number}")
        after = await capture()
        assert len(after) == len(before)
        assert len((await self.topology()).public.impacts) == 6
