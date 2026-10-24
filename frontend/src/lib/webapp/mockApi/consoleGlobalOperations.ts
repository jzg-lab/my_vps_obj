import {
  operationArchives,
  operationPhases,
  operationStatuses,
  operationQuery,
  readOperationsRoute,
  validOperationIds,
  type GlobalOperation,
  type GlobalOperations,
} from "$lib/admin/consoleGlobalOperations";
import type { ServiceOperation } from "$lib/admin/consoleServiceOperations";
import type { ConsoleServiceOperationsDemoState } from "./consoleServiceOperations";
import { demoAdminUserById } from "./users";

type Position = Pick<GlobalOperation, "created_at" | "record_type" | "id">;
const compare = (left: Position, right: Position) =>
  Date.parse(right.created_at) - Date.parse(left.created_at) ||
  left.record_type.localeCompare(right.record_type) ||
  left.id.localeCompare(right.id);
const invalid = () => ({ ok: false as const, error: "invalid_global_operations_query" });

// Read the shared demo ledger. Executions exist only when explicitly supplied by a fixture.
export function consoleGlobalOperationsDemoResponse(
  path: string,
  options: RequestInit,
  state: ConsoleServiceOperationsDemoState
): (GlobalOperations & { ok: true }) | { ok: false; error: string } | undefined {
  const url = new URL(path, "https://demo.invalid");
  if (url.pathname !== "/admin/console/operations") return undefined;
  if ((options.method ?? "GET") !== "GET") return invalid();
  const params = url.searchParams;
  const allowed = new Set([
    "status",
    "phase",
    "user_id",
    "service_id",
    "archived",
    "needs_attention",
    "limit",
    "cursor",
  ]);
  for (const key of params.keys())
    if (!allowed.has(key) || params.getAll(key).length !== 1) return invalid();
  for (const [key, values] of [
    ["status", operationStatuses],
    ["phase", operationPhases],
    ["archived", operationArchives],
    ["needs_attention", ["true", "false"]],
  ] as const)
    if (params.has(key) && !values.some((value) => value === params.get(key))) return invalid();
  const route = readOperationsRoute(url.search);
  const limit = Number(params.get("limit") ?? "25");
  if (
    !validOperationIds(route.userId, route.serviceId) ||
    (params.has("user_id") && !route.userId) ||
    (params.has("service_id") && !route.serviceId) ||
    !/^[1-9][0-9]*$/.test(params.get("limit") ?? "25") ||
    limit > 200
  )
    return invalid();
  const filterKey = operationQuery({ ...route, cursor: "" }).toString();
  let after: Position | null = null;
  if (params.has("cursor")) {
    if (!/^[A-Za-z0-9_-]{1,1024}$/.test(route.cursor)) return invalid();
    try {
      const value: unknown = JSON.parse(
        atob(route.cursor.replaceAll("-", "+").replaceAll("_", "/"))
      );
      if (
        !Array.isArray(value) ||
        value.length !== 4 ||
        value[0] !== filterKey ||
        typeof value[1] !== "string" ||
        !Number.isFinite(Date.parse(value[1])) ||
        !["execution", "order"].includes(value[2]) ||
        typeof value[3] !== "string" ||
        !/^[0-9a-f]{32}$/.test(value[3])
      )
        return invalid();
      after = { created_at: value[1], record_type: value[2], id: value[3] };
    } catch {
      return invalid();
    }
  }
  const executions = state.operations ?? [];
  const records: Array<{
    operation: ServiceOperation;
    recordType: GlobalOperation["record_type"];
  }> = executions.map((operation) => ({ operation, recordType: "execution" }));
  for (const order of state.orders ?? []) {
    if (order.kind === "retry" || executions.some((item) => item.order_id === order.id)) continue;
    records.push({
      recordType: "order",
      operation: {
        id: order.id,
        service_id: order.service_id,
        order_id: order.id,
        kind: order.kind,
        phase: null,
        target_revision: null,
        source: "unknown",
        actor_id: order.actor_id,
        status: "unknown",
        attempt_count: null,
        created_at: order.created_at,
        attempted_at: null,
        first_failed_at: null,
        completed_at: null,
        error_code: null,
        retryable: false,
        retry_block_reason: "historical_result_unknown",
        replacement_progress: null,
      },
    });
  }
  const services = new Map(
    [...state.services, ...state.archived].map((service) => [service.id, service])
  );
  const rows: GlobalOperation[] = [];
  for (const { operation, recordType } of records) {
    const service = services.get(operation.service_id);
    if (!service) continue;
    const archived = service.user_id === null;
    const needsAttention =
      recordType === "execution" &&
      (operation.status === "failed" ||
        operation.status === "unknown" ||
        (operation.status === "pending" && operation.error_code !== null));
    if (
      (route.status !== "all" && route.status !== operation.status) ||
      (route.phase !== "all" && route.phase !== operation.phase) ||
      (route.userId && Number(route.userId) !== service.user_id) ||
      (route.serviceId && route.serviceId !== service.id) ||
      (route.archived === "only" && !archived) ||
      (route.archived === "exclude" && archived) ||
      (route.needsAttention && !needsAttention)
    )
      continue;
    const user = archived ? undefined : demoAdminUserById(service.user_id);
    const successes =
      operation.phase === null
        ? []
        : executions.filter(
            (item) =>
              item.service_id === service.id &&
              item.phase === operation.phase &&
              item.status === "succeeded" &&
              item.completed_at !== null
          );
    successes.sort((a, b) => Date.parse(b.completed_at!) - Date.parse(a.completed_at!));
    rows.push({
      id: operation.id,
      service_id: service.id,
      order_id: operation.order_id,
      kind: operation.kind,
      phase: operation.phase,
      target_revision: operation.target_revision,
      source: operation.source,
      actor_id: operation.actor_id,
      status: operation.status,
      attempt_count: operation.attempt_count,
      created_at: operation.created_at,
      attempted_at: operation.attempted_at,
      first_failed_at: operation.first_failed_at,
      completed_at: operation.completed_at,
      error_code: operation.error_code,
      replacement_progress: operation.replacement_progress,
      retryable: !archived && operation.retryable,
      retry_block_reason:
        recordType === "order"
          ? "historical_result_unknown"
          : archived
            ? "service_not_editable"
            : operation.retry_block_reason,
      record_type: recordType,
      needs_attention: needsAttention,
      service_revision: service.revision,
      service_name: service.name,
      archived,
      customer: {
        user_id: user ? service.user_id : null,
        minishop_id: user?.minishop_id ?? null,
        username: user?.username ?? null,
        email: user?.email ?? null,
        first_name: user?.first_name ?? null,
        last_name: user?.last_name ?? null,
        is_banned: user ? Boolean(user.is_banned) : null,
      },
      last_success_at: successes[0]?.completed_at ?? null,
    });
  }
  rows.sort(compare);
  const remaining = after ? rows.filter((row) => compare(row, after) > 0) : rows;
  const page = remaining.slice(0, limit);
  const last = page.at(-1);
  const cursor =
    last && remaining.length > limit
      ? btoa(JSON.stringify([filterKey, last.created_at, last.record_type, last.id]))
          .replaceAll("+", "-")
          .replaceAll("/", "_")
          .replace(/=+$/, "")
      : null;
  return {
    ok: true,
    operations: page,
    total: rows.length,
    limit,
    next_cursor: cursor,
    observed_at: new Date().toISOString(),
  };
}
