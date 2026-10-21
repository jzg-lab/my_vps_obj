import type { components } from "$lib/api/openapi.generated.js";
import { type ApiClient } from "$lib/webapp/publicApi.js";

export type ServiceActivation = components["schemas"]["ServiceActivationBody"];
const storageKey = (userId: number) => `my-vps-service-activation:${userId}`;

// Keep an uncertain POST across dialog closes/reloads, so retries cannot open another service.
export function pendingServiceActivation(
  storage: Storage,
  userId: number
): ServiceActivation | null {
  const raw = storage.getItem(storageKey(userId));
  if (!raw) return null;
  const value: unknown = JSON.parse(raw);
  if (
    !value ||
    typeof value !== "object" ||
    !("user_id" in value) ||
    value.user_id !== userId ||
    !("plan_id" in value) ||
    typeof value.plan_id !== "string" ||
    !("expected_revision" in value) ||
    typeof value.expected_revision !== "number" ||
    !("idempotency_key" in value) ||
    typeof value.idempotency_key !== "string" ||
    !("exit_id" in value) ||
    (value.exit_id !== null && typeof value.exit_id !== "string")
  ) {
    throw new Error("Invalid pending activation");
  }
  return {
    user_id: userId,
    plan_id: value.plan_id,
    expected_revision: value.expected_revision,
    idempotency_key: value.idempotency_key,
    exit_id: value.exit_id,
  };
}

export async function submitServiceActivation(
  api: ApiClient["api"],
  storage: Storage,
  body: ServiceActivation
) {
  storage.setItem(storageKey(body.user_id), JSON.stringify(body));
  const response = await api("/admin/services", { method: "POST", body: JSON.stringify(body) });
  if (response.ok && "service" in response) {
    storage.removeItem(storageKey(body.user_id));
    return response.service;
  }
  // These are explicit transactional rejections. Transport/server failures remain retryable.
  const rejected = new Set([
    "user_not_found",
    "account_banned",
    "plan_not_found",
    "plan_disabled",
    "plan_revision_changed",
    "dedicated_exit_required",
    "exit_not_found",
    "exit_unavailable",
    "shared_plan_cannot_bind_exit",
    "idempotency_conflict",
    "idempotency_owner_changed",
    "invalid_payload",
  ]);
  if ("error" in response && rejected.has(String(response.error)))
    storage.removeItem(storageKey(body.user_id));
  throw response;
}
