import { readFileSync } from "node:fs";
import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import ConsoleNodesSection from "../../admin/sections/ConsoleNodesSection.svelte";
import ConsoleNodeAssetTable from "../../admin/sections/nodes/ConsoleNodeAssetTable.svelte";
import ConsoleNodeAssetDialog from "../../admin/sections/nodes/ConsoleNodeAssetDialog.svelte";
import ConsoleNodeAssets from "../../admin/sections/nodes/ConsoleNodeAssets.svelte";
import type { ApiClient } from "../webapp/publicApi";
import { createApiClient } from "../webapp/publicApi";
import {
  consoleNodeAssetsDemoResponse,
  createConsoleNodeAssetsDemoState,
} from "../webapp/mockApi/consoleNodeAssets";
import {
  loadNodeAssets,
  saveNodeAsset,
  deleteNodeAsset,
  nodeAssetErrorKey,
  nodeAssetDraftReady,
  nodeAssetsViewUrl,
  readNodeAssetsRoute,
  type NodeAsset,
} from "./consoleNodeAssets";

const at = (key: string) => key;
const fixture: NodeAsset = {
  id: "a".repeat(32),
  name: "Pending node",
  address: "192.0.2.1",
  notes: "Manual inventory",
  management_state: "unmanaged",
  created_at: "2026-10-24T00:00:00Z",
  updated_at: "2026-10-24T00:00:00Z",
};
const noApi: ApiClient["api"] = async () => {
  throw new Error("SSR must not make API calls");
};

describe("pending node route and generated-contract consumers", () => {
  it("keeps pending pagination separate and prioritizes an explicit managed-node deep link", () => {
    expect(readNodeAssetsRoute("?nodes_view=unmanaged&node_assets_page=2&nodes_page=8")).toEqual({
      view: "unmanaged",
      page: 2,
    });
    expect(readNodeAssetsRoute("?nodes_view=unmanaged&node_id=managed").view).toBe("managed");
    for (const page of ["-1", "1.5", "1000001", "Infinity", "broken"])
      expect(readNodeAssetsRoute(`?node_assets_page=${page}`).page).toBe(0);
    expect(readNodeAssetsRoute("?nodes_view=invalid").view).toBe("managed");
  });
  it("retains managed filters, traffic window, prefix and mock settings when switching views", () => {
    const current =
      "https://example.test/demo/runtime/admin/nodes?mock=services&nodes_q=HK&nodes_page=2&nodes_traffic_window=7d&node_id=old&nodes_related_page=3";
    const pending = nodeAssetsViewUrl(current, "unmanaged", 1);
    expect(pending.pathname).toBe("/demo/runtime/admin/nodes");
    expect(pending.searchParams.get("nodes_q")).toBe("HK");
    expect(pending.searchParams.get("nodes_page")).toBe("2");
    expect(pending.searchParams.get("nodes_traffic_window")).toBe("7d");
    expect(pending.searchParams.get("mock")).toBe("services");
    expect(pending.searchParams.has("node_id")).toBe(false);
    expect(pending.searchParams.has("nodes_related_page")).toBe(false);
    expect(readNodeAssetsRoute(pending.search)).toEqual({ view: "unmanaged", page: 1 });
    const managed = nodeAssetsViewUrl(pending.href, "managed");
    expect(managed.searchParams.has("nodes_view")).toBe(false);
    expect(managed.searchParams.get("node_assets_page")).toBe("1");
  });
  it("sends generated paths and only the three editable fields through the real API client", async () => {
    const state = createConsoleNodeAssetsDemoState();
    const calls: Array<{ path: string; options: RequestInit }> = [];
    const { api } = createApiClient({
      mockApi: async (path, options) => {
        calls.push({ path, options });
        return consoleNodeAssetsDemoResponse(path, options, state);
      },
    });
    const signal = new AbortController().signal;
    expect((await loadNodeAssets(api, 2, signal)).total).toBe(0);
    expect(calls[0].path).toBe("/admin/console/node-assets?page=2&page_size=20");
    const created = await saveNodeAsset(api, null, {
      name: " Pending ",
      address: " ::1 ",
      notes: " note ",
    });
    expect(calls.at(-1)?.options.method).toBe("POST");
    expect(JSON.parse(String(calls.at(-1)?.options.body))).toEqual({
      name: "Pending",
      address: "::1",
      notes: "note",
    });
    await saveNodeAsset(api, created.id, { name: "Changed", address: "::1", notes: "" });
    expect(calls.at(-1)?.path).toBe(`/admin/console/node-assets/${created.id}`);
    expect(calls.at(-1)?.options.method).toBe("PUT");
    expect((await loadNodeAssets(api, 0)).items[0].notes).toBe("");
    expect(await deleteNodeAsset(api, created.id)).toMatchObject({ deleted: true, id: created.id });
    expect(calls.at(-1)?.options.method).toBe("DELETE");
    expect((await loadNodeAssets(api, 0)).total).toBe(0);
  });
  it("unwraps failures without automatic write retries or treating failure as empty inventory", async () => {
    const mocked = vi.fn(async () => ({ ok: false, error: "node_assets_unavailable" }));
    const { api } = createApiClient({ mockApi: mocked });
    await expect(loadNodeAssets(api, 0)).rejects.toBeDefined();
    const before = mocked.mock.calls.length;
    await expect(
      saveNodeAsset(api, null, { name: "Node", address: "::1", notes: "" })
    ).rejects.toBeDefined();
    expect(mocked.mock.calls.length - before).toBe(1);
    expect(nodeAssetErrorKey({ error: "node_assets_unavailable", message: "SECRET" })).toBe(
      "console_node_assets_write_failed"
    );
    for (const error of ["unauthorized", "forbidden", "csrf_failed"])
      expect(nodeAssetErrorKey({ error })).toBe("console_node_assets_forbidden");
    expect(nodeAssetErrorKey({ error: "invalid_node_asset_request" })).toBe(
      "console_node_assets_invalid"
    );
    expect(nodeAssetErrorKey({ error: "node_asset_not_found" })).toBe(
      "console_node_assets_not_found"
    );
  });
  it("blocks empty and oversized drafts without substituting a zero or remote identity", () => {
    const body = { name: "Node", address: "::1", notes: "" };
    expect(nodeAssetDraftReady(body)).toBe(true);
    for (const patch of [
      { name: "  " },
      { address: "" },
      { name: "a".repeat(121) },
      { notes: "a".repeat(2001) },
    ])
      expect(nodeAssetDraftReady({ ...body, ...patch })).toBe(false);
  });
});

describe("pending node UI consumers", () => {
  it("renders separate view tabs in the actual nodes section without changing managed metrics", () => {
    const html = render(ConsoleNodesSection, {
      props: { api: noApi, at, onOpenUserCard: () => {} },
    }).body;
    expect(html).toContain("console_node_assets_managed");
    expect(html).toContain("console_node_assets_pending");
    expect(html).toContain("console_nodes_window_label");
  });
  it("renders the actual pending view without managed metrics or remote onboarding", () => {
    vi.stubGlobal("window", {
      location: new URL("https://example.test/admin/nodes?nodes_view=unmanaged"),
    });
    try {
      const html = render(ConsoleNodesSection, {
        props: { api: noApi, at, onOpenUserCard: () => {} },
      }).body;
      expect(html).toContain("console_node_assets_scope");
      expect(html).toContain("console_node_assets_add");
      expect(html).not.toContain("console_nodes_window_label");
      expect(html).not.toContain("resource_ops_action_node_create");
    } finally {
      vi.unstubAllGlobals();
    }
  });
  it("shows loading as unknown count, not an empty list or invented online metrics", () => {
    const html = render(ConsoleNodeAssets, {
      props: { api: noApi, at, page: 0, onPageChange: () => {} },
    }).body;
    expect(html).toContain("console_node_assets_scope");
    expect(html).toContain('aria-busy="true"');
    expect(html).not.toContain("console_node_assets_empty");
    expect(html).not.toContain("console_nodes_traffic");
    expect(html).not.toContain("console_nodes_online");
    expect(html).not.toContain("admin-list-toolbar-summary");
  });
  it("renders plain-text records and local-only actions without resource or service links", () => {
    const html = render(ConsoleNodeAssetTable, {
      props: {
        assets: [
          { ...fixture, name: "<script>unsafe</script>", notes: "<img src=x onerror=evil>" },
        ],
        at,
        onAction: () => {},
      },
    }).body;
    expect(html).toContain("console_node_assets_unmanaged");
    expect(html).toContain("&lt;script>");
    expect(html).not.toContain("<script>unsafe");
    expect(html).not.toContain("<img src=x");
    expect(html).not.toContain('href="');
    expect(html).not.toContain("traffic");
    expect(html).not.toContain("customers");
    expect(html).toContain("console_node_assets_edit");
    expect(html).toContain("console_node_assets_delete");
  });
  it.each(["en", "ru", "zh-hans"])(
    "resolves actual dialog titles and safety disclosure before browser portal mounting in %s",
    (language) => {
      const locale: Record<string, string> = JSON.parse(
        readFileSync(new URL(`../../../../locales/${language}.json`, import.meta.url), "utf8")
      );
      const translatedKeys: string[] = [];
      const translate = (key: string) => {
        expect(locale[`admin_${key}`], key).toBeTruthy();
        translatedKeys.push(key);
        return locale[`admin_${key}`];
      };
      for (const kind of ["create", "edit", "delete"] as const) {
        render(ConsoleNodeAssetDialog, {
          props: {
            api: noApi,
            at: translate,
            action: kind === "create" ? { kind } : { kind, asset: fixture },
            onclose: () => {},
            onsaved: () => {},
          },
        }).body;
        // Portal controls mount only in the browser; the dedicated E2E checks those fields.
        expect(translatedKeys).toContain(
          `console_node_assets_${kind === "delete" ? "delete_hint" : "scope"}`
        );
        expect(translatedKeys).toContain(
          `console_node_assets_${kind === "delete" ? "delete_title" : kind === "edit" ? "edit" : "add"}`
        );
      }
    }
  );
});
