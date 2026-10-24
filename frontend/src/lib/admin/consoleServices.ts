import type { components } from "$lib/api/openapi.generated";
import { withRoutePrefix } from "$lib/webapp/routes";

export type ConsoleService = components["schemas"]["ConsoleServiceOut"];
export type ConsoleSummary = components["schemas"]["ConsoleSummaryOut"];
export const consoleStatuses = [
  "all",
  "active",
  "pending",
  "paused",
  "cancelled",
  "expired",
  "exhausted",
  "account_banned",
  "sync_error",
  "sync_pending",
  "usage_unconfirmed",
  "expiring",
] as const;
export const consoleSorts = [
  "created_desc",
  "created_asc",
  "expires_asc",
  "expires_desc",
  "usage_desc",
] as const;
export type ServicesRoute = {
  q: string;
  status: string;
  sort: string;
  page: number;
  serviceId: string;
  userId: string;
};

export function readServicesRoute(search: string): ServicesRoute {
  const params = new URLSearchParams(search);
  const page = Number(params.get("page") || 0);
  return {
    q: (params.get("q") || "").slice(0, 200),
    status: consoleStatuses.find((value) => value === params.get("status")) || "all",
    sort: consoleSorts.find((value) => value === params.get("sort")) || "created_desc",
    page: Number.isSafeInteger(page) && page >= 0 && page <= 1_000_000 ? page : 0,
    serviceId: params.get("service_id") || "",
    userId: /^-?\d+$/.test(params.get("user_id") || "") ? params.get("user_id")! : "",
  };
}

export function servicesRouteUrl(current: string, route: ServicesRoute, routePrefix = ""): URL {
  const url = new URL(current);
  url.pathname = withRoutePrefix("/admin/services", routePrefix);
  url.searchParams.set("section", "services");
  url.searchParams.delete("node_id");
  for (const [key, value] of Object.entries({
    q: route.q,
    status: route.status === "all" ? "" : route.status,
    sort: route.sort === "created_desc" ? "" : route.sort,
    page: route.page ? String(route.page) : "",
    service_id: route.serviceId,
    user_id: route.userId,
  })) {
    if (value) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
  }
  return url;
}

export function customerLabel(customer: ConsoleService["customer"]): string {
  if (customer.user_id === null) return "";
  return (
    [customer.first_name, customer.last_name].filter(Boolean).join(" ") ||
    customer.email ||
    (customer.username ? `@${customer.username}` : (customer.minishop_id ?? ""))
  );
}

export function consoleAccessDenied(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "error" in error &&
    ["forbidden", "unauthorized"].includes(String(error.error))
  );
}
