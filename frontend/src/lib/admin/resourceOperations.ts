import type { components } from "$lib/api/openapi.generated";
import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi";
import { withRoutePrefix } from "$lib/webapp/routes";
import type { ResourceChange } from "../../admin/sections/nodes/resourcePreview";

export type ResourceOperation = components["schemas"]["ConsoleResourceOperationOut"];
export type ResourceStart = Omit<
  components["schemas"]["ConsoleResourceOperationStartBody"],
  "change"
> & { change: ResourceChange };
export type ResourceEvidence = components["schemas"]["ConsoleResourceOperationEvidenceBody"];
export type ResourceAccepted = components["schemas"]["ConsoleResourceOperationAcceptedOut"];
export const resourceActions = [
  "node_create",
  "group_create",
  "host_create",
  "node_enable",
  "node_disable",
  "node_restart",
  "group_inbounds",
  "host_update",
] as const;
export function resourceActionKey(value: string): string {
  return resourceActions.some((action) => action === value)
    ? `resource_ops_action_${value}`
    : "console_unknown";
}
const errorKeys: Record<string, string> = {
  resource_operation_in_progress: "resource_ops_error_busy",
  resource_operation_not_found: "resource_ops_error_missing",
  resource_operation_changed: "resource_ops_error_changed",
  resource_sources_incomplete: "resource_ops_error_incomplete",
  resource_preview_changed: "resource_ops_error_changed",
  resource_write_unknown: "resource_ops_error_unknown",
  resource_write_rejected: "resource_ops_error_rejected",
  resource_partial_write: "resource_ops_error_partial",
  resource_target_removed: "resource_ops_error_removed",
  resource_manual_reconciliation_required: "resource_ops_error_manual",
  resource_evidence_invalid: "resource_ops_error_evidence",
  resource_retry_not_allowed: "resource_ops_error_retry",
  resource_recovery_invalid: "resource_ops_error_recovery",
  resource_prior_write_unknown: "resource_ops_error_busy",
  resource_replacement_in_progress: "resource_ops_error_busy",
  resource_dry_run: "resource_ops_error_disabled",
  resource_panel_unsupported: "resource_ops_error_disabled",
  resource_create_conflict: "resource_ops_error_conflict",
  resource_deployment_unavailable: "resource_ops_error_deployment",
  resource_idempotency_conflict: "resource_ops_error_conflict",
  invalid_resource_operation_request: "resource_ops_error_input",
  invalid_resource_change: "resource_ops_error_input",
};
export function resourceErrorKey(failure: unknown): string {
  const code =
    typeof failure === "string"
      ? failure
      : failure && typeof failure === "object" && "error" in failure
        ? String(failure.error)
        : "";
  return Object.hasOwn(errorKeys, code) ? errorKeys[code] : "resource_ops_error_unknown";
}
export function resourceRejected(failure: unknown): boolean {
  if (!failure || typeof failure !== "object" || !("error" in failure)) return false;
  if ("status" in failure && ![400, 403, 404, 409, 422].includes(Number(failure.status)))
    return false;
  return (
    Object.hasOwn(errorKeys, String(failure.error)) &&
    ![
      "resource_write_unknown",
      "resource_partial_write",
      "resource_deployment_unavailable",
    ].includes(String(failure.error))
  );
}
export function resourceOperationsUrl(current: string, prefix = "", id = ""): URL {
  const url = new URL(current);
  url.pathname = withRoutePrefix("/admin/console-operations", prefix);
  url.searchParams.set("section", "console-operations");
  url.searchParams.set("operations_view", "resources");
  if (id) url.searchParams.set("resource_operation_id", id);
  else url.searchParams.delete("resource_operation_id");
  return url;
}
export function readResourceOperation(api: ApiClient["api"], id: string) {
  return api(
    builtApiPath<"/api/admin/console/resources/operations/{operation_id}">(
      `/admin/console/resources/operations/${encodeURIComponent(id)}`
    )
  ).then(unwrap);
}
export function resourceReconcile(api: ApiClient["api"], operation: ResourceOperation) {
  return api(
    builtApiPath<"/api/admin/console/resources/operations/{operation_id}/reconcile">(
      `/admin/console/resources/operations/${operation.id}/reconcile`
    ),
    {
      method: "POST",
      body: JSON.stringify({
        expected_version: operation.version,
      } satisfies components["schemas"]["ConsoleResourceOperationReconcileBody"]),
    }
  ).then(unwrap);
}
export function resourceEvidence(api: ApiClient["api"], id: string, body: ResourceEvidence) {
  return api(
    builtApiPath<"/api/admin/console/resources/operations/{operation_id}/evidence">(
      `/admin/console/resources/operations/${id}/evidence`
    ),
    { method: "POST", body: JSON.stringify(body) }
  ).then(unwrap);
}
export function resourceRetry(
  api: ApiClient["api"],
  operation: ResourceOperation,
  fingerprint: string
) {
  return api(
    builtApiPath<"/api/admin/console/resources/operations/{operation_id}/retry">(
      `/admin/console/resources/operations/${operation.id}/retry`
    ),
    {
      method: "POST",
      body: JSON.stringify({
        expected_version: operation.version,
        expected_fingerprint: fingerprint,
      } satisfies components["schemas"]["ConsoleResourceOperationRetryBody"]),
    }
  ).then(unwrap);
}

export function resourceRecovery(operation: ResourceOperation): ResourceChange | null {
  const before = operation.preview.current;
  if (
    !before?.id ||
    operation.gate_active ||
    operation.error_code === "resource_target_removed" ||
    ["pending", "unknown"].includes(operation.status)
  )
    return null;
  switch (operation.change.operation) {
    case "node_enable":
    case "node_disable":
      return before.is_disabled === null
        ? null
        : {
            operation: before.is_disabled ? "node_disable" : "node_enable",
            target_id: before.id,
            force_restart: false,
          };
    case "group_inbounds":
      return {
        operation: "group_inbounds",
        target_id: before.id,
        inbound_ids: [...before.inbound_ids],
      };
    case "host_update": {
      const old = operation.change.patch;
      const patch: Partial<components["schemas"]["ResourceHostPatch"]> = {};
      if (old.profile_id != null) {
        if (!before.profile_id || before.inbound_ids.length !== 1) return null;
        patch.profile_id = before.profile_id;
        patch.inbound_id = before.inbound_ids[0];
      }
      if (old.group_mode != null) {
        if (before.group_mode === null || !before.group_ids) return null;
        patch.group_mode = before.group_mode;
        patch.group_ids = [...before.group_ids];
      }
      if (old.node_ids != null) {
        if (!before.node_ids) return null;
        patch.node_ids = [...before.node_ids];
      }
      if (old.is_disabled != null) {
        if (before.is_disabled === null) return null;
        patch.is_disabled = before.is_disabled;
      }
      if (old.is_hidden != null) {
        if (before.is_hidden === null) return null;
        patch.is_hidden = before.is_hidden;
      }
      if (old.address != null) {
        if (!before.address) return null;
        patch.address = before.address;
      }
      if (old.port != null) {
        if (!before.port) return null;
        patch.port = before.port;
      }
      return { operation: "host_update", target_id: before.id, patch };
    }
    default:
      return null;
  }
}

export function resourceEvidenceBody(
  operation: ResourceOperation,
  result: ResourceEvidence["result"] | "",
  digest: string,
  checkedAt: string,
  targetId: string,
  originalRequestTerminated = false
): ResourceEvidence | null {
  const attempt = operation.attempts.at(-1);
  const time = Date.parse(checkedAt);
  const target = targetId.trim();
  if (
    operation.status !== "unknown" ||
    !attempt ||
    !result ||
    !/^[a-f0-9]{64}$/.test(digest) ||
    !Number.isFinite(time) ||
    time > Date.now() ||
    time < Date.parse(attempt.started_at)
  )
    return null;
  if (target && !/^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/i.test(target)) return null;
  if (operation.change.operation.endsWith("_create") && result !== "not_applied" && !target)
    return null;
  if (
    result === "externally_removed" &&
    (!originalRequestTerminated ||
      !operation.target_id ||
      target !== operation.target_id ||
      Date.now() - time > 5 * 60 * 1000)
  )
    return null;
  return {
    expected_version: operation.version,
    attempt: attempt.number,
    result,
    target_id: target || null,
    evidence_digest: digest,
    checked_at: new Date(time).toISOString(),
    original_request_terminated: result === "externally_removed" ? true : null,
  };
}
