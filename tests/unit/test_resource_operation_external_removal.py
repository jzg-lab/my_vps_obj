"""External removal closes uncertainty, not the original resource or service work."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

import pytest
from pydantic import ValidationError

from bot.app.web.admin_console_resource_operation_schemas import (
    ConsoleResourceOperationEvidenceBody,
    ConsoleResourceOperationOut,
    ConsoleResourceOperationRetryBody,
)
from bot.services.resource_operation_reconciliation import reconcile_resource_operation
from bot.services.resource_operation_runner import run_resource_operation
from bot.services.resource_operations import retry_resource_operation
from bot.services.resource_preview_panel import read_preview_inventory
from config.service_periods import as_utc
from db.dal.user_services_dal import ServiceConflict
from db.resource_operation_models import ResourceOperation
from tests.unit.test_admin_console_resource_preview import G1, H1, N1, N2
from tests.unit.test_resource_operations import (
    CREATED,
    ResourceOperationDatabaseCase,
    create_change,
)


def removal_body(**changes: object) -> dict[str, object]:
    return {
        "expected_version": 1,
        "attempt": 1,
        "result": "externally_removed",
        "target_id": H1,
        "evidence_digest": "a" * 64,
        "checked_at": datetime.now(UTC),
        "original_request_terminated": True,
        **changes,
    }


def test_external_removal_has_a_distinct_result_and_explicit_attestation() -> None:
    body = ConsoleResourceOperationEvidenceBody.model_validate(removal_body())
    assert body.result == "externally_removed"
    assert body.model_dump()["original_request_terminated"] is True


@pytest.mark.parametrize("attestation", [None, False, 1, "true"])
def test_removal_attestation_is_required_and_strict(attestation: object) -> None:
    with pytest.raises(ValidationError):
        ConsoleResourceOperationEvidenceBody.model_validate(
            removal_body(original_request_terminated=attestation)
        )


def test_external_removal_requires_an_explicit_uuid() -> None:
    with pytest.raises(ValidationError):
        ConsoleResourceOperationEvidenceBody.model_validate(removal_body(target_id=None))


def test_external_removal_cannot_omit_the_termination_attestation() -> None:
    body = removal_body()
    del body["original_request_terminated"]
    with pytest.raises(ValidationError):
        ConsoleResourceOperationEvidenceBody.model_validate(body)


@pytest.mark.parametrize("result", ["applied", "not_applied", "partial"])
def test_old_results_do_not_require_or_accept_the_removal_attestation(result: str) -> None:
    body = removal_body(result=result)
    del body["original_request_terminated"]
    assert ConsoleResourceOperationEvidenceBody.model_validate(body).result == result
    with pytest.raises(ValidationError):
        ConsoleResourceOperationEvidenceBody.model_validate(
            {**body, "original_request_terminated": True}
        )


class ExternalRemovalTests(ResourceOperationDatabaseCase):
    async def unknown_host(self) -> ConsoleResourceOperationOut:
        operation = await self.submit(
            {"operation": "host_update", "target_id": H1, "patch": {"port": 8443}}
        )
        self.lose_reply = True
        await run_resource_operation(self.sessions, self.panel, operation.id)
        result = await self.output(operation.id)
        assert result.status == "unknown" and result.gate_active
        return result

    def remove_target(self, kind: str, target: str) -> None:
        path, key = {
            "host": ("/hosts", None),
            "node": ("/nodes", None),
            "group": ("/internal-squads", "internalSquads"),
        }[kind]
        rows = self.rows(path, key)
        rows[:] = [row for row in rows if row["uuid"] != target]
        if key:
            envelope = self.payloads[path]
            assert isinstance(envelope, dict)
            envelope["total"] = len(rows)
        if kind == "node":
            for profile in self.rows("/config-profiles", "configProfiles"):
                members = profile["nodes"]
                assert isinstance(members, list)
                profile["nodes"] = [item for item in members if item["uuid"] != target]
            hosts = self.rows("/hosts")
            for host in hosts[:]:
                members = host["nodes"]
                assert isinstance(members, list)
                if target in members:
                    hosts.remove(host)

    async def close_removed(
        self,
        operation_id: str,
        target: str = H1,
        **overrides: object,
    ) -> ConsoleResourceOperationOut:
        result = await self.evidence(
            operation_id,
            "externally_removed",
            target=target,
            overrides={"original_request_terminated": True, **overrides},
        )
        stored = await self.output(operation_id)
        assert result.model_dump(exclude={"completed_at"}) == stored.model_dump(
            exclude={"completed_at"}
        )
        assert result.completed_at is not None and stored.completed_at is not None
        assert as_utc(result.completed_at) == as_utc(stored.completed_at)
        return stored

    async def test_removed_host_releases_unrelated_writes_and_activation_without_replay(
        self,
    ) -> None:
        existing_service, _, _ = await self.activate(key="existing-service")
        before = await self.unknown_host()
        assert before.preview.affected_service_ids == [existing_service.id]
        assert before.preview.affected_customer_ids == [1]
        self.remove_target("host", H1)
        with pytest.raises(ServiceConflict, match="resource_operation_in_progress"):
            await self.activate()
        with pytest.raises(ServiceConflict, match="resource_operation_in_progress"):
            await self.submit({"operation": "node_disable", "target_id": N2}, key="unrelated")
        await run_resource_operation(self.sessions, self.panel, before.id)
        self.writes.assert_awaited_once()

        closed = await self.close_removed(before.id)
        assert closed.preview.fingerprint is not None
        assert closed.status == "failed" and closed.error_code == "resource_target_removed"
        assert not closed.gate_active and not closed.can_retry
        assert not closed.requires_manual_reconciliation and closed.completed_at is not None
        assert closed.target_id == H1
        assert closed.change == before.change and closed.preview == before.preview
        assert closed.attempts == before.attempts and closed.version > before.version
        assert closed.observation is not None
        assert closed.observation.configuration == "missing" and closed.observation.values is None
        assert closed.observation.runtime == "unverified"
        evidence = closed.evidence[-1]
        assert evidence.result == "externally_removed" and evidence.actor_id == 1
        assert evidence.attempt == 1 and evidence.target_id == H1
        assert evidence.evidence_digest == "a" * 64
        assert evidence.model_dump()["original_request_terminated"] is True
        assert await self.output(before.id) == closed
        service, _, _ = await self.activate()
        assert service.id
        unrelated = await self.submit(
            {"operation": "node_disable", "target_id": N2}, key="unrelated"
        )
        assert unrelated.status == "pending"
        await run_resource_operation(self.sessions, self.panel, before.id)
        self.writes.assert_awaited_once()

    async def test_removed_terminal_cannot_retry_or_restore_even_if_uuid_reappears(self) -> None:
        before = await self.unknown_host()
        host = self.rows("/hosts")[0]
        self.remove_target("host", H1)
        closed = await self.close_removed(before.id)
        assert closed.preview.fingerprint is not None
        async with self.sessions.begin() as session:
            with pytest.raises(ServiceConflict, match="resource_retry_not_allowed"):
                await retry_resource_operation(
                    session,
                    self.panel,
                    closed.id,
                    ConsoleResourceOperationRetryBody(
                        expected_version=closed.version,
                        expected_fingerprint=closed.preview.fingerprint,
                    ),
                )
        self.rows("/hosts").append(host)
        with pytest.raises(ServiceConflict, match="resource_recovery_invalid"):
            await self.submit(
                {"operation": "host_update", "target_id": H1, "patch": {"port": 443}},
                key="forbidden-recovery",
                recovery_of=closed.id,
            )
        assert await self.output(closed.id) == closed
        self.writes.assert_awaited_once()

    async def test_missing_target_does_not_auto_close_or_accept_old_results(self) -> None:
        before = await self.unknown_host()
        self.remove_target("host", H1)
        async with self.sessions.begin() as session:
            result = await reconcile_resource_operation(
                session, self.panel, before.id, expected_version=before.version
            )
        assert result.operation.status == "unknown" and result.operation.gate_active
        for result_name in ("applied", "partial", "not_applied"):
            with pytest.raises(ServiceConflict, match="resource_evidence_invalid"):
                await self.evidence(before.id, result_name, target=H1)
        assert (await self.output(before.id)).gate_active

    async def test_existing_target_and_wrong_uuid_cannot_unlock(self) -> None:
        before = await self.unknown_host()
        with pytest.raises(ServiceConflict, match="resource_evidence_invalid"):
            await self.close_removed(before.id)
        self.remove_target("host", H1)
        with pytest.raises(ServiceConflict, match="resource_evidence_invalid"):
            await self.close_removed(before.id, target=str(UUID(int=999)))
        assert await self.output(before.id) == before

    async def test_attempt_version_and_bounded_evidence_are_checked_without_mutation(self) -> None:
        before = await self.unknown_host()
        self.remove_target("host", H1)
        async with self.sessions.begin() as session:
            row = await session.get(ResourceOperation, before.id)
            assert row is not None
            row.attempted_at = datetime.now(UTC) - timedelta(hours=1)
        for overrides, error in (
            ({"expected_version": before.version - 1}, "resource_operation_changed"),
            ({"attempt": 2}, "resource_evidence_invalid"),
            ({"checked_at": datetime.now(UTC) - timedelta(minutes=6)}, "resource_evidence_invalid"),
            ({"checked_at": datetime.now(UTC) - timedelta(hours=2)}, "resource_evidence_invalid"),
        ):
            with self.subTest(overrides=overrides):
                with pytest.raises(ServiceConflict, match=error):
                    await self.close_removed(before.id, **overrides)
                assert await self.output(before.id) == before

    async def test_partial_failed_unsupported_and_cached_inventory_cannot_prove_absence(
        self,
    ) -> None:
        before = await self.unknown_host()
        self.remove_target("host", H1)
        groups = self.payloads["/internal-squads"]
        assert isinstance(groups, dict)
        for replacement in (
            {**groups, "total": 4},
            RuntimeError("upstream unavailable"),
        ):
            self.payloads["/internal-squads"] = replacement
            with pytest.raises(ServiceConflict, match="resource_sources_incomplete"):
                await self.close_removed(before.id)
        self.payloads["/internal-squads"] = groups
        self.payloads["/system/metadata"] = {"version": "3.4.6"}
        with pytest.raises(ServiceConflict, match="resource_sources_incomplete"):
            await self.close_removed(before.id)
        self.payloads["/system/metadata"] = {"version": "3.4.5"}
        stale = await read_preview_inventory(self.panel)
        for source in stale.sources:
            source.observed_at = datetime.now(UTC) - timedelta(minutes=6)
        with (
            patch(
                "bot.services.resource_operation_reconciliation.read_preview_inventory",
                AsyncMock(return_value=stale),
            ),
            pytest.raises(ServiceConflict, match="resource_sources_incomplete"),
        ):
            await self.close_removed(before.id)
        assert await self.output(before.id) == before

    async def test_evidence_expiring_during_remote_reads_keeps_gate(self) -> None:
        before = await self.unknown_host()
        self.remove_target("host", H1)
        now = [datetime.now(UTC)]
        clock = Mock(wraps=datetime)
        clock.now.side_effect = lambda *_args: now[0]

        async def slow_inventory(*_args: object):
            inventory = await read_preview_inventory(self.panel)
            now[0] += timedelta(minutes=6)
            return inventory

        with (
            patch("bot.services.resource_operation_reconciliation.datetime", clock),
            patch(
                "bot.services.resource_operation_reconciliation.read_preview_inventory",
                side_effect=slow_inventory,
            ),
            pytest.raises(ServiceConflict, match="resource_evidence_invalid"),
        ):
            await self.close_removed(before.id, checked_at=now[0])
        assert await self.output(before.id) == before

    async def test_deleted_node_and_group_keep_their_original_target(self) -> None:
        cases: list[tuple[str, dict[str, object], str]] = [
            ("node", {"operation": "node_disable", "target_id": N1}, N1),
            ("group", {"operation": "group_inbounds", "target_id": G1, "inbound_ids": []}, G1),
        ]
        for kind, change, target in cases:
            with self.subTest(kind=kind):
                operation = await self.submit(change, key=kind)
                self.lose_reply = True
                await run_resource_operation(self.sessions, self.panel, operation.id)
                self.remove_target(kind, target)
                closed = await self.close_removed(operation.id, target)
                assert closed.target_id == target and closed.error_code == "resource_target_removed"
                assert not closed.gate_active

    async def test_marked_creation_survives_repeated_missing_readback_without_guessing(
        self,
    ) -> None:
        operation = await self.submit(create_change("host"))
        self.lose_reply = True
        await run_resource_operation(self.sessions, self.panel, operation.id)
        first = await self.output(operation.id)
        assert first.target_id is None and first.observation is not None
        assert first.observation.correlation == "creation_marker"
        metadata = self.payloads["/system/metadata"]
        self.payloads["/system/metadata"] = RuntimeError("readback failed")
        async with self.sessions.begin() as session:
            unavailable = await reconcile_resource_operation(
                session, self.panel, operation.id, expected_version=first.version
            )
        assert unavailable.operation.target_id == CREATED
        assert unavailable.operation.observation is not None
        assert unavailable.operation.observation.configuration == "unavailable"
        assert unavailable.operation.observation.correlation == "creation_marker"
        self.payloads["/system/metadata"] = metadata
        self.remove_target("host", CREATED)
        for _ in range(2):
            current = await self.output(operation.id)
            async with self.sessions.begin() as session:
                result = await reconcile_resource_operation(
                    session, self.panel, operation.id, expected_version=current.version
                )
            assert result.operation.target_id == CREATED
            assert result.operation.status == "unknown" and result.operation.gate_active
        closed = await self.close_removed(operation.id, CREATED)
        assert closed.target_id == CREATED and not closed.gate_active
        assert closed.observation is not None
        assert closed.observation.correlation == "creation_marker"

    async def test_unknown_group_creation_cannot_be_claimed_with_an_absent_uuid(self) -> None:
        operation = await self.submit(create_change("group"))
        self.lose_reply = True
        await run_resource_operation(self.sessions, self.panel, operation.id)
        before = await self.output(operation.id)
        self.remove_target("group", CREATED)
        with pytest.raises(ServiceConflict, match="resource_evidence_invalid"):
            await self.close_removed(operation.id, CREATED)
        assert await self.output(operation.id) == before

    async def test_unobserved_host_creation_cannot_be_claimed_after_marker_disappears(self) -> None:
        operation = await self.submit(create_change("host"))
        metadata = self.payloads["/system/metadata"]
        self.lose_reply = True

        async def lose_response_and_readback(method: str, path: str, **kwargs: object):
            try:
                return await self.write(method, path, **kwargs)
            finally:
                self.payloads["/system/metadata"] = RuntimeError("readback failed")

        self.writes.side_effect = lose_response_and_readback
        await run_resource_operation(self.sessions, self.panel, operation.id)
        before = await self.output(operation.id)
        assert before.target_id is None and before.observation is not None
        assert before.observation.correlation == "unresolved"
        self.payloads["/system/metadata"] = metadata
        self.remove_target("host", CREATED)
        with pytest.raises(ServiceConflict, match="resource_evidence_invalid"):
            await self.close_removed(operation.id, CREATED)
        assert await self.output(operation.id) == before

    async def test_create_receipt_can_identify_removed_target_without_a_successful_readback(
        self,
    ) -> None:
        operation = await self.submit(create_change("group"))

        async def accepted_without_readback(method: str, path: str, **kwargs: object):
            response = await self.write(method, path, **kwargs)
            self.payloads["/system/metadata"] = RuntimeError("readback failed")
            return response

        self.writes.side_effect = accepted_without_readback
        await run_resource_operation(self.sessions, self.panel, operation.id)
        before = await self.output(operation.id)
        assert before.status == "unknown" and before.target_id == CREATED
        self.payloads["/system/metadata"] = {"version": "3.4.5"}
        self.remove_target("group", CREATED)
        closed = await self.close_removed(operation.id, CREATED)
        assert not closed.gate_active and closed.error_code == "resource_target_removed"

    async def test_conflicting_creation_marker_cannot_be_closed_as_removed(self) -> None:
        operation = await self.submit(create_change("host"))
        self.lose_reply = True
        await run_resource_operation(self.sessions, self.panel, operation.id)
        before = await self.output(operation.id)
        created = next(host for host in self.rows("/hosts") if host["uuid"] == CREATED)
        created["uuid"] = str(UUID(int=999))
        with pytest.raises(ServiceConflict, match="resource_evidence_invalid"):
            await self.close_removed(operation.id, CREATED)
        assert await self.output(operation.id) == before
