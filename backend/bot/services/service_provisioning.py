"""Prepare separate, disabled panel identities before usage sync and delivery."""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.services.panel_api_service import PanelApiService
from bot.services.service_delivery import deliver_service_identity
from bot.services.service_operations import enabling_block
from bot.services.service_panel_state import (
    locked_service,
    matches_service_terms,
    owns_identity,
    panel_traffic_limit,
    service_squads,
)
from bot.services.service_revocation import revoke_service_identity
from config.service_periods import as_utc
from db.dal.resource_operations_dal import resource_gate_active
from db.dal.service_operations_dal import begin_execution, finish_execution
from db.models import User
from db.service_models import DedicatedExit, ServiceConnection, ServiceOrder, UserService

logger = logging.getLogger(__name__)


def _can_prepare(user: User, service: UserService) -> bool:
    return (
        not user.is_banned
        and service.desired_status == "active"
        and as_utc(service.expires_at) > datetime.now(UTC)
    )


async def provision_service_identity(
    session_factory: sessionmaker, service_id: str, panel: PanelApiService
) -> None:
    async with session_factory() as session:
        locked = await locked_service(session, service_id)
        if locked is None:
            return
        user, service, connection = locked
        if await resource_gate_active(session):
            connection.last_error = "resource_operation_in_progress"
            await session.commit()
            return
        if (
            connection.revoke_requested_at is not None
            or connection.replacement_order_id is not None
        ):
            return
        if connection.state == "ready" or (
            connection.panel_user_uuid is not None and connection.state == "pending"
        ):
            return
        if connection.state == "pending" and (
            not _can_prepare(user, service) or await service_squads(session, service) is None
        ):
            await finish_execution(
                session,
                service,
                "prepare",
                success=False,
                error=enabling_block(user, service) or "service_not_deliverable",
            )
            await session.commit()
            return
        connection.attempted_at = datetime.now(UTC)
        # Commit uncertainty before the first remote call. Deletion cannot mistake a
        # crashed create request for an identity that has never been submitted.
        connection.state = "error"
        connection.last_error = "panel_identity_unconfirmed"
        await begin_execution(session, service, "prepare", create=True)
        intent = (service.user_id, service.revision)
        await session.commit()

    async with session_factory() as session:
        locked = await locked_service(session, service_id, expected_intent=intent)
        if locked is None:
            return
        user, service, connection = locked
        if (
            connection.state != "error"
            or connection.revoke_requested_at is not None
            or connection.replacement_order_id is not None
        ):
            return
        try:
            await _prepare_locked(session, user, service, connection, panel)
        except Exception:
            # Keep the durable uncertainty marker, never credentials or API responses.
            logger.warning("Service identity preparation needs retry for %s", service_id)
            connection.last_error = "panel_identity_unconfirmed"
        await finish_execution(
            session,
            service,
            "prepare",
            success=connection.state == "pending"
            and connection.panel_user_uuid is not None
            and connection.last_error is None,
            error=connection.last_error,
        )
        await session.commit()


async def _prepare_locked(
    session: AsyncSession,
    user: User,
    service: UserService,
    connection: ServiceConnection,
    panel: PanelApiService,
) -> None:
    if connection.replacement_order_id is not None:
        return
    if await resource_gate_active(session):
        connection.last_error = "resource_operation_in_progress"
        return
    squads = await service_squads(session, service)
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
                # A prior create may still arrive; a temporary empty lookup while
                # restricted cannot turn its durable uncertainty into "never sent".
                return
            await panel.create_panel_user(
                connection.username,
                expire_at=service.expires_at,
                default_traffic_limit_bytes=panel_traffic_limit(service, connection),
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
    if not owns_identity(remote, connection):
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
        if not isinstance(remote, dict) or not owns_identity(remote, connection):
            return
    if (
        squads is None
        or remote.get("status") not in {"DISABLED", "EXPIRED", "LIMITED"}
        or not matches_service_terms(remote, service, squads, connection=connection)
    ):
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
            gate_active = await resource_gate_active(session)
            prepared_resource = (
                UserService.terms["resource_type"].as_string() == "shared"
            ) | select(DedicatedExit.id).where(
                DedicatedExit.service_id == UserService.id,
                DedicatedExit.enabled.is_(True),
                DedicatedExit.verified_at.is_not(None),
                DedicatedExit.resource_pool == UserService.terms["resource_pool"].as_string(),
            ).exists()
            service_ids = list(
                await session.scalars(
                    select(ServiceConnection.service_id)
                    .join(UserService, UserService.id == ServiceConnection.service_id)
                    .join(User, User.user_id == UserService.user_id)
                    .where(
                        UserService.user_id.is_not(None),
                        ServiceConnection.replacement_order_id.is_(None),
                        # Blocked grants cannot consume every slot ahead of revocation.
                        ServiceConnection.revoke_requested_at.is_not(None)
                        if gate_active
                        else true(),
                        or_(
                            (ServiceConnection.revoke_requested_at.is_not(None))
                            & (ServiceConnection.state != "revoked"),
                            (ServiceConnection.state == "pending")
                            & select(ServiceOrder.id)
                            .where(
                                ServiceOrder.service_id == ServiceConnection.service_id,
                                ServiceOrder.kind == "deliver",
                            )
                            .exists(),
                            ServiceConnection.state == "error",
                            (ServiceConnection.state == "pending")
                            & ServiceConnection.panel_user_uuid.is_(None)
                            & User.is_banned.is_(False)
                            & (UserService.desired_status == "active")
                            & (UserService.expires_at > datetime.now(UTC))
                            & prepared_resource,
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
                await revoke_service_identity(self.session_factory, service_id, self.panel)
                await provision_service_identity(self.session_factory, service_id, self.panel)
                await deliver_service_identity(self.session_factory, service_id, self.panel)
            except Exception:
                logger.exception("Service identity worker will retry %s", service_id)

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("Service identity worker tick failed")
            await asyncio.sleep(30)
