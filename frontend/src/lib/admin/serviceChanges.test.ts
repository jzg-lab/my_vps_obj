import { describe, expect, it, vi } from "vitest";
import {
  pendingServiceChange,
  serviceChangeActions,
  submitServiceChange,
  type ServiceChangeBody,
} from "./serviceChanges";

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
const body: ServiceChangeBody = {
  user_id: 17,
  expected_revision: 2,
  idempotency_key: "same-renewal",
  change: {
    action: "renew",
    days: 31,
    price: "12.30",
    currency: "CNY",
    verified_total_bytes: null,
    expected_raw_bytes: null,
    evidence: null,
  },
};

describe("available service changes", () => {
  it.each(["panel_usage_reset", "panel_usage_regressed"])(
    "allows only exact reconciliation after cancellation with %s",
    (usage_error) => {
      expect(
        serviceChangeActions({
          desired_status: "cancelled",
          connection_state: "ready",
          usage_error,
        })
      ).toEqual(["reconcile_usage"]);
    }
  );
  it.each([null, "panel_usage_unavailable"])(
    "keeps other cancelled services closed: %s",
    (usage_error) => {
      expect(
        serviceChangeActions({
          desired_status: "cancelled",
          connection_state: "ready",
          usage_error,
        })
      ).toEqual([]);
    }
  );
  it("does not expose reconciliation for a revoked identity or active service", () => {
    expect(
      serviceChangeActions({
        desired_status: "cancelled",
        connection_state: "revoked",
        usage_error: "panel_usage_reset",
      })
    ).toEqual([]);
    expect(
      serviceChangeActions({
        desired_status: "active",
        connection_state: "ready",
        usage_error: "panel_usage_reset",
      })
    ).toEqual(["renew", "pause"]);
    expect(
      serviceChangeActions({
        desired_status: "paused",
        connection_state: "ready",
        usage_error: "panel_usage_reset",
      })
    ).toEqual(["renew", "reconcile_usage", "resume"]);
  });
});

describe("service change retries", () => {
  it("replays the same renewal after a lost response and dialog reopen", async () => {
    const cache = storage();
    const api = vi
      .fn()
      .mockRejectedValueOnce(new Error("lost response"))
      .mockResolvedValueOnce({ ok: true, service: { id: "one" }, duplicate: true });
    await expect(submitServiceChange(api, cache, "one", body)).rejects.toThrow("lost response");
    expect(pendingServiceChange(cache, 18, "one")).toBeNull();
    expect(pendingServiceChange(cache, 17, "two")).toBeNull();
    const pending = pendingServiceChange(cache, 17, "one");
    expect(pending).toEqual(body);
    await submitServiceChange(api, cache, "one", pending!);
    expect(api.mock.calls[0]).toEqual(api.mock.calls[1]);
    expect(pendingServiceChange(cache, 17, "one")).toBeNull();
  });
  it.each(["service_revision_changed", "idempotency_owner_changed", "service_not_editable"])(
    "clears a rejected operation: %s",
    async (error) => {
      const cache = storage();
      const api = vi.fn().mockResolvedValue({ ok: false, error });
      await expect(submitServiceChange(api, cache, "one", body)).rejects.toMatchObject({ error });
      expect(pendingServiceChange(cache, 17, "one")).toBeNull();
    }
  );
  it("keeps unknown outcomes and does not send if retry storage fails", async () => {
    const cache = storage();
    const api = vi.fn().mockResolvedValue({ ok: false, error: "internal_error" });
    await expect(submitServiceChange(api, cache, "one", body)).rejects.toMatchObject({
      error: "internal_error",
    });
    expect(pendingServiceChange(cache, 17, "one")).toEqual(body);
    cache.setItem = () => {
      throw new Error("unavailable");
    };
    api.mockClear();
    await expect(submitServiceChange(api, cache, "one", body)).rejects.toThrow("unavailable");
    expect(api).not.toHaveBeenCalled();
  });
  it("rejects corrupt persisted requests without issuing a fresh operation", () => {
    const cache = storage();
    cache.setItem(
      "my-vps-service-change:17:one",
      JSON.stringify({ ...body, change: { action: "renew", days: -1 } })
    );
    expect(() => pendingServiceChange(cache, 17, "one")).toThrow("services_storage_failed");
  });
});

it("retains exact reconciliation evidence across lost replies", async () => {
  const cache = storage();
  const recovery: ServiceChangeBody = {
    ...body,
    change: {
      action: "reconcile_usage",
      days: null,
      price: null,
      currency: null,
      verified_total_bytes: 600,
      expected_raw_bytes: 100,
      evidence: "Verified incident ledger",
    },
  };
  const api = vi.fn().mockRejectedValue(new Error("lost reply"));
  await expect(submitServiceChange(api, cache, "one", recovery)).rejects.toThrow("lost reply");
  expect(pendingServiceChange(cache, 17, "one")).toEqual(recovery);
});
