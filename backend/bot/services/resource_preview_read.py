"""Use the same fresh inventory and complete local scope for preview and dispatch."""

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.admin_console_resource_schemas import ConsoleResourcePreviewOut, ResourceChange
from bot.services.panel_api_service import PanelApiService
from bot.services.resource_operation_panel import resource_writes_enabled
from bot.services.resource_preview import build_resource_preview
from bot.services.resource_preview_authorizations import read_preview_authorizations
from bot.services.resource_preview_panel import PreviewInventory, read_preview_inventory
from db.dal.admin_console_nodes_dal import ServiceResourceRow, read_service_resources
from db.service_models import DedicatedExit, ServiceConnection, UserService


async def preview_service_rows(session: AsyncSession) -> tuple[list[ServiceResourceRow], bool]:
    rows = await read_service_resources(session)
    return rows, await unconfirmed_resource_archive(session)


async def unconfirmed_resource_archive(session: AsyncSession) -> bool:
    archive = await session.scalar(
        select(UserService.id)
        .outerjoin(ServiceConnection, ServiceConnection.service_id == UserService.id)
        .outerjoin(DedicatedExit, DedicatedExit.service_id == UserService.id)
        .where(
            UserService.user_id.is_(None),
            or_(
                UserService.desired_status != "cancelled",
                DedicatedExit.id.is_not(None),
                ServiceConnection.service_id.is_(None),
                ServiceConnection.state != "revoked",
                ServiceConnection.sync_pending.is_(True),
                and_(
                    ServiceConnection.panel_user_uuid.is_not(None),
                    ServiceConnection.revoked_at.is_(None),
                ),
            ),
        )
        .limit(1)
    )
    return archive is not None


async def read_resource_preview(
    session: AsyncSession,
    panel: PanelApiService | None,
    change: ResourceChange,
) -> tuple[ConsoleResourcePreviewOut, PreviewInventory]:
    inventory = await read_preview_inventory(panel)
    rows, archive = await preview_service_rows(session)
    authorizations = await read_preview_authorizations(panel, rows)
    result = build_resource_preview(
        change,
        inventory,
        rows,
        archived_scope_unconfirmed=archive,
        authorizations=authorizations,
    )
    result.execution_available = result.coverage == "complete" and resource_writes_enabled(panel)
    return result, inventory


async def stable_resource_preview(
    session: AsyncSession,
    panel: PanelApiService | None,
    change: ResourceChange,
) -> tuple[ConsoleResourcePreviewOut, PreviewInventory]:
    first, inventory = await read_resource_preview(session, panel, change)
    if first.fingerprint is None:
        return first, inventory
    second, inventory = await read_resource_preview(session, panel, change)
    if second.fingerprint != first.fingerprint:
        second.fingerprint = None
        second.coverage = "partial"
        second.execution_available = False
        second.blockers = sorted(set(second.blockers) | {"sources_changed_during_read"})
    return second, inventory
