"""Shared allowlisted current values and inventory consistency checks."""

from uuid import UUID

from bot.app.web.admin_console_resource_schemas import ResourceHostPatch, ResourceValuesOut
from bot.services.resource_preview_panel import (
    PreviewGroup,
    PreviewHost,
    PreviewInventory,
    PreviewNode,
)


def group_values(group: PreviewGroup) -> ResourceValuesOut:
    return ResourceValuesOut(
        kind="group",
        id=str(group.uuid),
        name=group.name,
        inbound_ids=sorted({str(item.uuid) for item in group.inbounds}),
    )


def node_values(node: PreviewNode) -> ResourceValuesOut:
    profile = node.configProfile.activeConfigProfileUuid
    return ResourceValuesOut(
        kind="node",
        id=str(node.uuid),
        name=node.name,
        inbound_ids=sorted({str(item.uuid) for item in node.configProfile.activeInbounds}),
        profile_id=str(profile) if profile else None,
        is_disabled=node.isDisabled,
    )


def host_values(host: PreviewHost, blockers: set[str]) -> ResourceValuesOut:
    try:
        address = ResourceHostPatch.public_endpoint(host.address)
    except ValueError:
        address = None
        blockers.add("unsupported_host_address")
    return ResourceValuesOut(
        kind="host",
        id=str(host.uuid),
        name=host.remark,
        inbound_ids=[str(host.inbound.configProfileInboundUuid)]
        if host.inbound.configProfileInboundUuid
        else [],
        profile_id=str(host.inbound.configProfileUuid) if host.inbound.configProfileUuid else None,
        node_ids=sorted({str(value) for value in host.nodes}),
        is_disabled=host.isDisabled,
        is_hidden=host.isHidden,
        group_mode=host.internalSquads.mode,
        group_ids=sorted({str(value) for value in host.internalSquads.squads}),
        address=address,
        port=host.port,
    )


def topology_problems(inventory: PreviewInventory) -> set[str]:
    problems: set[str] = set()
    nodes = {node.uuid: node for node in inventory.nodes.rows}
    groups = {group.uuid for group in inventory.groups.rows}
    profiles = {profile.uuid: profile for profile in inventory.profiles.rows}
    inbound_profiles: dict[UUID, UUID] = {}
    for profile in profiles.values():
        for inbound in profile.inbounds:
            if inbound.uuid in inbound_profiles or inbound.profileUuid != profile.uuid:
                problems.add("inconsistent_inbound_profile")
            inbound_profiles[inbound.uuid] = profile.uuid
        for node in profile.nodes:
            if node.uuid not in nodes or (
                nodes[node.uuid].configProfile.activeConfigProfileUuid != profile.uuid
            ):
                problems.add("inconsistent_profile_nodes")
    for node in nodes.values():
        profile = node.configProfile
        if profile.activeConfigProfileUuid is None and not profile.activeInbounds:
            continue
        if profile.activeConfigProfileUuid not in profiles:
            problems.add("missing_node_profile")
        elif node.uuid not in {
            item.uuid for item in profiles[profile.activeConfigProfileUuid].nodes
        }:
            problems.add("inconsistent_profile_nodes")
        if any(
            inbound_profiles.get(item.uuid) != profile.activeConfigProfileUuid
            for item in profile.activeInbounds
        ):
            problems.add("missing_node_inbound")
    for group in inventory.groups.rows:
        if any(item.uuid not in inbound_profiles for item in group.inbounds):
            problems.add("missing_group_inbound")
    for host in inventory.hosts.rows:
        if (
            host.inbound.configProfileInboundUuid is None
            or inbound_profiles.get(host.inbound.configProfileInboundUuid)
            != host.inbound.configProfileUuid
        ):
            problems.add("missing_host_inbound")
        if set(host.nodes) - nodes.keys() or set(host.internalSquads.squads) - groups:
            problems.add("missing_host_scope")
    return problems
