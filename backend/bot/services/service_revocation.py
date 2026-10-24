"""Terminal revocation retries one identity; inventory release still requires Node evidence."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.services.panel_api_service import PanelApiService
from bot.services.service_change_sync import synchronize_service_entitlement_locked
from bot.services.service_operations import record_revocation_result
from bot.services.service_panel_state import locked_service, owns_identity
from bot.services.service_period_sync import settle_cancelled_service_period
from bot.services.service_usage_sync import RECONCILIATION_ERRORS, record_service_usage
from db.dal.service_operations_dal import begin_execution
from db.service_models import ServiceConnection, ServiceOrder, UserService


async def _preserve_usage(
    session: AsyncSession,
    service: UserService,
    connection: ServiceConnection,
    remote: dict[str, object],
) -> bool:
    connection.usage_attempted_at = datetime.now(UTC)
    record_service_usage(service, connection, remote)
    if connection.usage_error:
        return False
    if connection.cycle_cutover_bytes is None:
        return True
    actor_id = await session.scalar(
        select(ServiceOrder.actor_id)
        .where(ServiceOrder.service_id == service.id, ServiceOrder.kind == "revoke")
        .limit(1)
    )
    if actor_id is None or not await settle_cancelled_service_period(
        session, service, connection, remote, actor_id=actor_id
    ):
        connection.sync_error = "service_revoke_cycle_pending"
        return False
    return True


async def revoke_service_identity(
    session_factory: sessionmaker, service_id: str, panel: PanelApiService
) -> None:
    async with session_factory() as session:
        locked = await locked_service(session, service_id)
        if (
            locked is None
            or locked[2].revoke_requested_at is None
            or locked[1].desired_status != "cancelled"
        ):
            return
        if locked[2].replacement_order_id is not None:
            await synchronize_service_entitlement_locked(session, *locked, panel)
            await session.commit()
            return
        await begin_execution(session, locked[1], "revocation", create=True)
        intent = (locked[1].user_id, locked[1].revision)
        await session.commit()
    await _revoke_service_identity(session_factory, service_id, panel, intent)
    async with session_factory() as session:
        locked = await locked_service(
            session, service_id, include_revoked=True, expected_intent=intent
        )
        if locked is not None:
            await record_revocation_result(session, locked[1], locked[2])
            await session.commit()


async def _revoke_service_identity(
    session_factory: sessionmaker,
    service_id: str,
    panel: PanelApiService,
    intent: tuple[int | None, int],
) -> None:
    async with session_factory() as session:
        locked = await locked_service(session, service_id, expected_intent=intent)
        if locked is None:
            return
        _user, service, connection = locked
        if connection.replacement_order_id is not None:
            await synchronize_service_entitlement_locked(session, *locked, panel)
            await session.commit()
            return
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
                    if isinstance(remote, dict):
                        # A readable identity needs fresh stopped-state and usage evidence.
                        connection.revoke_delete_requested_at = None
                    if not isinstance(remote, dict) or not owns_identity(remote, connection):
                        await session.commit()
                        return
                    # Even a not-yet-stopped identity can expose a counter reset.
                    connection.usage_attempted_at = datetime.now(UTC)
                    record_service_usage(service, connection, remote)
                    await panel.update_user_status_on_panel(reference, False)
                    result = await panel.get_user_by_uuid_lookup(reference)
                    remote = result.get("user") if result.get("ok") is True else None
                    if isinstance(remote, dict) and owns_identity(remote, connection):
                        record_service_usage(service, connection, remote)
                    if (
                        not isinstance(remote, dict)
                        or not owns_identity(remote, connection)
                        or remote.get("status") not in {"DISABLED", "EXPIRED", "LIMITED"}
                        or connection.usage_error in RECONCILIATION_ERRORS
                    ):
                        await session.commit()
                        return
                    # Preserve the last readable counter before deleting credentials.
                    if not await _preserve_usage(session, service, connection, remote):
                        await session.commit()
                        return
                    # A crash after DELETE must not discard the final accepted observation.
                    await session.commit()
                    locked = await locked_service(session, service_id, expected_intent=intent)
                    if locked is None:
                        return
                    _user, service, connection = locked
                    if (
                        service.desired_status != "cancelled"
                        or connection.replacement_order_id is not None
                        or connection.panel_user_uuid != reference
                    ):
                        return
                    result = await panel.get_user_by_uuid_lookup(reference)
                    remote = result.get("user") if result.get("ok") is True else None
                    if isinstance(remote, dict) and owns_identity(remote, connection):
                        record_service_usage(service, connection, remote)
                    if result.get("not_found") is not True and (
                        not isinstance(remote, dict)
                        or not owns_identity(remote, connection)
                        or remote.get("status") not in {"DISABLED", "EXPIRED", "LIMITED"}
                    ):
                        await session.commit()
                        return
                    if isinstance(remote, dict):
                        if not await _preserve_usage(session, service, connection, remote):
                            await session.commit()
                            return
                        # The final read may contain late bytes after the first settlement.
                        # Commit the deletion intent together with its accepted counters.
                        connection.revoke_delete_requested_at = datetime.now(UTC)
                        await session.commit()
                        locked = await locked_service(session, service_id, expected_intent=intent)
                        if locked is None:
                            return
                        _user, service, connection = locked
                        if (
                            service.desired_status != "cancelled"
                            or connection.replacement_order_id is not None
                            or connection.panel_user_uuid != reference
                            or connection.usage_error is not None
                            or connection.cycle_cutover_bytes is not None
                            or connection.revoke_delete_requested_at is None
                        ):
                            connection.revoke_delete_requested_at = None
                            await session.commit()
                            return
                    absent = result.get("not_found") is True
                    if not absent:
                        await panel.delete_user_from_panel(reference)
                        result = await panel.get_user_by_uuid_lookup(reference)
                        absent = result.get("not_found") is True
                        remote = result.get("user") if result.get("ok") is True else None
                        if isinstance(remote, dict):
                            # DELETE may be delayed; this observation supersedes its evidence.
                            connection.revoke_delete_requested_at = None
                            if owns_identity(remote, connection):
                                await _preserve_usage(session, service, connection, remote)
                            else:
                                connection.sync_error = "panel_identity_conflict"
            if absent:
                if (
                    connection.cycle_cutover_bytes is not None
                    or connection.usage_error
                    not in {None, "panel_identity_missing", "panel_usage_unavailable"}
                    or (reference is not None and connection.revoke_delete_requested_at is None)
                ):
                    connection.sync_error = "service_revoke_usage_unconfirmed"
                    await session.commit()
                    return
                connection.state = "revoked"
                connection.revoked_at = datetime.now(UTC)
                connection.sync_pending = False
                connection.sync_error = None
                connection.last_error = None
                connection.usage_error = None
                connection.sync_confirmed_at = connection.revoked_at
        except Exception:
            # Persist intent; don't log exception text or remote credentials.
            pass
        await record_revocation_result(session, service, connection)
        await session.commit()
