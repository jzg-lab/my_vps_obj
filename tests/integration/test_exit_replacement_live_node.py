"""UC2-EXIT-LOCAL-DATA: F05/F07, UA-12/13/14/15; internal egress only.

The default is an offline skip, before environment, DB, Docker or network access.
The main window owns live execution. Use the existing LiveNode environment plus
QA_SERVICE_OPERATIONS_ADAPTER_DIR=/tmp/my-vpn-uc2-r3-repo-rebuild/artifacts.
Stop/candidate attestations use measured machine evidence through the real DAL;
this is not a browser/HTTP acceptance test or proof of public dedicated IPs.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import suppress
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.app.web.admin_console_exit_replacement_schemas import (
    ConsoleExitReplacementConfirmBody,
    ConsoleExitReplacementOut,
    ConsoleExitReplacementQuery,
    ConsoleExitReplacementStartBody,
    ExitReplacementReclaimBody,
)
from bot.services.resource_preview_panel import digest
from bot.services.service_delivery import deliver_service_identity
from bot.services.service_exit_replacement import (
    current_state,
    observe_identity,
    observed_groups,
    require_stopped,
    run_exit_replacement,
)
from bot.services.service_exit_replacement_commands import confirm_replacement, start_replacement
from bot.services.service_exit_replacement_evidence import scoped_exit_evidence
from bot.services.service_exit_replacement_view import replacement_view, stable_topology
from bot.services.service_provisioning import provision_service_identity
from bot.services.service_usage_sync import synchronize_service_usage, usage_counters
from config.service_exit_replacement import ReplacementCandidateEvidence, ReplacementStopEvidence
from config.service_periods import as_utc
from db.auth_models import AccountRole
from db.dal.service_delivery_dal import record_exit_evidence, request_service_delivery
from db.dal.service_exit_replacement_dal import (
    accept_replacement_stop,
    verify_replacement_candidate,
)
from db.dal.user_services_dal import activate_service, create_exit, save_plan
from db.service_models import DedicatedExit, ServiceOrder
from tests.integration.test_service_operations_live_node import LiveScenario
from tests.integration.test_user_services_postgres import DATABASE_URL as SCENARIO_DATABASE_URL
from tests.integration.test_user_services_postgres import scenario
from tests.qa.test_remnawave_panel_contract import _panel_service
from tests.support.exit_replacement_live_node import (
    SCOPE,
    ExitNode,
    cleanup_pair,
    ledger_totals,
    require_exit_environment,
    retained_client,
)
from tests.support.service_operations_live_node import eventually, private_json
from tests.unit.test_user_services import sample_terms


class ExitScenario(LiveScenario):
    old: ExitNode
    target: ExitNode
    old_exit: str
    new_exit: str
    operation_id: str
    old_port: int
    old_client: dict[str, object]

    def report(self, name: str, values: dict[str, object]) -> str:
        report = {"scope": SCOPE, **values}
        private_json(self.fixture.directory / (name + ".json"), report)
        self.fixture.evidence[name] = report
        private_json(self.fixture.directory / "report.json", self.fixture.evidence)
        evidence_hash: str = digest(report)
        return evidence_hash

    async def prepare_dedicated(self) -> None:
        probe = await self.old.probe_exit()
        self.report("initial-old-egress", probe)
        old_ip, new_ip = await self.old.internal_ip(), await self.target.internal_ip()
        assert old_ip != new_ip, "Two actual internal exits are mandatory"
        self.report(
            "paths",
            {
                "old": {"node": self.old.node_id, "group": self.old.squad_id, "ip": old_ip},
                "target": {
                    "node": self.target.node_id,
                    "group": self.target.squad_id,
                    "ip": new_ip,
                },
                "origin_ip": self.old.origin_ip,
                "public_dedicated_verified": False,
            },
        )
        async with self.factory.begin() as session:
            session.add(AccountRole(user_id=2, role="admin"))
            resources = []
            for node, address in ((self.old, old_ip), (self.target, new_ip)):
                resource = await create_exit(
                    session,
                    label=node.prefix,
                    ip_address=address,
                    resource_pool=self.old.prefix,
                    squad_uuid=node.squad_id,
                )
                resources.append(resource.id)
            self.old_exit, self.new_exit = resources
            plan = await save_plan(
                session,
                terms=sample_terms(
                    resource_type="dedicated",
                    resource_pool=self.old.prefix,
                    squad_uuids=[],
                    quota_bytes=64 * 1024 * 1024,
                ),
                enabled=True,
                actor_id=2,
            )
            service, _, duplicate = await activate_service(
                session,
                user_id=1,
                actor_id=2,
                plan_id=plan.id,
                expected_revision=1,
                idempotency_key="local-exit-service",
                exit_id=self.old_exit,
            )
            assert not duplicate
            self.services.append(service.id)
            self.old.remember_service(service.id)
            # Either path may own the identity after a lost response; clean it before groups.
            self.target.remember_service(service.id)
            old = await session.get(DedicatedExit, self.old_exit)
            assert old is not None
            await record_exit_evidence(
                session,
                exit_id=old.id,
                actor_id=2,
                action="verify",
                command={
                    "service_id": service.id,
                    "expected_revision": old.revision,
                    "idempotency_key": "measured-internal-old",
                    "checked_at": probe["checked_at"],
                    "observed_ip": old_ip,
                    "fixed": True,
                    "exclusive": True,
                    "scope": SCOPE,
                    "provenance": "machine",
                    "evidence_digest": digest(probe),
                },
            )
        await provision_service_identity(self.sessions, self.services[0], self.panel)
        await synchronize_service_usage(self.sessions, self.services[0], self.panel)
        async with self.factory.begin() as session:
            await request_service_delivery(
                session,
                service_id=self.services[0],
                user_id=1,
                actor_id=2,
                expected_revision=1,
                idempotency_key="deliver-local-exit",
            )
        await deliver_service_identity(self.sessions, self.services[0], self.panel)
        service, connection = await self.saved(0)
        remote = await self.remote(0)
        assert connection.state == "ready" and not connection.sync_pending
        assert service.used_bytes == 0 and remote["status"] == "ACTIVE"
        assert observed_groups(remote) == {self.old.squad_id}
        assert usage_counters(remote) == (0, 0)
        self.old_port = await self.old.client(str(remote["vlessUuid"]))
        self.old_client = retained_client(self.old, self.old_port, str(remote["vlessUuid"]))
        self.report("retained-old-service-client", self.old_client)

    async def rights(self) -> dict[str, object]:
        service, connection = await self.saved(0)
        remote = await self.remote(0)
        assert connection.panel_user_uuid
        return {
            "service_id": service.id,
            "owner": service.user_id,
            "plan_id": service.plan_id,
            "plan_revision": service.plan_revision,
            "quota_revision": service.quota_revision,
            "terms": service.terms,
            "quota_bytes": service.quota_bytes,
            "starts_at": as_utc(service.starts_at).isoformat(),
            "expires_at": as_utc(service.expires_at).isoformat(),
            "cycle_started_at": service.cycle_started_at,
            "cycle_ends_at": service.cycle_ends_at,
            "desired_status": service.desired_status,
            "connection_username": connection.username,
            "panel_identity_sha256": digest(connection.panel_user_uuid),
            "vless_identity_sha256": digest(remote["vlessUuid"]),
            "remote_limit": remote["trafficLimitBytes"],
            "remote_expiry": remote["expireAt"],
            "remote_strategy": remote["trafficLimitStrategy"],
        }

    async def meter(self, expected: int) -> dict[str, object]:
        async def reconciled() -> bool:
            await synchronize_service_usage(self.sessions, self.services[0], self.panel)
            service, connection = await self.saved(0)
            assert connection.usage_error is None
            assert connection.cycle_cutover_bytes is None
            assert (connection.usage_lifetime_offset or 0) == 0
            assert connection.usage_raw_bytes is not None
            assert service.used_bytes <= expected and connection.usage_raw_bytes <= expected, (
                "Meter exceeds independently accounted payload; cannot attest complete usage"
            )
            matches: bool = (
                service.used_bytes
                == connection.usage_total_bytes
                == connection.usage_raw_bytes
                == expected
            )
            return matches

        await eventually(reconciled)
        service, connection = await self.saved(0)
        remote = await self.remote(0)
        assert usage_counters(remote) == (expected, expected)
        assert service.last_usage_sync_at is not None
        return {
            "usage_total_bytes": connection.usage_total_bytes,
            "usage_raw_bytes": connection.usage_raw_bytes,
            "usage_lifetime_offset": connection.usage_lifetime_offset or 0,
            "stored_usage_lifetime_offset": connection.usage_lifetime_offset,
            "used_bytes": service.used_bytes,
            "observed_at": as_utc(service.last_usage_sync_at).isoformat(),
            "remote_raw_bytes": usage_counters(remote)[0],
            "remote_lifetime_bytes": usage_counters(remote)[1],
            "expected_business_bytes": expected,
            "method": "closed-origin-ledger plus fully-read client payload; exact up+down",
        }

    async def view(self) -> ConsoleExitReplacementOut:
        async with self.factory() as session:
            result = await replacement_view(
                session,
                self.panel,
                self.services[0],
                ConsoleExitReplacementQuery(operation_id=self.operation_id),
            )
            assert result.replacement is not None
            return result.replacement

    async def tick(self) -> None:
        await run_exit_replacement(self.sessions, self.services[0], self.panel)
        view = await self.view()
        self.fixture.evidence["last_progress"] = view.progress.model_dump(mode="json")
        self.fixture.evidence["last_operation"] = {
            "status": view.operation.status,
            "error_code": view.operation.error_code,
        }
        assert view.operation.status not in {"failed", "unknown"}, "Real runner blocked: " + str(
            view.operation.error_code
        )

    async def replace(self) -> None:
        token = self.services[0]
        port = self.old_port
        before_rights = await self.rights()
        for _ in range(2):
            await self.old.exchange(port, token, b"P")
        await self.old.exchange(port, token, b"U", 4096)
        await self.old.exchange(port, token, b"D", 16384)
        # Drain a finite payload, then leave the same established flow open. No in-flight
        # payload ambiguity is allowed when claiming an exact final accounting cut.
        _, reader, writer = await self.old.exchange(port, token, b"H", 8192)
        try:
            assert not reader.at_eof()
            self.report(
                "before-replacement-usage",
                await self.meter(5 * 21 + 4096 + 2 * 16 + 1 + 16384 + 8192),
            )
            held = await self.old.ledger(token)
            assert len(held) == 5 and held[-1]["op"] == "H" and held[-1]["closed"] is False
            assert not reader.at_eof(), "Original flow ended before stop_old"
            async with self.factory.begin() as session:
                preview = await replacement_view(
                    session,
                    self.panel,
                    token,
                    ConsoleExitReplacementQuery(candidate_exit_id=self.new_exit),
                )
                draft = preview.draft
                self.report(
                    "replacement-preflight",
                    {
                        "coverage": draft.coverage if draft else None,
                        "block_reasons": draft.block_reasons if draft else [],
                        "allowed_to_start": draft.allowed_to_start if draft else False,
                    },
                )
                assert draft and draft.allowed_to_start, "Real topology blocks local replacement"
                assert draft.resource_fingerprint
                started = await start_replacement(
                    session,
                    self.panel,
                    service_id=token,
                    actor_id=2,
                    body=ConsoleExitReplacementStartBody(
                        user_id=1,
                        expected_revision=preview.service_revision,
                        old_exit_id=self.old_exit,
                        new_exit_id=self.new_exit,
                        expected_old_exit_revision=draft.old_exit.revision,
                        expected_new_exit_revision=draft.candidate_exit.revision,
                        expected_resource_fingerprint=draft.resource_fingerprint,
                        reason="Isolated internal exit replacement acceptance",
                        idempotency_key="replace-internal-exit",
                    ),
                )
                self.operation_id = started.replacement.operation.id
                assert not started.duplicate
                assert started.replacement.current_exit_id == self.old_exit
                assert started.replacement.candidate_exit.hold_order_id is not None
            await self.tick()
            remote = await self.remote(0)
            require_stopped(remote)
            assert await asyncio.wait_for(reader.read(1), 4) == b"", (
                "stop_old did not close the original connection"
            )
            stopped_at = datetime.now(UTC)
            probes = await self.old.rejected(port, token)
            stop_digest = self.report(
                "old-stop",
                {
                    "observed_at": stopped_at.isoformat(),
                    "original_flow": "eof",
                    "flow_kind": "finite_payload_drained_then_held_open",
                    "probes": probes,
                },
            )
        finally:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()

        rows = await self.old.ledger(token)
        assert [row["op"] for row in rows] == ["P", "P", "U", "D", "H"]
        up, down = ledger_totals(rows, expected_peer=await self.old.internal_ip())
        assert (up, down) == (5 * 21 + 4096, 2 * 16 + 1 + 16384 + 8192)
        old_total = up + down
        accounting = await self.meter(old_total)
        usage_digest = self.report("old-usage", {**accounting, "origin_ledger": rows})
        async with self.factory.begin() as session:
            state = await current_state(session, token, self.operation_id)
            topology = await stable_topology(session, self.panel, state)
            topology.require(state.request.resource_fingerprint)
            require_stopped(await observe_identity(self.panel, state))
            assert state.connection.usage_total_bytes == old_total
            assert state.service.last_usage_sync_at is not None
            await accept_replacement_stop(
                session,
                state,
                actor_id=2,
                expected_version=state.progress.version,
                idempotency_key="measured-old-stop",
                evidence=ReplacementStopEvidence(
                    resource_fingerprint=state.request.resource_fingerprint,
                    stopped_at=stopped_at,
                    usage_observed_at=as_utc(state.service.last_usage_sync_at),
                    stop_provenance="machine",
                    usage_provenance="machine",
                    stop_report_digest=stop_digest,
                    usage_report_digest=usage_digest,
                    authorization_removed=True,
                    connections_stopped=True,
                    old_config_rejected=True,
                    usage_total_bytes=old_total,
                    usage_raw_bytes=old_total,
                    usage_lifetime_offset=0,
                ),
            )

        probe = await self.target.probe_exit()
        candidate_digest = self.report("candidate-egress", probe)
        async with self.factory.begin() as session:
            state = await current_state(session, token, self.operation_id)
            topology = await stable_topology(session, self.panel, state)
            topology.require(state.request.resource_fingerprint)
            assert topology.new_scope is not None
            assert (
                state.new_exit.service_id is None and state.new_exit.hold_order_id == state.order.id
            )
            await verify_replacement_candidate(
                session,
                state,
                actor_id=2,
                expected_version=state.progress.version,
                idempotency_key="measured-internal-candidate",
                evidence=ReplacementCandidateEvidence(
                    resource_fingerprint=state.request.resource_fingerprint,
                    checked_at=datetime.fromisoformat(str(probe["checked_at"])),
                    observed_ip=await self.target.internal_ip(),
                    provenance="machine",
                    report_digest=candidate_digest,
                    fixed=True,
                    exclusive=True,
                ),
            )
        view = await self.view()
        assert view.old_stop and view.old_stop.valid and view.old_stop.provenance == "machine"
        assert view.candidate_verification and view.candidate_verification.provenance == "machine"
        assert "confirm" in view.allowed_actions and not view.restore_requested
        async with self.factory.begin() as session:
            state = await current_state(session, token, self.operation_id)
            assert state.progress.stop_audit_id and state.progress.verification_audit_id
            accepted = await confirm_replacement(
                session,
                self.panel,
                service_id=token,
                actor_id=2,
                body=ConsoleExitReplacementConfirmBody(
                    user_id=1,
                    operation_id=self.operation_id,
                    expected_revision=state.service.revision,
                    expected_operation_version=state.progress.version,
                    expected_old_exit_revision=state.old_exit.revision,
                    expected_new_exit_revision=state.new_exit.revision,
                    expected_resource_fingerprint=state.request.resource_fingerprint,
                    old_stop_audit_id=state.progress.stop_audit_id,
                    candidate_verify_audit_id=state.progress.verification_audit_id,
                    confirm_replace_and_request_restore=True,
                    idempotency_key="confirm-and-request-restore",
                ),
            )
            assert accepted.replacement.restore_requested
            assert accepted.replacement.switch_result == "pending"
        steps = []
        for _ in range(8):
            await self.tick()
            view = await self.view()
            remote = await self.remote(0)
            groups = observed_groups(remote)
            assert groups in (set(), {self.target.squad_id}), "Unexpected shared fallback"
            steps.append(
                {
                    "stage": view.progress.stage,
                    "remote_status": remote["status"],
                    "groups": sorted(groups),
                }
            )
            if view.progress.stage == "restoring":
                assert view.current_exit_id == self.new_exit
                assert view.old_resource_state == "held"
            if view.progress.stage == "completed":
                break
        assert view.progress.stage == "completed" and view.progress.restore_result == "enabled"
        assert view.operation.status == "succeeded" and not view.gate_active
        assert view.switch_result == "confirmed" and view.old_resource_state == "held"
        assert remote["status"] == "ACTIVE" and groups == {self.target.squad_id}
        assert await self.rights() == before_rights
        assert (await self.saved(0))[0].used_bytes == old_total
        self.report(
            "replacement-completed",
            {"steps": steps, "rights": before_rights, "used_bytes": old_total},
        )

        new_port = await self.target.client(str(remote["vlessUuid"]))
        new_client = retained_client(self.target, new_port, str(remote["vlessUuid"]))
        self.report("new-service-client", new_client)
        for _ in range(2):
            await self.target.exchange(new_port, token, b"P")
        await self.target.exchange(new_port, token, b"U", 2048)
        await self.target.exchange(new_port, token, b"D", 32768)
        combined = await self.target.ledger(token)
        assert combined[:5] == rows
        new_rows = combined[5:]
        assert [row["op"] for row in new_rows] == ["P", "P", "U", "D"]
        up, down = ledger_totals(new_rows, expected_peer=await self.target.internal_ip())
        assert (up, down) == (4 * 21 + 2048, 2 * 16 + 1 + 32768)
        final_usage = await self.meter(old_total + up + down)
        self.report("new-path-usage", {**final_usage, "origin_ledger": new_rows})
        await self.old.rejected(port, token)
        assert retained_client(self.old, port, str(remote["vlessUuid"])) == self.old_client
        assert retained_client(self.target, new_port, str(remote["vlessUuid"])) == new_client
        assert await self.rights() == before_rights
        view = await self.view()
        assert view.old_stop and view.old_stop.valid, "Historical stop proof lost after new usage"
        assert view.old_resource_state == "held" and "reclaim" in view.allowed_actions
        reclaim_digest = self.report(
            "reclaim-check",
            {
                "old_stop_digest": stop_digest,
                "retained_config_rejected": True,
                "usage": final_usage,
            },
        )
        async with self.factory.begin() as session:
            state = await current_state(session, token, self.operation_id, allow_terminal=True)
            topology = await stable_topology(session, self.panel, state, candidate_required=False)
            assert topology.old_scope
            assert (
                state.old_exit.service_id is None and state.old_exit.hold_order_id == state.order.id
            )
            assert state.new_exit.service_id == token and state.new_exit.hold_order_id is None
            resource, _, duplicate = await scoped_exit_evidence(
                session,
                self.panel,
                exit_id=self.old_exit,
                actor_id=2,
                body=ExitReplacementReclaimBody(
                    replacement_operation_id=self.operation_id,
                    service_id=token,
                    reclaim_purpose="retained_old",
                    expected_revision=state.old_exit.revision,
                    expected_operation_version=state.progress.version,
                    scope_fingerprint=topology.old_scope,
                    checked_at=datetime.now(UTC),
                    connections_stopped=True,
                    old_config_rejected=True,
                    evidence_digest=reclaim_digest,
                    idempotency_key="explicit-old-reclaim",
                ),
            )
            assert not duplicate and resource.hold_order_id is None and resource.verified_at is None
        view = await self.view()
        assert view.old_resource_state == "released" and view.current_exit_id == self.new_exit
        assert (await self.remote(0))["status"] == "ACTIVE"
        assert await self.rights() == before_rights
        assert (await self.saved(0))[0].used_bytes == final_usage["used_bytes"]
        await self.target.exchange(new_port, token, b"P")
        after_reclaim = await self.meter(old_total + up + down + 21 + 16)
        async with self.factory() as session:
            kinds = list(await session.scalars(select(ServiceOrder.kind)))
            assert sorted(kinds) == ["activate", "deliver", "replace_exit"]
        self.report(
            "explicit-reclaim",
            {
                "old_state": view.old_resource_state,
                "new_exit": self.new_exit,
                "new_path_still_transfers": True,
                "usage": after_reclaim,
            },
        )


def run_local_exit_replacement() -> None:
    if os.environ.get("QA_SERVICE_OPERATIONS_LIVE_NODE") != "1":
        pytest.skip("Requires the exclusive opt-in local exit replacement slot")
    database = require_exit_environment()
    if database != SCENARIO_DATABASE_URL:
        raise ValueError("Set the validated local PostgreSQL environment before importing tests")
    root: ExitNode | None = None

    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        nonlocal root
        panel = _panel_service()
        root = ExitNode(panel)
        root.evidence["scope"] = SCOPE
        print(f"Local exit replacement manifest: {root.manifest}", flush=True)
        try:
            async with factory() as session:
                root.state["schema"] = await session.scalar(text("SELECT current_schema()"))
                root.save()
            await root.setup()
            target = root.target()
            await target.setup_target()
            case = ExitScenario(factory, root)
            case.old, case.target = root, target
            await case.prepare_dedicated()
            await case.replace()
            root.evidence["state"] = "passed"
        except BaseException as exc:
            root.evidence["state"] = "failed"
            root.evidence["failure_type"] = type(exc).__name__
            await root.capture_failure()
            if root.companion:
                await root.companion.capture_failure()
            raise
        finally:
            try:
                cleanup = asyncio.create_task(cleanup_pair(root))
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    await cleanup
                    raise
            finally:
                root.close_lock()
                await panel.close_session()

    scenario(run)
    assert root is not None and root.companion is not None
    root.evidence["schema_cleanup"] = "temporary schema dropped by existing scenario finally"
    private_json(root.directory / "report.json", root.evidence)
    root.companion.manifest.unlink()
    root.manifest.unlink()
    print(f"Local exit replacement report: {root.directory / 'report.json'}", flush=True)


@pytest.mark.skipif(
    os.environ.get("QA_SERVICE_OPERATIONS_LIVE_NODE") != "1",
    reason="Requires the exclusive opt-in local exit replacement slot",
)
def test_real_node_exit_replacement_and_explicit_reclaim() -> None:
    run_local_exit_replacement()
