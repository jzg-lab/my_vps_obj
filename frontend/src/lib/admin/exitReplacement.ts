import type { components } from "$lib/api/openapi.generated";
import type { UserService } from "./servicePlans";
import { builtApiPath, unwrap, type ApiClient } from "../webapp/publicApi";

export type ReplacementState = components["schemas"]["ConsoleExitReplacementStateOut"];
export type Replacement = components["schemas"]["ConsoleExitReplacementOut"];
export type ReplacementDraft = components["schemas"]["ConsoleExitReplacementDraftOut"];
export type ReplacementExit = components["schemas"]["ReplacementExitOut"];
export type ReplacementAction = Replacement["allowed_actions"][number];
export type ReplacementWrite =
  | { action: "start"; body: components["schemas"]["ConsoleExitReplacementStartBody"] }
  | { action: "confirm"; body: components["schemas"]["ConsoleExitReplacementConfirmBody"] }
  | {
      action: "stop_evidence" | "close_evidence" | "resolve_write";
      body: components["schemas"]["ConsoleExitReplacementEvidenceBody"];
    }
  | { action: "verify"; exitId: string; body: components["schemas"]["ExitReplacementVerifyBody"] }
  | {
      action: "reclaim" | "candidate_cleanup";
      exitId: string;
      body: components["schemas"]["ExitReplacementReclaimBody"];
    }
  | {
      action: "retry";
      operationId: string;
      body: components["schemas"]["ConsoleServiceRetryBody"];
    };

export type ReplacementFields = {
  checkedAt: string;
  digest: string;
  observedIp: string;
  usageAt: string;
  total: string;
  raw: string;
  offset: string;
  usageDigest: string;
  result: "" | "applied" | "not_applied";
  authorizationRemoved: boolean;
  connectionsStopped: boolean;
  oldConfigRejected: boolean;
  fixed: boolean;
  exclusive: boolean;
  confirmed: boolean;
};

export function emptyReplacementFields(): ReplacementFields {
  return {
    checkedAt: "",
    digest: "",
    observedIp: "",
    usageAt: "",
    total: "",
    raw: "",
    offset: "",
    usageDigest: "",
    result: "",
    authorizationRemoved: false,
    connectionsStopped: false,
    oldConfigRejected: false,
    fixed: false,
    exclusive: false,
    confirmed: false,
  };
}

export const replacementActions: ReplacementAction[] = [
  "stop_evidence",
  "resolve_write",
  "verify",
  "confirm",
  "retry",
  "candidate_cleanup",
  "close_evidence",
  "reclaim",
];

export const replacementLabels: Record<string, Record<string, string>> = {
  stage: Object.fromEntries(
    [
      "stopping_old",
      "awaiting_confirmation",
      "switching",
      "restoring",
      "closing",
      "completed",
      "closed",
    ].map((code) => [code, `replacement_stage_${code}`])
  ),
  switch: Object.fromEntries(
    ["not_started", "pending", "confirmed", "unknown", "interrupted"].map((code) => [
      code,
      `replacement_switch_${code}`,
    ])
  ),
  restore: Object.fromEntries(
    ["not_requested", "pending", "enabled", "restricted", "unknown", "interrupted"].map((code) => [
      code,
      `replacement_restore_${code}`,
    ])
  ),
  old: Object.fromEntries(
    ["current", "held", "released"].map((code) => [code, `replacement_old_${code}`])
  ),
  action: Object.fromEntries(
    replacementActions.map((code) => [code, `replacement_action_${code}`])
  ),
  write: Object.fromEntries(
    ["stop_old", "set_target_group", "restore", "close_access"].map((code) => [
      code,
      `replacement_write_${code}`,
    ])
  ),
  block: {
    account_banned: "services_account_banned",
    service_paused: "services_status_paused",
    service_expired: "services_status_expired",
    service_exhausted: "services_status_exhausted",
    service_cancelled: "services_status_cancelled",
    service_not_started: "services_status_pending",
    service_not_deliverable: "services_service_not_deliverable",
    exit_unavailable: "services_exit_unavailable",
  },
};
export function replacementLabel(group: string, code: string | null): string {
  const labels = Object.hasOwn(replacementLabels, group) ? replacementLabels[group] : undefined;
  return labels && code && Object.hasOwn(labels, code) ? labels[code] : "console_unknown";
}

export function replacementSnapshot(state: ReplacementState): string {
  const row = state.replacement ?? state.draft;
  return JSON.stringify([
    state.service_id,
    state.service_revision,
    row?.resource_fingerprint,
    row?.coverage,
    state.draft?.allowed_to_start,
    row?.old_exit.id,
    row?.old_exit.revision,
    row?.old_exit.scope_fingerprint,
    row?.candidate_exit.id,
    row?.candidate_exit.revision,
    row?.candidate_exit.scope_fingerprint,
    state.replacement?.operation.id,
    state.replacement?.progress.version,
    state.replacement?.progress.pending_action,
    state.replacement?.requested_resource_fingerprint,
    state.replacement?.allowed_actions,
  ]);
}

export function replacementAvailable(state: ReplacementState, action: ReplacementAction): boolean {
  const row = state.replacement;
  if (!row || !row.allowed_actions.includes(action)) return false;
  if (row.progress.pending_action) return action === "resolve_write";
  if (["verify", "confirm"].includes(action))
    return (
      row.coverage === "complete" && row.resource_fingerprint === row.requested_resource_fingerprint
    );
  return true;
}

export function replacementInteger(value: string): number {
  if (!/^(0|[1-9]\d*)$/.test(value) || !Number.isSafeInteger(Number(value)))
    throw { error: "replacement_invalid_evidence" };
  return Number(value);
}
export function replacementTime(value: string): string {
  const stamp = new Date(value);
  if (!value || !Number.isFinite(stamp.getTime()) || stamp.getTime() > Date.now())
    throw { error: "replacement_invalid_evidence" };
  return stamp.toISOString();
}
export function replacementDigest(value: string | null): string {
  if (!value || !/^[0-9a-f]{64}$/.test(value)) throw { error: "replacement_invalid_evidence" };
  return value;
}

export function startReplacementWrite(
  state: ReplacementState,
  userId: number,
  reason: string,
  key: string = crypto.randomUUID()
): ReplacementWrite {
  const draft = state.draft;
  if (
    !draft?.allowed_to_start ||
    draft.coverage !== "complete" ||
    reason.trim().length < 3 ||
    reason.trim().length > 1000
  )
    throw { error: "replacement_start_blocked" };
  return {
    action: "start",
    body: {
      user_id: userId,
      expected_revision: state.service_revision,
      old_exit_id: draft.old_exit.id,
      new_exit_id: draft.candidate_exit.id,
      expected_old_exit_revision: draft.old_exit.revision,
      expected_new_exit_revision: draft.candidate_exit.revision,
      expected_resource_fingerprint: replacementDigest(draft.resource_fingerprint),
      reason: reason.trim(),
      idempotency_key: key,
    },
  };
}

export function replacementWrite(
  state: ReplacementState,
  userId: number,
  action: ReplacementAction,
  fields: ReplacementFields,
  exitId?: string,
  key: string = crypto.randomUUID()
): ReplacementWrite {
  const row = state.replacement;
  if (!row || !replacementAvailable(state, action)) throw { error: "operation_not_retryable" };
  if (action === "retry")
    return {
      action,
      operationId: row.operation.id,
      body: {
        user_id: userId,
        expected_revision: state.service_revision,
        idempotency_key: key,
      },
    };
  if (action === "confirm") {
    if (!fields.confirmed || !row.old_stop?.valid || !row.candidate_verification?.valid)
      throw { error: "replacement_invalid_evidence" };
    return {
      action,
      body: {
        user_id: userId,
        operation_id: row.operation.id,
        expected_revision: state.service_revision,
        expected_operation_version: row.progress.version,
        expected_old_exit_revision: row.old_exit.revision,
        expected_new_exit_revision: row.candidate_exit.revision,
        expected_resource_fingerprint: replacementDigest(row.resource_fingerprint),
        old_stop_audit_id: row.old_stop.audit_id,
        candidate_verify_audit_id: row.candidate_verification.audit_id,
        confirm_replace_and_request_restore: true,
        idempotency_key: key,
      },
    };
  }
  const common = {
    idempotency_key: key,
    expected_operation_version: row.progress.version,
    checked_at: replacementTime(fields.checkedAt),
    evidence_digest: replacementDigest(fields.digest),
  };
  if (action === "verify") {
    if (!fields.fixed || !fields.exclusive || !fields.observedIp.trim())
      throw { error: "replacement_invalid_evidence" };
    return {
      action,
      exitId: row.candidate_exit.id,
      body: {
        ...common,
        replacement_operation_id: row.operation.id,
        service_id: state.service_id,
        expected_revision: row.candidate_exit.revision,
        scope_fingerprint: replacementDigest(row.candidate_exit.scope_fingerprint),
        observed_ip: fields.observedIp.trim(),
        fixed: true,
        exclusive: true,
      },
    };
  }
  if (action === "reclaim" || action === "candidate_cleanup") {
    const resource =
      exitId === row.old_exit.id
        ? row.old_exit
        : exitId === row.candidate_exit.id
          ? row.candidate_exit
          : null;
    if (
      !resource ||
      !fields.connectionsStopped ||
      !fields.oldConfigRejected ||
      (action === "candidate_cleanup" && resource.id !== row.candidate_exit.id) ||
      (action === "reclaim" && resource.hold_order_id !== row.operation.order_id)
    )
      throw { error: "replacement_invalid_evidence" };
    return {
      action,
      exitId: resource.id,
      body: {
        ...common,
        replacement_operation_id: row.operation.id,
        service_id: state.service_id,
        expected_revision: resource.revision,
        scope_fingerprint: replacementDigest(resource.scope_fingerprint),
        reclaim_purpose: resource.id === row.old_exit.id ? "retained_old" : "candidate_cleanup",
        connections_stopped: true,
        old_config_rejected: true,
      },
    };
  }
  const body: components["schemas"]["ConsoleExitReplacementEvidenceBody"] = {
    ...common,
    operation_id: row.operation.id,
    resource_fingerprint: replacementDigest(row.resource_fingerprint),
    purpose:
      action === "stop_evidence" ? "stop" : action === "close_evidence" ? "close" : "resolve_write",
    authorization_removed: null,
    connections_stopped: null,
    old_config_rejected: null,
    usage_observed_at: null,
    usage_total_bytes: null,
    usage_raw_bytes: null,
    usage_lifetime_offset: null,
    usage_evidence_digest: null,
    action: null,
    attempt: null,
    result: null,
  };
  if (action === "resolve_write") {
    if (!row.progress.pending_action || !row.operation.attempt_count || !fields.result)
      throw { error: "replacement_invalid_evidence" };
    body.action = row.progress.pending_action;
    body.attempt = row.operation.attempt_count;
    body.result = fields.result;
  } else {
    if (!fields.authorizationRemoved || !fields.connectionsStopped || !fields.oldConfigRejected)
      throw { error: "replacement_invalid_evidence" };
    body.authorization_removed = true;
    body.connections_stopped = true;
    body.old_config_rejected = true;
    body.usage_observed_at = replacementTime(fields.usageAt);
    if (body.usage_observed_at < body.checked_at) throw { error: "replacement_invalid_evidence" };
    body.usage_total_bytes = replacementInteger(fields.total);
    body.usage_raw_bytes = replacementInteger(fields.raw);
    body.usage_lifetime_offset = replacementInteger(fields.offset);
    body.usage_evidence_digest = replacementDigest(fields.usageDigest);
  }
  return { action, body };
}

export function readReplacement(
  api: ApiClient["api"],
  serviceId: string,
  query: { candidate_exit_id?: string; operation_id?: string } = {},
  signal?: AbortSignal
): Promise<ReplacementState> {
  const params = new URLSearchParams(query);
  return api(
    builtApiPath<"/api/admin/console/services/{service_id}/exit-replacement">(
      `/admin/console/services/${encodeURIComponent(serviceId)}/exit-replacement${params.size ? `?${params}` : ""}`
    ),
    { signal }
  ).then(unwrap);
}

export async function postReplacement(
  api: ApiClient["api"],
  serviceId: string,
  write: ReplacementWrite
): Promise<void> {
  const base = `/admin/console/services/${encodeURIComponent(serviceId)}`;
  const options = { method: "POST", body: JSON.stringify(write.body) } as const;
  switch (write.action) {
    case "start":
      unwrap(
        await api(
          builtApiPath<"/api/admin/console/services/{service_id}/exit-replacement">(
            `${base}/exit-replacement`
          ),
          options
        )
      );
      break;
    case "confirm":
      unwrap(
        await api(
          builtApiPath<"/api/admin/console/services/{service_id}/exit-replacement/confirm">(
            `${base}/exit-replacement/confirm`
          ),
          options
        )
      );
      break;
    case "retry":
      unwrap(
        await api(
          builtApiPath<"/api/admin/console/services/{service_id}/operations/{operation_id}/retry">(
            `${base}/operations/${write.operationId}/retry`
          ),
          options
        )
      );
      break;
    case "verify": {
      const body: components["schemas"]["ExitVerifyCommand"] = write.body;
      unwrap(
        await api(
          builtApiPath<"/api/admin/dedicated-exits/{exit_id}/verify">(
            `/admin/dedicated-exits/${write.exitId}/verify`
          ),
          { method: "POST", body: JSON.stringify(body) }
        )
      );
      break;
    }
    case "reclaim":
    case "candidate_cleanup": {
      const body: components["schemas"]["ExitReclaimCommand"] = write.body;
      unwrap(
        await api(
          builtApiPath<"/api/admin/dedicated-exits/{exit_id}/reclaim">(
            `/admin/dedicated-exits/${write.exitId}/reclaim`
          ),
          { method: "POST", body: JSON.stringify(body) }
        )
      );
      break;
    }
    default:
      unwrap(
        await api(
          builtApiPath<"/api/admin/console/services/{service_id}/exit-replacement/evidence">(
            `${base}/exit-replacement/evidence`
          ),
          options
        )
      );
  }
}

export function canInspectReplacement(service: UserService): boolean {
  return service.resource_type === "dedicated" || service.replacement_order_id != null;
}
