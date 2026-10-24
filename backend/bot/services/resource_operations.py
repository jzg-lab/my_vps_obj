"""Confirmed resource commands and explicit retries; HTTP submission never dispatches."""

import hmac
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.admin_console_resource_operation_schemas import (
    ConsoleResourceOperationAcceptedOut,
    ConsoleResourceOperationOut,
    ConsoleResourceOperationRetryBody,
    ConsoleResourceOperationStartBody,
)
from bot.app.web.admin_console_resource_schemas import (
    ConsoleResourcePreviewOut,
    ResourceChange,
    ResourceGroupChange,
    ResourceHostChange,
    ResourceNodeChange,
)
from bot.services.panel_api_service import PanelApiService
from bot.services.resource_operation_errors import safe_resource_error
from bot.services.resource_operation_panel import require_resource_panel
from bot.services.resource_preview_panel import PreviewInventory
from bot.services.resource_preview_read import stable_resource_preview
from db.dal.resource_operations_dal import (
    PANEL_GATE,
    coordinate_resources,
    locked_resource_operation,
    resource_gate_active,
)
from db.dal.user_services_dal import ServiceConflict
from db.resource_operation_models import ResourceOperation
from db.service_models import ServiceConnection, ServiceOperationExecution

CHANGE_ADAPTER = TypeAdapter(ResourceChange)


def operation_output(
    row: ResourceOperation, *, duplicate: bool = False
) -> ConsoleResourceOperationAcceptedOut:
    return ConsoleResourceOperationAcceptedOut(
        duplicate=duplicate,
        operation=ConsoleResourceOperationOut.model_validate(
            {
                "id": row.id,
                "actor_id": row.actor_id,
                "status": row.status,
                "version": row.version,
                "change": row.request,
                "target_id": row.target_id,
                "recovery_of": row.recovery_of,
                "preview": row.preview,
                "attempts": row.attempts,
                "observation": row.observation,
                "evidence": row.evidence,
                "gate_active": row.gate_key is not None,
                "error_code": safe_resource_error(row.error_code),
                "created_at": row.created_at,
                "completed_at": row.completed_at,
                "can_retry": row.status == "failed" and row.error_code == "resource_write_rejected",
                "requires_manual_reconciliation": row.status == "unknown",
            }
        ),
    )


def require_preview(preview: ConsoleResourcePreviewOut, fingerprint: str) -> None:
    if preview.coverage != "complete" or preview.fingerprint is None:
        raise ServiceConflict("resource_sources_incomplete")
    if not hmac.compare_digest(preview.fingerprint, fingerprint):
        raise ServiceConflict("resource_preview_changed")


def inventory_ids(change: ResourceChange, inventory: PreviewInventory) -> list[str]:
    if change.operation == "node_create":
        return sorted(str(row.uuid) for row in inventory.nodes.rows)
    if change.operation == "host_create":
        return sorted(str(row.uuid) for row in inventory.hosts.rows)
    if change.operation == "group_create":
        return sorted(str(row.uuid) for row in inventory.groups.rows)
    return []


async def require_no_prior_write(session: AsyncSession) -> None:
    if (
        await session.scalar(
            select(ServiceConnection.service_id)
            .where(ServiceConnection.replacement_order_id.is_not(None))
            .limit(1)
        )
        is not None
    ):
        raise ServiceConflict("resource_replacement_in_progress")
    if (
        await session.scalar(
            select(ServiceOperationExecution.id)
            .where(ServiceOperationExecution.status == "unknown")
            .limit(1)
        )
        is not None
    ):
        raise ServiceConflict("resource_prior_write_unknown")


async def _recovery(
    session: AsyncSession,
    body: ConsoleResourceOperationStartBody,
    preview: ConsoleResourcePreviewOut,
) -> None:
    if body.recovery_of is None:
        return
    original = await session.get(ResourceOperation, body.recovery_of, populate_existing=True)
    if (
        original is None
        or original.status in {"pending", "unknown"}
        or original.error_code == "resource_target_removed"
    ):
        raise ServiceConflict("resource_recovery_invalid")
    before = ConsoleResourcePreviewOut.model_validate(original.preview).current
    change = body.change
    if before is None or preview.current is None or before.id != preview.current.id:
        raise ServiceConflict("resource_recovery_invalid")
    if isinstance(change, ResourceHostChange) and original.operation == "host_update":
        desired = change.patch.model_dump(mode="json", exclude_unset=True)
        old_change = CHANGE_ADAPTER.validate_python(original.request)
        if (
            not isinstance(old_change, ResourceHostChange)
            or set(desired) != old_change.patch.model_fields_set
        ):
            raise ServiceConflict("resource_recovery_invalid")
        previous = before.model_dump()
        previous["inbound_id"] = before.inbound_ids[0] if before.inbound_ids else None
        if any(previous.get(key) != value for key, value in desired.items()):
            raise ServiceConflict("resource_recovery_invalid")
    elif isinstance(change, ResourceGroupChange) and original.operation == "group_inbounds":
        if [str(item) for item in change.inbound_ids] != before.inbound_ids:
            raise ServiceConflict("resource_recovery_invalid")
    elif isinstance(change, ResourceNodeChange) and original.operation in {
        "node_enable",
        "node_disable",
    }:
        if change.operation != ("node_disable" if before.is_disabled else "node_enable"):
            raise ServiceConflict("resource_recovery_invalid")
    else:
        raise ServiceConflict("resource_recovery_invalid")


async def start_resource_operation(
    session: AsyncSession,
    panel: PanelApiService | None,
    *,
    actor_id: int,
    body: ConsoleResourceOperationStartBody,
) -> ConsoleResourceOperationAcceptedOut:
    await coordinate_resources(session, exclusive=True)
    previous = await session.scalar(
        select(ResourceOperation).where(
            ResourceOperation.actor_id == actor_id,
            ResourceOperation.idempotency_key == body.idempotency_key,
        )
    )
    change = body.change.model_dump(mode="json")
    if previous is not None:
        if (
            previous.request != change
            or previous.fingerprint != body.expected_fingerprint
            or previous.recovery_of != body.recovery_of
        ):
            raise ServiceConflict("resource_idempotency_conflict")
        return operation_output(previous, duplicate=True)
    await require_resource_panel(panel)
    if await resource_gate_active(session):
        raise ServiceConflict("resource_operation_in_progress")
    await require_no_prior_write(session)
    preview, inventory = await stable_resource_preview(session, panel, body.change)
    require_preview(preview, body.expected_fingerprint)
    await _recovery(session, body, preview)
    row = ResourceOperation(
        id=uuid4().hex,
        actor_id=actor_id,
        idempotency_key=body.idempotency_key,
        operation=body.change.operation,
        target_id=str(body.change.target_id)
        if isinstance(body.change, (ResourceGroupChange, ResourceHostChange, ResourceNodeChange))
        else None,
        recovery_of=body.recovery_of,
        request=change,
        preview=preview.model_dump(mode="json"),
        baseline_ids=inventory_ids(body.change, inventory),
        fingerprint=body.expected_fingerprint,
        status="pending",
        gate_key=PANEL_GATE,
        version=1,
        attempt_count=0,
        attempts=[],
        evidence=[],
        created_at=datetime.now(UTC),
    )
    session.add(row)
    await session.flush()
    return operation_output(row)


async def retry_resource_operation(
    session: AsyncSession,
    panel: PanelApiService | None,
    operation_id: str,
    body: ConsoleResourceOperationRetryBody,
) -> ConsoleResourceOperationAcceptedOut:
    await coordinate_resources(session, exclusive=True)
    row = await locked_resource_operation(session, operation_id)
    if row.version != body.expected_version:
        raise ServiceConflict("resource_operation_changed")
    if row.status != "failed" or row.error_code != "resource_write_rejected":
        raise ServiceConflict("resource_retry_not_allowed")
    await require_resource_panel(panel)
    if await resource_gate_active(session):
        raise ServiceConflict("resource_operation_in_progress")
    await require_no_prior_write(session)
    preview, _ = await stable_resource_preview(
        session, panel, CHANGE_ADAPTER.validate_python(row.request)
    )
    # A retry never overwrites the immutable original request/confirmation.
    require_preview(preview, row.fingerprint)
    require_preview(preview, body.expected_fingerprint)
    row.status, row.gate_key, row.error_code = "pending", PANEL_GATE, None
    row.completed_at = None
    row.version += 1
    await session.flush()
    return operation_output(row)


async def list_resource_operations(
    session: AsyncSession, *, offset: int, limit: int
) -> tuple[list[ConsoleResourceOperationOut], int]:
    total = await session.scalar(select(func.count()).select_from(ResourceOperation))
    rows = await session.scalars(
        select(ResourceOperation)
        .order_by(
            ResourceOperation.created_at.desc(),
            ResourceOperation.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    return [operation_output(row).operation for row in rows], int(total or 0)
