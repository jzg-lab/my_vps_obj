"""One attempt per confirmed intent; unknown writes are never worker-replayed."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.services.panel_api_service import PanelApiService
from bot.services.resource_operation_panel import dispatch_resource, require_resource_panel
from bot.services.resource_operation_reconciliation import observe_resource_operation
from bot.services.resource_operations import CHANGE_ADAPTER, require_preview
from bot.services.resource_preview_read import stable_resource_preview
from db.dal.resource_operations_dal import finish_resource_operation, locked_resource_operation
from db.dal.user_services_dal import ServiceConflict
from db.resource_operation_models import ResourceOperation


async def run_resource_operation(
    sessions: async_sessionmaker[AsyncSession], panel: PanelApiService, operation_id: str
) -> None:
    async with sessions() as session:
        row = await locked_resource_operation(session, operation_id)
        if row.status != "pending":
            return
        try:
            await require_resource_panel(panel)
            change = CHANGE_ADAPTER.validate_python(row.request)
            preview, _ = await stable_resource_preview(session, panel, change)
            require_preview(preview, row.fingerprint)
        except ServiceConflict as exc:
            finish_resource_operation(row, success=False, error=exc.code)
            await session.commit()
            return
        # The attempt and its uncertainty are indivisible, including a pre-send crash.
        row.status = "unknown"
        row.error_code = "resource_write_unknown"
        row.attempt_count += 1
        row.attempted_at = datetime.now(UTC)
        row.attempts = [
            *row.attempts,
            {
                "number": row.attempt_count,
                "started_at": row.attempted_at.isoformat(),
                "receipt": "unknown",
            },
        ]
        row.version += 1
        version = row.version
        await session.commit()
    async with sessions() as session:
        row = await locked_resource_operation(session, operation_id)
        if row.status != "unknown" or row.version != version:
            return
        try:
            await require_resource_panel(panel)
            change = CHANGE_ADAPTER.validate_python(row.request)
            preview, _ = await stable_resource_preview(session, panel, change)
            require_preview(preview, row.fingerprint)
        except ServiceConflict as exc:
            # This process still owns the unchanged attempt and has not sent it.
            row.attempts = [*row.attempts[:-1], {**row.attempts[-1], "receipt": "rejected"}]
            finish_resource_operation(row, success=False, error=exc.code)
            await session.commit()
            return
        receipt = await dispatch_resource(panel, change, row.id)
        row.attempts = [*row.attempts[:-1], {**row.attempts[-1], "receipt": receipt.result}]
        row.version += 1
        if receipt.target_id is not None:
            row.target_id = receipt.target_id
        if receipt.result == "rejected":
            finish_resource_operation(row, success=False, error="resource_write_rejected")
        else:
            observation = await observe_resource_operation(panel, row)
            row.observation = observation.model_dump(mode="json")
            if receipt.result == "accepted" and observation.configuration == "matched":
                finish_resource_operation(row, success=True)
            elif observation.configuration == "different":
                row.error_code = "resource_partial_write"
        await session.commit()


async def run_pending_resource_operation(
    sessions: async_sessionmaker[AsyncSession], panel: PanelApiService
) -> None:
    async with sessions() as session:
        operation_id = await session.scalar(
            select(ResourceOperation.id)
            .where(ResourceOperation.status == "pending")
            .order_by(ResourceOperation.created_at, ResourceOperation.id)
            .limit(1)
        )
    if operation_id is not None:
        await run_resource_operation(sessions, panel, operation_id)
