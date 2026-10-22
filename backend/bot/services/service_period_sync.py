"""Prepare a fixed cutover without interrupting access or writing a panel allowance."""

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import sessionmaker

from bot.services.service_panel_state import ServiceEntitlementPanel, locked_service, owns_identity
from bot.services.service_usage_sync import record_service_usage
from db.dal.service_periods_dal import cycle_due, prepare_period

logger = logging.getLogger(__name__)


async def prepare_service_cycle(
    session_factory: sessionmaker, service_id: str, panel: ServiceEntitlementPanel
) -> None:
    async with session_factory() as session:
        locked = await locked_service(session, service_id)
        if locked is None:
            return
        _user, service, connection = locked
        if (
            connection.panel_user_uuid is None
            or connection.cycle_cutover_bytes is not None
            or not cycle_due(service, datetime.now(UTC))
        ):
            return
        try:
            lookup = await panel.get_user_by_uuid_lookup(connection.panel_user_uuid)
            remote = lookup.get("user") if lookup.get("ok") is True else None
            if not isinstance(remote, dict) or not owns_identity(remote, connection):
                return
            record_service_usage(service, connection, remote)
            await prepare_period(session, service, connection, datetime.now(UTC))
            # No panel mutation precedes this commit; a crash cannot lose its cutover.
            await session.commit()
        except Exception:
            logger.exception("Monthly checkpoint needs retry for %s", service_id)
            await session.rollback()
