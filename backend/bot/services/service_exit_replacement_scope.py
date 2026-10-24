"""Fresh local and remote authorization coverage, without exporting identity secrets."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.admin_console_resource_schemas import ResourceSourceOut
from bot.services.panel_api_service import PanelApiService
from bot.services.resource_preview_authorizations import read_preview_authorizations
from bot.services.resource_preview_panel import digest
from config.service_plans import ServicePlanTerms
from db.dal.admin_console_nodes_dal import read_service_resources, replacement_impacts
from db.models import User
from db.service_models import DedicatedExit, ServiceConnection, UserService


class _Group(BaseModel):
    uuid: UUID


class _Authorization(BaseModel):
    uuid: str
    activeInternalSquads: list[UUID | _Group]


@dataclass(frozen=True)
class ReplacementAuthorizations:
    remote: dict[str, set[str]]
    local: dict[str, set[str]]
    exits: list[DedicatedExit]
    blockers: set[str]
    sources: list[ResourceSourceOut]
    service_details: dict[str, tuple[int | None, str | None]]


async def read_replacement_authorizations(
    session: AsyncSession,
    panel: PanelApiService | None,
    service_id: str,
    own_reference: str | None,
) -> ReplacementAuthorizations:
    blockers: set[str] = set()
    local: dict[str, set[str]] = {}
    rows = await read_service_resources(session)
    observed = await read_preview_authorizations(panel, rows)
    if observed.source.availability != "available":
        blockers.add("exit_replacement_authorizations_unavailable")
    for service, connection, resource, _user in rows:
        if service.id == service_id:
            continue
        try:
            terms = ServicePlanTerms.model_validate(service.terms)
            groups = {str(value) for value in terms.squad_uuids}
            if terms.resource_type == "dedicated":
                groups = {str(UUID(resource.squad_uuid))} if resource else set()
                if resource is None and connection and connection.state != "revoked":
                    blockers.add("exit_replacement_binding_unconfirmed")
            if connection is None or connection.state != "revoked":
                local[service.id] = groups
            local.setdefault(service.id, set()).update(
                str(value) for value in observed.groups.get(service.id, set())
            )
        except (ValueError, ValidationError):
            blockers.add("exit_replacement_service_scope_invalid")
    for impact in replacement_impacts(rows):
        if impact.service_id == service_id:
            continue
        if impact.unknown_scope or impact.service_id is None:
            blockers.add("exit_replacement_service_scope_invalid")
        elif impact.group_ids:
            local.setdefault(impact.service_id, set()).update(impact.group_ids)
    archive = await session.scalar(
        select(UserService.id)
        .outerjoin(ServiceConnection, ServiceConnection.service_id == UserService.id)
        .where(
            UserService.user_id.is_(None),
            or_(
                UserService.desired_status != "cancelled",
                ServiceConnection.service_id.is_(None),
                ServiceConnection.state != "revoked",
                ServiceConnection.sync_pending.is_(True),
                ServiceConnection.revoked_at.is_(None),
            ),
        )
        .limit(1)
    )
    if archive is not None:
        blockers.add("exit_replacement_archived_scope_unconfirmed")
    service_details: dict[str, tuple[int | None, str | None]] = {}
    if local:
        details = await session.execute(
            select(UserService.id, User.user_id, UserService.terms)
            .outerjoin(User, User.user_id == UserService.user_id)
            .where(UserService.id.in_(local))
        )
        for identity, customer_id, terms in details:
            name = terms.get("name") if isinstance(terms, dict) else None
            service_details[identity] = (customer_id, name if isinstance(name, str) else None)
    exits = list(await session.scalars(select(DedicatedExit).order_by(DedicatedExit.id)))
    remote: dict[str, set[str]] = {}
    source = ResourceSourceOut(
        source="authorizations", availability="unavailable", observed_at=datetime.now(UTC)
    )
    if panel is not None:
        try:
            # Existing stream adapter verifies pagination; bypass the TTL cache.
            users = await panel._get_all_panel_users_uncached(log_responses=False)
            if users is not None:
                seen: set[str] = set()
                for value in users:
                    item = _Authorization.model_validate(value)
                    if item.uuid in seen:
                        raise ValueError("duplicate_identity")
                    seen.add(item.uuid)
                    remote_groups = [
                        str(group.uuid if isinstance(group, _Group) else group)
                        for group in item.activeInternalSquads
                    ]
                    if len(remote_groups) != len(set(remote_groups)):
                        raise ValueError("duplicate_scope")
                    if item.uuid != own_reference:
                        remote[digest(item.uuid)] = set(remote_groups)
                source.availability = "available"
        except Exception:
            # Upstream bodies/exception messages can contain private connection data.
            pass
    if source.availability != "available":
        blockers.add("exit_replacement_authorizations_unavailable")
    if observed.source.availability != "available":
        source.availability = "unavailable"
    local_source = ResourceSourceOut(
        source="services",
        observed_at=datetime.now(UTC),
        availability="available"
        if not (blockers - {"exit_replacement_authorizations_unavailable"})
        else "invalid",
    )
    return ReplacementAuthorizations(
        remote, local, exits, blockers, [local_source, source], service_details
    )
