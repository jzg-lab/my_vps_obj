"""Project fresh inventory into draft inputs, never execution authorization."""

from datetime import UTC, datetime

from bot.app.web.admin_console_resource_schemas import (
    ConsoleResourceCatalogOut,
    ResourceCatalogInboundOut,
    ResourceCatalogProfileOut,
)
from bot.services.resource_preview_panel import PreviewInventory, digest
from bot.services.resource_preview_values import (
    group_values,
    host_values,
    node_values,
    topology_problems,
)


def build_resource_catalog(inventory: PreviewInventory) -> ConsoleResourceCatalogOut:
    blockers = {
        f"{source.source}_{source.availability}"
        for source in inventory.sources
        if source.availability != "available"
    }
    blockers.update(topology_problems(inventory))
    hosts = [
        host_values(host, blockers)
        for host in sorted(inventory.hosts.rows, key=lambda item: item.uuid)
    ]
    return ConsoleResourceCatalogOut(
        groups=[
            group_values(group)
            for group in sorted(inventory.groups.rows, key=lambda item: item.uuid)
        ],
        profiles=[
            ResourceCatalogProfileOut(
                id=str(profile.uuid),
                name=profile.name,
                inbounds=[
                    ResourceCatalogInboundOut(
                        id=str(inbound.uuid), profile_id=str(inbound.profileUuid), tag=inbound.tag
                    )
                    for inbound in sorted(profile.inbounds, key=lambda item: item.uuid)
                ],
                node_ids=sorted({str(node.uuid) for node in profile.nodes}),
                config_digest=digest(profile.config),
            )
            for profile in sorted(inventory.profiles.rows, key=lambda item: item.uuid)
        ],
        nodes=[
            node_values(node) for node in sorted(inventory.nodes.rows, key=lambda item: item.uuid)
        ],
        hosts=hosts,
        sources=inventory.sources,
        coverage="partial" if blockers else "complete",
        blockers=sorted(blockers),
        draft_available=not blockers,
        observed_panel_version=inventory.version,
        observed_at=datetime.now(UTC),
    )
