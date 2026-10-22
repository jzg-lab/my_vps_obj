"""Retry saved changes without renewing twice or enabling an unprepared identity."""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.services.panel_api_service import PanelApiService
from bot.services.service_panel_state import (
    locked_service,
    matches_service_terms,
    owns_identity,
    service_squads,
)
from bot.services.user_service_access import service_status
from config.service_periods import as_utc
from db.models import User
from db.service_models import DedicatedExit, ServiceConnection, UserService

logger = logging.getLogger(__name__)
DISABLED_STATES = {"DISABLED", "EXPIRED", "LIMITED"}


async def synchronize_service_change(
    session_factory: sessionmaker, service_id: str, panel: PanelApiService
) -> None:
    async with session_factory() as session:
        locked = await locked_service(session, service_id)
        if locked is None:
            return
        user, service, connection = locked
        if not connection.sync_pending:
            return
        connection.sync_attempted_at = datetime.now(UTC)
        connection.sync_error = "panel_change_unconfirmed"
        try:
            await _synchronize_locked(session, user, service, connection, panel)
        except Exception:
            logger.exception("Saved service change needs retry for %s", service_id)
        await session.commit()


async def _synchronize_locked(
    session: AsyncSession,
    user: User,
    service: UserService,
    connection: ServiceConnection,
    panel: PanelApiService,
) -> None:
    reference = connection.panel_user_uuid
    if reference is None:
        if connection.state == "pending":
            # No remote call was submitted. Preparation will use the new terms.
            connection.sync_pending = False
            connection.sync_error = None
            connection.sync_confirmed_at = None
        return
    lookup = await panel.get_user_by_uuid_lookup(reference)
    remote = lookup.get("user") if lookup.get("ok") is True else None
    if not isinstance(remote, dict):
        if lookup.get("not_found"):
            connection.sync_error = "panel_identity_missing"
        return
    if not owns_identity(remote, connection):
        connection.sync_error = "panel_identity_conflict"
        return
    resource = await session.scalar(
        select(DedicatedExit).where(DedicatedExit.service_id == service.id)
    )
    enable = service_status(service, connection, resource, banned=bool(user.is_banned)) == "active"
    # Pause/ban/expiry takes precedence even if another field needs repair.
    if not enable and remote.get("status") not in DISABLED_STATES:
        await panel.update_user_status_on_panel(reference, False)
    await panel.update_user_details_on_panel(
        reference,
        {
            "expireAt": as_utc(service.expires_at).isoformat(timespec="milliseconds"),
            **({"status": "DISABLED"} if not enable or remote.get("status") != "ACTIVE" else {}),
        },
    )
    lookup = await panel.get_user_by_uuid_lookup(reference)
    remote = lookup.get("user") if lookup.get("ok") is True else None
    if not isinstance(remote, dict) or not owns_identity(remote, connection):
        return
    squads = await service_squads(session, service)
    if squads is None or not matches_service_terms(remote, service, squads):
        connection.sync_error = "panel_identity_terms_mismatch"
        return
    # Recheck expiry after remote waits; renewal does not override pause or account ban.
    enable = service_status(service, connection, resource, banned=bool(user.is_banned)) == "active"
    desired_states = {"ACTIVE"} if enable else DISABLED_STATES
    if remote.get("status") not in desired_states:
        await panel.update_user_status_on_panel(reference, enable)
        lookup = await panel.get_user_by_uuid_lookup(reference)
        remote = lookup.get("user") if lookup.get("ok") is True else None
    if (
        not isinstance(remote, dict)
        or not owns_identity(remote, connection)
        or not matches_service_terms(remote, service, squads)
        or remote.get("status") not in desired_states
    ):
        return
    connection.sync_pending = False
    connection.sync_error = None
    connection.sync_confirmed_at = datetime.now(UTC)


class ServiceChangeWorker:
    def __init__(self, session_factory: sessionmaker, panel: PanelApiService) -> None:
        self.session_factory = session_factory
        self.panel = panel

    async def tick(self) -> None:
        async with self.session_factory() as session:
            service_ids = list(
                await session.scalars(
                    select(ServiceConnection.service_id)
                    .join(UserService, UserService.id == ServiceConnection.service_id)
                    .where(
                        UserService.user_id.is_not(None),
                        ServiceConnection.sync_pending.is_(True),
                        ServiceConnection.state != "revoked",
                    )
                    .order_by(
                        ServiceConnection.sync_attempted_at.asc().nulls_first(),
                        ServiceConnection.service_id,
                    )
                    .limit(50)
                )
            )
        for service_id in service_ids:
            try:
                await synchronize_service_change(self.session_factory, service_id, self.panel)
            except Exception:
                logger.exception("Service change worker will retry %s", service_id)

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("Service change worker tick failed")
            await asyncio.sleep(30)
