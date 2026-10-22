"""Shared service eligibility for presentation and account connection controls."""

from datetime import UTC, datetime

from config.service_periods import as_utc
from config.service_plans import ServicePlanTerms
from db.service_models import DedicatedExit, ServiceConnection, UserService


def service_status(
    service: UserService,
    connection: ServiceConnection | None,
    resource: DedicatedExit | None,
    *,
    banned: bool = False,
    now: datetime | None = None,
    require_ready: bool = True,
) -> str:
    now = as_utc(now or datetime.now(UTC))
    if banned:
        return "account_banned"
    if service.user_id is None:
        return "cancelled"
    if service.desired_status != "active":
        return service.desired_status
    if as_utc(service.expires_at) <= now:
        return "expired"
    if service.used_bytes >= service.quota_bytes:
        return "exhausted"
    if (
        as_utc(service.starts_at) > now
        or connection is None
        or (require_ready and connection.state != "ready")
    ):
        return "pending"
    terms = ServicePlanTerms.model_validate(service.terms)
    if terms.resource_type == "dedicated" and (
        resource is None
        or resource.verified_at is None
        or not resource.enabled
        or resource.service_id != service.id
        or resource.resource_pool != terms.resource_pool
    ):
        return "pending"
    return "active"


def service_ready_for_delivery(
    service: UserService,
    connection: ServiceConnection,
    resource: DedicatedExit | None,
    *,
    banned: bool = False,
    now: datetime | None = None,
) -> bool:
    """Local preconditions only; the caller must also verify remote identity/terms."""
    return (
        connection.state in {"pending", "ready"}
        and connection.panel_user_uuid is not None
        and connection.last_error is None
        and connection.usage_total_bytes is not None
        and connection.usage_error is None
        and service.last_usage_sync_at is not None
        and not connection.sync_pending
        and service_status(
            service, connection, resource, banned=banned, now=now, require_ready=False
        )
        == "active"
    )
