import type { components } from "$lib/api/openapi.generated.js";

export type ServicePlan = components["schemas"]["ServicePlanOut"];
export type ServiceTerms = components["schemas"]["ServicePlanTerms"];
export type DedicatedExit = components["schemas"]["DedicatedExitOut"];
export type UserService = components["schemas"]["UserServiceOut"];
export type ServiceTranslate = (
  key: string,
  params?: Record<string, unknown>,
  fallback?: string
) => string;
export const GIB = 2 ** 30;

export type ServicePlanDraft = {
  name: string;
  description: string;
  resourceType: ServiceTerms["resource_type"];
  trafficRule: ServiceTerms["traffic_rule"];
  quotaGiB: string;
  validityDays: string;
  price: string;
  currency: string;
  squadUuids: string[];
  resourcePool: string;
  enabled: boolean;
};

export function servicePlanDraft(plan?: ServicePlan | null): ServicePlanDraft {
  const terms = plan?.terms;
  return {
    name: terms?.name ?? "",
    description: terms?.description ?? "",
    resourceType: terms?.resource_type ?? "shared",
    trafficRule: terms?.traffic_rule ?? "total",
    quotaGiB: terms ? String(terms.quota_bytes / GIB) : "",
    validityDays: terms ? String(terms.validity_days) : "",
    price: terms ? String(terms.price) : "",
    currency: terms?.currency ?? "CNY",
    squadUuids: [...(terms?.squad_uuids ?? [])],
    resourcePool: terms?.resource_pool ?? "",
    enabled: plan?.enabled ?? true,
  };
}

export function servicePlanBody(draft: ServicePlanDraft): components["schemas"]["ServicePlanBody"] {
  const quota = Number(draft.quotaGiB) * GIB;
  const days = Number(draft.validityDays);
  const price = draft.price.trim();
  const currency = draft.currency.trim().toUpperCase();
  if (
    !draft.name.trim() ||
    !Number.isSafeInteger(quota) ||
    quota <= 0 ||
    !Number.isInteger(days) ||
    days < 1 ||
    days > 36500 ||
    !/^\d{1,12}(\.\d{1,2})?$/.test(price) ||
    !/^[A-Z]{3}$/.test(currency)
  ) {
    throw new Error("services_invalid_terms");
  }
  const squads = [...new Set(draft.squadUuids)];
  if (
    (draft.resourceType === "shared" && !squads.length) ||
    (draft.resourceType === "dedicated" && !draft.resourcePool.trim())
  ) {
    throw new Error("services_resource_required");
  }
  return {
    enabled: draft.enabled,
    terms: {
      name: draft.name.trim(),
      description: draft.description.trim(),
      resource_type: draft.resourceType,
      traffic_rule: draft.trafficRule,
      quota_bytes: quota,
      validity_days: days,
      price,
      currency,
      squad_uuids: draft.resourceType === "shared" ? squads : [],
      resource_pool: draft.resourceType === "dedicated" ? draft.resourcePool.trim() : null,
    },
  };
}

export function serviceErrorKey(failure: unknown): string {
  const code =
    failure && typeof failure === "object" && "error" in failure
      ? String(failure.error)
      : failure instanceof Error
        ? failure.message
        : "";
  const aliases: Record<string, string> = {
    plan_revision_changed: "plan_changed",
    plan_disabled: "plan_unavailable",
    plan_not_found: "plan_unavailable",
    exit_not_found: "exit_unavailable",
    dedicated_exit_required: "services_resource_required",
  };
  const normalized = aliases[code] || code;
  const codes = [
    "plan_changed",
    "plan_unavailable",
    "exit_unavailable",
    "exit_already_exists",
    "account_banned",
    "user_not_found",
    "idempotency_conflict",
    "idempotency_owner_changed",
    "services_invalid_terms",
    "services_resource_required",
  ];
  return codes.includes(normalized)
    ? normalized.startsWith("services_")
      ? normalized
      : `services_${normalized}`
    : "services_request_failed";
}

export function serviceBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"];
  const index = Math.min(
    units.length - 1,
    Math.max(0, Math.floor(Math.log(Math.abs(bytes)) / Math.log(1024)))
  );
  return `${Number((bytes / 1024 ** index).toFixed(2))} ${units[index]}`;
}
