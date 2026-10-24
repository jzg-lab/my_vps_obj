"""Persist ban intent before remote calls, then retry every account identity safely."""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker

from bot.services.account_roles import can_ban_account
from bot.services.service_change_sync import synchronize_service_entitlement_locked
from bot.services.service_operations import record_entitlement_result
from bot.services.service_panel_state import ServiceEntitlementPanel
from bot.services.user_service_access import service_status
from db.dal import user_dal
from db.dal.account_access_dal import enqueue_access_sync
from db.dal.account_operations_dal import (
    begin_account_attempt,
    current_account_attempt,
    finish_account_attempt,
)
from db.dal.resource_operations_dal import coordinate_resources, resource_gate_active
from db.dal.service_operations_dal import begin_execution
from db.dal.user_reads_dal import normalize_panel_user_reference
from db.dal.user_services_dal import ServiceConflict
from db.models import Subscription, User
from db.service_models import AccountAccessSync, DedicatedExit, ServiceConnection, UserService

logger = logging.getLogger(__name__)


async def set_account_ban(
    session: AsyncSession, *, user_id: int, actor_id: int, banned: bool
) -> User:
    await coordinate_resources(session)
    if banned and not await can_ban_account(session, actor_id, user_id):
        raise ServiceConflict("forbidden", 403)
    user = await user_dal.lock_user_by_id(session, user_id)
    if user is None:
        raise ServiceConflict("not_found", 404)
    before_banned = bool(user.is_banned)
    user.is_banned = banned
    await enqueue_access_sync(session, user_id, actor_id=actor_id, before_banned=before_banned)
    return user


async def _apply_reference(panel: ServiceEntitlementPanel, reference: str, enable: bool) -> bool:
    try:
        await panel.update_user_status_on_panel(reference, enable, log_response=False)
    except Exception:
        logger.warning("Account connection update needs verification")
    try:
        result = await panel.get_user_by_uuid_lookup(reference, log_response=False)
    except Exception:
        logger.warning("Account connection verification failed")
        return False
    if result.get("not_found") is True:
        return not enable
    remote = result.get("user")
    if result.get("ok") is not True or not isinstance(remote, dict):
        return False
    return remote.get("status") in ({"ACTIVE"} if enable else {"DISABLED", "EXPIRED", "LIMITED"})


async def synchronize_account_access(
    session: AsyncSession, user_id: int, panel: ServiceEntitlementPanel | None
) -> AccountAccessSync | None:
    await coordinate_resources(session)
    user = await user_dal.lock_user_by_id(session, user_id)
    if user is None:
        return None
    job = await session.get(AccountAccessSync, user_id, populate_existing=True)
    if job is None or not job.pending:
        return job
    attempt = await begin_account_attempt(session, user, job)
    attempt_revisions: dict[str, int] = {}
    if panel is not None:
        service_targets = await session.execute(
            select(UserService, ServiceConnection, DedicatedExit)
            .join(ServiceConnection, ServiceConnection.service_id == UserService.id)
            .outerjoin(DedicatedExit, DedicatedExit.service_id == UserService.id)
            .where(
                UserService.user_id == user_id,
                ServiceConnection.panel_user_uuid.is_not(None),
                ServiceConnection.state != "revoked",
            )
            .execution_options(populate_existing=True)
        )
        for service, connection, resource in service_targets:
            if connection.replacement_order_id is not None:
                continue
            enable = (
                service_status(service, connection, resource, banned=bool(user.is_banned))
                == "active"
            )
            if enable and connection.sync_pending:
                continue
            await begin_execution(session, service, "entitlement")
            if connection.state == "ready":
                await begin_execution(session, service, "delivery")
            attempt_revisions[service.id] = service.revision
    await session.commit()
    # The commit releases the account lock; restrictions and intent may have changed.
    await coordinate_resources(session)
    user = await user_dal.lock_user_by_id(session, user_id)
    if user is None:
        return None
    job = await session.get(AccountAccessSync, user_id, populate_existing=True)
    if job is None or not job.pending:
        return job
    if await current_account_attempt(session, user, job, attempt) is None:
        return job
    now = datetime.now(UTC)
    references = await user_dal.get_panel_user_uuids_for_user(session, user_id, user=user)
    active_legacy = {
        normalize_panel_user_reference(reference)
        for reference in await session.scalars(
            select(Subscription.panel_user_uuid).where(
                Subscription.user_id == user_id,
                Subscription.is_active.is_(True),
                Subscription.end_date > now,
            )
        )
    }
    targets = {
        reference: not user.is_banned and reference in active_legacy for reference in references
    }
    rows = await session.execute(
        select(UserService, ServiceConnection, DedicatedExit)
        .outerjoin(ServiceConnection, ServiceConnection.service_id == UserService.id)
        .outerjoin(DedicatedExit, DedicatedExit.service_id == UserService.id)
        .where(UserService.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    error: str | None = None
    for service, connection, resource in rows:
        if connection is None:
            error = "service_connection_unconfirmed"
            continue
        if connection.panel_user_uuid is None:
            if connection.state not in {"pending", "revoked"}:
                error = "service_connection_unconfirmed"
            continue
        enable = (
            service_status(service, connection, resource, banned=bool(user.is_banned), now=now)
            == "active"
        )
        targets.pop(connection.panel_user_uuid, None)
        if connection.replacement_order_id is not None:
            error = error or "exit_replacement_in_progress"
            continue
        if connection.state == "revoked":
            continue
        if enable and connection.sync_pending:
            error = error or "service_change_pending"
            continue
        if panel is None:
            error = error or "panel_service_unavailable"
            continue
        if attempt_revisions.get(service.id) != service.revision:
            # A later command needs its own durable marker before any remote call.
            error = error or "service_change_pending"
            continue
        try:
            confirmed = await synchronize_service_entitlement_locked(
                session, user, service, connection, panel
            )
        except Exception:
            logger.warning("Account service entitlement needs retry")
            confirmed = False
        await record_entitlement_result(session, user, service, connection, confirmed=confirmed)
        if not confirmed:
            error = error or "panel_access_unconfirmed"
    for reference, enable in targets.items():
        if panel is None:
            error = error or "panel_service_unavailable"
        elif enable and await resource_gate_active(session):
            error = error or "resource_operation_in_progress"
        elif not await _apply_reference(panel, reference, enable):
            error = error or "panel_access_unconfirmed"
    await finish_account_attempt(session, user, job, attempt, error=error)
    await session.commit()
    await session.refresh(job)
    return job


async def synchronize_access_after_commit(
    session: AsyncSession, user_id: int, panel: ServiceEntitlementPanel | None
) -> bool:
    """Return whether a saved change still needs retry, without undoing its intent."""
    try:
        job = await synchronize_account_access(session, user_id, panel)
        return bool(job and job.pending)
    except Exception:
        logger.warning("Saved account change awaits connection retry for user %s", user_id)
        await session.rollback()
        return True


class AccountAccessWorker:
    def __init__(
        self,
        session_factory: sessionmaker | async_sessionmaker[AsyncSession],
        panel: ServiceEntitlementPanel | None,
    ) -> None:
        self.session_factory = session_factory
        self.panel = panel

    async def tick(self) -> None:
        async with self.session_factory() as session:
            user_ids = list(
                await session.scalars(
                    select(AccountAccessSync.user_id)
                    .where(AccountAccessSync.pending.is_(True))
                    .order_by(
                        AccountAccessSync.attempted_at.asc().nulls_first(),
                        AccountAccessSync.user_id,
                    )
                    .limit(50)
                )
            )
        for user_id in user_ids:
            try:
                async with self.session_factory() as session:
                    await synchronize_account_access(session, user_id, self.panel)
            except Exception:
                logger.warning("Account access sync remains pending for user %s", user_id)

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                logger.warning("Account access sync worker tick failed")
            await asyncio.sleep(30)
