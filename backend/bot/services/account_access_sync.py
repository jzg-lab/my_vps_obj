"""Persist ban intent before remote calls, then retry every account identity safely."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.services.account_roles import can_ban_account
from bot.services.user_service_access import service_status
from db.dal import user_dal
from db.dal.account_access_dal import enqueue_access_sync
from db.dal.user_reads_dal import normalize_panel_user_reference
from db.dal.user_services_dal import ServiceConflict
from db.models import Subscription, User
from db.service_models import AccountAccessSync, DedicatedExit, ServiceConnection, UserService

logger = logging.getLogger(__name__)


class AccountAccessPanel(Protocol):
    async def update_user_status_on_panel(
        self, user_uuid: str, enable: bool, log_response: bool = False
    ) -> bool: ...

    async def get_user_by_uuid_lookup(
        self, user_uuid: str, log_response: bool = False
    ) -> dict[str, Any]: ...


async def set_account_ban(
    session: AsyncSession, *, user_id: int, actor_id: int, banned: bool
) -> User:
    if banned and not await can_ban_account(session, actor_id, user_id):
        raise ServiceConflict("forbidden", 403)
    user = await user_dal.lock_user_by_id(session, user_id)
    if user is None:
        raise ServiceConflict("not_found", 404)
    user.is_banned = banned
    await enqueue_access_sync(session, user_id)
    return user


async def _apply_reference(panel: AccountAccessPanel, reference: str, enable: bool) -> bool:
    try:
        await panel.update_user_status_on_panel(reference, enable, log_response=False)
    except Exception:
        logger.warning("Account connection update needs verification", exc_info=True)
    try:
        result = await panel.get_user_by_uuid_lookup(reference, log_response=False)
    except Exception:
        logger.warning("Account connection verification failed", exc_info=True)
        return False
    if result.get("not_found") is True:
        return not enable
    remote = result.get("user")
    if result.get("ok") is not True or not isinstance(remote, dict):
        return False
    return remote.get("status") in ({"ACTIVE"} if enable else {"DISABLED", "EXPIRED", "LIMITED"})


async def synchronize_account_access(
    session: AsyncSession, user_id: int, panel: AccountAccessPanel | None
) -> AccountAccessSync | None:
    user = await user_dal.lock_user_by_id(session, user_id)
    if user is None:
        return None
    job = await session.get(AccountAccessSync, user_id, populate_existing=True)
    if job is None or not job.pending:
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
        if enable and connection.sync_pending:
            targets.pop(connection.panel_user_uuid, None)
            error = error or "service_change_pending"
        else:
            targets[connection.panel_user_uuid] = enable
    for reference, enable in targets.items():
        if panel is None:
            error = error or "panel_service_unavailable"
        elif not await _apply_reference(panel, reference, enable):
            error = error or "panel_access_unconfirmed"
    job.pending = error is not None
    job.last_error = error
    job.attempted_at = now
    await session.commit()
    await session.refresh(job)
    return job


async def synchronize_access_after_commit(
    session: AsyncSession, user_id: int, panel: AccountAccessPanel | None
) -> bool:
    """Return whether a saved change still needs retry, without undoing its intent."""
    try:
        job = await synchronize_account_access(session, user_id, panel)
        return bool(job and job.pending)
    except Exception:
        logger.exception("Saved account change awaits connection retry for user %s", user_id)
        await session.rollback()
        return True


class AccountAccessWorker:
    def __init__(self, session_factory: sessionmaker, panel: AccountAccessPanel | None) -> None:
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
                logger.exception("Account access sync remains pending for user %s", user_id)

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("Account access sync worker tick failed")
            await asyncio.sleep(30)
