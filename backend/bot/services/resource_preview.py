"""Compute potential impact without changing resources or service entitlements."""

from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID

from pydantic import ValidationError

from bot.app.web.admin_console_resource_schemas import (
    ConsoleResourcePreviewOut,
    ResourceChange,
    ResourceGroupChange,
    ResourceGroupCreate,
    ResourceHostChange,
    ResourceHostCreate,
    ResourceImpactOut,
    ResourceImpactServiceOut,
    ResourceNodeCreate,
    ResourceSourceOut,
    ResourceValuesOut,
)
from bot.services.resource_preview_authorizations import PreviewAuthorizations
from bot.services.resource_preview_panel import PreviewInventory, digest
from bot.services.resource_preview_values import (
    group_values,
    host_values,
    node_values,
    topology_problems,
)
from config.service_plans import ServicePlanTerms
from db.dal.admin_console_nodes_dal import (
    ReplacementImpact,
    ServiceResourceRow,
    replacement_impacts,
)


def _ids(values: set[UUID]) -> list[str]:
    return sorted(str(value) for value in values)


def _impact(
    groups: set[UUID],
    nodes: set[UUID],
    profiles: set[UUID],
    services: list[ResourceImpactServiceOut],
    replacements: list[ReplacementImpact],
) -> ResourceImpactOut:
    group_ids = set(_ids(groups))
    related = (
        [impact for impact in replacements if impact.affects(group_ids)]
        if groups or nodes or profiles
        else []
    )
    service_ids = {impact.service_id for impact in related if impact.service_id is not None}
    matched = [
        service
        for service in services
        if set(service.group_ids) & group_ids or service.service_id in service_ids
    ]
    # The public row requires an owner; archived IDs stay in totals and affected_service_ids.
    service_ids.update(service.service_id for service in matched)
    customers = sorted(
        {service.customer_id for service in matched}
        | {impact.customer_id for impact in related if impact.customer_id is not None}
    )
    return ResourceImpactOut(
        group_ids=_ids(groups),
        node_ids=_ids(nodes),
        profile_ids=_ids(profiles),
        services=matched,
        customer_ids=customers,
        service_total=len(service_ids),
        customer_total=len(customers),
    )


def _local_services(
    rows: list[ServiceResourceRow],
    blockers: set[str],
    authorizations: PreviewAuthorizations | None,
) -> tuple[list[ResourceImpactServiceOut], list[object]]:
    services: list[ResourceImpactServiceOut] = []
    revisions: list[object] = []
    seen: set[str] = set()
    for service, connection, resource, user in rows:
        if service.id in seen:
            blockers.add("duplicate_service_binding")
            continue
        seen.add(service.id)
        observed = authorizations.groups.get(service.id) if authorizations else None
        try:
            terms = ServicePlanTerms.model_validate(service.terms)
            groups = set(terms.squad_uuids)
            if terms.resource_type == "dedicated":
                # Disabled or unverified bound exits may still have remote connections.
                groups = {UUID(resource.squad_uuid)} if resource else set()
                if (
                    resource is None
                    and connection
                    and connection.panel_user_uuid
                    and not (connection.state == "revoked" and observed == set())
                ):
                    blockers.add("missing_dedicated_binding")
            configured = groups.copy()
            if observed is None:
                blockers.add("authorizations_unavailable")
            groups |= observed or set()
            services.append(
                ResourceImpactServiceOut(
                    service_id=service.id,
                    customer_id=cast(int, user.user_id),
                    name=terms.name,
                    group_ids=_ids(groups),
                    configured_group_ids=_ids(configured),
                    observed_group_ids=_ids(observed or set()),
                    connection_state=connection.state if connection else None,
                )
            )
            revisions.append(
                [
                    service.id,
                    user.user_id,
                    bool(user.is_banned),
                    service.revision,
                    service.desired_status,
                    service.expires_at.isoformat(),
                    _ids(groups),
                    connection.state if connection else None,
                    connection.panel_user_uuid if connection else None,
                    [
                        resource.id,
                        resource.revision,
                        resource.enabled,
                        resource.verified_at.isoformat() if resource.verified_at else None,
                    ]
                    if resource
                    else None,
                ]
            )
        except (ValidationError, ValueError):
            blockers.add("invalid_service_scope")
    return sorted(services, key=lambda value: value.service_id), sorted(revisions, key=str)


def build_resource_preview(
    change: ResourceChange,
    inventory: PreviewInventory,
    rows: list[ServiceResourceRow],
    *,
    local_available: bool = True,
    archived_scope_unconfirmed: bool = False,
    authorizations: PreviewAuthorizations | None = None,
) -> ConsoleResourcePreviewOut:
    blockers = {
        f"{source.source}_{source.availability}"
        for source in inventory.sources
        if source.availability != "available"
    }
    blockers.update(topology_problems(inventory))
    if not local_available:
        blockers.add("services_unavailable")
    if archived_scope_unconfirmed:
        blockers.add("archived_resource_scope_unconfirmed")
    if authorizations is None or authorizations.source.availability != "available":
        blockers.add("authorizations_unavailable")
    services, revisions = _local_services(rows, blockers, authorizations)
    replacements = replacement_impacts(rows)
    potential_groups: dict[str, set[str]] = {}
    for impact in replacements:
        if impact.service_id is not None:
            potential_groups.setdefault(impact.service_id, set()).update(impact.group_ids)
    for service in services:
        # Held resources affect this service, but are neither configured nor observed grants.
        service.group_ids = sorted(
            set(service.group_ids) | potential_groups.get(service.service_id, set())
        )
    nodes = {node.uuid: node for node in inventory.nodes.rows}
    groups = {group.uuid: {item.uuid for item in group.inbounds} for group in inventory.groups.rows}
    inbound_profiles = {
        item.uuid: profile.uuid for profile in inventory.profiles.rows for item in profile.inbounds
    }
    for service in services:
        if {UUID(value) for value in service.group_ids} - groups.keys():
            blockers.add("missing_service_group")

    def nodes_for(inbounds: set[UUID]) -> set[UUID]:
        return {
            node.uuid
            for node in nodes.values()
            if inbounds & {item.uuid for item in node.configProfile.activeInbounds}
        }

    def groups_for(node_ids: set[UUID]) -> set[UUID]:
        active = {
            item.uuid
            for node_id in node_ids
            if node_id in nodes
            for item in nodes[node_id].configProfile.activeInbounds
        }
        return {group_id for group_id, inbounds in groups.items() if active & inbounds}

    current: ResourceValuesOut | None = None
    proposed: ResourceValuesOut | None = None
    direct_groups: set[UUID] = set()
    direct_nodes: set[UUID] = set()
    direct_profiles: set[UUID] = set()
    reload_nodes: set[UUID] = set()
    reload_profiles: set[UUID] = set()
    recovery: LiteralRecovery

    if isinstance(change, (ResourceGroupCreate, ResourceNodeCreate)):
        recovery = "creation_requires_explicit_reconciliation_no_automatic_delete"
        selected = set(change.inbound_ids)
        if selected - inbound_profiles.keys():
            blockers.add("unknown_proposed_inbound")
        direct_nodes = nodes_for(selected)
        direct_profiles = {inbound_profiles[item] for item in selected if item in inbound_profiles}
        direct_groups = {group_id for group_id, values in groups.items() if selected & values}
        proposed = ResourceValuesOut(
            kind="node" if isinstance(change, ResourceNodeCreate) else "group",
            id=None,
            name=change.name,
            inbound_ids=_ids(selected),
        )
        if isinstance(change, ResourceNodeCreate):
            proposed.profile_id = str(change.profile_id)
            proposed.address, proposed.port = change.address, change.port
            proposed.is_disabled = False
            if any(inbound_profiles.get(item) != change.profile_id for item in selected):
                blockers.add("unknown_proposed_inbound")
            if any(
                node.name == change.name or node.address == change.address
                for node in nodes.values()
            ):
                blockers.add("resource_create_conflict")
        elif any(group.name == change.name for group in inventory.groups.rows):
            blockers.add("resource_create_conflict")
    elif isinstance(change, ResourceGroupChange):
        recovery = "restore_previous_inbounds_and_recheck_profile_nodes"
        group = next(
            (item for item in inventory.groups.rows if item.uuid == change.target_id), None
        )
        if group:
            before = groups[group.uuid]
            after = set(change.inbound_ids)
            current = group_values(group)
            proposed = current.model_copy(update={"inbound_ids": _ids(after)})
            if after - inbound_profiles.keys():
                blockers.add("unknown_proposed_inbound")
            direct_groups = {group.uuid}
            direct_nodes = nodes_for(before | after)
            direct_profiles = {
                inbound_profiles[item] for item in before | after if item in inbound_profiles
            }
            # 3.4.5 updateInternalSquad restarts ALL nodes on each changed profile.
            reload_profiles = {
                inbound_profiles[item] for item in before ^ after if item in inbound_profiles
            }
            reload_nodes = {
                node.uuid
                for node in nodes.values()
                if node.configProfile.activeConfigProfileUuid in reload_profiles
            }
    elif isinstance(change, (ResourceHostChange, ResourceHostCreate)):
        recovery = "restore_previous_host_and_refresh_subscription"
        if isinstance(change, ResourceHostCreate):
            recovery = "creation_requires_explicit_reconciliation_no_automatic_delete"
            proposed = ResourceValuesOut(
                kind="host",
                id=None,
                name=change.name,
                inbound_ids=[str(change.inbound_id)],
                profile_id=str(change.profile_id),
                node_ids=_ids(set(change.node_ids)),
                group_mode=change.group_mode,
                group_ids=_ids(set(change.group_ids)),
                address=change.address,
                port=change.port,
                is_disabled=change.is_disabled,
                is_hidden=change.is_hidden,
            )
        else:
            host = next(
                (item for item in inventory.hosts.rows if item.uuid == change.target_id), None
            )
            if host:
                current = host_values(host, blockers)
                patch = change.patch.model_dump(mode="json", exclude_unset=True)
                if "inbound_id" in patch:
                    patch["inbound_ids"] = [patch.pop("inbound_id")]
                proposed = ResourceValuesOut.model_validate({**current.model_dump(), **patch})
        if proposed:
            for state in [current, proposed] if current else [proposed]:
                selected = {UUID(value) for value in state.group_ids}
                if (
                    selected - groups.keys()
                    or {UUID(value) for value in state.node_ids} - nodes.keys()
                ):
                    blockers.add("unknown_host_selection")
                for value in state.inbound_ids:
                    inbound_id = UUID(value)
                    if state.profile_id is None or inbound_profiles.get(inbound_id) != UUID(
                        state.profile_id
                    ):
                        blockers.add("unknown_host_inbound")
                    applicable = {
                        group_id for group_id, inbounds in groups.items() if inbound_id in inbounds
                    }
                    direct_groups |= (
                        applicable & selected
                        if state.group_mode == "ALLOW_ONLY"
                        else applicable - selected
                    )
                    target_nodes = nodes_for({inbound_id})
                    if state.node_ids:
                        target_nodes &= {UUID(value) for value in state.node_ids}
                    direct_nodes |= target_nodes
                if state.profile_id:
                    direct_profiles.add(UUID(state.profile_id))
            # Host updates change subscriptions; the pinned handler queues no Node restart.
    else:
        recovery = (
            "restart_has_no_automatic_rollback"
            if change.operation == "node_restart"
            else "inverse_node_action_requires_fresh_preview"
        )
        node = nodes.get(change.target_id)
        if node:
            profile = node.configProfile.activeConfigProfileUuid
            current = node_values(node)
            proposed = current.model_copy(
                update={
                    "is_disabled": change.operation == "node_disable"
                    if change.operation != "node_restart"
                    else current.is_disabled,
                    "force_restart": change.force_restart
                    if change.operation == "node_restart"
                    else None,
                }
            )
            if change.operation == "node_restart" and node.isDisabled:
                blockers.add("node_disabled")
            if change.operation == "node_enable" and (profile is None or not current.inbound_ids):
                blockers.add("node_has_no_active_inbounds")
            direct_nodes = {node.uuid}
            direct_groups = groups_for(direct_nodes)
            direct_profiles = {profile} if profile else set()
    if proposed is None:
        blockers.add("target_not_found")
    reload_groups = groups_for(reload_nodes) - direct_groups
    relevant_replacements = [
        impact
        for impact in replacements
        if impact.affects(set(_ids(direct_groups | reload_groups)))
    ]
    for impact in relevant_replacements:
        blockers.update(impact.blockers)
    direct = _impact(direct_groups, direct_nodes, direct_profiles, services, replacements)
    reload = _impact(reload_groups, reload_nodes, reload_profiles, services, replacements)
    now = datetime.now(UTC)
    fingerprint = (
        None
        if blockers
        else digest(
            {
                "inventory": inventory.fingerprint,
                "services": revisions,
                "authorizations": {key: _ids(value) for key, value in authorizations.groups.items()}
                if authorizations
                else None,
                "change": change.model_dump(mode="json"),
                "direct": direct.model_dump(),
                "reload": reload.model_dump(),
            }
        )
    )
    return ConsoleResourcePreviewOut(
        change=change,
        current=current,
        proposed=proposed,
        direct=direct,
        possible_reload=reload,
        affected_service_ids=sorted(
            {item.service_id for item in direct.services + reload.services}
            | {
                impact.service_id
                for impact in relevant_replacements
                if impact.service_id is not None
            }
        ),
        affected_customer_ids=sorted(set(direct.customer_ids + reload.customer_ids)),
        coverage="partial" if blockers else "complete",
        blockers=sorted(blockers),
        sources=[
            *inventory.sources,
            authorizations.source
            if authorizations
            else ResourceSourceOut(
                source="authorizations",
                availability="unavailable",
                observed_at=now,
            ),
            ResourceSourceOut(
                source="services",
                availability="unavailable"
                if not local_available
                else "invalid"
                if archived_scope_unconfirmed
                else "available",
                observed_at=now,
            ),
        ],
        fingerprint=fingerprint,
        observed_panel_version=inventory.version,
        remote_authorization_verified=local_available
        and not archived_scope_unconfirmed
        and not relevant_replacements
        and authorizations is not None
        and authorizations.source.availability == "available",
        observed_at=now,
        recovery=recovery,
    )


type LiteralRecovery = Literal[
    "restore_previous_inbounds_and_recheck_profile_nodes",
    "restore_previous_host_and_refresh_subscription",
    "inverse_node_action_requires_fresh_preview",
    "restart_has_no_automatic_rollback",
    "creation_requires_explicit_reconciliation_no_automatic_delete",
]
