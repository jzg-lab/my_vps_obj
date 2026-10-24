import type { components } from "$lib/api/openapi.generated";
import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi";
import { serviceErrorKey } from "./servicePlans";

export type ServicePreflightBody = components["schemas"]["ConsoleServicePreflightBody"];
export type ServicePreflight = components["schemas"]["ConsoleServicePreflightOut"];
export type ServiceDiagnostics = components["schemas"]["ConsoleServiceDiagnosticsOut"];
export type ServiceOperation = components["schemas"]["ConsoleServiceOperationOut"];
export type ServiceOperations = components["schemas"]["ConsoleServiceOperationsOut"];
export type ServiceRetryBody = components["schemas"]["ConsoleServiceRetryBody"];

export const consoleServiceLabels: Record<string, Record<string, string>> = {
  check: Object.fromEntries(
    [
      "account",
      "plan",
      "plan_revision",
      "exit",
      "resource_sources",
      "groups",
      "subscription_path",
      "exit_verification",
      "identity_and_metering",
    ].map((key) => [key, `console_preflight_check_${key}`])
  ),
  checkStatus: {
    passed: "console_preflight_passed",
    blocked: "console_preflight_blocked",
    unknown: "console_unknown",
  },
  readiness: {
    ready: "console_preflight_ready",
    blocked: "console_preflight_blocked",
    unknown: "console_unknown",
  },
  operation: Object.fromEntries(
    ["pending", "unknown", "failed", "succeeded", "superseded"].map((key) => [
      key,
      `console_ops_status_${key}`,
    ])
  ),
  phase: Object.fromEntries(
    ["prepare", "delivery", "entitlement", "revocation", "usage", "exit_replace"].map((key) => [
      key,
      `console_ops_phase_${key}`,
    ])
  ),
  source: {
    administrator: "console_ops_administrator",
    worker: "console_ops_worker",
    unknown: "console_unknown",
  },
  access: {
    enabled: "console_ops_access_enabled",
    disabled: "console_ops_access_disabled",
    unknown: "console_unknown",
  },
  remote: Object.fromEntries(
    [
      "available",
      "unavailable",
      "unconfigured",
      "not_prepared",
      "unconfirmed",
      "not_found",
      "conflict",
    ].map((key) => [key, `console_ops_remote_${key}`])
  ),
  remoteStatus: {
    ACTIVE: "console_ops_remote_active",
    DISABLED: "console_ops_remote_disabled",
    EXPIRED: "services_status_expired",
    LIMITED: "console_ops_remote_limited",
  },
  status: Object.fromEntries(
    ["active", "pending", "paused", "cancelled", "expired", "exhausted", "account_banned"].map(
      (key) => [key, `services_status_${key}`]
    )
  ),
  connection: Object.fromEntries(
    ["pending", "ready", "error", "revoked"].map((key) => [key, `console_connection_${key}`])
  ),
  next: Object.fromEntries(
    [
      "reconcile_usage",
      "review_identity",
      "review_resources",
      "check_panel_source",
      "verify_exit",
      "inspect_operation_results",
    ].map((key) => [key, `console_ops_next_${key}`])
  ),
  kind: {
    replace_exit: "console_ops_phase_exit_replace",
    ...Object.fromEntries(
      [
        "quota",
        "activate",
        "renew",
        "pause",
        "resume",
        "deliver",
        "revoke",
        "reconcile_usage",
        "settle_usage",
      ].map((key) => [key, `services_${key}`])
    ),
  },
};

export function consoleServiceLabel(group: string, code: string | null): string {
  const labels = Object.hasOwn(consoleServiceLabels, group)
    ? consoleServiceLabels[group]
    : undefined;
  return labels && code !== null && Object.hasOwn(labels, code) ? labels[code] : "console_unknown";
}

const safeMessages: Record<string, string> = {
  replacement_invalid_evidence: "replacement_invalid_evidence",
  replacement_start_blocked: "replacement_start_blocked",
  invalid_replacement_request: "replacement_invalid_evidence",
  invalid_exit_evidence: "replacement_invalid_evidence",
  invalid_service_retry_query: "console_ops_not_retryable",
  invalid_replacement_query: "replacement_changed",
  exit_replacement_evidence_invalid: "replacement_invalid_evidence",
  exit_replacement_scope_changed: "replacement_changed",
  exit_replacement_version_changed: "replacement_changed",
  exit_replacement_stage_changed: "replacement_changed",
  exit_replacement_hold_changed: "replacement_changed",
  exit_replacement_sources_incomplete: "replacement_sources_incomplete",
  exit_replacement_authorizations_unavailable: "replacement_sources_incomplete",
  exit_replacement_service_scope_invalid: "replacement_sources_incomplete",
  exit_replacement_archived_scope_unconfirmed: "replacement_sources_incomplete",
  exit_replacement_authorization_conflict: "replacement_scope_conflict",
  exit_replacement_exclusivity_conflict: "replacement_scope_conflict",
  exit_replacement_group_missing: "replacement_sources_incomplete",
  exit_replacement_path_unavailable: "replacement_sources_incomplete",
  exit_replacement_path_unlocated: "replacement_sources_incomplete",
  exit_replacement_usage_unconfirmed: "replacement_usage_unconfirmed",
  exit_replacement_stop_unconfirmed: "replacement_stop_unconfirmed",
  exit_replacement_stop_evidence_required: "replacement_stop_unconfirmed",
  exit_replacement_close_evidence_required: "replacement_close_required",
  exit_replacement_confirmation_required: "replacement_confirmation_required",
  exit_replacement_binding_unconfirmed: "replacement_binding_unconfirmed",
  exit_replacement_prior_write_unknown: "console_exit_replacement_write_unknown",
  exit_replacement_interrupted: "replacement_interrupted",
  exit_replacement_panel_unsupported: "replacement_panel_unsupported",
  exit_replacement_not_available: "replacement_start_blocked",
  exit_replacement_not_switchable: "replacement_start_blocked",
  exit_replacement_pause_required: "replacement_pause_required",
  exit_replacement_in_progress: "console_exit_replacement_in_progress",
  exit_replacement_state_invalid: "console_exit_replacement_state_invalid",
  exit_replacement_write_unknown: "console_exit_replacement_write_unknown",
  exit_replacement_write_failed: "console_exit_replacement_write_failed",
  account_unavailable: "console_preflight_account_unavailable",
  plan_unavailable: "services_plan_unavailable",
  resource_observation_incomplete: "console_preflight_sources_incomplete",
  configured_groups_unavailable: "console_preflight_groups_unavailable",
  subscription_path_unconfirmed: "console_preflight_path_unconfirmed",
  exit_verification_required: "console_preflight_exit_unverified",
  requires_service_preparation: "console_preflight_not_deliverable",
  shared_plan_cannot_bind_exit: "console_preflight_shared_exit",
  historical_result_unknown: "console_ops_history_unknown",
  operation_not_retryable: "console_ops_not_retryable",
  operation_not_found: "console_ops_not_retryable",
  service_expired: "services_status_expired",
  service_exhausted: "services_status_exhausted",
  usage_reconciliation_required: "console_ops_next_reconcile_usage",
  panel_identity_unconfirmed: "console_ops_identity_unconfirmed",
  panel_identity_missing: "console_ops_identity_missing",
  panel_identity_conflict: "console_ops_next_review_identity",
  panel_identity_terms_mismatch: "console_ops_next_review_resources",
  panel_change_unconfirmed: "console_ops_change_unconfirmed",
  panel_cycle_unconfirmed: "console_ops_cycle_unconfirmed",
  panel_cycle_conflict: "console_ops_cycle_conflict",
  panel_limit_invalid: "console_ops_next_review_resources",
  panel_usage_unavailable: "console_ops_usage_unconfirmed",
  panel_usage_unconfirmed: "console_ops_usage_unconfirmed",
  panel_usage_invalid: "console_ops_usage_unconfirmed",
  panel_usage_regressed: "console_ops_next_reconcile_usage",
  panel_usage_reset: "console_ops_next_reconcile_usage",
  service_delivery_pending: "console_ops_delivery_pending",
  resource_operation_in_progress: "resource_ops_error_busy",
  service_revoke_pending: "console_ops_revoke_pending",
  service_revoke_cycle_pending: "console_ops_cycle_unconfirmed",
  service_revoke_usage_unconfirmed: "console_ops_usage_unconfirmed",
};
export const consoleServiceMessageKeys = Object.values(safeMessages);

export function consoleServiceErrorKey(failure: unknown): string {
  const code =
    typeof failure === "string"
      ? failure
      : failure &&
          typeof failure === "object" &&
          "error" in failure &&
          typeof failure.error === "string"
        ? failure.error
        : "";
  if (Object.hasOwn(safeMessages, code)) return safeMessages[code];
  const existing = serviceErrorKey({ error: code });
  return existing === "services_request_failed" ? "console_ops_unclassified_error" : existing;
}

export function preflightSelectionKey(body: ServicePreflightBody, exitRevision: number | null) {
  return JSON.stringify([
    body.user_id,
    body.plan_id,
    body.expected_revision,
    body.exit_id,
    exitRevision,
  ]);
}

export function readServiceDiagnostics(
  api: ApiClient["api"],
  serviceId: string,
  signal?: AbortSignal
): Promise<ServiceDiagnostics> {
  return api(
    builtApiPath<"/api/admin/console/services/{service_id}/diagnostics">(
      `/admin/console/services/${encodeURIComponent(serviceId)}/diagnostics`
    ),
    { signal }
  ).then(unwrap);
}

export function readServiceOperations(
  api: ApiClient["api"],
  serviceId: string,
  page: number,
  signal?: AbortSignal
): Promise<ServiceOperations> {
  return api(
    builtApiPath<"/api/admin/console/services/{service_id}/operations">(
      `/admin/console/services/${encodeURIComponent(serviceId)}/operations?limit=25&offset=${page * 25}`
    ),
    { signal }
  ).then(unwrap);
}

const retryKey = (serviceId: string, operationId: string) =>
  `my-vps-operation-retry:${serviceId}:${operationId}`;

export function pendingOperationRetry(
  storage: Storage,
  serviceId: string,
  operationId: string
): ServiceRetryBody | null {
  const raw = storage.getItem(retryKey(serviceId, operationId));
  if (!raw) return null;
  const body: unknown = JSON.parse(raw);
  if (
    !body ||
    typeof body !== "object" ||
    !("user_id" in body) ||
    typeof body.user_id !== "number" ||
    !Number.isSafeInteger(body.user_id) ||
    !("expected_revision" in body) ||
    typeof body.expected_revision !== "number" ||
    !Number.isSafeInteger(body.expected_revision) ||
    body.expected_revision < 1 ||
    !("idempotency_key" in body) ||
    typeof body.idempotency_key !== "string" ||
    !body.idempotency_key.trim() ||
    body.idempotency_key.length > 128
  )
    throw new Error("services_storage_failed");
  return {
    user_id: body.user_id,
    expected_revision: body.expected_revision,
    idempotency_key: body.idempotency_key,
  };
}

export function retryBodyForSnapshot(
  diagnostics: ServiceDiagnostics,
  operations: ServiceOperations,
  operationId: string,
  displayed: Pick<ServiceDiagnostics, "user_id" | "service_revision">,
  pending: ServiceRetryBody | null
): ServiceRetryBody {
  if (
    diagnostics.user_id === null ||
    diagnostics.user_id !== displayed.user_id ||
    (pending && pending.user_id !== diagnostics.user_id)
  )
    throw { error: "idempotency_owner_changed" };
  if (
    diagnostics.service_id !== operations.service_id ||
    diagnostics.service_revision !== operations.service_revision
  )
    throw { error: "service_revision_changed" };
  // Reconcile an uncertain receipt with the exact original request, never a new intent.
  if (pending) return pending;
  if (diagnostics.service_revision !== displayed.service_revision)
    throw { error: "service_revision_changed" };
  if (!operations.operations.find((item) => item.id === operationId && item.retryable))
    throw { error: "operation_not_retryable" };
  return {
    user_id: diagnostics.user_id,
    expected_revision: diagnostics.service_revision,
    idempotency_key: crypto.randomUUID(),
  };
}

export async function submitOperationRetry(
  api: ApiClient["api"],
  storage: Storage,
  serviceId: string,
  operationId: string,
  body: ServiceRetryBody
) {
  const key = retryKey(serviceId, operationId);
  storage.setItem(key, JSON.stringify(body));
  const response = await api(
    builtApiPath<"/api/admin/console/services/{service_id}/operations/{operation_id}/retry">(
      `/admin/console/services/${encodeURIComponent(serviceId)}/operations/${encodeURIComponent(operationId)}/retry`
    ),
    { method: "POST", body: JSON.stringify(body) }
  );
  if (response.ok && "accepted" in response && response.accepted) {
    storage.removeItem(key);
    return response;
  }
  if (
    "error" in response &&
    [
      "service_not_found",
      "operation_not_found",
      "service_not_editable",
      "service_revision_changed",
      "operation_not_retryable",
      "usage_reconciliation_required",
      "account_banned",
      "service_expired",
      "service_exhausted",
      "idempotency_conflict",
      "idempotency_owner_changed",
      "invalid_payload",
    ].includes(String(response.error))
  )
    storage.removeItem(key);
  throw response;
}
