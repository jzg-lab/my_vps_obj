"""Shared ownership and terms checks for independent panel identities."""

from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.service_periods import as_utc
from config.service_plans import ServicePlanTerms
from db.dal.resource_operations_dal import coordinate_resources
from db.dal.user_dal import lock_user_by_id
from db.models import User
from db.service_models import DedicatedExit, ServiceConnection, UserService


class ServiceEntitlementPanel(Protocol):
    async def get_user_by_uuid_lookup(
        self, user_uuid: str, log_response: bool = False
    ) -> dict[str, Any]: ...

    async def update_user_status_on_panel(
        self, user_uuid: str, enable: bool, log_response: bool = False
    ) -> bool: ...

    async def update_user_details_on_panel(
        self, user_uuid: str, update_payload: dict[str, Any], log_response: bool = False
    ) -> dict[str, Any] | None: ...


def panel_traffic_limit(service: UserService, connection: ServiceConnection | None) -> int:
    """Absolute NO_RESET cap; accepted samples advance total and usage equally."""
    total = connection.usage_total_bytes if connection is not None else None
    raw = connection.usage_raw_bytes if connection is not None else None
    cutover = connection.cycle_cutover_bytes if connection is not None else None
    total = service.used_bytes if total is None else total
    raw = total if raw is None else raw
    used = total - cutover if cutover is not None else service.used_bytes
    # Panel zero means unlimited. Exhausted services remain disabled with a positive cap.
    limit = max(1, raw + service.quota_bytes - used)
    if used < 0 or limit > 2**53 - 1:
        raise ValueError("panel_limit_invalid")
    return limit


async def locked_service(
    session: AsyncSession,
    service_id: str,
    *,
    include_revoked: bool = False,
    expected_intent: tuple[int | None, int] | None = None,
) -> tuple[User, UserService, ServiceConnection] | None:
    await coordinate_resources(session)
    owner_id = await session.scalar(select(UserService.user_id).where(UserService.id == service_id))
    if owner_id is None:
        return None
    user = await lock_user_by_id(session, owner_id)
    service = await session.get(UserService, service_id, populate_existing=True)
    connection = await session.get(ServiceConnection, service_id, populate_existing=True)
    # A merge may have moved ownership while we waited for the original account lock.
    if user is None or service is None or service.user_id != owner_id or connection is None:
        return None
    if connection.state == "revoked" and not include_revoked:
        return None
    if expected_intent is not None and (service.user_id, service.revision) != expected_intent:
        return None
    return user, service, connection


async def service_squads(session: AsyncSession, service: UserService) -> list[str] | None:
    connection = await session.get(ServiceConnection, service.id)
    if connection is not None and connection.replacement_order_id is not None:
        return None
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


def matches_service_terms(
    remote: dict[str, Any],
    service: UserService,
    squads: list[str],
    *,
    connection: ServiceConnection | None = None,
) -> bool:
    try:
        limit = panel_traffic_limit(service, connection)
    except ValueError:
        return False
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
        and type(remote.get("trafficLimitBytes")) is int
        and remote.get("trafficLimitBytes") == limit
        and remote.get("trafficLimitStrategy") == "NO_RESET"
        and remote.get("externalSquadUuid") in (None, "")
    )
