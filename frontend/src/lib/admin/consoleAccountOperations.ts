import type { components } from "$lib/api/openapi.generated";
import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi";
import { withRoutePrefix } from "$lib/webapp/routes";
import { operationArchives, operationStatuses, validOperationIds } from "./consoleGlobalOperations";

export type AccountOperation = components["schemas"]["ConsoleAccountOperationOut"];
export type AccountOperations = components["schemas"]["ConsoleAccountOperationsOut"];
export { operationArchives as accountArchives, operationStatuses as accountStatuses };
export const accountSources = ["all", "administrator", "worker"] as const;
export const operationViews = ["services", "resources", "accounts"] as const;
export type AccountOperationsRoute = {
  status: (typeof operationStatuses)[number];
  source: (typeof accountSources)[number];
  archived: (typeof operationArchives)[number];
  needsAttention: boolean;
  userId: string;
  actorId: string;
  page: number;
  operationId: string;
};

export function readOperationView(search: string) {
  const value = new URLSearchParams(search).get("operations_view");
  return operationViews.find((view) => view === value) ?? "services";
}

export function readAccountOperationsRoute(search: string): AccountOperationsRoute {
  const params = new URLSearchParams(search);
  const page = params.get("account_page") ?? "0";
  const id = params.get("account_operation_id") ?? "";
  return {
    status: operationStatuses.find((value) => value === params.get("account_status")) ?? "all",
    source: accountSources.find((value) => value === params.get("account_source")) ?? "all",
    archived: operationArchives.find((value) => value === params.get("account_archived")) ?? "all",
    needsAttention: params.get("account_needs_attention") === "true",
    userId: params.get("account_user_id") ?? "",
    actorId: params.get("account_actor_id") ?? "",
    page: /^(0|[1-9][0-9]*)$/.test(page) && Number(page) <= 1_000_000 ? Number(page) : -1,
    operationId: /^[0-9a-f]{32}$/.test(id) ? id : "",
  };
}

export function validAccountOperationsRoute(route: AccountOperationsRoute) {
  return (
    validOperationIds(route.userId, "") &&
    validOperationIds(route.actorId, "") &&
    Number.isSafeInteger(route.page) &&
    route.page >= 0 &&
    route.page <= 1_000_000
  );
}

export function accountOperationQuery(route: AccountOperationsRoute): URLSearchParams {
  const params = new URLSearchParams({
    status: route.status,
    source: route.source,
    archived: route.archived,
    needs_attention: String(route.needsAttention),
    page: String(route.page),
    page_size: "25",
  });
  if (route.userId) params.set("user_id", route.userId);
  if (route.actorId) params.set("actor_id", route.actorId);
  return params;
}

export function accountOperationsUrl(current: string, route: AccountOperationsRoute, prefix = "") {
  const url = new URL(current);
  url.pathname = withRoutePrefix("/admin/console-operations", prefix);
  url.searchParams.set("section", "console-operations");
  url.searchParams.set("operations_view", "accounts");
  // Separate account filters from the service cursor and resource detail retained in this URL.
  for (const key of [
    "status",
    "source",
    "archived",
    "needs_attention",
    "user_id",
    "actor_id",
    "page",
  ])
    url.searchParams.delete(`account_${key}`);
  accountOperationQuery(route).forEach((value, key) => {
    if (key !== "page_size") url.searchParams.set(`account_${key}`, value);
  });
  url.searchParams.delete("account_operation_id");
  if (route.operationId) url.searchParams.set("account_operation_id", route.operationId);
  return url;
}

export function readAccountOperations(
  api: ApiClient["api"],
  route: AccountOperationsRoute,
  signal?: AbortSignal
) {
  return api(
    builtApiPath<"/api/admin/console/account-operations">(
      `/admin/console/account-operations?${accountOperationQuery(route)}`
    ),
    { signal }
  ).then(unwrap);
}

export function readAccountOperation(api: ApiClient["api"], id: string, signal?: AbortSignal) {
  return api(
    builtApiPath<"/api/admin/console/account-operations/{operation_id}">(
      `/admin/console/account-operations/${encodeURIComponent(id)}`
    ),
    { signal }
  ).then((result) => unwrap(result).operation);
}

export function accountOperationCustomer(operation: AccountOperation): number | null {
  return operation.archived ? null : operation.user_id;
}

export function accountBanKey(value: boolean | null) {
  return value === null ? "console_unknown" : value ? "account_ops_banned" : "account_ops_unbanned";
}

const errors: Record<string, string> = {
  panel_service_unavailable: "account_ops_error_panel",
  service_connection_unconfirmed: "account_ops_error_connection",
  service_change_pending: "account_ops_error_change",
  exit_replacement_in_progress: "account_ops_error_replacement",
  resource_operation_in_progress: "resource_ops_error_busy",
  panel_access_unconfirmed: "account_ops_error_access",
  account_sync_unconfirmed: "account_ops_error_unconfirmed",
};
export function accountOperationErrorKey(code: string) {
  return Object.hasOwn(errors, code) ? errors[code] : "account_ops_error_unconfirmed";
}
