"""Read authoritative stopped-identity counters before an audited manual recovery."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.service_panel_state import ServiceEntitlementPanel, owns_identity
from bot.services.service_usage_sync import usage_counters
from config.service_changes import ServiceChange
from db.dal.service_changes_dal import change_service
from db.dal.user_dal import lock_user_by_id
from db.dal.user_services_dal import ServiceConflict
from db.service_models import ServiceConnection, ServiceOrder, UserService


async def reconcile_service_usage(
    session: AsyncSession,
    *,
    service_id: str,
    user_id: int,
    actor_id: int,
    expected_revision: int,
    idempotency_key: str,
    change: ServiceChange,
    panel: ServiceEntitlementPanel | None,
) -> tuple[UserService, ServiceOrder, bool]:
    user = await lock_user_by_id(session, user_id)
    service = await session.get(UserService, service_id, populate_existing=True)
    if user is None or service is None or service.user_id != user_id:
        raise ServiceConflict("service_not_found", 404)
    previous = await session.scalar(
        select(ServiceOrder).where(
            ServiceOrder.request_owner_id == user_id,
            ServiceOrder.idempotency_key == idempotency_key,
        )
    )
    observation = None
    if previous is None:
        # Completed operations remain replayable after the worker revokes the identity.
        connection = await session.get(ServiceConnection, service_id, populate_existing=True)
        if connection is None or connection.state == "revoked":
            raise ServiceConflict("service_not_found", 404)
        if service.revision != expected_revision:
            raise ServiceConflict("service_revision_changed")
        if panel is None or connection.panel_user_uuid is None:
            raise ServiceConflict("usage_reconciliation_unavailable")
        try:
            result = await panel.get_user_by_uuid_lookup(connection.panel_user_uuid)
        except Exception:
            raise ServiceConflict("usage_reconciliation_unavailable") from None
        remote = result.get("user") if result.get("ok") is True else None
        if not isinstance(remote, dict) or not owns_identity(remote, connection):
            raise ServiceConflict("usage_reconciliation_unavailable")
        if service.desired_status not in {"paused", "cancelled"} or remote.get("status") not in {
            "DISABLED",
            "LIMITED",
            "EXPIRED",
        }:
            raise ServiceConflict("usage_reconciliation_pause_required")
        try:
            observation = usage_counters(remote)
        except ValueError:
            raise ServiceConflict("usage_reconciliation_unavailable") from None
    return await change_service(
        session,
        service_id=service_id,
        user_id=user_id,
        actor_id=actor_id,
        expected_revision=expected_revision,
        idempotency_key=idempotency_key,
        change=change,
        usage_observation=observation,
    )
