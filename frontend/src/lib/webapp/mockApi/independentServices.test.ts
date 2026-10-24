import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockApi } from "../mockApi";
import { DATASET } from "./dataset";
import { seedIndependentServicesDemo } from "./independentServices";
import type { DedicatedExit, UserService } from "$lib/admin/servicePlans";

const userId = 910370;
const selection = {
  user_id: userId,
  plan_id: "1".repeat(32),
  expected_revision: 1,
  exit_id: null,
};
const post = (path: string, body: unknown) =>
  mockApi(path, { method: "POST", body: JSON.stringify(body) });

describe("activation preflight uses the selected demo customer", () => {
  beforeEach(() => {
    vi.stubGlobal("window", { location: { search: "" }, setTimeout });
    seedIndependentServicesDemo(Number(DATASET.currentUser?.user_id));
  });
  afterEach(() => vi.unstubAllGlobals());

  it("keeps the trust fixture expiry boundary separate from unknown and confirmed usage", async () => {
    vi.stubGlobal("window", { location: { search: "?trust_demo=1&delivery=1" }, setTimeout });
    seedIndependentServicesDemo(Number(DATASET.currentUser?.user_id));
    const result = await mockApi("/services");
    expect(result).toMatchObject({
      services: expect.arrayContaining([
        expect.objectContaining({
          traffic_rule: "monthly",
          cycle_ends_at: "2026-11-22T04:00:00Z",
          expires_at: "2026-11-22T04:00:00Z",
          used_bytes: 23 * 2 ** 30,
          usage_error: "panel_usage_unavailable",
        }),
        expect.objectContaining({
          status: "active",
          used_bytes: 0,
          last_usage_sync_at: "2026-10-22T04:00:00Z",
        }),
        expect.objectContaining({ status: "pending", used_bytes: 0, last_usage_sync_at: null }),
        expect.objectContaining({
          status: "cancelled",
          desired_status: "cancelled",
          traffic_rule: "monthly",
          cycle_ends_at: "2026-11-22T04:00:00Z",
          expires_at: "2027-01-20T04:00:00Z",
        }),
      ]),
    });
  });

  it("allows a listed customer other than the current user without claiming delivery readiness", async () => {
    expect(userId).not.toBe(Number(DATASET.currentUser?.user_id));
    expect(await mockApi(`/admin/users/${userId}`)).toMatchObject({
      ok: true,
      user: { user_id: userId, is_banned: false },
    });
    const servicesPath = `/admin/services?user_id=${userId}`;
    const before = await mockApi(servicesPath);
    expect(await post("/admin/console/service-preflight", selection)).toMatchObject({
      ok: true,
      allow_pending_creation: true,
      resource_readiness: "unknown",
      ready_for_delivery: false,
      checks: expect.arrayContaining([{ code: "account", status: "passed", reason: null }]),
    });
    expect(await mockApi(servicesPath)).toEqual(before);
    expect(
      await post("/admin/services", { ...selection, idempotency_key: crypto.randomUUID() })
    ).toMatchObject({
      ok: true,
      service: { user_id: userId, status: "pending", connection_state: "pending" },
    });
    expect(await mockApi(servicesPath)).toMatchObject({ total: 1 });
  });

  it("records successful exact reconciliation time once and preserves it on replay", async () => {
    vi.stubGlobal("window", { location: { search: "?mock=usage-reconciliation" }, setTimeout });
    const activation = (await post("/admin/services", {
      ...selection,
      idempotency_key: crypto.randomUUID(),
    })) as { service: UserService };
    expect(activation.service).toMatchObject({
      used_bytes: 500,
      usage_error: "panel_usage_reset",
      desired_status: "paused",
      last_usage_sync_at: null,
    });
    const path = `/admin/services/${activation.service.id}/changes`;
    const body = {
      user_id: userId,
      expected_revision: activation.service.revision,
      idempotency_key: crypto.randomUUID(),
      change: {
        action: "reconcile_usage",
        verified_total_bytes: 600,
        expected_raw_bytes: 100,
        evidence: "Exact per-identity ledger, incident 42",
      },
    };
    const result = (await post(path, body)) as {
      service: UserService;
      order: { created_at: string };
    };
    const confirmedAt = result.service.last_usage_sync_at;
    expect(result).toMatchObject({
      ok: true,
      duplicate: false,
      service: {
        used_bytes: 600,
        usage_total_bytes: 600,
        usage_error: null,
        desired_status: "paused",
        last_usage_sync_at: result.order.created_at,
      },
    });
    expect(Number.isFinite(Date.parse(confirmedAt!))).toBe(true);
    expect(await post(path, body)).toMatchObject({
      ok: true,
      duplicate: true,
      service: { used_bytes: 600, last_usage_sync_at: confirmedAt },
    });
  });

  it("uses the same live ban state as customer management", async () => {
    try {
      expect(await post(`/admin/users/${userId}/ban`, { banned: true })).toMatchObject({
        ok: true,
      });
      expect(await post("/admin/console/service-preflight", selection)).toMatchObject({
        allow_pending_creation: false,
        resource_readiness: "blocked",
        checks: expect.arrayContaining([
          { code: "account", status: "blocked", reason: "account_unavailable" },
        ]),
      });
    } finally {
      await post(`/admin/users/${userId}/ban`, { banned: false });
    }
    expect(await post("/admin/console/service-preflight", selection)).toMatchObject({
      allow_pending_creation: true,
    });
  });

  it.each([0, -1])("blocks missing customer %s even with a valid plan", async (missingId) => {
    expect(
      await post("/admin/console/service-preflight", { ...selection, user_id: missingId })
    ).toMatchObject({
      allow_pending_creation: false,
      ready_for_delivery: false,
      checks: expect.arrayContaining([
        { code: "account", status: "blocked", reason: "account_unavailable" },
      ]),
    });
  });

  it("still rejects a stale plan revision for an available customer", async () => {
    expect(
      await post("/admin/console/service-preflight", { ...selection, expected_revision: 2 })
    ).toMatchObject({
      allow_pending_creation: false,
      checks: expect.arrayContaining([
        { code: "account", status: "passed", reason: null },
        { code: "plan_revision", status: "blocked", reason: "plan_revision_changed" },
      ]),
    });
  });

  it("keeps a held exit unavailable to activation and ordinary evidence actions", async () => {
    const inventory = (await mockApi("/admin/dedicated-exits")) as { exits: DedicatedExit[] };
    const exit = inventory.exits[0];
    const before = { ...exit };
    try {
      exit.hold_order_id = "a".repeat(32);
      exit.hold_service_id = "b".repeat(32);
      exit.service_id = null;
      exit.enabled = true;
      expect(
        await post("/admin/services", {
          ...selection,
          plan_id: "2".repeat(32),
          exit_id: exit.id,
          idempotency_key: crypto.randomUUID(),
        })
      ).toMatchObject({ ok: false, error: "exit_unavailable" });
      for (const action of ["verify", "reclaim"]) {
        expect(
          await post(`/admin/dedicated-exits/${exit.id}/${action}`, {
            expected_revision: exit.revision,
            service_id: null,
            idempotency_key: crypto.randomUUID(),
          })
        ).toMatchObject({ ok: false, error: "exit_replacement_in_progress" });
      }
      expect(exit.hold_order_id).toBe("a".repeat(32));
      expect(exit.service_id).toBeNull();
    } finally {
      Object.assign(exit, before);
    }
  });
});
