import type { components } from "$lib/api/openapi.generated";
import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi";
import { withRoutePrefix } from "$lib/webapp/routes";

export type GlobalOperation = components["schemas"]["ConsoleGlobalOperationOut"];
export type GlobalOperations = components["schemas"]["ConsoleGlobalOperationsOut"];
export const operationStatuses = [
  "all",
  "pending",
  "unknown",
  "failed",
  "succeeded",
  "superseded",
] as const;
export const operationPhases = [
  "all",
  "prepare",
  "delivery",
  "entitlement",
  "revocation",
  "usage",
  "exit_replace",
] as const;
export const operationArchives = ["all", "only", "exclude"] as const;
export type OperationsRoute = {
  status: "all" | GlobalOperation["status"];
  phase: "all" | NonNullable<GlobalOperation["phase"]>;
  archived: (typeof operationArchives)[number];
  userId: string;
  serviceId: string;
  needsAttention: boolean;
  cursor: string;
  detailServiceId: string;
};

export function readOperationsRoute(search: string): OperationsRoute {
  const params = new URLSearchParams(search);
  return {
    status: operationStatuses.find((value) => value === params.get("status")) ?? "all",
    phase: operationPhases.find((value) => value === params.get("phase")) ?? "all",
    archived: operationArchives.find((value) => value === params.get("archived")) ?? "all",
    userId: params.get("user_id") ?? "",
    serviceId: params.get("service_id") ?? "",
    needsAttention: params.get("needs_attention") === "true",
    cursor: params.get("cursor") ?? "",
    detailServiceId: /^[0-9a-f]{32}$/.test(params.get("detail_service_id") ?? "")
      ? params.get("detail_service_id")!
      : "",
  };
}

export function validOperationIds(userId: string, serviceId: string): boolean {
  return (
    (!userId || (/^-?(0|[1-9][0-9]*)$/.test(userId) && Number.isSafeInteger(Number(userId)))) &&
    (!serviceId || /^[0-9a-f]{32}$/.test(serviceId))
  );
}

export function operationQuery(route: OperationsRoute): URLSearchParams {
  const query = new URLSearchParams({
    status: route.status,
    phase: route.phase,
    archived: route.archived,
    needs_attention: String(route.needsAttention),
  });
  if (route.userId) query.set("user_id", route.userId);
  if (route.serviceId) query.set("service_id", route.serviceId);
  if (route.cursor) query.set("cursor", route.cursor);
  return query;
}

export function operationsRouteUrl(current: string, route: OperationsRoute, routePrefix = ""): URL {
  const url = new URL(current);
  url.pathname = withRoutePrefix("/admin/console-operations", routePrefix);
  for (const key of [
    "q",
    "sort",
    "page",
    "node_id",
    "user_id",
    "service_id",
    "cursor",
    "detail_service_id",
  ])
    url.searchParams.delete(key);
  url.searchParams.set("section", "console-operations");
  operationQuery(route).forEach((value, key) => url.searchParams.set(key, value));
  if (route.detailServiceId) url.searchParams.set("detail_service_id", route.detailServiceId);
  return url;
}

export function readGlobalOperations(
  api: ApiClient["api"],
  route: OperationsRoute,
  signal?: AbortSignal
): Promise<GlobalOperations> {
  const query = operationQuery(route);
  query.set("limit", "25");
  return api(builtApiPath<"/api/admin/console/operations">(`/admin/console/operations?${query}`), {
    signal,
  }).then(unwrap);
}

export function readOperationTrail(state: unknown, route: OperationsRoute): string[] {
  if (!state || typeof state !== "object" || !("consoleOperationTrail" in state)) return [];
  const saved = state.consoleOperationTrail;
  if (
    !saved ||
    typeof saved !== "object" ||
    !("query" in saved) ||
    !("cursors" in saved) ||
    saved.query !== operationQuery(route).toString() ||
    !Array.isArray(saved.cursors) ||
    !saved.cursors.every(
      (cursor): cursor is string => typeof cursor === "string" && cursor.length <= 1024
    )
  )
    return [];
  return saved.cursors;
}

export function operationHistoryState(route: OperationsRoute, cursors: string[]) {
  // History cannot structured-clone a Svelte state proxy; cursor entries are strings.
  return {
    consoleOperationTrail: { query: operationQuery(route).toString(), cursors: [...cursors] },
  };
}
