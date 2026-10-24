"""Replacement-only entitlement evaluation under a live, validated binding lock."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.service_operations import enabling_block
from bot.services.service_panel_state import panel_traffic_limit
from config.service_periods import as_utc
from db.dal.service_exit_replacement_dal import ReplacementState, _live
from db.dal.service_periods_dal import confirm_period
from db.dal.user_services_dal import ServiceConflict
from db.models import User


def period_allowance_blocked(state: ReplacementState) -> bool:
    return state.connection.cycle_cutover_bytes is not None and (
        as_utc(state.service.expires_at) <= datetime.now(UTC)
        or state.service.desired_status == "cancelled"
    )


async def confirm_replacement_period(session: AsyncSession, state: ReplacementState) -> None:
    if period_allowance_blocked(state):
        raise ServiceConflict("panel_cycle_unconfirmed")
    await confirm_period(session, state.service, state.connection, datetime.now(UTC))


async def restore_reasons(session: AsyncSession, state: ReplacementState) -> list[str]:
    _live(state)
    if (
        state.progress.stage != "restoring"
        or not state.progress.binding_audit_id
        or not state.progress.confirmation_audit_id
        or state.new_exit.service_id != state.service.id
        or state.old_exit.hold_order_id != state.order.id
    ):
        raise ServiceConflict("exit_replacement_state_invalid")
    user = await session.get(User, state.service.user_id)
    if user is None:
        raise ServiceConflict("service_not_found", 404)
    service, connection = state.service, state.connection
    reasons: list[str] = []
    block = enabling_block(user, service)
    if block:
        reasons.append(block)
    if service.desired_status != "active":
        reasons.append(
            "service_paused" if service.desired_status == "paused" else "service_cancelled"
        )
    if as_utc(service.starts_at) > datetime.now(UTC):
        reasons.append("service_not_started")
    if (
        connection.state != "ready"
        or connection.last_error is not None
        or connection.revoke_requested_at is not None
    ):
        reasons.append("service_not_deliverable")
    if (
        not state.new_exit.enabled
        or state.new_exit.verified_at is None
        or state.new_exit.resource_pool != service.terms.get("resource_pool")
    ):
        reasons.append("exit_unavailable")
    if connection.usage_error is not None or connection.usage_total_bytes is None:
        raise ServiceConflict("exit_replacement_usage_unconfirmed")
    return reasons


def replacement_terms(
    state: ReplacementState, groups: list[str], *, enable: bool
) -> dict[str, object]:
    if period_allowance_blocked(state):
        raise ServiceConflict("panel_cycle_unconfirmed")
    return {
        "activeInternalSquads": groups,
        "status": "ACTIVE" if enable else "DISABLED",
        "trafficLimitBytes": panel_traffic_limit(state.service, state.connection),
        "expireAt": as_utc(state.service.expires_at).isoformat(timespec="milliseconds"),
        "trafficLimitStrategy": "NO_RESET",
    }
