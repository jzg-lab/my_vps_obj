"""只读资源预检；不占用出口，不替代开通事务或交付核对。"""

from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.admin_console_nodes_panel import NodeInventory
from bot.app.web.admin_console_operations_schemas import (
    ConsolePreflightCheckOut,
    ConsoleServicePreflightBody,
    ConsoleServicePreflightOut,
)
from config.service_plans import ServicePlanTerms
from db.models import User
from db.service_models import DedicatedExit, ServicePlan


async def service_preflight(
    session: AsyncSession, body: ConsoleServicePreflightBody, inventory: NodeInventory
) -> ConsoleServicePreflightOut:
    checks: list[ConsolePreflightCheckOut] = []

    def check(code: str, allowed: bool, reason: str) -> None:
        checks.append(
            ConsolePreflightCheckOut(
                code=code,
                status="passed" if allowed else "blocked",
                reason=None if allowed else reason,
            )
        )

    user = await session.get(User, body.user_id)
    plan = await session.get(ServicePlan, body.plan_id)
    terms = ServicePlanTerms.model_validate(plan.terms) if plan else None
    check("account", user is not None and not user.is_banned, "account_unavailable")
    check("plan", plan is not None and plan.enabled, "plan_unavailable")
    check(
        "plan_revision",
        plan is not None and plan.revision == body.expected_revision,
        "plan_revision_changed",
    )
    resource = await session.get(DedicatedExit, body.exit_id) if body.exit_id else None
    groups: set[str] = set()
    verified = True
    if terms and terms.resource_type == "dedicated":
        check(
            "exit",
            resource is not None
            and resource.enabled
            and resource.service_id is None
            and resource.hold_order_id is None
            and resource.resource_pool == terms.resource_pool,
            "exit_unavailable",
        )
        verified = resource is not None and resource.verified_at is not None
        if resource:
            groups.add(resource.squad_uuid)
    elif terms:
        check("exit", body.exit_id is None, "shared_plan_cannot_bind_exit")
        groups = {str(value) for value in terms.squad_uuids}
    allow_pending_creation = all(item.status == "passed" for item in checks)

    known_groups = {str(squad.uuid) for squad in inventory.squads.rows}
    nodes = [node for node in inventory.nodes.rows if groups & inventory.node_groups(node)]
    hosts = {host.id: host for node in nodes for host in inventory.node_hosts(node, groups=groups)}
    source_complete = inventory.coverage == "complete"
    unknown_hosts = any(
        host.permits(groups) is None
        for host in inventory.hosts.rows
        if any(
            item.uuid == host.inbound.configProfileInboundUuid
            for squad in inventory.squads.rows
            if str(squad.uuid) in groups
            for item in squad.inbounds
        )
    )
    checks.append(
        ConsolePreflightCheckOut(
            code="resource_sources",
            status="passed" if source_complete and not unknown_hosts else "unknown",
            reason=None
            if source_complete and not unknown_hosts
            else "resource_observation_incomplete",
        )
    )
    checks.append(
        ConsolePreflightCheckOut(
            code="groups",
            status="passed"
            if groups and groups <= known_groups
            else ("blocked" if inventory.squads.source.availability == "available" else "unknown"),
            reason=None if groups and groups <= known_groups else "configured_groups_unavailable",
        )
    )
    usable = [node for node in nodes if inventory.node_hosts(node, groups=groups)]
    online = any(
        node.isConnected is True
        and node.isDisabled is False
        and any(
            host.is_disabled is False and host.is_hidden is False
            for host in inventory.node_hosts(node, groups=groups)
        )
        for node in usable
    )
    uncertain = any(
        node.isConnected is None
        or node.isDisabled is None
        or any(
            host.is_disabled is None or host.is_hidden is None
            for host in inventory.node_hosts(node, groups=groups)
        )
        for node in usable
    )
    checks.append(
        ConsolePreflightCheckOut(
            code="subscription_path",
            status="passed"
            if online and source_complete
            else ("unknown" if uncertain or not source_complete or unknown_hosts else "blocked"),
            reason=None if online and source_complete else "subscription_path_unconfirmed",
        )
    )
    checks.append(
        ConsolePreflightCheckOut(
            code="exit_verification",
            status="passed" if verified else "blocked",
            reason=None if verified else "exit_verification_required",
        )
    )
    readiness: Literal["ready", "blocked", "unknown"] = (
        "blocked"
        if any(item.status == "blocked" for item in checks)
        else ("unknown" if any(item.status == "unknown" for item in checks) else "ready")
    )
    checks.append(
        ConsolePreflightCheckOut(
            code="identity_and_metering",
            status="unknown",
            reason="requires_service_preparation",
        )
    )
    return ConsoleServicePreflightOut(
        user_id=body.user_id,
        plan_id=body.plan_id,
        plan_revision=plan.revision if plan else None,
        exit_id=body.exit_id,
        exit_revision=resource.revision if resource else None,
        terms=terms,
        allow_pending_creation=allow_pending_creation,
        resource_readiness=readiness,
        checks=checks,
        configured_group_ids=sorted(groups),
        nodes=[inventory.node_out(node) for node in nodes],
        hosts=list(hosts.values()),
        sources=inventory.sources,
        local_observed_at=datetime.now(UTC),
    )
