import type { components } from "$lib/api/openapi.generated.js";

export type UserService = components["schemas"]["UserServiceOut"];
export type CatalogPlan = components["schemas"]["ServiceCatalogPlanOut"];

// The server selects the business model; upstream demo fixtures can omit it.
export function independentServiceScreen(screen: string): string {
  return ["home", "settings", "security", "notifications", "support", "status", "admin"].includes(
    screen
  )
    ? screen
    : "home";
}

export function serviceUsage(service: Pick<UserService, "used_bytes" | "quota_bytes">) {
  return {
    remaining: Math.max(0, service.quota_bytes - service.used_bytes),
    overage: Math.max(0, service.used_bytes - service.quota_bytes),
    percent: Math.min(100, Math.max(0, (service.used_bytes / service.quota_bytes) * 100)),
  };
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
