"""Fresh safe readback and attempt-scoped administrator reconciliation."""

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.admin_console_resource_operation_schemas import (
    ConsoleResourceOperationAcceptedOut,
    ConsoleResourceOperationEvidenceBody,
    ResourceEvidenceOut,
    ResourceObservationOut,
)
from bot.app.web.admin_console_resource_schemas import (
    ConsoleResourcePreviewOut,
    ResourceHostPatch,
    ResourceValuesOut,
)
from bot.services.panel_api_service import PanelApiService
from bot.services.resource_operation_panel import creation_marker
from bot.services.resource_operations import operation_output
from bot.services.resource_preview_panel import read_preview_inventory
from bot.services.resource_preview_values import (
    group_values,
    host_values,
    node_values,
    topology_problems,
)
from config.service_periods import as_utc
from db.dal.resource_operations_dal import finish_resource_operation, locked_resource_operation
from db.dal.user_services_dal import ServiceConflict
from db.resource_operation_models import ResourceOperation

REMOVAL_EVIDENCE_MAX_AGE = timedelta(minutes=5)


def _known_target(row: ResourceOperation) -> tuple[str | None, ResourceObservationOut | None]:
    previous = ResourceObservationOut.model_validate(row.observation) if row.observation else None
    target = row.target_id
    if previous and previous.values is not None and previous.correlation != "unresolved":
        observed_target = previous.values.id
        if target is not None and target != observed_target:
            raise ServiceConflict("resource_evidence_invalid")
        target = observed_target
    return target, previous


def _require_removal_evidence(
    row: ResourceOperation, body: ConsoleResourceOperationEvidenceBody
) -> None:
    target, previous = _known_target(row)
    now = datetime.now(UTC)
    if (
        body.original_request_terminated is not True
        or target is None
        or body.target_id is None
        or str(body.target_id) != target
        or not now - REMOVAL_EVIDENCE_MAX_AGE <= as_utc(body.checked_at) <= now
    ):
        raise ServiceConflict("resource_evidence_invalid")
    if row.operation.endswith("_create"):
        accepted = bool(
            row.target_id and row.attempts and row.attempts[-1].get("receipt") == "accepted"
        )
        marked = previous is not None and previous.correlation == "creation_marker"
        if not accepted and not marked:
            raise ServiceConflict("resource_evidence_invalid")


async def observe_resource_operation(
    panel: PanelApiService | None,
    row: ResourceOperation,
    *,
    attested_target: str | None = None,
    require_fresh: bool = False,
) -> ResourceObservationOut:
    read_started_at = datetime.now(UTC)
    inventory = await read_preview_inventory(panel)
    restart: Literal["not_requested", "accepted_unverified", "may_be_noop", "unknown"] = (
        "not_requested"
    )
    if row.operation == "node_restart":
        accepted = bool(row.attempts and row.attempts[-1].get("receipt") == "accepted")
        restart = (
            ("accepted_unverified" if row.request.get("force_restart") else "may_be_noop")
            if accepted
            else "unknown"
        )
    observation = ResourceObservationOut(
        observed_at=datetime.now(UTC),
        values=None,
        configuration="unavailable",
        restart=restart,
        correlation="unresolved",
    )
    if any(source.availability != "available" for source in inventory.sources) or topology_problems(
        inventory
    ):
        return observation
    if require_fresh and any(
        source.observed_at.tzinfo is None
        or not read_started_at <= as_utc(source.observed_at) <= observation.observed_at
        for source in inventory.sources
    ):
        return observation
    known_target, previous = _known_target(row)
    target = known_target or attested_target
    if known_target is not None and attested_target is not None and known_target != attested_target:
        raise ServiceConflict("resource_evidence_invalid")
    markers: list[str] | None = None
    if row.operation in {"node_create", "host_create"}:
        markers = (
            [
                str(node.uuid)
                for node in inventory.nodes.rows
                if node.note == creation_marker(row.id)
            ]
            if row.operation == "node_create"
            else [
                str(host.uuid)
                for host in inventory.hosts.rows
                if creation_marker(row.id, host=True) in host.tags
            ]
        )
        # Identity conflicts are not a partial write or proof of non-application.
        if (
            len(markers) > 1
            or any(identity in row.baseline_ids for identity in markers)
            or (markers and target is not None and markers != [target])
        ):
            raise ServiceConflict("resource_evidence_invalid")
    if target:
        accepted = bool(row.attempts and row.attempts[-1].get("receipt") == "accepted")
        observation.correlation = (
            "known_uuid"
            if not row.operation.endswith("_create")
            else "administrator_attestation"
            if attested_target
            else "response_uuid"
            if accepted
            else "creation_marker"
            if previous is not None and previous.correlation == "creation_marker"
            else "unresolved"
        )
    elif markers:
        target = markers[0]
        observation.correlation = "creation_marker"
    if target is None:
        observation.configuration = "missing"
        return observation
    if row.operation.endswith("_create") and target in row.baseline_ids:
        raise ServiceConflict("resource_evidence_invalid")
    identity = UUID(target)
    values: ResourceValuesOut | None = None
    blockers: set[str] = set()
    if row.operation.startswith("node_"):
        node = next((item for item in inventory.nodes.rows if item.uuid == identity), None)
        if node:
            values = node_values(node)
            if row.operation == "node_create":
                # Readback must include the submitted management endpoint, not guess it.
                try:
                    values.address = ResourceHostPatch.public_endpoint(node.address)
                except ValueError:
                    return observation
                values.port = node.port
                if values.address is None or values.port is None:
                    return observation
    elif row.operation.startswith("group_"):
        group = next((item for item in inventory.groups.rows if item.uuid == identity), None)
        if group:
            values = group_values(group)
    else:
        host = next((item for item in inventory.hosts.rows if item.uuid == identity), None)
        if host:
            values = host_values(host, blockers)
    if blockers:
        return observation
    observation.values = values
    if values is None:
        observation.configuration = "missing"
        return observation
    if markers is not None and markers != [target]:
        raise ServiceConflict("resource_evidence_invalid")
    expected = ConsoleResourcePreviewOut.model_validate(row.preview).proposed
    if expected is None:
        raise ServiceConflict("resource_evidence_invalid")
    requested = expected.model_dump(exclude={"id", "force_restart"})
    actual = values.model_dump(exclude={"id", "force_restart"})
    observation.configuration = "matched" if requested == actual else "different"
    return observation


async def reconcile_resource_operation(
    session: AsyncSession,
    panel: PanelApiService | None,
    operation_id: str,
    *,
    expected_version: int,
) -> ConsoleResourceOperationAcceptedOut:
    row = await locked_resource_operation(session, operation_id)
    if row.version != expected_version:
        raise ServiceConflict("resource_operation_changed")
    if row.status != "unknown":
        raise ServiceConflict("resource_retry_not_allowed")
    known_target, previous = _known_target(row)
    observation = await observe_resource_operation(panel, row)
    if observation.values is not None and observation.correlation == "creation_marker":
        row.target_id = observation.values.id
    elif known_target is not None:
        # A missing readback must not erase the identity observed before deletion.
        row.target_id = known_target
        if (
            observation.configuration == "unavailable"
            and previous is not None
            and previous.correlation in {"creation_marker", "response_uuid"}
        ):
            observation.correlation = previous.correlation
    row.observation = observation.model_dump(mode="json")
    row.version += 1
    # Matching configuration alone cannot prove an unanswered request has finished.
    accepted = bool(row.attempts and row.attempts[-1].get("receipt") == "accepted")
    if accepted and observation.configuration == "matched":
        finish_resource_operation(row, success=True)
    else:
        row.error_code = (
            "resource_partial_write"
            if observation.configuration == "different"
            else "resource_manual_reconciliation_required"
        )
    await session.flush()
    return operation_output(row)


async def accept_resource_evidence(
    session: AsyncSession,
    panel: PanelApiService | None,
    operation_id: str,
    *,
    actor_id: int,
    body: ConsoleResourceOperationEvidenceBody,
) -> ConsoleResourceOperationAcceptedOut:
    row = await locked_resource_operation(session, operation_id)
    if row.version != body.expected_version:
        raise ServiceConflict("resource_operation_changed")
    if row.status != "unknown" or row.attempt_count != body.attempt or row.attempted_at is None:
        raise ServiceConflict("resource_evidence_invalid")
    if as_utc(body.checked_at) < as_utc(row.attempted_at):
        raise ServiceConflict("resource_evidence_invalid")
    target = str(body.target_id) if body.target_id is not None else None
    if row.operation.endswith("_create") and body.result != "not_applied" and target is None:
        raise ServiceConflict("resource_evidence_invalid")
    removed = body.result == "externally_removed"
    if removed:
        _require_removal_evidence(row, body)
    observation = await observe_resource_operation(
        panel, row, attested_target=None if removed else target, require_fresh=removed
    )
    if observation.configuration == "unavailable":
        raise ServiceConflict("resource_sources_incomplete")
    if removed:
        # Recheck after IO; a slow inventory read cannot extend the evidence lifetime.
        _require_removal_evidence(row, body)
        if observation.configuration != "missing" or observation.values is not None:
            raise ServiceConflict("resource_evidence_invalid")
    if body.result == "applied" and observation.configuration != "matched":
        raise ServiceConflict("resource_evidence_invalid")
    if body.result == "partial" and (observation.values is None or row.operation == "node_restart"):
        raise ServiceConflict("resource_evidence_invalid")
    if body.result == "not_applied":
        if row.operation.endswith("_create"):
            if observation.values is not None:
                raise ServiceConflict("resource_evidence_invalid")
        else:
            before = ConsoleResourcePreviewOut.model_validate(row.preview).current
            if (
                before is None
                or observation.values is None
                or before.model_dump(exclude={"force_restart"})
                != observation.values.model_dump(exclude={"force_restart"})
            ):
                raise ServiceConflict("resource_evidence_invalid")
    evidence = ResourceEvidenceOut(
        actor_id=actor_id,
        attempt=body.attempt,
        result=body.result,
        target_id=target,
        evidence_digest=body.evidence_digest,
        observed_at=body.checked_at,
        recorded_at=datetime.now(UTC),
        original_request_terminated=body.original_request_terminated,
    )
    row.evidence = [*row.evidence, evidence.model_dump(mode="json")]
    row.observation = observation.model_dump(mode="json")
    if target is not None:
        row.target_id = target
    finish_resource_operation(
        row,
        success=body.result == "applied",
        error=(
            "resource_target_removed"
            if removed
            else "resource_write_rejected"
            if body.result == "not_applied"
            else "resource_partial_write"
            if body.result == "partial"
            else None
        ),
    )
    await session.flush()
    return operation_output(row)
