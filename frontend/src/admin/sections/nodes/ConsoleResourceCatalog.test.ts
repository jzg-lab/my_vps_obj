import { readFileSync } from "node:fs";
import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import { resolveLocaleKey } from "$lib/webapp/constants";
import { consoleResourceCatalogFixture } from "$lib/webapp/mockApi/consoleResourcePreview";
import ConsoleResourceCatalogStatus from "./ConsoleResourceCatalogStatus.svelte";
import ConsoleResourceCatalogTable from "./ConsoleResourceCatalogTable.svelte";
import ConsoleResourceDetail from "./ConsoleResourceDetail.svelte";
import ConsoleResourcesSection from "../ConsoleResourcesSection.svelte";

const at = (key: string) => key;
const api = async () => {
  throw new Error("SSR must not call the API");
};
describe("resource catalog presentation", () => {
  it("loads only on the client and exposes the shared filter controls", () => {
    const html = render(ConsoleResourcesSection, {
      props: { api, at, onOpenUserCard: () => {} },
    }).body;
    expect(html).toContain("console_catalog_search");
    expect(html).toContain("console_catalog_kind");
    expect(html).toContain('aria-busy="true"');
    expect(html).not.toContain("console_catalog_empty");
  });

  it("shows partial sources and safe unknown blockers without private codes", () => {
    const catalog = consoleResourceCatalogFixture();
    catalog.coverage = "partial";
    catalog.blockers = ["future_private_detail"];
    Object.assign(catalog.sources[0], {
      source: "private_source",
      availability: "private_failure",
    });
    const html = render(ConsoleResourceCatalogStatus, { props: { catalog, at } }).body;
    expect(html).toContain("console_nodes_coverage_partial");
    expect(html).toContain("console_resource_blocker_unknown");
    expect(html).toContain("console_unknown");
    for (const value of ["future_private_detail", "private_source", "private_failure"])
      expect(html).not.toContain(value);
  });

  it("renders complete long identities and true/false/unknown Host flags", () => {
    const catalog = consoleResourceCatalogFixture();
    const rows = [true, false, null].map((value, index) => ({
      ...catalog.hosts[0],
      id: `host-${index}`,
      name: "Long resource identity ".repeat(10),
      is_hidden: value,
      is_disabled: value,
    }));
    const html = render(ConsoleResourceCatalogTable, {
      props: { rows, kind: "host", at, onOpen: () => {} },
    }).body;
    for (const row of rows) expect(html).toContain(row.name);
    for (const text of ["yes", "no", "console_unknown", "hk.example.test", "443", "host-2"])
      expect(html).toContain(text);
  });

  it("does not execute catalog reads during server rendering of a portal detail", () => {
    const catalog = consoleResourceCatalogFixture();
    const props = {
      api,
      at,
      catalog,
      resource: catalog.hosts[0],
      kind: "host" as const,
      currentUrl: "https://console.test/app/admin/node-resources?resources_q=HK",
      routePrefix: "/app",
      onclose: () => {},
      onOpenUserCard: () => {},
    };
    expect(() => render(ConsoleResourceDetail, { props })).not.toThrow();
  });

  it.each(["en", "ru", "zh-hans"])("provides actual catalog translations in %s", (language) => {
    const locale: Record<string, string> = JSON.parse(
      readFileSync(new URL(`../../../../../locales/${language}.json`, import.meta.url), "utf8")
    );
    for (const file of [
      "../ConsoleResourcesSection.svelte",
      "ConsoleResourceCatalogStatus.svelte",
      "ConsoleResourceCatalogTable.svelte",
      "ConsoleResourceDetail.svelte",
    ])
      for (const match of readFileSync(new URL(file, import.meta.url), "utf8").matchAll(
        /"(console_[a-z_]+)"/g
      ))
        expect(
          locale[resolveLocaleKey(`admin_${match[1]}`)],
          `${language}: ${match[1]}`
        ).toBeTruthy();
  });
});
