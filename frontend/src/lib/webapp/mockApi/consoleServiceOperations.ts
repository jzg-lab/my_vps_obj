import type { components } from "$lib/api/openapi.generated";
import type { DedicatedExit, ServicePlan, UserService } from "$lib/admin/servicePlans";
import type { ServiceOrder } from "$lib/admin/serviceHistory";
import type {
  ServiceDiagnostics,
  ServiceOperation,
  ServiceOperations,
  ServicePreflight,
} from "$lib/admin/consoleServiceOperations";
import { jsonBody } from "../demoMockRuntime";

export type ConsoleServiceOperationsDemoState = {
  owner: number;
  banned?: boolean;
  services: UserService[];
  archived: UserService[];
  plans: ServicePlan[];
  exits: DedicatedExit[];
  orders?: ServiceOrder[];
  operations?: ServiceOperation[];
};
type RetryResult = components["schemas"]["ConsoleServiceRetryOut"];

// The shared router supplies its existing state; this adapter never creates entitlements.
export function createConsoleServiceOperationsDemo() {
  const receipts = new Map<string, { request: string; result: RetryResult }>();
  return (
    path: string,
    options: RequestInit,
    state: ConsoleServiceOperationsDemoState
  ): unknown => {
    const url = new URL(path, "https://demo.invalid");
    const method = options.method || "GET";
    const body = jsonBody(options);
    const now = new Date().toISOString();
    if (url.pathname === "/admin/console/service-preflight" && method === "POST") {
      if (
        typeof body.user_id !== "number" ||
        typeof body.plan_id !== "string" ||
        typeof body.expected_revision !== "number" ||
        (body.exit_id !== null && typeof body.exit_id !== "string")
      )
        return { ok: false, error: "invalid_payload" };
      const plan = state.plans.find((item) => item.id === body.plan_id);
      const exit = state.exits.find((item) => item.id === body.exit_id);
      const accountAllowed = body.user_id === state.owner && !state.banned;
      const checks: ServicePreflight["checks"] = [
        {
          code: "account",
          status: accountAllowed ? "passed" : "blocked",
          reason: accountAllowed ? null : "account_unavailable",
        },
        {
          code: "plan",
          status: plan?.enabled ? "passed" : "blocked",
          reason: plan?.enabled ? null : "plan_unavailable",
        },
        {
          code: "plan_revision",
          status: plan?.revision === body.expected_revision ? "passed" : "blocked",
          reason: plan?.revision === body.expected_revision ? null : "plan_revision_changed",
        },
      ];
      const exitAllowed =
        plan?.terms.resource_type === "dedicated"
          ? Boolean(
              exit?.enabled &&
              !exit.service_id &&
              !exit.hold_order_id &&
              exit.resource_pool === plan.terms.resource_pool
            )
          : body.exit_id === null;
      checks.push({
        code: "exit",
        status: exitAllowed ? "passed" : "blocked",
        reason: exitAllowed ? null : "exit_unavailable",
      });
      const allowed = checks.every((item) => item.status === "passed");
      checks.push(
        { code: "resource_sources", status: "unknown", reason: "resource_observation_incomplete" },
        { code: "identity_and_metering", status: "unknown", reason: "requires_service_preparation" }
      );
      const result: ServicePreflight = {
        user_id: body.user_id,
        plan_id: body.plan_id,
        plan_revision: plan?.revision ?? null,
        exit_id: body.exit_id,
        exit_revision: exit?.revision ?? null,
        terms: plan?.terms ?? null,
        allow_pending_creation: allowed,
        resource_readiness: allowed ? "unknown" : "blocked",
        ready_for_delivery: false,
        checks,
        configured_group_ids: plan?.terms.squad_uuids ?? [],
        nodes: [],
        hosts: [],
        sources: (["nodes", "hosts", "internal_squads"] as const).map((source) => ({
          source,
          availability: "unconfigured",
          attempted_at: now,
          last_success_at: null,
          error: "not_configured",
        })),
        local_observed_at: now,
      };
      return { ok: true, ...result };
    }
    const match = url.pathname.match(
      /^\/admin\/console\/services\/([^/]+)\/(diagnostics|operations)(?:\/([^/]+)\/retry)?$/
    );
    if (!match) return undefined;
    const service = [...state.services, ...state.archived].find((item) => item.id === match[1]);
    if (!service) return { ok: false, error: "service_not_found" };
    if (match[2] === "diagnostics" && !match[3] && method === "GET") {
      const result: ServiceDiagnostics = {
        service_id: service.id,
        user_id: service.user_id,
        service_revision: service.revision,
        status: service.status,
        desired_status: service.desired_status,
        target_access:
          service.status === "active" ? (service.usage_error ? "unknown" : "enabled") : "disabled",
        connection_state: service.connection_state,
        sync_pending: service.sync_pending,
        errors: { preparation: null, entitlement: service.sync_error, usage: service.usage_error },
        last_usage_sync_at: service.last_usage_sync_at,
        sync_confirmed_at: service.sync_confirmed_at,
        local_observed_at: now,
        data_plane_verified: false,
        remote: {
          availability: "unconfigured",
          attempted_at: null,
          observed_at: null,
          identity_matches: null,
          terms_match: null,
          status: null,
          usage_readable: null,
          raw_used_bytes: null,
          error: null,
        },
        next_steps: ["check_panel_source"],
      };
      return { ok: true, ...result };
    }
    const rows = (state.operations ?? []).filter((item) => item.service_id === service.id);
    if (match[2] === "operations" && !match[3] && method === "GET") {
      const legacy: ServiceOperation[] = (state.orders ?? [])
        .filter(
          (order) =>
            order.service_id === service.id &&
            order.kind !== "retry" &&
            !rows.some((item) => item.order_id === order.id)
        )
        .map((order) => ({
          id: order.id,
          service_id: service.id,
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
        }));
      const records = [...rows, ...legacy].sort(
        (a, b) => b.created_at.localeCompare(a.created_at) || b.id.localeCompare(a.id)
      );
      const limit = Math.max(1, Math.min(200, Number(url.searchParams.get("limit")) || 25));
      const offset = Math.max(0, Number(url.searchParams.get("offset")) || 0);
      const result: ServiceOperations = {
        service_id: service.id,
        service_revision: service.revision,
        operations: records.slice(offset, offset + limit),
        total: records.length,
        limit,
        offset,
      };
      return { ok: true, ...result };
    }
    if (match[2] !== "operations" || !match[3] || method !== "POST")
      return { ok: false, error: "invalid_payload" };
    if (
      typeof body.user_id !== "number" ||
      typeof body.expected_revision !== "number" ||
      typeof body.idempotency_key !== "string" ||
      !body.idempotency_key
    )
      return { ok: false, error: "invalid_payload" };
    if (service.user_id === null || service.user_id !== body.user_id)
      return { ok: false, error: "service_not_found" };
    const operation = rows.find((item) => item.id === match[3]);
    if (!operation) return { ok: false, error: "operation_not_found" };
    const key = `${body.user_id}:${body.idempotency_key}`;
    const request = JSON.stringify([service.id, operation.id, body.expected_revision]);
    const previous = receipts.get(key);
    if (previous)
      return previous.request === request
        ? { ok: true, ...previous.result, duplicate: true }
        : { ok: false, error: "idempotency_conflict" };
    if (service.revision !== body.expected_revision)
      return { ok: false, error: "service_revision_changed" };
    if (!operation.retryable)
      return { ok: false, error: operation.retry_block_reason ?? "operation_not_retryable" };
    // Simulated acknowledgement records no remote attempt or success timestamp.
    if (operation.status !== "unknown") operation.status = "pending";
    const result: RetryResult = {
      accepted: true,
      operation: { ...operation },
      retry_order_id: crypto.randomUUID().replaceAll("-", ""),
      duplicate: false,
    };
    receipts.set(key, { request, result });
    return { ok: true, ...result };
  };
}
