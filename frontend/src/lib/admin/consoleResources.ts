import type { components } from "$lib/api/openapi.generated";
import { withRoutePrefix } from "$lib/webapp/routes";

export type ResourceCatalog = components["schemas"]["ConsoleResourceCatalogOut"];
export type CatalogResource = components["schemas"]["ResourceValuesOut"] & { id: string };
export type ResourceKind = Exclude<CatalogResource["kind"], "node">;
export type ResourcesRoute = {
  kind: ResourceKind;
  query: string;
  resourceId: string;
};

export function readResourcesRoute(search: string): ResourcesRoute {
  const params = new URLSearchParams(search);
  return {
    kind: params.get("resources_kind") === "host" ? "host" : "group",
    query: params.get("resources_q") ?? "",
    resourceId: params.get("resource_id") ?? "",
  };
}

export function resourcesRouteUrl(current: string, route: ResourcesRoute, prefix = ""): URL {
  const url = new URL(current);
  url.pathname = withRoutePrefix("/admin/node-resources", prefix);
  url.searchParams.set("section", "node-resources");
  for (const key of [
    "node_id",
    "service_id",
    "user_id",
    "resource_preview",
    "resource_action",
    "resource_force",
    "resource_service_id",
  ])
    url.searchParams.delete(key);
  url.searchParams.set("resources_kind", route.kind);
  for (const [key, value] of [
    ["resources_q", route.query],
    ["resource_id", route.resourceId],
  ]) {
    if (value) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
  }
  return url;
}

export function catalogResources(catalog: ResourceCatalog, kind: ResourceKind): CatalogResource[] {
  return (kind === "group" ? catalog.groups : catalog.hosts).filter(
    (row): row is CatalogResource => typeof row.id === "string" && row.id.length > 0
  );
}

export function filterCatalogResources(
  catalog: ResourceCatalog,
  route: ResourcesRoute
): CatalogResource[] {
  const query = route.query.trim().toLocaleLowerCase();
  return catalogResources(catalog, route.kind)
    .filter((row) =>
      [
        row.id,
        row.name,
        row.address,
        ...row.inbound_ids,
        ...(row.node_ids ?? []),
        ...(row.group_ids ?? []),
      ].some((value) => value?.toLocaleLowerCase().includes(query))
    )
    .sort((left, right) => left.name.localeCompare(right.name) || left.id.localeCompare(right.id));
}
