"""Shared ownership and terms checks for independent panel identities."""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.service_periods import as_utc
from config.service_plans import ServicePlanTerms
from db.dal.user_dal import lock_user_by_id
from db.models import User
from db.service_models import DedicatedExit, ServiceConnection, UserService


async def locked_service(
    session: AsyncSession, service_id: str
) -> tuple[User, UserService, ServiceConnection] | None:
    owner_id = await session.scalar(select(UserService.user_id).where(UserService.id == service_id))
    if owner_id is None:
        return None
    user = await lock_user_by_id(session, owner_id)
    service = await session.get(UserService, service_id, populate_existing=True)
    connection = await session.get(ServiceConnection, service_id, populate_existing=True)
    # A merge may have moved ownership while we waited for the original account lock.
    if user is None or service is None or service.user_id != owner_id or connection is None:
        return None
    if connection.state == "revoked":
        return None
    return user, service, connection


async def service_squads(session: AsyncSession, service: UserService) -> list[str] | None:
    terms = ServicePlanTerms.model_validate(service.terms)
    if terms.resource_type == "shared":
        return [str(value) for value in terms.squad_uuids]
    resource = await session.scalar(
        select(DedicatedExit).where(DedicatedExit.service_id == service.id)
    )
    if (
        resource is None
        or not resource.enabled
        or resource.verified_at is None
        or resource.resource_pool != terms.resource_pool
    ):
        return None
    return [resource.squad_uuid]


def owns_identity(remote: dict[str, Any], connection: ServiceConnection) -> bool:
    return (
        remote.get("username") == connection.username
        and remote.get("description") == f"my_vps_obj:service:{connection.service_id}"
        and bool(remote.get("uuid"))
        and (
            connection.panel_user_uuid is None or str(remote["uuid"]) == connection.panel_user_uuid
        )
        and remote.get("telegramId") is None
        and remote.get("email") in (None, "")
    )


def matches_service_terms(remote: dict[str, Any], service: UserService, squads: list[str]) -> bool:
    groups = remote.get("activeInternalSquads")
    if not isinstance(groups, list):
        return False
    actual = [item.get("uuid") if isinstance(item, dict) else item for item in groups]
    if any(not isinstance(item, str) for item in actual) or set(actual) != set(squads):
        return False
    try:
        expiry = datetime.fromisoformat(str(remote.get("expireAt")).replace("Z", "+00:00"))
    except ValueError:
        return False
    return (
        expiry.tzinfo is not None
        and as_utc(expiry).isoformat(timespec="milliseconds")
        == as_utc(service.expires_at).isoformat(timespec="milliseconds")
        and remote.get("trafficLimitBytes") == service.quota_bytes
        and remote.get("trafficLimitStrategy") == "NO_RESET"
        and remote.get("externalSquadUuid") in (None, "")
    )
