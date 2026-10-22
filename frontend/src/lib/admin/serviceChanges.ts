import type { components } from "$lib/api/openapi.generated";
import { builtApiPath, type ApiClient } from "$lib/webapp/publicApi";

export type ServiceChangeBody = components["schemas"]["ServiceChangeBody"];
export type ServiceAction = ServiceChangeBody["change"]["action"];
const storageKey = (userId: number, serviceId: string) =>
  `my-vps-service-change:${userId}:${serviceId}`;

export function pendingServiceChange(
  storage: Storage,
  userId: number,
  serviceId: string
): ServiceChangeBody | null {
  const raw = storage.getItem(storageKey(userId, serviceId));
  if (!raw) return null;
  const body: unknown = JSON.parse(raw);
  if (
    !body ||
    typeof body !== "object" ||
    !("user_id" in body) ||
    body.user_id !== userId ||
    !("expected_revision" in body) ||
    typeof body.expected_revision !== "number" ||
    !Number.isSafeInteger(body.expected_revision) ||
    body.expected_revision < 1 ||
    !("idempotency_key" in body) ||
    typeof body.idempotency_key !== "string" ||
    !body.idempotency_key ||
    !("change" in body) ||
    !body.change ||
    typeof body.change !== "object"
  )
    throw new Error("services_storage_failed");
  const change = body.change;
  if (!("action" in change)) throw new Error("services_storage_failed");
  let terms: ServiceChangeBody["change"];
  if (change.action === "pause" || change.action === "resume") {
    terms = { action: change.action, days: null, price: null, currency: null };
  } else if (
    change.action === "renew" &&
    "days" in change &&
    typeof change.days === "number" &&
    Number.isSafeInteger(change.days) &&
    change.days > 0 &&
    change.days <= 36500 &&
    "price" in change &&
    typeof change.price === "string" &&
    /^\d{1,12}(\.\d{1,2})?$/.test(change.price) &&
    "currency" in change &&
    typeof change.currency === "string" &&
    /^[A-Z]{3}$/.test(change.currency)
  ) {
    terms = { action: "renew", days: change.days, price: change.price, currency: change.currency };
  } else throw new Error("services_storage_failed");
  return {
    user_id: userId,
    expected_revision: body.expected_revision,
    idempotency_key: body.idempotency_key,
    change: terms,
  };
}

export async function submitServiceChange(
  api: ApiClient["api"],
  storage: Storage,
  serviceId: string,
  body: ServiceChangeBody
) {
  const key = storageKey(body.user_id, serviceId);
  storage.setItem(key, JSON.stringify(body));
  const response = await api(
    builtApiPath<"/api/admin/services/{service_id}/changes">(
      `/admin/services/${serviceId}/changes`
    ),
    {
      method: "POST",
      body: JSON.stringify(body),
    }
  );
  if (response.ok && "service" in response) {
    storage.removeItem(key);
    return response.service;
  }
  if (
    "error" in response &&
    [
      "user_not_found",
      "service_not_found",
      "service_not_editable",
      "service_revision_changed",
      "service_state_unchanged",
      "account_banned",
      "idempotency_conflict",
      "idempotency_owner_changed",
      "invalid_payload",
      "invalid_renewal_date",
    ].includes(String(response.error))
  )
    storage.removeItem(key);
  throw response;
}
