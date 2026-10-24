"""Retry saved changes without renewing twice or enabling an unprepared identity."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.services.panel_api_service import PanelApiService
from bot.services.resource_operation_runner import run_pending_resource_operation
from bot.services.service_operations import record_entitlement_result
from bot.services.service_panel_state import (
    ServiceEntitlementPanel,
    locked_service,
    matches_service_terms,
    owns_identity,
    panel_traffic_limit,
    service_squads,
)
from bot.services.service_period_sync import prepare_service_cycle
from bot.services.service_usage_sync import RECONCILIATION_ERRORS, record_service_usage
from bot.services.user_service_access import service_status
from config.service_periods import as_utc
from db.dal.resource_operations_dal import resource_gate_active
from db.dal.service_operations_dal import begin_execution
from db.dal.service_periods_dal import confirm_period
from db.dal.service_quota_dal import apply_latest_quota
from db.models import User
from db.service_models import DedicatedExit, ServiceConnection, ServicePlanQuotaChange, UserService

logger = logging.getLogger(__name__)
DISABLED_STATES = {"DISABLED", "EXPIRED", "LIMITED"}


async def synchronize_service_change(
    session_factory: sessionmaker, service_id: str, panel: ServiceEntitlementPanel
) -> None:
    async with session_factory() as session:
        locked = await locked_service(session, service_id)
        if locked is None:
            return
        _user, service, connection = locked
        if connection.replacement_order_id is not None:
            await synchronize_service_entitlement_locked(session, _user, service, connection, panel)
            await session.commit()
            return
        await apply_latest_quota(session, service, connection)
        await session.commit()
    await prepare_service_cycle(session_factory, service_id, panel)
    # Persist retry intent before remote writes, including automatic expiry checks.
    async with session_factory() as session:
        locked = await locked_service(session, service_id)
        if locked is None:
            return
        _user, service, connection = locked
        if not connection.sync_pending and connection.panel_user_uuid is None:
            return
        if connection.panel_user_uuid is not None:
            await begin_execution(
                session,
                service,
                "entitlement",
                create=service.desired_status != "cancelled" and connection.sync_pending,
            )
            if connection.state == "ready":
                await begin_execution(session, service, "delivery")
            connection.sync_attempted_at = datetime.now(UTC)
        connection.sync_pending = True
        connection.sync_error = "panel_change_unconfirmed"
        intent = (service.user_id, service.revision)
        await session.commit()
    if await _synchronize_saved_change(session_factory, service_id, panel, intent):
        # A cutover must commit before re-enabling an exhausted/disabled identity.
        await _synchronize_saved_change(session_factory, service_id, panel, intent)


async def _synchronize_saved_change(
    session_factory: sessionmaker,
    service_id: str,
    panel: ServiceEntitlementPanel,
    intent: tuple[int | None, int],
) -> bool:
    async with session_factory() as session:
        locked = await locked_service(session, service_id, expected_intent=intent)
        if locked is None:
            return False
        user, service, connection = locked
        if not connection.sync_pending:
            return False
        cutover = connection.cycle_cutover_bytes
        confirmed = False
        try:
            confirmed = await synchronize_service_entitlement_locked(
                session, user, service, connection, panel
            )
        except Exception:
            logger.warning("Saved service change needs retry for %s", service_id)
        await record_entitlement_result(session, user, service, connection, confirmed=confirmed)
        await session.commit()
        return cutover is not None and connection.cycle_cutover_bytes is None


async def synchronize_service_entitlement_locked(
    session: AsyncSession,
    user: User,
    service: UserService,
    connection: ServiceConnection,
    panel: ServiceEntitlementPanel,
) -> bool:
    """Caller holds the account lock and has committed a durable retry intent.

    Returns whether required access is confirmed; false leaves synchronization
    pending. This never changes delivery readiness or chooses a new cutover; it
    can confirm a previously persisted monthly checkpoint.
    """
    connection.sync_pending = True
    connection.sync_error = "panel_change_unconfirmed"
    reference = connection.panel_user_uuid
    if reference is None:
        if connection.replacement_order_id is not None:
            connection.sync_error = "exit_replacement_in_progress"
            return False
        if connection.state == "pending":
            connection.sync_pending = False
            connection.sync_error = None
            connection.sync_confirmed_at = None
            return True
        return False
    connection.sync_attempted_at = datetime.now(UTC)
    lookup = await panel.get_user_by_uuid_lookup(reference)
    remote = lookup.get("user") if lookup.get("ok") is True else None
    if not isinstance(remote, dict):
        if connection.usage_error not in RECONCILIATION_ERRORS:
            connection.usage_error = "panel_usage_unavailable"
        if lookup.get("not_found"):
            connection.sync_error = "panel_identity_missing"
        return False
    connection.revoke_delete_requested_at = None
    if not owns_identity(remote, connection):
        connection.sync_error = "panel_identity_conflict"
        return False
    resource = await session.scalar(
        select(DedicatedExit).where(DedicatedExit.service_id == service.id)
    )

    def eligible() -> bool:
        return (
            service_status(service, connection, resource, banned=bool(user.is_banned)) == "active"
        )

    async def read_back() -> dict[str, Any] | None:
        result = await panel.get_user_by_uuid_lookup(reference)
        observed = result.get("user") if result.get("ok") is True else None
        if not isinstance(observed, dict) or not owns_identity(observed, connection):
            return None
        record_service_usage(service, connection, observed)
        return observed

    connection.usage_attempted_at = datetime.now(UTC)
    record_service_usage(service, connection, remote)
    if connection.replacement_order_id is not None:
        # Only the replacement runner can serialize writes against an unresolved action.
        # Ban/pause intents still win there; ordinary sync keeps sampling this identity.
        connection.sync_error = "exit_replacement_in_progress"
        return False
    # Confirmed restrictions win even when metering or another term is unknown.
    if not eligible() and remote.get("status") not in DISABLED_STATES:
        await panel.update_user_status_on_panel(reference, False)
        remote = await read_back()
        if remote is None or remote.get("status") not in DISABLED_STATES:
            return False
    if service.desired_status == "cancelled":
        # Cancellation only restricts access; revocation owns final accounting and deletion.
        return True
    if await resource_gate_active(session):
        # Restriction and sampling above remain available while resource writes are unresolved.
        connection.sync_error = "resource_operation_in_progress"
        return False
    squads = await service_squads(session, service)
    if connection.cycle_cutover_bytes is not None and (
        as_utc(service.expires_at) <= datetime.now(UTC) or service.desired_status == "cancelled"
    ):
        connection.sync_error = "panel_cycle_unconfirmed"
        return False
    if squads is None:
        connection.sync_error = "panel_identity_terms_mismatch"
        return not eligible() and remote.get("status") in DISABLED_STATES
    if connection.usage_error is not None:
        connection.sync_error = "panel_usage_unconfirmed"
        # Unknown traffic is neither zero usage nor a reason to cut active access.
        return not eligible() and remote.get("status") in DISABLED_STATES
    try:
        limit = panel_traffic_limit(service, connection)
    except ValueError as exc:
        connection.sync_error = str(exc)
        return False
    if not matches_service_terms(remote, service, squads, connection=connection):
        # Scope/strategy changes are not an admin renewal. Do not silently claim them.
        expected = dict(remote)
        expected["expireAt"] = as_utc(service.expires_at).isoformat(timespec="milliseconds")
        expected["trafficLimitBytes"] = limit
        if not matches_service_terms(expected, service, squads, connection=connection):
            connection.sync_error = "panel_identity_terms_mismatch"
            return False
        await panel.update_user_details_on_panel(
            reference,
            {
                "expireAt": as_utc(service.expires_at).isoformat(timespec="milliseconds"),
                "trafficLimitBytes": limit,
                **({"status": "DISABLED"} if not eligible() else {}),
            },
        )
        remote = await read_back()
        if remote is None:
            return False
    if not matches_service_terms(remote, service, squads, connection=connection):
        connection.sync_error = "panel_identity_terms_mismatch"
        return False
    if connection.cycle_cutover_bytes is not None:
        if as_utc(service.expires_at) <= datetime.now(UTC) or service.desired_status == "cancelled":
            return False
        if await confirm_period(session, service, connection, datetime.now(UTC)):
            connection.sync_error = "panel_cycle_unconfirmed"
        return False
    # Reads/updates can take time and observe more traffic: decide again before enable.
    enable = eligible()
    if enable and connection.usage_error is not None:
        connection.sync_error = "panel_usage_unconfirmed"
        return False
    desired_states = {"ACTIVE"} if enable else DISABLED_STATES
    if remote.get("status") not in desired_states:
        await panel.update_user_status_on_panel(reference, enable)
        remote = await read_back()
    if remote is None:
        return False
    # If expiry/exhaustion happened during enable, undo it instead of confirming stale rights.
    if enable and not eligible():
        await panel.update_user_status_on_panel(reference, False)
        remote = await read_back()
        desired_states = DISABLED_STATES
    if (
        remote is None
        or not matches_service_terms(remote, service, squads, connection=connection)
        or remote.get("status") not in desired_states
    ):
        return False
    if eligible() and connection.usage_error is not None:
        connection.sync_error = "panel_usage_unconfirmed"
        return False
    connection.sync_pending = False
    connection.sync_error = None
    connection.sync_confirmed_at = datetime.now(UTC)
    return True


class ServiceChangeWorker:
    def __init__(self, session_factory: sessionmaker, panel: ServiceEntitlementPanel) -> None:
        self.session_factory = session_factory
        self.panel = panel

    async def tick(self) -> None:
        if isinstance(self.panel, PanelApiService):
            try:
                await run_pending_resource_operation(self.session_factory, self.panel)
            except Exception:
                # Transport failures can contain credentials; the persisted operation owns recovery.
                logger.warning("Resource operation remains pending reconciliation")
        async with self.session_factory() as session:
            service_ids = list(
                await session.scalars(
                    select(ServiceConnection.service_id)
                    .join(UserService, UserService.id == ServiceConnection.service_id)
                    .where(
                        UserService.user_id.is_not(None),
                        or_(
                            ServiceConnection.sync_pending.is_(True),
                            ServiceConnection.panel_user_uuid.is_not(None),
                            select(ServicePlanQuotaChange.plan_id)
                            .where(
                                UserService.desired_status != "cancelled",
                                ServicePlanQuotaChange.plan_id == UserService.plan_id,
                                ServicePlanQuotaChange.revision > UserService.quota_revision,
                            )
                            .exists(),
                        ),
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
                async with self.session_factory() as session:
                    gate = await session.scalar(
                        select(ServiceConnection.replacement_order_id).where(
                            ServiceConnection.service_id == service_id
                        )
                    )
                if gate is not None:
                    from bot.services.service_exit_replacement import run_exit_replacement

                    await run_exit_replacement(self.session_factory, service_id, self.panel)
                    continue
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
