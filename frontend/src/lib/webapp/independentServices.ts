import type { components } from "$lib/api/openapi.generated.js";

export type UserService = components["schemas"]["UserServiceOut"];
export type CatalogPlan = components["schemas"]["ServiceCatalogPlanOut"];

// The server selects the business model; upstream demo fixtures can omit it.
export function independentServiceScreen(screen: string): string {
  return [
    "home",
    "services",
    "settings",
    "security",
    "notifications",
    "support",
    "status",
    "admin",
  ].includes(screen)
    ? screen
    : "home";
}

export function serviceUsage(
  service: Pick<UserService, "used_bytes" | "quota_bytes" | "last_usage_sync_at">
) {
  if (!service.last_usage_sync_at) return { remaining: null, overage: null, percent: null };
  return {
    remaining: Math.max(0, service.quota_bytes - service.used_bytes),
    overage: Math.max(0, service.used_bytes - service.quota_bytes),
    percent: Math.min(100, Math.max(0, (service.used_bytes / service.quota_bytes) * 100)),
  };
}

export function serviceResetState(
  service: Pick<
    UserService,
    "traffic_rule" | "cycle_ends_at" | "expires_at" | "desired_status" | "status"
  >
): "not_monthly" | "unknown" | "ended" | "expires_first" | "scheduled" {
  if (service.traffic_rule !== "monthly") return "not_monthly";
  if (service.desired_status === "cancelled" || service.status === "expired") return "ended";
  if (!service.cycle_ends_at || !service.expires_at) return "unknown";
  const boundary = Date.parse(service.cycle_ends_at);
  const expiry = Date.parse(service.expires_at);
  if (!Number.isFinite(boundary) || !Number.isFinite(expiry)) return "unknown";
  return expiry <= boundary ? "expires_first" : "scheduled";
}

export function serviceDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("sv-SE", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: "Asia/Shanghai",
  }).format(new Date(value));
}

export function serviceStatusKey(status: string): string {
  return `wa_services_status_${
    ["active", "pending", "expired", "exhausted", "paused", "cancelled", "account_banned"].includes(
      status
    )
      ? status
      : "unknown"
  }`;
}
