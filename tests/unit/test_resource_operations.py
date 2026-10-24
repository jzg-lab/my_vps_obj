"""Real operation rows and runner; only the upstream transport is simulated."""

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from bot.app.web.admin_console_resource_operation_schemas import (
    ConsoleResourceOperationEvidenceBody,
    ConsoleResourceOperationOut,
    ConsoleResourceOperationRetryBody,
    ConsoleResourceOperationStartBody,
)
from bot.services.resource_operation_panel import creation_marker
from bot.services.resource_operation_reconciliation import (
    accept_resource_evidence,
    reconcile_resource_operation,
)
from bot.services.resource_operation_runner import run_pending_resource_operation
from bot.services.resource_operations import (
    CHANGE_ADAPTER,
    operation_output,
    retry_resource_operation,
    start_resource_operation,
)
from bot.services.resource_preview_read import stable_resource_preview
from bot.services.service_change_sync import ServiceChangeWorker
from config.settings import Settings
from db.dal.user_services_dal import ServiceConflict
from db.resource_operation_models import ResourceOperation
from tests.unit.test_admin_console_resource_preview import (
    G1,
    H1,
    I1,
    N1,
    P1,
    SECRET,
    inventory_fixture,
    panel_fixture,
)
from tests.unit.test_user_services import ServiceDatabaseTestCase

CREATED = str(UUID(int=901))


def live_settings() -> Settings:
    return Settings(
        POSTGRES_USER="test",
        POSTGRES_PASSWORD="test",
        BOT_TOKEN="1234567890:AA_secret_bot_token_value",
        PANEL_WRITE_MODE="live",
        _env_file=None,
    )


def create_change(kind: str) -> dict[str, object]:
    if kind == "node":
        return {
            "operation": "node_create",
            "name": "New node",
            "address": "192.0.2.42",
            "port": 2222,
            "profile_id": P1,
            "inbound_ids": [I1],
        }
    if kind == "group":
        return {"operation": "group_create", "name": "New group", "inbound_ids": [I1]}
    return {
        "operation": "host_create",
        "name": "New host",
        "address": "192.0.2.43",
        "port": 443,
        "profile_id": P1,
        "inbound_id": I1,
        "node_ids": [N1],
        "is_disabled": False,
        "is_hidden": False,
        "group_mode": "ALLOW_ONLY",
        "group_ids": [G1],
    }


class ResourceOperationDatabaseCase(ServiceDatabaseTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.payloads = inventory_fixture()
        self.panel, self.reads = panel_fixture(self.payloads)
        self.panel.settings = live_settings()
        self.writes = AsyncMock(side_effect=self.write)
        self.panel._request_once = self.writes
        self.lose_reply = False
        self.partial_host = False
        self.reject = False

    def rows(self, path: str, key: str | None = None) -> list[dict[str, object]]:
        value = self.payloads[path]
        if key is not None:
            assert isinstance(value, dict)
            value = value[key]
        assert isinstance(value, list) and all(isinstance(row, dict) for row in value)
        return cast(list[dict[str, object]], value)

    async def write(self, method: str, path: str, **kwargs: object) -> dict[str, object]:
        assert kwargs["preserve_http_status"] is True
        assert kwargs["log_full_response"] is False
        if self.reject:
            return {"status_code": 403, "error": True, "details": SECRET}
        raw = kwargs.get("json", {})
        assert isinstance(raw, dict)
        data = cast(dict[str, object], raw)
        target: object = data.get("uuid", CREATED)
        status = 201 if method == "POST" else 200
        if path.startswith("/nodes/"):
            target = path.split("/")[2]
            node = next(row for row in self.rows("/nodes") if row["uuid"] == target)
            action = path.rsplit("/", 1)[1]
            if action != "restart":
                node["isDisabled"] = action == "disable"
            status = 202 if action == "restart" else 200
        elif path == "/nodes":
            profile = data["configProfile"]
            assert isinstance(profile, dict) and isinstance(profile["activeInbounds"], list)
            self.rows("/nodes").append(
                {
                    **data,
                    "uuid": target,
                    "isDisabled": False,
                    "configProfile": {
                        "activeConfigProfileUuid": profile["activeConfigProfileUuid"],
                        "activeInbounds": [{"uuid": item} for item in profile["activeInbounds"]],
                    },
                }
            )
            for row in self.rows("/config-profiles", "configProfiles"):
                if row["uuid"] == profile["activeConfigProfileUuid"]:
                    assert isinstance(row["nodes"], list)
                    row["nodes"].append({"uuid": target})
        elif path == "/internal-squads":
            groups = self.rows(path, "internalSquads")
            if method == "POST":
                groups.append({"uuid": target, "name": data["name"], "inbounds": []})
                envelope = self.payloads[path]
                assert isinstance(envelope, dict)
                envelope["total"] = len(groups)
            group = next(row for row in groups if row["uuid"] == target)
            assert isinstance(data["inbounds"], list)
            group["inbounds"] = [{"uuid": item} for item in data["inbounds"]]
        elif path == "/hosts":
            if method == "POST":
                self.rows(path).append({**data, "uuid": target})
            else:
                host = next(row for row in self.rows(path) if row["uuid"] == target)
                host.update(
                    {
                        key: value
                        for key, value in data.items()
                        if not self.partial_host or key == "address"
                    }
                )
        else:
            raise AssertionError(path)
        if self.lose_reply:
            raise TimeoutError(SECRET)
        return {"status_code": status, "response": {"uuid": target, "privateKey": SECRET}}

    async def submit(
        self,
        change: dict[str, object] | None = None,
        *,
        key: str = "resource-request",
        recovery_of: str | None = None,
    ) -> ConsoleResourceOperationOut:
        typed = CHANGE_ADAPTER.validate_python(
            change or {"operation": "node_disable", "target_id": N1}
        )
        async with self.sessions.begin() as session:
            preview, _ = await stable_resource_preview(session, self.panel, typed)
            assert preview.coverage == "complete", preview.blockers
            assert preview.fingerprint is not None
            result = await start_resource_operation(
                session,
                self.panel,
                actor_id=1,
                body=ConsoleResourceOperationStartBody(
                    change=typed,
                    expected_fingerprint=preview.fingerprint,
                    idempotency_key=key,
                    recovery_of=recovery_of,
                ),
            )
            return result.operation

    async def output(self, operation_id: str) -> ConsoleResourceOperationOut:
        async with self.sessions() as session:
            row = await session.get(ResourceOperation, operation_id)
            assert row is not None
            return operation_output(row).operation

    async def evidence(
        self,
        operation_id: str,
        result: str,
        *,
        target: str | None = None,
        overrides: dict[str, object] | None = None,
    ) -> ConsoleResourceOperationOut:
        current = await self.output(operation_id)
        body = ConsoleResourceOperationEvidenceBody.model_validate(
            {
                "expected_version": current.version,
                "attempt": len(current.attempts),
                "result": result,
                "target_id": target,
                "evidence_digest": "a" * 64,
                "checked_at": datetime.now(UTC),
                **(overrides or {}),
            }
        )
        async with self.sessions.begin() as session:
            accepted = await accept_resource_evidence(
                session, self.panel, operation_id, actor_id=1, body=body
            )
            return accepted.operation


class ResourceOperationTests(ResourceOperationDatabaseCase):
    async def test_worker_executes_pending_and_duplicate_submission_never_resends(self) -> None:
        first = await self.submit()
        duplicate = await self.submit()
        assert duplicate.id == first.id and first.status == "pending" and not first.attempts
        self.writes.assert_not_awaited()
        worker = ServiceChangeWorker(self.sessions, self.panel)
        await worker.tick()
        await worker.tick()
        output = await self.output(first.id)
        assert output.status == "succeeded" and not output.gate_active
        assert len(output.attempts) == 1 and output.attempts[0].receipt == "accepted"
        assert output.observation is not None and output.observation.runtime == "unverified"
        assert SECRET not in output.model_dump_json()
        self.writes.assert_awaited_once()

    async def test_stale_or_partial_source_is_rejected_before_a_wire_attempt(self) -> None:
        operation = await self.submit()
        self.rows("/nodes")[0]["name"] = "Changed after confirmation"
        await run_pending_resource_operation(self.sessions, self.panel)
        output = await self.output(operation.id)
        assert output.status == "failed" and output.error_code == "resource_preview_changed"
        assert not output.attempts and not output.gate_active
        self.writes.assert_not_awaited()
        second = await self.submit(key="second")
        self.payloads["/hosts"] = RuntimeError(SECRET)
        await run_pending_resource_operation(self.sessions, self.panel)
        output = await self.output(second.id)
        assert output.error_code == "resource_sources_incomplete" and not output.attempts

    async def test_lost_response_keeps_gate_and_requires_attempt_scoped_evidence(self) -> None:
        operation = await self.submit()
        self.lose_reply = True
        await run_pending_resource_operation(self.sessions, self.panel)
        for _ in range(2):
            await run_pending_resource_operation(self.sessions, self.panel)
        current = await self.output(operation.id)
        assert (
            current.status == "unknown"
            and current.gate_active
            and current.requires_manual_reconciliation
        )
        self.writes.assert_awaited_once()
        async with self.sessions.begin() as session:
            refreshed = await reconcile_resource_operation(
                session, self.panel, operation.id, expected_version=current.version
            )
        assert refreshed.operation.status == "unknown" and refreshed.operation.gate_active
        invalid_evidence: list[dict[str, object]] = [
            {"attempt": 2},
            {"expected_version": current.version},
            {"checked_at": datetime.now(UTC) - timedelta(days=1)},
        ]
        for overrides in invalid_evidence:
            with pytest.raises(ServiceConflict):
                await self.evidence(operation.id, "applied", overrides=overrides)
        accepted = await self.evidence(operation.id, "applied")
        assert accepted.status == "succeeded" and not accepted.gate_active
        assert accepted.evidence[0].provenance == "administrator_attestation"

    async def test_rejected_request_requires_explicit_same_intent_retry(self) -> None:
        operation = await self.submit()
        self.reject = True
        await run_pending_resource_operation(self.sessions, self.panel)
        current = await self.output(operation.id)
        assert current.status == "failed" and current.can_retry
        await run_pending_resource_operation(self.sessions, self.panel)
        self.writes.assert_awaited_once()
        async with self.sessions.begin() as session:
            await retry_resource_operation(
                session,
                self.panel,
                operation.id,
                ConsoleResourceOperationRetryBody(
                    expected_version=current.version,
                    expected_fingerprint=operation.preview.fingerprint,
                ),
            )
        self.reject = False
        await run_pending_resource_operation(self.sessions, self.panel)
        assert len((await self.output(operation.id)).attempts) == 2

    async def test_host_partial_requires_explicit_resolution_then_new_preview_restore(self) -> None:
        operation = await self.submit(
            {
                "operation": "host_update",
                "target_id": H1,
                "patch": {"address": "192.0.2.99", "port": 8443},
            }
        )
        self.partial_host = True
        await run_pending_resource_operation(self.sessions, self.panel)
        current = await self.output(operation.id)
        assert current.status == "unknown" and current.error_code == "resource_partial_write"
        with pytest.raises(ServiceConflict, match="evidence_invalid"):
            await self.evidence(operation.id, "applied")
        await self.evidence(operation.id, "partial")
        restore = await self.submit(
            {
                "operation": "host_update",
                "target_id": H1,
                "patch": {"address": "192.0.2.1", "port": 443},
            },
            key="restore",
            recovery_of=operation.id,
        )
        assert restore.recovery_of == operation.id and restore.id != operation.id
        self.partial_host = False
        await run_pending_resource_operation(self.sessions, self.panel)
        assert (await self.output(restore.id)).status == "succeeded"

    async def test_create_node_marker_and_baseline_survive_lost_response_without_replay(
        self,
    ) -> None:
        operation = await self.submit(create_change("node"))
        self.lose_reply = True
        await run_pending_resource_operation(self.sessions, self.panel)
        current = await self.output(operation.id)
        assert current.status == "unknown" and current.observation is not None
        assert current.observation.correlation == "creation_marker"
        assert current.observation.configuration == "matched"
        async with self.sessions.begin() as session:
            refreshed = await reconcile_resource_operation(
                session, self.panel, operation.id, expected_version=current.version
            )
        assert refreshed.operation.status == "unknown"
        next_view = refreshed.operation
        async with self.sessions.begin() as session:
            refreshed = await reconcile_resource_operation(
                session, self.panel, operation.id, expected_version=next_view.version
            )
        assert refreshed.operation.observation is not None
        assert refreshed.operation.observation.correlation == "creation_marker"
        with pytest.raises(ServiceConflict, match="evidence_invalid"):
            await self.evidence(operation.id, "applied", target=N1)
        final = await self.evidence(operation.id, "applied", target=CREATED)
        assert final.status == "succeeded"
        self.writes.assert_awaited_once()

    async def test_group_creation_is_not_claimed_by_name_and_needs_explicit_id(self) -> None:
        operation = await self.submit(create_change("group"))
        self.lose_reply = True
        await run_pending_resource_operation(self.sessions, self.panel)
        current = await self.output(operation.id)
        assert current.observation is not None
        assert current.observation.correlation == "unresolved" and current.target_id is None
        assert current.observation.values is None and current.gate_active
        await run_pending_resource_operation(self.sessions, self.panel)
        self.writes.assert_awaited_once()
        with pytest.raises(ServiceConflict, match="evidence_invalid"):
            await self.evidence(operation.id, "applied", target=G1)
        assert (await self.evidence(operation.id, "applied", target=CREATED)).status == "succeeded"

    async def test_ambiguous_creation_markers_keep_gate_until_unique_identity_is_restored(
        self,
    ) -> None:
        operation = await self.submit(create_change("host"))
        self.lose_reply = True
        await run_pending_resource_operation(self.sessions, self.panel)
        before = await self.output(operation.id)
        created = next(row for row in self.rows("/hosts") if row["uuid"] == CREATED)
        duplicate = {**created, "uuid": str(UUID(int=902))}
        self.rows("/hosts").append(duplicate)
        for result in ("not_applied", "partial", "applied"):
            with pytest.raises(ServiceConflict, match="resource_evidence_invalid"):
                await self.evidence(operation.id, result, target=CREATED)
        after = await self.output(operation.id)
        assert after == before and after.gate_active and not after.can_retry
        self.rows("/hosts").remove(duplicate)
        accepted = await self.evidence(operation.id, "applied", target=CREATED)
        assert accepted.status == "succeeded" and not accepted.gate_active
        assert accepted.target_id == CREATED
        assert accepted.evidence[0].provenance == "administrator_attestation"
        self.writes.assert_awaited_once()

    async def test_marked_creation_can_be_explicitly_closed_as_partial(self) -> None:
        operation = await self.submit(create_change("host"))
        self.lose_reply = True
        await run_pending_resource_operation(self.sessions, self.panel)
        created = next(row for row in self.rows("/hosts") if row["uuid"] == CREATED)
        created["port"] = 8443
        with pytest.raises(ServiceConflict, match="resource_evidence_invalid"):
            await self.evidence(operation.id, "applied", target=CREATED)
        closed = await self.evidence(operation.id, "partial", target=CREATED)
        assert closed.status == "failed" and not closed.gate_active and not closed.can_retry
        assert closed.target_id == CREATED and closed.error_code == "resource_partial_write"
        assert closed.observation is not None and closed.observation.configuration == "different"
        assert closed.evidence[0].result == "partial"
        self.writes.assert_awaited_once()

    async def test_lost_marker_cannot_reassign_the_previously_observed_identity(self) -> None:
        operation = await self.submit(create_change("host"))
        self.lose_reply = True
        await run_pending_resource_operation(self.sessions, self.panel)
        before = await self.output(operation.id)
        assert before.target_id is None and before.observation is not None
        assert before.observation.correlation == "creation_marker"
        created = next(row for row in self.rows("/hosts") if row["uuid"] == CREATED)
        created["tags"] = []
        for result in ("partial", "applied"):
            with pytest.raises(ServiceConflict, match="resource_evidence_invalid"):
                await self.evidence(operation.id, result, target=CREATED)
        self.rows("/hosts").remove(created)
        with pytest.raises(ServiceConflict, match="resource_evidence_invalid"):
            await self.evidence(operation.id, "not_applied", target=str(UUID(int=902)))
        assert await self.output(operation.id) == before
        self.writes.assert_awaited_once()

    async def test_not_applied_requires_no_marker_including_baseline_or_ambiguous_matches(
        self,
    ) -> None:
        operation = await self.submit(create_change("host"))
        self.writes.side_effect = TimeoutError(SECRET)
        await run_pending_resource_operation(self.sessions, self.panel)
        before = await self.output(operation.id)
        assert before.observation is not None and before.observation.values is None
        baseline = next(row for row in self.rows("/hosts") if row["uuid"] == H1)
        marker = creation_marker(operation.id, host=True)
        tags = baseline.get("tags", [])
        baseline["tags"] = [marker]
        with pytest.raises(ServiceConflict, match="resource_evidence_invalid"):
            await self.evidence(operation.id, "not_applied")
        baseline["tags"] = tags
        candidates = [
            {**baseline, "uuid": target, "tags": [marker]}
            for target in (CREATED, str(UUID(int=902)))
        ]
        self.rows("/hosts").extend(candidates)
        with pytest.raises(ServiceConflict, match="resource_evidence_invalid"):
            await self.evidence(operation.id, "not_applied")
        assert await self.output(operation.id) == before
        for candidate in candidates:
            self.rows("/hosts").remove(candidate)
        closed = await self.evidence(operation.id, "not_applied")
        assert closed.status == "failed" and not closed.gate_active and closed.can_retry
        assert closed.error_code == "resource_write_rejected"
        self.writes.assert_awaited_once()

    async def test_create_host_marker_and_complete_existing_service_impact(self) -> None:
        service, _, _ = await self.activate()
        operation = await self.submit(create_change("host"))
        assert operation.preview.affected_customer_ids == [1]
        assert operation.preview.affected_service_ids == [service.id]
        await run_pending_resource_operation(self.sessions, self.panel)
        output = await self.output(operation.id)
        assert output.status == "succeeded"
        created = next(row for row in self.rows("/hosts") if row["uuid"] == CREATED)
        assert created["tags"] == [creation_marker(operation.id, host=True)]

    async def test_dry_run_and_unreviewed_panel_never_create_an_operation(self) -> None:
        self.panel.settings.PANEL_WRITE_MODE = "dry_run"
        with pytest.raises(ServiceConflict, match="resource_dry_run"):
            await self.submit()
        self.writes.assert_not_awaited()
        self.panel.settings.PANEL_WRITE_MODE = "live"
        typed = CHANGE_ADAPTER.validate_python({"operation": "node_disable", "target_id": N1})
        self.payloads["/system/metadata"] = {"version": "3.4.6"}
        async with self.sessions.begin() as session:
            with pytest.raises(ServiceConflict, match="resource_panel_unsupported"):
                await start_resource_operation(
                    session,
                    self.panel,
                    actor_id=1,
                    body=ConsoleResourceOperationStartBody(
                        change=typed, expected_fingerprint="a" * 64, idempotency_key="unsupported"
                    ),
                )

    async def test_restart_receipt_is_not_a_runtime_proof_and_false_may_noop(self) -> None:
        operation = await self.submit(
            {"operation": "node_restart", "target_id": N1, "force_restart": False}
        )
        await run_pending_resource_operation(self.sessions, self.panel)
        result = await self.output(operation.id)
        assert result.status == "succeeded" and result.observation is not None
        assert result.observation.restart == "may_be_noop"
        assert result.observation.runtime == "unverified"
