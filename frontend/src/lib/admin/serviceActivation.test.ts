import { describe, expect, it, vi } from "vitest";
import {
  pendingServiceActivation,
  submitServiceActivation,
  type ServiceActivation,
} from "./serviceActivation";

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
const body: ServiceActivation = {
  user_id: 17,
  plan_id: "a".repeat(32),
  expected_revision: 2,
  idempotency_key: "stable-request",
  exit_id: null,
};

describe("activation retry", () => {
  it("persists an uncertain request and replays the same body after reopening", async () => {
    const cache = storage();
    const api = vi
      .fn()
      .mockRejectedValueOnce(new Error("connection lost"))
      .mockResolvedValueOnce({ ok: true, service: { id: "service-1" }, duplicate: true });
    await expect(submitServiceActivation(api, cache, body)).rejects.toThrow("connection lost");
    const pending = pendingServiceActivation(cache, 17);
    expect(pending).toEqual(body);
    expect(pendingServiceActivation(cache, 18)).toBeNull();
    expect(await submitServiceActivation(api, cache, pending!)).toEqual({ id: "service-1" });
    expect(api.mock.calls[0]).toEqual(api.mock.calls[1]);
    expect(pendingServiceActivation(cache, 17)).toBeNull();
  });
  it("allows a corrected selection only after an explicit transactional rejection", async () => {
    const cache = storage();
    const api = vi.fn().mockResolvedValue({ ok: false, error: "plan_revision_changed" });
    await expect(submitServiceActivation(api, cache, body)).rejects.toEqual({
      ok: false,
      error: "plan_revision_changed",
    });
    expect(pendingServiceActivation(cache, 17)).toBeNull();
  });
  it("retains unknown server results and refuses to POST without durable retry storage", async () => {
    const cache = storage();
    const api = vi.fn().mockResolvedValue({ ok: false, error: "internal_error" });
    await expect(submitServiceActivation(api, cache, body)).rejects.toMatchObject({
      error: "internal_error",
    });
    expect(pendingServiceActivation(cache, 17)).toEqual(body);
    cache.setItem = () => {
      throw new Error("storage unavailable");
    };
    api.mockClear();
    await expect(submitServiceActivation(api, cache, body)).rejects.toThrow("storage unavailable");
    expect(api).not.toHaveBeenCalled();
  });
});
