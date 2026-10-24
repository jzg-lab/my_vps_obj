import { get } from "svelte/store";
import { describe, expect, it } from "vitest";
import { createApiClient, type MockApi } from "$lib/webapp/publicApi";
import {
  consoleResourceCatalogFixture,
  consoleResourceDraftPreviewFixture,
} from "$lib/webapp/mockApi/consoleResourcePreview";
import {
  catalogAvailable,
  createResourceDraftPreview,
  initialDraft,
  validDraft,
  type DraftChange,
  type DraftTarget,
  type ResourceCatalog,
} from "./resourceDraftPreview";

const catalog = consoleResourceCatalogFixture();
const group: DraftTarget = { kind: "group", id: catalog.groups[0].id };
const host: DraftTarget = { kind: "host", id: catalog.hosts[0].id };
const result = (change: DraftChange) => ({
  ok: true,
  ...consoleResourceDraftPreviewFixture(change),
});
function harness(target = group) {
  const calls: {
    path: string;
    options: RequestInit;
    resolve: (value: unknown) => void;
    reject: (reason: Error) => void;
  }[] = [];
  const mockApi: MockApi = (path, options) =>
    new Promise((resolve, reject) => calls.push({ path, options, resolve, reject }));
  const draft = createResourceDraftPreview(createApiClient({ mockApi }).api, target);
  async function loadCatalog(value: ResourceCatalog = catalog) {
    const pending = draft.loadCatalog();
    calls.at(-1)!.resolve({ ok: true, ...value });
    await pending;
  }
  async function preview() {
    const pending = draft.load();
    calls.at(-1)!.resolve(result(get(draft).change!));
    await pending;
  }
  return { draft, calls, loadCatalog, preview };
}

describe("resource draft construction", () => {
  it("takes the whole group membership from the catalog, retaining empty replacement sets", () => {
    expect(initialDraft(catalog, group)).toEqual({
      operation: "group_inbounds",
      target_id: group.id,
      inbound_ids: catalog.groups[0].inbound_ids,
    });
    expect(
      validDraft(catalog, { operation: "group_inbounds", target_id: group.id, inbound_ids: [] })
    ).toBe(true);
    expect(initialDraft(catalog, { ...group, id: "missing" })).toBeNull();
  });
  it("pairs Host fields and omits endpoints and nulls rather than resending unrelated values", () => {
    const change = initialDraft(catalog, host)!;
    expect(change.operation).toBe("host_update");
    if (change.operation !== "host_update") throw new Error("wrong fixture");
    expect(change.patch).toEqual({
      profile_id: catalog.hosts[0].profile_id,
      inbound_id: catalog.hosts[0].inbound_ids[0],
      node_ids: catalog.hosts[0].node_ids,
      group_mode: "EXCLUDE",
      group_ids: [],
      is_disabled: false,
      is_hidden: false,
    });
    expect(validDraft(catalog, change)).toBe(true);
    expect(
      validDraft(catalog, {
        ...change,
        patch: { ...change.patch, profile_id: catalog.profiles[1].id },
      })
    ).toBe(false);
    expect(
      validDraft(catalog, { ...change, patch: { ...change.patch, node_ids: ["missing"] } })
    ).toBe(false);
    expect(
      validDraft(catalog, { ...change, patch: { ...change.patch, group_ids: ["missing"] } })
    ).toBe(false);
  });
  it("does not invent unknown Host flags or silently accept missing group members", () => {
    const unknown = structuredClone(catalog);
    unknown.hosts[0].is_hidden = null;
    expect(initialDraft(unknown, host)).toBeNull();
    unknown.hosts[0].is_hidden = false;
    delete unknown.hosts[0].node_ids;
    expect(initialDraft(unknown, host)).toBeNull();
    expect(
      validDraft(catalog, {
        operation: "group_inbounds",
        target_id: group.id,
        inbound_ids: ["missing"],
      })
    ).toBe(false);
    expect(
      validDraft(catalog, {
        operation: "group_inbounds",
        target_id: group.id,
        inbound_ids: [catalog.groups[0].inbound_ids[0], catalog.groups[0].inbound_ids[0]],
      })
    ).toBe(false);
  });
});

describe("resource draft preview state", () => {
  it.each<Partial<ResourceCatalog>>([
    { coverage: "partial" },
    { draft_available: false },
    { blockers: ["nodes_unavailable"] },
    { sources: [] },
    {
      sources: [{ source: "nodes", availability: "unavailable", observed_at: catalog.observed_at }],
    },
  ])("blocks draft creation and confirmation for an incomplete catalog: %j", async (patch) => {
    const { draft, calls, loadCatalog } = harness();
    const incomplete = { ...catalog, ...patch };
    await loadCatalog(incomplete);
    expect(catalogAvailable(incomplete)).toBe(false);
    draft.setChange(initialDraft(catalog, group)!);
    await draft.load();
    await draft.revalidate();
    draft.confirm(true);
    expect(get(draft)).toMatchObject({ preview: null, confirmed: false });
    expect(calls).toHaveLength(1);
  });
  it.each([group, host])("uses only catalog, preview and revalidate for $kind", async (target) => {
    const { draft, calls, loadCatalog, preview } = harness(target);
    await draft.load();
    draft.confirm(true);
    expect(calls).toHaveLength(0);
    await loadCatalog();
    await preview();
    draft.confirm(true);
    expect(get(draft)).toMatchObject({ confirmed: true, failed: false });
    const pending = draft.revalidate();
    expect(get(draft).confirmed).toBe(false);
    const change = get(draft).change!;
    expect(JSON.parse(String(calls[2].options.body))).toEqual({
      change,
      expected_fingerprint: result(change).fingerprint,
    });
    calls[2].resolve({ ok: true, valid: true, reason: "unchanged", preview: result(change) });
    await pending;
    expect(get(draft).confirmed).toBe(true);
    expect(calls.map((call) => [call.path, call.options.method ?? "GET"])).toEqual([
      ["/admin/console/resources/catalog", "GET"],
      ["/admin/console/resources/preview", "POST"],
      ["/admin/console/resources/revalidate", "POST"],
    ]);
  });
  it.each(["changed", "incomplete", "failed"] as const)(
    "clears confirmation on %s revalidation",
    async (reason) => {
      const { draft, calls, loadCatalog, preview } = harness(host);
      await loadCatalog();
      await preview();
      draft.confirm(true);
      const pending = draft.revalidate();
      if (reason === "failed") calls.at(-1)!.reject(new Error("private_transport_error"));
      else
        calls.at(-1)!.resolve({
          ok: true,
          valid: false,
          reason,
          preview: {
            ...result(get(draft).change!),
            ...(reason === "incomplete"
              ? { coverage: "partial", fingerprint: null }
              : { fingerprint: "f".repeat(64) }),
          },
        });
      await pending;
      expect(get(draft)).toMatchObject({ confirmed: false, validation: reason });
      if (reason !== "changed") {
        draft.confirm(true);
        expect(get(draft).confirmed).toBe(false);
      }
      expect(JSON.stringify(get(draft))).not.toContain("private_transport_error");
    }
  );
  it("clears confirmation on every edited Host field", async () => {
    const { draft, loadCatalog, preview } = harness(host);
    await loadCatalog();
    const change = get(draft).change!;
    if (change.operation !== "host_update") throw new Error("wrong fixture");
    const patches: Partial<typeof change.patch>[] = [
      { is_disabled: true },
      { is_hidden: true },
      { node_ids: [] },
      { group_mode: "ALLOW_ONLY" },
      { group_ids: [catalog.groups[0].id] },
      { inbound_id: catalog.profiles[0].inbounds[1].id },
      { profile_id: catalog.profiles[1].id, inbound_id: catalog.profiles[1].inbounds[0].id },
    ];
    for (const patch of patches) {
      draft.setChange(change);
      await preview();
      draft.confirm(true);
      expect(get(draft).confirmed).toBe(true);
      draft.setChange({ ...change, patch: { ...change.patch, ...patch } });
      expect(get(draft)).toMatchObject({ preview: null, confirmed: false, validation: null });
    }
  });
  it.each(["preview", "revalidate"] as const)(
    "ignores late %s after a membership edit",
    async (operation) => {
      const { draft, calls, loadCatalog, preview } = harness();
      await loadCatalog();
      await preview();
      draft.confirm(true);
      const oldChange = get(draft).change!;
      const pending = operation === "preview" ? draft.load() : draft.revalidate();
      const old = calls.at(-1)!;
      draft.setChange({ operation: "group_inbounds", target_id: group.id, inbound_ids: [] });
      await preview();
      draft.confirm(true);
      old.resolve(
        operation === "preview"
          ? result(oldChange)
          : { ok: true, valid: true, reason: "unchanged", preview: result(oldChange) }
      );
      await pending;
      expect(old.options.signal?.aborted).toBe(true);
      expect(get(draft)).toMatchObject({
        confirmed: true,
        change: { inbound_ids: [] },
        preview: { proposed: { inbound_ids: [] } },
      });
    }
  );
  it("reload invalidates confirmation, failures remain retryable, and late catalogs cannot revive closed drafts", async () => {
    const { draft, calls, loadCatalog, preview } = harness();
    await loadCatalog();
    await preview();
    draft.confirm(true);
    const reload = draft.loadCatalog();
    expect(get(draft)).toMatchObject({ confirmed: false, preview: null, change: null });
    calls.at(-1)!.reject(new Error("unavailable"));
    await reload;
    expect(get(draft).failed).toBe(true);
    await loadCatalog();
    expect(get(draft).failed).toBe(false);
    const pending = draft.loadCatalog();
    const call = calls.at(-1)!;
    draft.destroy();
    const state = get(draft);
    call.resolve({ ok: true, ...catalog });
    await pending;
    expect(get(draft)).toBe(state);
    expect(call.options.signal?.aborted).toBe(true);
  });
  it.each(["change", "current", "proposed"] as const)(
    "rejects mismatched %s evidence",
    async (field) => {
      const { draft, calls, loadCatalog } = harness();
      await loadCatalog();
      const pending = draft.load();
      const response = result(get(draft).change!);
      if (field === "change")
        response.change = { operation: "group_inbounds", target_id: group.id, inbound_ids: [] };
      else response[field] = { ...response[field]!, id: "wrong-target" };
      calls.at(-1)!.resolve(response);
      await pending;
      draft.confirm(true);
      expect(get(draft)).toMatchObject({ failed: true, preview: null, confirmed: false });
    }
  );
  it("blocks confirmation when fresh preview authorization coverage is missing", async () => {
    const { draft, calls, loadCatalog } = harness();
    await loadCatalog();
    const pending = draft.load();
    calls.at(-1)!.resolve({ ...result(get(draft).change!), remote_authorization_verified: false });
    await pending;
    draft.confirm(true);
    await draft.revalidate();
    expect(get(draft).confirmed).toBe(false);
    expect(calls).toHaveLength(2);
  });
});
