"""Prepare separate, disabled panel identities before usage sync and delivery."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.services.panel_api_service import PanelApiService
from config.service_periods import as_utc
from config.service_plans import ServicePlanTerms
from db.dal.user_dal import lock_user_by_id
from db.models import User
from db.service_models import DedicatedExit, ServiceConnection, UserService

logger = logging.getLogger(__name__)


async def _locked_service(
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


def _can_prepare(user: User, service: UserService) -> bool:
    return (
        not user.is_banned
        and service.desired_status == "active"
        and as_utc(service.expires_at) > datetime.now(UTC)
    )


async def _squads(session: AsyncSession, service: UserService) -> list[str] | None:
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


def _owned(remote: dict[str, Any], connection: ServiceConnection) -> bool:
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


def _matches_terms(remote: dict[str, Any], service: UserService, squads: list[str]) -> bool:
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
        and remote.get("status") in {"DISABLED", "EXPIRED", "LIMITED"}
    )


async def provision_service_identity(
    session_factory: sessionmaker, service_id: str, panel: PanelApiService
) -> None:
    async with session_factory() as session:
        locked = await _locked_service(session, service_id)
        if locked is None:
            return
        user, service, connection = locked
        if connection.state == "ready" or (
            connection.panel_user_uuid is not None and connection.state == "pending"
        ):
            return
        connection.attempted_at = datetime.now(UTC)
        if connection.state == "pending" and (
            not _can_prepare(user, service) or await _squads(session, service) is None
        ):
            await session.commit()
            return
        # Commit uncertainty before the first remote call. Deletion cannot mistake a
        # crashed create request for an identity that has never been submitted.
        connection.state = "error"
        connection.last_error = "panel_identity_unconfirmed"
        await session.commit()

    async with session_factory() as session:
        locked = await _locked_service(session, service_id)
        if locked is None:
            return
        user, service, connection = locked
        if connection.state != "error":
            return
        try:
            await _prepare_locked(session, user, service, connection, panel)
        except Exception:
            # Keep the durable uncertainty marker, never credentials or API responses.
            logger.exception("Service identity preparation needs retry for %s", service_id)
            connection.last_error = "panel_identity_unconfirmed"
        await session.commit()


async def _prepare_locked(
    session: AsyncSession,
    user: User,
    service: UserService,
    connection: ServiceConnection,
    panel: PanelApiService,
) -> None:
    squads = await _squads(session, service)
    if connection.panel_user_uuid is not None:
        lookup = await panel.get_user_by_uuid_lookup(connection.panel_user_uuid)
        remote = lookup.get("user") if lookup.get("ok") is True else None
        if not isinstance(remote, dict):
            connection.last_error = (
                "panel_identity_missing"
                if lookup.get("not_found")
                else "panel_identity_unconfirmed"
            )
            return
    else:
        users = await panel.get_users_by_filter(username=connection.username)
        if users is None:
            return
        if not users:
            if not _can_prepare(user, service) or squads is None:
                connection.state = "pending"
                connection.last_error = None
                return
            await panel.create_panel_user(
                connection.username,
                expire_at=service.expires_at,
                default_traffic_limit_bytes=service.quota_bytes,
                default_traffic_limit_strategy="NO_RESET",
                specific_squad_uuids=squads,
                hwid_device_limit=0,
                description=f"my_vps_obj:service:{service.id}",
                status="DISABLED",
            )
            # Creation success (including dry-run) is not evidence of a real identity.
            users = await panel.get_users_by_filter(username=connection.username)
        if users is None or len(users) != 1:
            return
        remote = users[0]
    if not _owned(remote, connection):
        connection.last_error = "panel_identity_conflict"
        return
    reference = str(remote["uuid"])
    connection.panel_user_uuid = reference
    # A recovered request must stay disabled until metering is ready, even if the
    # panel was manually changed while the application could not confirm creation.
    if remote.get("status") not in {"DISABLED", "EXPIRED", "LIMITED"}:
        await panel.update_user_status_on_panel(reference, False)
        lookup = await panel.get_user_by_uuid_lookup(reference)
        remote = lookup.get("user") if lookup.get("ok") is True else None
        if not isinstance(remote, dict) or not _owned(remote, connection):
            return
    if squads is None or not _matches_terms(remote, service, squads):
        connection.last_error = "panel_identity_terms_mismatch"
        return
    connection.state = "pending"
    connection.last_error = None


class ServiceProvisioningWorker:
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
                        or_(
                            ServiceConnection.state == "error",
                            (ServiceConnection.state == "pending")
                            & ServiceConnection.panel_user_uuid.is_(None),
                        ),
                    )
                    .order_by(
                        ServiceConnection.attempted_at.asc().nulls_first(),
                        ServiceConnection.service_id,
                    )
                    .limit(50)
                )
            )
        for service_id in service_ids:
            try:
                await provision_service_identity(self.session_factory, service_id, self.panel)
            except Exception:
                logger.exception("Service identity worker will retry %s", service_id)

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("Service identity worker tick failed")
            await asyncio.sleep(30)
