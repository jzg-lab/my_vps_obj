"""Fresh semantic scopes; local hold/revision changes never change a topology digest."""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.admin_console_exit_replacement_schemas import (
    ReplacementExitOut,
    ReplacementImpactOut,
    ReplacementTopologyOut,
)
from bot.services.panel_api_service import PanelApiService
from bot.services.resource_preview_panel import PreviewInventory, digest, read_preview_inventory
from bot.services.resource_preview_values import host_values, node_values, topology_problems
from bot.services.service_exit_replacement_scope import (
    ReplacementAuthorizations,
    read_replacement_authorizations,
)
from config.service_periods import as_utc
from db.dal.user_services_dal import ServiceConflict
from db.service_models import DedicatedExit, ServiceConnection


@dataclass(frozen=True)
class ReplacementTopology:
    old_scope: str | None
    new_scope: str | None
    public: ReplacementTopologyOut

    def require(self, fingerprint: str) -> None:
        if self.public.coverage != "complete":
            raise ServiceConflict("exit_replacement_sources_incomplete")
        if self.public.resource_fingerprint != fingerprint:
            raise ServiceConflict("exit_replacement_scope_changed")


def _scope(
    resource: DedicatedExit,
    inventory: PreviewInventory,
    authorizations: ReplacementAuthorizations,
    blockers: set[str],
    *,
    usable: bool,
) -> tuple[str, list[ReplacementImpactOut]]:
    group = next(
        (group for group in inventory.groups.rows if str(group.uuid) == resource.squad_uuid), None
    )
    if group is None or not group.inbounds:
        blockers.add("exit_replacement_group_missing")
        return digest([resource.id, "missing_group"]), []
    inbound_ids = {item.uuid for item in group.inbounds}
    nodes = [
        node
        for node in inventory.nodes.rows
        if inbound_ids & {item.uuid for item in node.configProfile.activeInbounds}
    ]
    hosts = [
        host
        for host in inventory.hosts.rows
        if host.inbound.configProfileInboundUuid in inbound_ids
        and (
            (group.uuid in host.internalSquads.squads) == (host.internalSquads.mode == "ALLOW_ONLY")
        )
    ]
    # A failed old path can still be located and attested; only a candidate must serve traffic.
    for inbound in inbound_ids:
        located = {
            node.uuid
            for node in nodes
            if inbound in {item.uuid for item in node.configProfile.activeInbounds}
        }
        if not located or not any(
            host.inbound.configProfileInboundUuid == inbound
            and (not host.nodes or located & set(host.nodes))
            for host in hosts
        ):
            blockers.add("exit_replacement_path_unlocated")
    if usable:
        if not resource.enabled:
            blockers.add("exit_replacement_path_unavailable")
        for inbound in inbound_ids:
            active = {
                node.uuid
                for node in nodes
                if not node.isDisabled
                and inbound in {item.uuid for item in node.configProfile.activeInbounds}
            }
            if not active or not any(
                not host.isDisabled
                and host.inbound.configProfileInboundUuid == inbound
                and (not host.nodes or active & set(host.nodes))
                for host in hosts
            ):
                blockers.add("exit_replacement_path_unavailable")
    profiles = [
        profile
        for profile in inventory.profiles.rows
        if any(item.uuid in inbound_ids for item in profile.inbounds)
    ]
    profile_inbounds = {item.uuid for profile in profiles for item in profile.inbounds}
    direct = {
        str(row.uuid)
        for row in inventory.groups.rows
        if inbound_ids & {item.uuid for item in row.inbounds}
    }
    related = {
        str(row.uuid)
        for row in inventory.groups.rows
        if profile_inbounds & {item.uuid for item in row.inbounds}
    }
    impacts = [
        ReplacementImpactOut(
            service_id=key,
            customer_id=authorizations.service_details.get(key, (None, None))[0],
            service_name=authorizations.service_details.get(key, (None, None))[1],
            group_ids=sorted(groups & related),
            kind="direct_authorization" if groups & direct else "possible_reload",
        )
        for key, groups in sorted(authorizations.local.items())
        if groups & related
    ]
    remote = {
        key: sorted(groups & related)
        for key, groups in sorted(authorizations.remote.items())
        if groups & related
    }
    impacts.extend(
        ReplacementImpactOut(
            service_id=None,
            group_ids=groups,
            kind="direct_authorization" if set(groups) & direct else "possible_reload",
        )
        for groups in remote.values()
    )
    if any(set(groups) & direct for groups in remote.values()) or any(
        value.kind == "direct_authorization" for value in impacts
    ):
        blockers.add("exit_replacement_authorization_conflict")
    if any(
        row.id != resource.id
        and row.ip_address == resource.ip_address
        and (row.service_id is not None or row.hold_order_id is not None)
        for row in authorizations.exits
    ):
        blockers.add("exit_replacement_exclusivity_conflict")
    return digest(
        {
            "version": inventory.version,
            "exit": [
                resource.id,
                resource.ip_address,
                resource.resource_pool,
                resource.squad_uuid,
                resource.enabled,
            ],
            "inbounds": sorted(str(value) for value in inbound_ids),
            "groups": [
                row.model_dump(mode="json")
                for row in sorted(inventory.groups.rows, key=lambda row: row.uuid)
                if str(row.uuid) in related
            ],
            "nodes": [
                node_values(node).model_dump(mode="json")
                for node in sorted(inventory.nodes.rows, key=lambda row: row.uuid)
                if node.configProfile.activeConfigProfileUuid
                in {profile.uuid for profile in profiles}
            ],
            "hosts": [
                host_values(host, blockers).model_dump(mode="json")
                for host in sorted(hosts, key=lambda row: row.uuid)
            ],
            "profiles": [
                {
                    "id": str(profile.uuid),
                    "config_digest": digest(profile.config),
                    "inbounds": [
                        item.model_dump(mode="json")
                        for item in sorted(profile.inbounds, key=lambda row: row.uuid)
                    ],
                }
                for profile in sorted(profiles, key=lambda row: row.uuid)
            ],
            "authorizations": remote,
            # Reject pre-customer digests even for an empty impact list; names are display-only.
            "service_impacts": [
                {
                    "service_id": item.service_id,
                    "customer_id": item.customer_id,
                    "group_ids": item.group_ids,
                    "kind": item.kind,
                }
                for item in impacts
            ],
        }
    ), impacts


async def read_replacement_topology(
    session: AsyncSession,
    panel: PanelApiService | None,
    old: DedicatedExit,
    new: DedicatedExit,
    *,
    service_id: str,
    candidate_required: bool = True,
) -> ReplacementTopology:
    inventory = await read_preview_inventory(panel)
    connection = await session.get(ServiceConnection, service_id)
    authorizations = await read_replacement_authorizations(
        session, panel, service_id, connection.panel_user_uuid if connection else None
    )
    common = topology_problems(inventory) | authorizations.blockers
    if any(source.availability != "available" for source in inventory.sources):
        common.add("exit_replacement_sources_incomplete")
    old_blockers, new_blockers = common.copy(), common.copy()
    old_scope, old_impacts = _scope(old, inventory, authorizations, old_blockers, usable=False)
    new_scope, new_impacts = _scope(
        new, inventory, authorizations, new_blockers, usable=candidate_required
    )
    blockers = old_blockers | new_blockers
    impacts = {item.model_dump_json(): item for item in old_impacts + new_impacts}
    return ReplacementTopology(
        old_scope if not old_blockers else None,
        new_scope if not new_blockers else None,
        ReplacementTopologyOut(
            resource_fingerprint=digest([old_scope, new_scope]) if not blockers else None,
            sources=inventory.sources + authorizations.sources,
            coverage="partial" if blockers else "complete",
            observed_at=datetime.now(UTC),
            block_reasons=sorted(blockers),
            impacts=list(impacts.values()),
        ),
    )


def exit_output(resource: DedicatedExit, scope: str | None) -> ReplacementExitOut:
    return ReplacementExitOut(
        id=resource.id,
        revision=resource.revision,
        label=resource.label,
        ip_address=resource.ip_address,
        resource_pool=resource.resource_pool,
        squad_uuid=resource.squad_uuid,
        service_id=resource.service_id,
        hold_order_id=resource.hold_order_id,
        enabled=resource.enabled,
        verified_at=as_utc(resource.verified_at) if resource.verified_at else None,
        scope_fingerprint=scope,
    )
