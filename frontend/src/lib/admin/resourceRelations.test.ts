import { describe, expect, it } from "vitest";
import { consoleResourceCatalogFixture } from "$lib/webapp/mockApi/consoleResourcePreview";
import { resourceRelations } from "./resourceRelations";

describe("configured resource relationships", () => {
  it("matches stable inbound IDs instead of equal group names or shared profiles", () => {
    const catalog = consoleResourceCatalogFixture();
    const first = resourceRelations(catalog, catalog.groups[0]);
    const second = resourceRelations(catalog, catalog.groups[1]);
    expect(first.complete).toBe(true);
    expect(first.nodes.map((node) => node.id)).toEqual([catalog.nodes[0].id]);
    expect(first.peers.map((host) => host.id)).toEqual([catalog.hosts[0].id]);
    expect(second.branches[0].inbound?.tag).toBe("vless-alt");
    expect(second.nodes).toEqual([]);
    expect(second.peers).toEqual([]);
  });
  it("respects host node restrictions and group include/exclude rules", () => {
    const catalog = consoleResourceCatalogFixture();
    catalog.nodes.push({ ...catalog.nodes[0], id: "second-node" });
    const host = catalog.hosts[0];
    expect(resourceRelations(catalog, host).nodes).toHaveLength(1);
    host.node_ids = [];
    expect(resourceRelations(catalog, host).nodes).toHaveLength(2);
    host.group_mode = "ALLOW_ONLY";
    host.group_ids = [catalog.groups[1].id];
    expect(resourceRelations(catalog, host).peers).toEqual([]);
    expect(resourceRelations(catalog, catalog.groups[0]).peers).toEqual([]);
    host.group_ids = [catalog.groups[0].id];
    expect(resourceRelations(catalog, host).peers).toEqual([catalog.groups[0]]);
    host.group_mode = "EXCLUDE";
    expect(resourceRelations(catalog, host).peers).toEqual([]);
  });
  it("retains missing inbound references and marks incomplete observations", () => {
    const catalog = consoleResourceCatalogFixture();
    catalog.groups[0].inbound_ids.push("missing-inbound");
    const result = resourceRelations(catalog, catalog.groups[0]);
    expect(result.complete).toBe(false);
    expect(result.branches[1].id).toBe("missing-inbound");
    expect(result.branches[1].inbound).toBeUndefined();
    catalog.coverage = "partial";
    expect(resourceRelations(catalog, catalog.hosts[0]).complete).toBe(false);
  });
  it("does not call disabled or hidden endpoints healthy or remove their configuration", () => {
    const catalog = consoleResourceCatalogFixture();
    catalog.hosts[0].is_disabled = true;
    catalog.hosts[0].is_hidden = true;
    expect(resourceRelations(catalog, catalog.groups[0]).peers).toEqual(catalog.hosts);
    catalog.hosts[0].group_mode = null;
    expect(resourceRelations(catalog, catalog.groups[0]).complete).toBe(false);
  });
  it("rejects mismatched profiles and keeps missing selections unknown", () => {
    const catalog = consoleResourceCatalogFixture();
    const host = catalog.hosts[0];
    host.profile_id = "missing-profile";
    const result = resourceRelations(catalog, host);
    expect(result.complete).toBe(false);
    expect(result.nodes).toEqual([]);
    expect(result.peers).toEqual([]);
    expect(resourceRelations(catalog, catalog.groups[0]).complete).toBe(false);
    host.profile_id = catalog.profiles[0].id;
    host.node_ids = undefined;
    expect(resourceRelations(catalog, host).nodes).toEqual([]);
    expect(resourceRelations(catalog, host).complete).toBe(false);
    host.group_ids = undefined;
    expect(resourceRelations(catalog, catalog.groups[0]).peers).toEqual([]);
    host.group_ids = ["missing-group"];
    expect(resourceRelations(catalog, host).complete).toBe(false);
  });
});
