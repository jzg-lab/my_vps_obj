import type { AccountOperation } from "$lib/admin/consoleAccountOperations";
import {
  accountArchives,
  accountSources,
  accountStatuses,
} from "$lib/admin/consoleAccountOperations";
import { validOperationIds } from "$lib/admin/consoleGlobalOperations";

const safeErrors = new Set([
  "panel_service_unavailable",
  "service_connection_unconfirmed",
  "service_change_pending",
  "exit_replacement_in_progress",
  "resource_operation_in_progress",
  "panel_access_unconfirmed",
  "account_sync_unconfirmed",
]);
const error = (value: string, status = 400) => ({ ok: false as const, error: value, status });
function project(row: AccountOperation): AccountOperation {
  return {
    id: row.id,
    actor_id: row.actor_id,
    target_id: row.target_id,
    user_id: row.user_id,
    before_banned: row.before_banned,
    desired_banned: row.desired_banned,
    source: row.source,
    status: row.status,
    attempt_count: row.attempt_count,
    created_at: row.created_at,
    attempted_at: row.attempted_at,
    first_failed_at: row.first_failed_at,
    completed_at: row.completed_at,
    error_code:
      row.error_code === null || safeErrors.has(row.error_code)
        ? row.error_code
        : "account_sync_unconfirmed",
    archived: row.user_id === null,
    needs_attention: row.needs_attention,
  };
}

// Reads explicitly supplied evidence only; never creates an audit result or retries a lifecycle.
export function consoleAccountOperationsDemoResponse(
  path: string,
  options: RequestInit,
  records: readonly AccountOperation[] = []
) {
  const url = new URL(path, "https://demo.invalid");
  const root = "/admin/console/account-operations";
  if (url.pathname !== root && !url.pathname.startsWith(`${root}/`)) return undefined;
  if ((options.method ?? "GET") !== "GET") return error("method_not_allowed", 405);
  if (url.pathname !== root) {
    const id = url.pathname.slice(root.length + 1);
    if (!/^[0-9a-f]{32}$/.test(id)) return error("invalid_account_operation_id");
    const row = records.find((operation) => operation.id === id);
    return row
      ? { ok: true as const, operation: project(row) }
      : error("account_operation_not_found", 404);
  }
  const params = url.searchParams;
  const invalid = () => error("invalid_account_operations_query");
  const allowed = new Set([
    "status",
    "source",
    "archived",
    "needs_attention",
    "user_id",
    "actor_id",
    "page",
    "page_size",
  ]);
  for (const key of params.keys())
    if (!allowed.has(key) || params.getAll(key).length !== 1) return invalid();
  for (const [key, values] of [
    ["status", accountStatuses],
    ["source", accountSources],
    ["archived", accountArchives],
    ["needs_attention", ["true", "false"]],
  ] as const)
    if (params.has(key) && !values.some((value) => value === params.get(key))) return invalid();
  for (const key of ["user_id", "actor_id"])
    if (params.has(key) && (!params.get(key) || !validOperationIds(params.get(key)!, "")))
      return invalid();
  const pageText = params.get("page") ?? "0";
  const sizeText = params.get("page_size") ?? "25";
  const page = Number(pageText);
  const pageSize = Number(sizeText);
  if (
    !/^(0|[1-9][0-9]*)$/.test(pageText) ||
    page > 1_000_000 ||
    !/^[1-9][0-9]*$/.test(sizeText) ||
    pageSize > 200
  )
    return invalid();
  const status = params.get("status") ?? "all";
  const source = params.get("source") ?? "all";
  const archived = params.get("archived") ?? "all";
  const rows = records
    .filter(
      (row) =>
        (status === "all" || row.status === status) &&
        (source === "all" || row.source === source) &&
        (archived === "all" ||
          (archived === "only" ? row.user_id === null : row.user_id !== null)) &&
        (!params.has("user_id") || row.target_id === Number(params.get("user_id"))) &&
        (!params.has("actor_id") || row.actor_id === Number(params.get("actor_id"))) &&
        (params.get("needs_attention") !== "true" || row.needs_attention)
    )
    .sort(
      (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at) || b.id.localeCompare(a.id)
    );
  return {
    ok: true as const,
    operations: rows.slice(page * pageSize, (page + 1) * pageSize).map(project),
    total: rows.length,
    page,
    page_size: pageSize,
    observed_at: new Date().toISOString(),
  };
}
