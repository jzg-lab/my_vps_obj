"""Deliver only the requested service identity; never fall back to account credentials."""

from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.services.panel_api_service import PanelApiService
from bot.services.service_change_sync import (
    synchronize_service_change,
    synchronize_service_entitlement_locked,
)
from bot.services.service_panel_state import (
    locked_service,
    matches_service_terms,
    owns_identity,
    service_squads,
)
from bot.services.service_usage_sync import record_service_usage
from bot.services.user_service_access import service_ready_for_delivery
from db.dal.user_services_dal import ServiceConflict, get_service_resource
from db.service_models import ServiceOrder


async def service_subscription(
    session: AsyncSession, *, user_id: int, service_id: str, panel: PanelApiService | None
) -> str:
    locked = await locked_service(session, service_id)
    if locked is None or locked[1].user_id != user_id:
        raise ServiceConflict("service_not_found", 404)
    user, service, connection = locked
    if user.is_banned:
        raise ServiceConflict("account_banned", 403)
    _, resource = await get_service_resource(session, service_id)
    if (
        connection.state != "ready"
        or not service_ready_for_delivery(
            service, connection, resource, banned=bool(user.is_banned)
        )
        or connection.sync_pending
        or connection.revoke_requested_at is not None
        or connection.panel_user_uuid is None
    ):
        raise ServiceConflict("service_not_deliverable")
    if panel is None:
        raise ServiceConflict("service_delivery_unconfirmed", 503)
    try:
        lookup = await panel.get_user_by_uuid_lookup(connection.panel_user_uuid)
    except Exception:
        # Exception messages can contain a response or a subscription credential.
        raise ServiceConflict("service_delivery_unconfirmed", 503) from None
    remote = lookup.get("user") if lookup.get("ok") is True else None
    if isinstance(remote, dict) and owns_identity(remote, connection):
        record_service_usage(service, connection, remote)
    squads = await service_squads(session, service)
    if (
        not isinstance(remote, dict)
        or not owns_identity(remote, connection)
        or squads is None
        or not matches_service_terms(remote, service, squads, connection=connection)
        or remote.get("status") != "ACTIVE"
        or not service_ready_for_delivery(
            service, connection, resource, banned=bool(user.is_banned)
        )
    ):
        raise ServiceConflict("service_delivery_unconfirmed", 503)
    url = remote.get("subscriptionUrl")
    if not isinstance(url, str) or any(
        char.isspace() or ord(char) < 32 or 127 <= ord(char) <= 159 for char in url
    ):
        raise ServiceConflict("service_delivery_unconfirmed", 503)
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.fragment
            and (parsed.port is None or 0 < parsed.port <= 65535)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ServiceConflict("service_delivery_unconfirmed", 503)
    return url


async def deliver_service_identity(
    session_factory: sessionmaker, service_id: str, panel: PanelApiService
) -> None:
    async with session_factory() as session:
        locked = await locked_service(session, service_id)
        if locked is None or locked[2].state != "pending":
            return
        _user, _service, connection = locked
        requested = await session.scalar(
            select(ServiceOrder.id)
            .where(ServiceOrder.service_id == service_id, ServiceOrder.kind == "deliver")
            .limit(1)
        )
        if requested is None or connection.revoke_requested_at is not None:
            return
        connection.attempted_at = datetime.now(UTC)
        connection.sync_pending = True
        connection.sync_error = "service_delivery_pending"
        await session.commit()
    async with session_factory() as session:
        locked = await locked_service(session, service_id)
        if locked is None or locked[2].state != "pending":
            return
        user, service, connection = locked
        if connection.revoke_requested_at is not None:
            return
        try:
            confirmed = await synchronize_service_entitlement_locked(
                session, user, service, connection, panel
            )
        except Exception:
            await session.commit()
            return
        _, resource = await get_service_resource(session, service_id)
        if (
            not confirmed
            or connection.sync_pending
            or not service_ready_for_delivery(
                service, connection, resource, banned=bool(user.is_banned)
            )
        ):
            await session.commit()
            return
        # Ready only means prerequisites are established. Persist the next sync before
        # any enabling write, so crashes and account changes go through A's same retry path.
        connection.state = "ready"
        connection.sync_pending = True
        connection.sync_error = "service_delivery_pending"
        await session.commit()
    await synchronize_service_change(session_factory, service_id, panel)
