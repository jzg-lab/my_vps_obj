import { get } from "svelte/store";
import { beforeEach, describe, expect, it } from "vitest";
import { createApiClient } from "$lib/webapp/publicApi";
import {
  consoleResourceOperationsDemoResponse,
  resetResourceOperationsDemo,
  resourceOperationPreviewFixture,
} from "$lib/webapp/mockApi/consoleResourceOperations";
import { createResourceIntent, readResourceIntent } from "./resourceIntent";
import { consoleResourceCatalogFixture } from "$lib/webapp/mockApi/consoleResourcePreview";

function storage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => {
      values.set(key, value);
    },
    removeItem: (key) => {
      values.delete(key);
    },
    key: (index) => [...values.keys()][index] ?? null,
  };
}
const preview = () =>
  resourceOperationPreviewFixture({
    operation: "group_create",
    name: "New group",
    inbound_ids: [],
  });
function harness() {
  const saved = storage();
  const calls: { path: string; options: RequestInit }[] = [];
  let fail: "" | "unknown" | "rejected" | "changed" = "";
  let actor = 910001;
  const api = createApiClient({
    mockApi: async (path, options) => {
      calls.push({ path, options });
      if (path === "/admin/me") return { ok: true, user_id: actor, admin_ids: [actor] };
      if (path.endsWith("/revalidate") && fail === "changed")
        return {
          ok: true,
          valid: false,
          reason: "changed",
          preview: { ...preview(), fingerprint: "b".repeat(64) },
        };
      if (
        path === "/admin/console/resources/operations" &&
        options.method === "POST" &&
        fail === "rejected"
      )
        return { ok: false, error: "invalid_resource_operation_request", status: 400 };
      const response = consoleResourceOperationsDemoResponse(path, options);
      if (
        path === "/admin/console/resources/operations" &&
        options.method === "POST" &&
        fail === "unknown"
      )
        throw Object.assign(new Error("timeout after commit"), { status: 503 });
      return response;
    },
  }).api;
  const intent = createResourceIntent(api, saved);
  return {
    intent,
    saved,
    calls,
    api,
    setFailure: (value: typeof fail) => {
      fail = value;
    },
    setActor: (value: number) => {
      actor = value;
    },
  };
}
const writes = (calls: { path: string; options: RequestInit }[]) =>
  calls.filter(
    (call) => call.path === "/admin/console/resources/operations" && call.options.method === "POST"
  );
beforeEach(resetResourceOperationsDemo);
describe("resource intention submission", () => {
  it("revalidates before one confirmed submission and leaves it pending without an upstream attempt", async () => {
    const { intent, calls, saved } = harness();
    await intent.initialize();
    await intent.submit(preview(), false);
    expect(writes(calls)).toHaveLength(0);
    await Promise.all([intent.submit(preview(), true), intent.submit(preview(), true)]);
    expect(writes(calls)).toHaveLength(1);
    expect(calls.findIndex((call) => call.path.endsWith("/revalidate"))).toBeLessThan(
      calls.findIndex((call) => call.path.endsWith("/operations"))
    );
    expect(get(intent).operation).toMatchObject({
      status: "pending",
      attempts: [],
      gate_active: true,
      completed_at: null,
    });
    expect(saved.length).toBe(0);
  });
  it("never writes after a changed fingerprint or when capability is disabled", async () => {
    const { intent, calls, setFailure } = harness();
    await intent.initialize();
    await intent.submit({ ...preview(), execution_available: false }, true);
    expect(writes(calls)).toHaveLength(0);
    setFailure("changed");
    await intent.submit(preview(), true);
    expect(get(intent)).toMatchObject({ needsPreview: true, error: "resource_ops_error_changed" });
    expect(writes(calls)).toHaveLength(0);
  });
  it("omits nullable response-only Host fields in revalidation and submission", async () => {
    const { intent, calls } = harness();
    const host = consoleResourceCatalogFixture().hosts[0];
    await intent.initialize();
    await intent.submit(
      resourceOperationPreviewFixture({
        operation: "host_update",
        target_id: host.id,
        patch: { port: 8443 },
      }),
      true
    );
    for (const call of calls.filter((call) => call.options.method === "POST")) {
      const body: unknown = JSON.parse(String(call.options.body));
      expect(body).toMatchObject({
        change: { operation: "host_update", target_id: host.id, patch: { port: 8443 } },
      });
      expect(String(call.options.body)).not.toContain('"address":null');
    }
    expect(writes(calls)).toHaveLength(1);
  });
  it("persists an uncertain original request, never replays automatically and resolves with the same key", async () => {
    const { intent, calls, saved, api, setFailure } = harness();
    await intent.initialize();
    setFailure("unknown");
    await intent.submit(preview(), true);
    expect(writes(calls)).toHaveLength(1);
    expect(get(intent).pending).not.toBeNull();
    const firstBody = writes(calls)[0].options.body;
    const resumed = createResourceIntent(api, saved);
    setFailure("");
    await resumed.initialize();
    expect(writes(calls)).toHaveLength(1);
    await resumed.submit(preview(), true);
    expect(writes(calls)).toHaveLength(1);
    await resumed.resume();
    expect(writes(calls)).toHaveLength(2);
    expect(writes(calls)[1].options.body).toBe(firstBody);
    expect(get(resumed).operation?.attempts).toEqual([]);
    expect(get(resumed).operation?.status).toBe("pending");
    expect(saved.length).toBe(0);
  });
  it("clears only a known validation rejection, permitting correction after a new preview", async () => {
    const { intent, setFailure, calls } = harness();
    await intent.initialize();
    setFailure("rejected");
    await intent.submit(preview(), true);
    expect(get(intent)).toMatchObject({ pending: null, needsPreview: true });
    setFailure("");
    await intent.submit(preview(), true);
    expect(writes(calls)).toHaveLength(1);
    intent.resetPreview();
    await intent.submit(preview(), true);
    expect(writes(calls)).toHaveLength(2);
    const first: unknown = JSON.parse(String(writes(calls)[0].options.body));
    expect(JSON.parse(String(writes(calls)[1].options.body))).not.toEqual(first);
  });
  it("does not replay another administrator's intention after a session change", async () => {
    const { intent, calls, setFailure, setActor } = harness();
    await intent.initialize();
    setFailure("unknown");
    await intent.submit(preview(), true);
    setFailure("");
    setActor(910002);
    await intent.resume();
    expect(writes(calls)).toHaveLength(1);
    expect(get(intent).ready).toBe(false);
  });
  it("rejects corrupted persisted bodies instead of sending arbitrary requests", () => {
    const saved = storage();
    saved.setItem(
      "my-vps-resource-intent:1",
      JSON.stringify({
        change: { operation: "future_admin_command" },
        idempotency_key: "old",
        expected_fingerprint: "a".repeat(64),
      })
    );
    expect(() => readResourceIntent(saved, 1)).toThrow();
    expect(readResourceIntent(saved, 2)).toBeNull();
  });
  it("cannot submit after the review component is destroyed during revalidation", async () => {
    let release: ((value: unknown) => void) | undefined;
    const calls: string[] = [];
    const api = createApiClient({
      mockApi: async (path) => {
        calls.push(path);
        if (path === "/admin/me") return { ok: true, user_id: 1, admin_ids: [1] };
        return new Promise((resolve) => {
          release = resolve;
        });
      },
    }).api;
    const intent = createResourceIntent(api, storage());
    await intent.initialize();
    const pending = intent.submit(preview(), true);
    while (!release) await Promise.resolve();
    intent.destroy();
    release({ ok: true, valid: true, reason: "unchanged", preview: preview() });
    await pending;
    expect(calls).not.toContain("/admin/console/resources/operations");
  });
});
