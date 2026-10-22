"""Observe cumulative service traffic without resetting counters or delivering access."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from bot.services.panel_api_service import PanelApiService
from bot.services.service_panel_state import locked_service, owns_identity
from db.service_models import ServiceConnection, UserService

logger = logging.getLogger(__name__)
MAX_USAGE_BYTES = 2**53 - 1
RECONCILIATION_ERRORS = {"panel_usage_regressed", "panel_usage_reset"}


def _usage_total(remote: dict[str, Any]) -> int:
    traffic = remote.get("userTraffic")
    if not isinstance(traffic, dict):
        raise ValueError("panel_usage_invalid")
    current = traffic.get("usedTrafficBytes")
    lifetime = traffic.get("lifetimeUsedTrafficBytes")
    if any(
        type(value) is not int or not 0 <= value <= MAX_USAGE_BYTES for value in (current, lifetime)
    ):
        raise ValueError("panel_usage_invalid")
    if remote.get("trafficLimitStrategy") != "NO_RESET" or current != lifetime:
        # Our identities never reset the panel counter, including at business month boundaries.
        raise ValueError("panel_usage_reset")
    assert isinstance(lifetime, int)
    return lifetime


async def synchronize_service_usage(
    session_factory: sessionmaker, service_id: str, panel: PanelApiService
) -> None:
    async with session_factory() as session:
        locked = await locked_service(session, service_id)
        if locked is None:
            return
        _user, service, connection = locked
        reference = connection.panel_user_uuid
        if reference is None:
            return
        connection.usage_attempted_at = datetime.now(UTC)
        if connection.usage_error in RECONCILIATION_ERRORS:
            # A higher later value cannot distinguish a stale sample from lost history.
            await session.commit()
            return
        connection.usage_error = "panel_usage_unavailable"
        try:
            lookup = await panel.get_user_by_uuid_lookup(reference)
            remote = lookup.get("user") if lookup.get("ok") is True else None
            if not isinstance(remote, dict):
                if lookup.get("not_found"):
                    connection.usage_error = "panel_identity_missing"
            elif not owns_identity(remote, connection):
                connection.usage_error = "panel_identity_conflict"
            else:
                _record_usage(service, connection, remote)
        except Exception:
            logger.exception("Service usage observation needs retry for %s", service_id)
        await session.commit()


def _record_usage(
    service: UserService, connection: ServiceConnection, remote: dict[str, Any]
) -> None:
    try:
        total = _usage_total(remote)
    except ValueError as exc:
        connection.usage_error = str(exc)
        return
    previous = connection.usage_total_bytes
    if previous is None:
        previous = service.used_bytes
    if total < previous:
        connection.usage_error = "panel_usage_regressed"
        return
    used = service.used_bytes + total - previous
    if used > MAX_USAGE_BYTES:
        connection.usage_error = "panel_usage_invalid"
        return
    service.used_bytes = used
    service.last_usage_sync_at = datetime.now(UTC)
    connection.usage_total_bytes = total
    connection.usage_error = None


class ServiceUsageWorker:
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
                        ServiceConnection.panel_user_uuid.is_not(None),
                        ServiceConnection.state != "revoked",
                    )
                    .order_by(
                        ServiceConnection.usage_attempted_at.asc().nulls_first(),
                        ServiceConnection.service_id,
                    )
                    .limit(50)
                )
            )
        for service_id in service_ids:
            try:
                await synchronize_service_usage(self.session_factory, service_id, self.panel)
            except Exception:
                logger.exception("Service usage worker will retry %s", service_id)

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("Service usage worker tick failed")
            await asyncio.sleep(30)
