import type { components } from "$lib/api/openapi.generated";

export type ServiceOrder = components["schemas"]["ServiceOrderOut"];

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function date(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

// Read only the recorded terms; never fall back to today's plan or invent missing values.
export function activationSnapshot(order: ServiceOrder) {
  return order.kind === "activate" ? termsSnapshot(order) : null;
}

function termsSnapshot(order: ServiceOrder) {
  const snapshot = order.snapshot;
  const terms = snapshot.terms;
  if (
    !record(terms) ||
    typeof terms.name !== "string" ||
    typeof terms.price !== "string" ||
    !/^\d{1,12}(\.\d{1,2})?$/.test(terms.price) ||
    typeof terms.currency !== "string" ||
    !/^[A-Z]{3}$/.test(terms.currency) ||
    typeof terms.quota_bytes !== "number" ||
    !Number.isSafeInteger(terms.quota_bytes) ||
    terms.quota_bytes <= 0 ||
    !["shared", "dedicated"].includes(String(terms.resource_type)) ||
    !["total", "monthly"].includes(String(terms.traffic_rule)) ||
    !date(snapshot.starts_at) ||
    !date(snapshot.expires_at) ||
    typeof snapshot.plan_revision !== "number" ||
    !Number.isSafeInteger(snapshot.plan_revision) ||
    snapshot.plan_revision < 1
  )
    return null;
  return {
    name: terms.name,
    price: terms.price,
    currency: terms.currency,
    quotaBytes: terms.quota_bytes,
    resourceType: String(terms.resource_type),
    trafficRule: String(terms.traffic_rule),
    startsAt: snapshot.starts_at,
    expiresAt: snapshot.expires_at,
    revision: snapshot.plan_revision,
  };
}

export function serviceOrderSnapshot(order: ServiceOrder) {
  if (order.kind === "activate") {
    const snapshot = activationSnapshot(order);
    return snapshot
      ? { ...snapshot, kind: "activate", beforeStatus: null, desiredStatus: null }
      : null;
  }
  if (!["renew", "pause", "resume"].includes(order.kind)) return null;
  const snapshot = termsSnapshot(order);
  const { change, before, quota_bytes: quotaBytes, desired_status: desiredStatus } = order.snapshot;
  if (
    !snapshot ||
    !record(change) ||
    change.action !== order.kind ||
    !record(before) ||
    !date(before.expires_at) ||
    typeof before.desired_status !== "string" ||
    !["active", "paused"].includes(before.desired_status) ||
    typeof desiredStatus !== "string" ||
    !["active", "paused"].includes(desiredStatus) ||
    typeof quotaBytes !== "number" ||
    !Number.isSafeInteger(quotaBytes) ||
    quotaBytes <= 0
  )
    return null;
  if (
    order.kind === "renew" &&
    (typeof change.price !== "string" ||
      !/^\d{1,12}(\.\d{1,2})?$/.test(change.price) ||
      typeof change.currency !== "string" ||
      !/^[A-Z]{3}$/.test(change.currency))
  )
    return null;
  return {
    ...snapshot,
    kind: order.kind,
    quotaBytes,
    startsAt: before.expires_at,
    price: order.kind === "renew" ? String(change.price) : null,
    currency: order.kind === "renew" ? String(change.currency) : null,
    beforeStatus: before.desired_status,
    desiredStatus,
  };
}
