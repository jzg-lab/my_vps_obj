"""Read existing service identities afresh; never provision or reconcile them."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ValidationError

from bot.app.web.admin_console_resource_schemas import ResourceSourceOut
from bot.services.panel_api_service import PanelApiService
from bot.services.service_panel_state import owns_identity
from db.dal.admin_console_nodes_dal import ServiceResourceRow


class _Group(BaseModel):
    uuid: UUID


class _Scope(BaseModel):
    activeInternalSquads: list[_Group | UUID]


@dataclass
class PreviewAuthorizations:
    groups: dict[str, set[UUID]]
    source: ResourceSourceOut


async def read_preview_authorizations(
    panel: PanelApiService | None,
    rows: list[ServiceResourceRow],
) -> PreviewAuthorizations:
    semaphore = asyncio.Semaphore(8)

    async def read(row: ServiceResourceRow) -> tuple[str, set[UUID] | None]:
        service, connection, _, _ = row
        if connection is None:
            return service.id, set()
        if connection.panel_user_uuid is None:
            # An earlier create may still finish remotely; absence of a local ID proves nothing.
            return service.id, set() if connection.attempted_at is None else None
        if panel is None:
            return service.id, None
        try:
            async with semaphore:
                result = await panel.get_user_by_uuid_lookup(
                    connection.panel_user_uuid, log_response=False
                )
            if result.get("not_found") is True:
                return service.id, set()
            remote = result.get("user")
            if result.get("ok") is not True or not isinstance(remote, dict):
                return service.id, None
            if not owns_identity(remote, connection):
                return service.id, None
            scope = _Scope.model_validate(remote)
            groups = [
                item.uuid if isinstance(item, _Group) else item
                for item in scope.activeInternalSquads
            ]
            if len(groups) != len(set(groups)):
                return service.id, None
            return service.id, set(groups)
        except (ValidationError, ValueError):
            return service.id, None
        except Exception:
            return service.id, None

    resolved = await asyncio.gather(*(read(row) for row in rows))
    complete = all(groups is not None for _, groups in resolved)
    return PreviewAuthorizations(
        {service_id: groups for service_id, groups in resolved if groups is not None},
        ResourceSourceOut(
            source="authorizations",
            availability="available" if complete else "unavailable",
            observed_at=datetime.now(UTC),
        ),
    )
