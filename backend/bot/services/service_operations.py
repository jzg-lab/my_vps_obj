"""Stage-specific evidence; saved intentions and panel read-back are different facts."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.service_operation_errors import CONFIRMED_SERVICE_FAILURES
from bot.services.user_service_access import service_status
from config.service_periods import as_utc
from db.dal.service_operations_dal import finish_execution
from db.dal.user_services_dal import get_service_resource
from db.models import User
from db.service_models import ServiceConnection, UserService


def enabling_block(user: User, service: UserService) -> str | None:
    if user.is_banned:
        return "account_banned"
    if as_utc(service.expires_at) <= datetime.now(UTC):
        return "service_expired"
    if service.used_bytes >= service.quota_bytes:
        return "service_exhausted"
    return None


async def record_entitlement_result(
    session: AsyncSession,
    user: User,
    service: UserService,
    connection: ServiceConnection,
    *,
    confirmed: bool,
) -> None:
    if service.desired_status == "cancelled":
        return
    _, resource = await get_service_resource(session, service.id)
    active = service_status(service, connection, resource, banned=bool(user.is_banned)) == "active"
    blocked = (
        (enabling_block(user, service) or "service_not_deliverable")
        if service.desired_status == "active" and not active
        else None
    )
    success = bool(
        confirmed
        and not connection.sync_pending
        and connection.usage_error is None
        and connection.cycle_cutover_bytes is None
        and (
            (connection.panel_user_uuid and connection.sync_confirmed_at is not None)
            or (
                connection.panel_user_uuid is None
                and service.desired_status == "paused"
                and connection.state == "pending"
                and connection.last_error is None
            )
        )
    )
    error = connection.usage_error or connection.sync_error
    if connection.sync_error in CONFIRMED_SERVICE_FAILURES:
        error = connection.sync_error
    await finish_execution(
        session,
        service,
        "entitlement",
        success=success,
        error=error,
        enabling_error=blocked,
        attempted_at=connection.sync_attempted_at if connection.panel_user_uuid else None,
    )
    if connection.state == "ready":
        await finish_execution(
            session,
            service,
            "delivery",
            success=success and active,
            error=error,
            enabling_error=blocked,
            capture_failure=False,
            attempted_at=connection.sync_attempted_at,
        )


async def record_revocation_result(
    session: AsyncSession,
    service: UserService,
    connection: ServiceConnection,
) -> None:
    await finish_execution(
        session,
        service,
        "revocation",
        success=connection.state == "revoked" and connection.revoked_at is not None,
        error=connection.usage_error or connection.sync_error or "service_revoke_pending",
    )
