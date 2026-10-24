"""Read panel evidence without accepting traffic, changing rights or exposing credentials."""

from datetime import UTC, datetime
from typing import Literal, cast

from bot.app.web.admin_console_operations_schemas import (
    ConsoleServiceDiagnosticsOut,
    ConsoleServiceRemoteObservationOut,
)
from bot.services.service_operation_errors import safe_service_error
from bot.services.service_panel_state import (
    ServiceEntitlementPanel,
    matches_service_terms,
    owns_identity,
)
from bot.services.service_usage_sync import RECONCILIATION_ERRORS, usage_counters
from bot.services.user_service_access import service_status
from config.service_periods import as_utc
from config.service_plans import ServicePlanTerms
from db.models import User
from db.service_models import DedicatedExit, ServiceConnection, UserService


async def service_diagnostics(
    service: UserService,
    connection: ServiceConnection | None,
    resource: DedicatedExit | None,
    user: User | None,
    panel: ServiceEntitlementPanel | None,
) -> ConsoleServiceDiagnosticsOut:
    now = datetime.now(UTC)
    status = service_status(
        service, connection, resource, banned=bool(user and user.is_banned), now=now
    )
    terms = ServicePlanTerms.model_validate(service.terms)
    groups = [str(value) for value in terms.squad_uuids]
    if terms.resource_type == "dedicated":
        groups = (
            [resource.squad_uuid]
            if (
                resource
                and resource.enabled
                and resource.verified_at
                and resource.service_id == service.id
                and resource.resource_pool == terms.resource_pool
            )
            else []
        )
    errors = {
        "preparation": safe_service_error(connection.last_error) if connection else None,
        "entitlement": safe_service_error(connection.sync_error) if connection else None,
        "usage": safe_service_error(connection.usage_error) if connection else None,
    }
    target: Literal["enabled", "disabled", "unknown"] = (
        "disabled"
        if status != "active"
        else ("unknown" if connection and connection.usage_error else "enabled")
    )
    observation = ConsoleServiceRemoteObservationOut(
        availability="unconfigured" if panel is None else "not_prepared",
    )
    if connection and connection.panel_user_uuid is None and connection.state == "error":
        observation.availability = "unconfirmed"
        observation.error = "panel_identity_unconfirmed"
    if panel is not None and connection is not None and connection.panel_user_uuid:
        observation.attempted_at = datetime.now(UTC)
        observation.availability = "unavailable"
        observation.error = "panel_identity_unconfirmed"
        try:
            lookup = await panel.get_user_by_uuid_lookup(connection.panel_user_uuid)
            remote = lookup.get("user") if lookup.get("ok") is True else None
            if isinstance(remote, dict):
                observation.observed_at = datetime.now(UTC)
                observation.identity_matches = owns_identity(remote, connection)
                if not observation.identity_matches:
                    observation.availability = "conflict"
                    observation.error = "panel_identity_conflict"
                else:
                    observation.availability = "available"
                    observation.error = None
                    observation.terms_match = (
                        matches_service_terms(remote, service, groups, connection=connection)
                        if groups
                        else None
                    )
                    remote_status = remote.get("status")
                    if isinstance(remote_status, str) and remote_status in {
                        "ACTIVE",
                        "DISABLED",
                        "EXPIRED",
                        "LIMITED",
                    }:
                        observation.status = cast(
                            Literal["ACTIVE", "DISABLED", "EXPIRED", "LIMITED"], remote_status
                        )
                    try:
                        raw, lifetime = usage_counters(remote)
                        if lifetime - raw != (connection.usage_lifetime_offset or 0):
                            raise ValueError("panel_usage_reset")
                        if (
                            connection.usage_raw_bytes is not None
                            and raw < connection.usage_raw_bytes
                        ):
                            raise ValueError("panel_usage_regressed")
                        observation.usage_readable = True
                        observation.raw_used_bytes = raw
                    except ValueError as exc:
                        observation.usage_readable = False
                        observation.error = safe_service_error(str(exc))
            elif lookup.get("not_found") is True:
                observation.availability = "not_found"
                observation.observed_at = datetime.now(UTC)
                observation.error = "panel_identity_missing"
        except Exception:
            observation.availability = "unavailable"
            observation.error = "panel_identity_unconfirmed"
    if status == "active" and observation.usage_readable is False:
        target = "unknown"
    next_steps = []
    if connection and connection.usage_error in RECONCILIATION_ERRORS:
        next_steps.append("reconcile_usage")
    if observation.availability == "conflict":
        next_steps.append("review_identity")
    elif observation.terms_match is False:
        next_steps.append("review_resources")
    elif observation.availability in {"unavailable", "unconfigured"}:
        next_steps.append("check_panel_source")
    if resource and resource.verified_at is None:
        next_steps.append("verify_exit")
    if not next_steps:
        next_steps.append("inspect_operation_results")
    return ConsoleServiceDiagnosticsOut(
        service_id=service.id,
        user_id=service.user_id,
        service_revision=service.revision,
        status=status,
        desired_status=service.desired_status,
        target_access=target,
        connection_state=connection.state if connection else None,
        sync_pending=connection.sync_pending if connection else None,
        errors=errors,
        last_usage_sync_at=as_utc(service.last_usage_sync_at)
        if service.last_usage_sync_at
        else None,
        sync_confirmed_at=as_utc(connection.sync_confirmed_at)
        if connection and connection.sync_confirmed_at
        else None,
        local_observed_at=now,
        remote=observation,
        next_steps=next_steps,
    )
