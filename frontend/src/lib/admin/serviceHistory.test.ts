import { describe, expect, it } from "vitest";
import { activationSnapshot, type ServiceOrder } from "./serviceHistory";

const order: ServiceOrder = {
  id: "a".repeat(32),
  user_id: null,
  service_id: "b".repeat(32),
  actor_id: 42,
  kind: "activate",
  created_at: "2026-10-22T00:00:00Z",
  snapshot: {
    plan_revision: 2,
    starts_at: "2026-10-22T00:00:00Z",
    expires_at: "2027-01-20T00:00:00Z",
    terms: {
      name: "Original plan",
      price: "19.90",
      currency: "CNY",
      quota_bytes: 107374182401,
      resource_type: "shared",
      traffic_rule: "total",
    },
  },
};

describe("activationSnapshot", () => {
  it("preserves the historical price and exact byte allowance after account deletion", () => {
    expect(activationSnapshot(order)).toMatchObject({
      name: "Original plan",
      price: "19.90",
      quotaBytes: 107374182401,
      revision: 2,
    });
  });
  it.each([
    {},
    { terms: null },
    { terms: { price: 0 } },
    { ...order.snapshot, expires_at: "invalid" },
  ])("does not invent values for incomplete history", (snapshot) => {
    expect(activationSnapshot({ ...order, snapshot })).toBeNull();
  });
  it("does not mislabel another operation as an activation", () => {
    expect(activationSnapshot({ ...order, kind: "renew" })).toBeNull();
  });
});

import { serviceOrderSnapshot } from "./serviceHistory";

describe("operation history", () => {
  const snapshot = {
    ...order.snapshot,
    quota_bytes: 100,
    desired_status: "paused",
    before: { expires_at: "2027-01-20T00:00:00Z", desired_status: "paused" },
    change: { action: "renew", days: 31, price: "3.90", currency: "USD" },
  };
  it("uses the renewal's recorded price and quota instead of the activation price", () => {
    expect(serviceOrderSnapshot({ ...order, kind: "renew", snapshot })).toMatchObject({
      kind: "renew",
      price: "3.90",
      currency: "USD",
      quotaBytes: 100,
      beforeStatus: "paused",
      desiredStatus: "paused",
    });
  });
  it("does not label a pause as a purchase or invent a price for it", () => {
    expect(
      serviceOrderSnapshot({
        ...order,
        kind: "pause",
        snapshot: { ...snapshot, change: { action: "pause" } },
      })
    ).toMatchObject({ kind: "pause", price: null });
    expect(
      serviceOrderSnapshot({ ...order, kind: "renew", snapshot: { ...snapshot, change: {} } })
    ).toBeNull();
  });
});
