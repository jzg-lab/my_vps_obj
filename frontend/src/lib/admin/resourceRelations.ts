import type { CatalogResource, ResourceCatalog } from "./consoleResources";

export function resourceRelations(catalog: ResourceCatalog, resource: CatalogResource) {
  const identified = (rows: ResourceCatalog["nodes"]): CatalogResource[] =>
    rows.filter((row): row is CatalogResource => typeof row.id === "string" && row.id.length > 0);
  const nodes = identified(catalog.nodes);
  const hosts = identified(catalog.hosts);
  const groups = identified(catalog.groups);
  const branches = [...new Set(resource.inbound_ids)].map((id) => {
    const profile = catalog.profiles.find((item) =>
      item.inbounds.some((inbound) => inbound.id === id)
    );
    const inbound = profile?.inbounds.find((item) => item.id === id);
    const resolved = Boolean(
      profile && (resource.kind !== "host" || resource.profile_id === profile.id)
    );
    const matchingNodes = nodes.filter(
      (node) =>
        resolved &&
        node.inbound_ids.includes(id) &&
        node.profile_id === profile?.id &&
        (resource.kind !== "host" ||
          (resource.node_ids !== undefined &&
            (!resource.node_ids.length || resource.node_ids.includes(node.id))))
    );
    const matchingHosts = hosts.filter(
      (host) =>
        resolved &&
        host.inbound_ids.includes(id) &&
        host.profile_id === profile?.id &&
        host.group_ids !== undefined &&
        (host.group_mode === "ALLOW_ONLY"
          ? host.group_ids?.includes(resource.id)
          : host.group_mode === "EXCLUDE" && !host.group_ids?.includes(resource.id))
    );
    const matchingGroups = groups.filter(
      (group) =>
        resolved &&
        resource.group_ids !== undefined &&
        group.inbound_ids.includes(id) &&
        (resource.group_mode === "ALLOW_ONLY"
          ? resource.group_ids?.includes(group.id)
          : resource.group_mode === "EXCLUDE" && !resource.group_ids?.includes(group.id))
    );
    return {
      id,
      profile,
      inbound,
      resolved,
      nodes: matchingNodes,
      peers: resource.kind === "group" ? matchingHosts : matchingGroups,
    };
  });
  const related = (field: "nodes" | "peers") => [
    ...new Map(branches.flatMap((branch) => branch[field]).map((item) => [item.id, item])).values(),
  ];
  const complete =
    catalog.coverage === "complete" &&
    !catalog.blockers.length &&
    ["nodes", "hosts", "groups", "profiles"].every((name) =>
      catalog.sources.some(
        (source) => source.source === name && source.availability === "available"
      )
    ) &&
    branches.every((branch) => branch.resolved) &&
    (resource.kind !== "host" || validHost(resource)) &&
    !hosts.some(
      (host) => host.inbound_ids.some((id) => resource.inbound_ids.includes(id)) && !validHost(host)
    );
  return { branches, nodes: related("nodes"), peers: related("peers"), complete };

  function validHost(host: CatalogResource) {
    return (
      (host.group_mode === "ALLOW_ONLY" || host.group_mode === "EXCLUDE") &&
      host.node_ids !== undefined &&
      host.node_ids.every((id) => nodes.some((node) => node.id === id)) &&
      host.group_ids !== undefined &&
      host.group_ids.every((id) => groups.some((group) => group.id === id)) &&
      host.inbound_ids.every((id) =>
        catalog.profiles.some(
          (profile) =>
            profile.id === host.profile_id && profile.inbounds.some((inbound) => inbound.id === id)
        )
      )
    );
  }
}
