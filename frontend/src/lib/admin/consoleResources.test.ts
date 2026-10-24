import { describe, expect, it } from "vitest";
import { consoleResourceCatalogFixture } from "$lib/webapp/mockApi/consoleResourcePreview";
import { consoleNodeFixture } from "./consoleNodesFixtures";
import {
  catalogResources,
  filterCatalogResources,
  readResourcesRoute,
  resourcesRouteUrl,
} from "./consoleResources";

describe("resource catalog navigation and filtering", () => {
  it("preserves filters, literal IDs, prefix and unrelated context through detail/back", () => {
    const route = readResourcesRoute(
      "?resources_kind=host&resources_q=HK%26EU&resource_id=a%2Fb%2Bc"
    );
    const url = resourcesRouteUrl(
      "https://console.test/app/admin/nodes?node_id=n&service_id=s&resource_preview=node&resource_force=1&resource_service_id=x&lang=zh#content",
      route,
      "/app"
    );
    expect(url.pathname).toBe("/app/admin/node-resources");
    expect(readResourcesRoute(url.search)).toEqual(route);
    expect(url.searchParams.get("lang")).toBe("zh");
    expect(url.hash).toBe("#content");
    for (const key of [
      "node_id",
      "service_id",
      "resource_preview",
      "resource_force",
      "resource_service_id",
    ])
      expect(url.searchParams.has(key)).toBe(false);
    const back = resourcesRouteUrl(url.href, { ...route, resourceId: "" }, "/app");
    expect(back.searchParams.has("resource_id")).toBe(false);
    expect(readResourcesRoute(back.search)).toEqual({ ...route, resourceId: "" });
  });

  it("defaults unknown kinds to groups without treating an unknown ID as a match", () => {
    expect(readResourcesRoute("?resources_kind=future")).toEqual({
      kind: "group",
      query: "",
      resourceId: "",
    });
    expect(
      filterCatalogResources(consoleResourceCatalogFixture(), {
        kind: "group",
        query: "missing",
        resourceId: "",
      })
    ).toEqual([]);
  });

  it("keeps equal names distinct and searches stable IDs without mutating inventory", () => {
    const catalog = consoleResourceCatalogFixture();
    const before = structuredClone(catalog);
    const route = { kind: "group", query: " shared HK ", resourceId: "" } as const;
    expect(filterCatalogResources(catalog, route).map((row) => row.id)).toEqual(
      catalog.groups.map((row) => row.id)
    );
    expect(filterCatalogResources(catalog, { ...route, query: catalog.groups[1].id })).toEqual([
      catalog.groups[1],
    ]);
    expect(
      filterCatalogResources(catalog, { ...route, kind: "host", query: "HK.EXAMPLE" })
    ).toEqual(catalog.hosts);
    expect(
      filterCatalogResources(catalog, { ...route, kind: "host", query: catalog.nodes[0].id })
    ).toEqual(catalog.hosts);
    expect(catalogResources(catalog, "group")).toEqual(catalog.groups);
    expect(catalog).toEqual(before);
  });

  it("excludes proposed resources without stable identifiers from the directory", () => {
    const catalog = consoleResourceCatalogFixture();
    expect(
      catalogResources(
        { ...catalog, groups: [...catalog.groups, { ...catalog.groups[0], id: null }] },
        "group"
      )
    ).toEqual(catalog.groups);
  });

  it("keeps shared node fixture missing values and sample time explicit", () => {
    expect(consoleNodeFixture.users_online_quality).toBe("missing");
    expect(consoleNodeFixture.users_online).toBeNull();
    expect(consoleNodeFixture.system?.sampled_at).toBeNull();
    for (const [field, value] of Object.entries(consoleNodeFixture.system ?? {}))
      expect(value, field).toEqual(field === "invalid_fields" ? [] : null);
  });
});
