"""Terminal revocation retries one identity; inventory release still requires Node evidence."""

from datetime import UTC, datetime

from sqlalchemy.orm import sessionmaker

from bot.services.panel_api_service import PanelApiService
from bot.services.service_panel_state import locked_service, owns_identity
from bot.services.service_usage_sync import RECONCILIATION_ERRORS, record_service_usage


async def revoke_service_identity(
    session_factory: sessionmaker, service_id: str, panel: PanelApiService
) -> None:
    async with session_factory() as session:
        locked = await locked_service(session, service_id)
        if locked is None:
            return
        _user, service, connection = locked
        if (
            connection.state == "revoked"
            or connection.revoke_requested_at is None
            or service.desired_status != "cancelled"
        ):
            return
        connection.attempted_at = datetime.now(UTC)
        connection.sync_pending = True
        connection.sync_error = "service_revoke_pending"
        try:
            reference = connection.panel_user_uuid
            if reference is None:
                users = await panel.get_users_by_filter(username=connection.username)
                if users is None or len(users) > 1:
                    await session.commit()
                    return
                if not users and connection.state == "error":
                    # A timed-out create can still be in flight. An empty name lookup
                    # cannot turn an uncertain submission into "never submitted".
                    await session.commit()
                    return
                if users:
                    if not owns_identity(users[0], connection):
                        connection.sync_error = "panel_identity_conflict"
                        await session.commit()
                        return
                    reference = str(users[0]["uuid"])
                    connection.panel_user_uuid = reference
            absent = reference is None
            if reference is not None:
                result = await panel.get_user_by_uuid_lookup(reference)
                absent = result.get("not_found") is True
                if not absent:
                    remote = result.get("user") if result.get("ok") is True else None
                    if not isinstance(remote, dict) or not owns_identity(remote, connection):
                        await session.commit()
                        return
                    await panel.update_user_status_on_panel(reference, False)
                    result = await panel.get_user_by_uuid_lookup(reference)
                    remote = result.get("user") if result.get("ok") is True else None
                    if (
                        not isinstance(remote, dict)
                        or not owns_identity(remote, connection)
                        or remote.get("status") not in {"DISABLED", "EXPIRED", "LIMITED"}
                        or connection.usage_error in RECONCILIATION_ERRORS
                    ):
                        await session.commit()
                        return
                    # Preserve the last readable counter before deleting credentials.
                    connection.usage_attempted_at = datetime.now(UTC)
                    record_service_usage(service, connection, remote)
                    if connection.usage_error:
                        await session.commit()
                        return
                    if connection.cycle_cutover_bytes is not None:
                        # A pending cutover needs terminal accounting, not a fabricated
                        # successful allowance confirmation or a frozen final usage page.
                        connection.sync_error = "service_revoke_cycle_pending"
                        await session.commit()
                        return
                    # A crash after DELETE must not discard the final accepted observation.
                    await session.commit()
                    locked = await locked_service(session, service_id)
                    if locked is None:
                        return
                    _user, service, connection = locked
                    if (
                        service.desired_status != "cancelled"
                        or connection.panel_user_uuid != reference
                    ):
                        return
                    result = await panel.get_user_by_uuid_lookup(reference)
                    remote = result.get("user") if result.get("ok") is True else None
                    if result.get("not_found") is not True and (
                        not isinstance(remote, dict) or not owns_identity(remote, connection)
                    ):
                        await session.commit()
                        return
                    await panel.delete_user_from_panel(reference)
                    result = await panel.get_user_by_uuid_lookup(reference)
                    absent = result.get("not_found") is True
            if absent:
                connection.state = "revoked"
                connection.revoked_at = datetime.now(UTC)
                connection.sync_pending = False
                connection.sync_error = None
                connection.last_error = None
                connection.sync_confirmed_at = connection.revoked_at
        except Exception:
            # Persist intent; don't log exception text or remote credentials.
            pass
        await session.commit()
