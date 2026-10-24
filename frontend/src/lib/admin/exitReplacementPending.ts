import {
  replacementAvailable,
  replacementSnapshot,
  type ReplacementState,
  type ReplacementWrite,
} from "./exitReplacement";

export type PendingReplacement = {
  serviceId: string;
  userId: number;
  snapshot: string;
  write: ReplacementWrite;
};
const key = (serviceId: string) => `my-vps-exit-replacement:${serviceId}`;

export function replacementRejected(failure: unknown): boolean {
  if (!failure || typeof failure !== "object" || !("error" in failure)) return false;
  // Transport failures can follow a committed write. Only explicit command rejections unlock editing.
  if ("status" in failure && ![400, 403, 404, 409, 422].includes(Number(failure.status)))
    return false;
  return [
    "invalid_exit_evidence",
    "invalid_payload",
    "invalid_service_retry_query",
    "invalid_replacement_request",
    "invalid_idempotency_key",
    "exit_replacement_evidence_invalid",
    "exit_replacement_scope_changed",
    "exit_replacement_version_changed",
    "exit_replacement_stage_changed",
    "exit_replacement_hold_changed",
    "exit_revision_changed",
    "service_revision_changed",
    "idempotency_conflict",
    "idempotency_owner_changed",
    "operation_not_retryable",
    "operation_not_found",
    "user_not_found",
    "service_not_found",
    "exit_not_found",
    "exit_unavailable",
    "service_not_editable",
    "exit_replacement_not_available",
    "exit_replacement_not_switchable",
    "exit_replacement_in_progress",
    "exit_replacement_pause_required",
    "exit_replacement_stop_unconfirmed",
    "exit_replacement_usage_unconfirmed",
    "exit_replacement_confirmation_required",
    "exit_replacement_sources_incomplete",
    "exit_replacement_authorizations_unavailable",
    "exit_replacement_panel_unsupported",
    "panel_identity_missing",
    "panel_identity_conflict",
    "usage_reconciliation_required",
    "account_banned",
    "service_expired",
    "service_exhausted",
  ].includes(String(failure.error));
}
const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);
const text = (value: unknown): value is string => typeof value === "string";
const integer = (value: unknown) => typeof value === "number" && Number.isSafeInteger(value);
const revision = (value: unknown) => integer(value) && Number(value) > 0;
const count = (value: unknown) => integer(value) && Number(value) >= 0;
const id = (value: unknown) => text(value) && /^[0-9a-f]{32}$/.test(value);
const digest = (value: unknown) => text(value) && /^[0-9a-f]{64}$/.test(value);
const time = (value: unknown) =>
  text(value) && /(?:Z|[+-]\d\d:\d\d)$/.test(value) && Number.isFinite(Date.parse(value));
const yes = (value: unknown) => value === true;
const nil = (value: unknown) => value === null;
type Rule = (value: unknown) => boolean;
function shape(value: unknown, rules: Record<string, Rule>): boolean {
  return (
    record(value) &&
    Object.keys(value).length === Object.keys(rules).length &&
    Object.entries(rules).every(
      ([field, rule]) => Object.hasOwn(value, field) && rule(value[field])
    )
  );
}

// Session storage is untrusted. Only the exact administrator command shapes can be replayed.
export function validReplacementWrite(value: unknown): value is ReplacementWrite {
  if (!record(value) || !text(value.action) || !record(value.body)) return false;
  const common = {
    idempotency_key: (v: unknown) => text(v) && v.trim().length > 0 && v.length <= 128,
  };
  const version = { expected_operation_version: revision };
  const evidence = { ...common, ...version, checked_at: time, evidence_digest: digest };
  const scope = {
    ...evidence,
    replacement_operation_id: id,
    service_id: id,
    expected_revision: revision,
    scope_fingerprint: digest,
  };
  switch (value.action) {
    case "start":
      return shape(value, {
        action: text,
        body: (body) =>
          shape(body, {
            ...common,
            user_id: integer,
            expected_revision: revision,
            old_exit_id: id,
            new_exit_id: id,
            expected_old_exit_revision: revision,
            expected_new_exit_revision: revision,
            expected_resource_fingerprint: digest,
            reason: (v) => text(v) && v.trim().length >= 3 && v.trim().length <= 1000,
          }),
      });
    case "confirm":
      return shape(value, {
        action: text,
        body: (body) =>
          shape(body, {
            ...common,
            ...version,
            user_id: integer,
            operation_id: id,
            expected_revision: revision,
            expected_old_exit_revision: revision,
            expected_new_exit_revision: revision,
            expected_resource_fingerprint: digest,
            old_stop_audit_id: id,
            candidate_verify_audit_id: id,
            confirm_replace_and_request_restore: yes,
          }),
      });
    case "retry":
      return shape(value, {
        action: text,
        operationId: id,
        body: (body) =>
          shape(body, {
            ...common,
            user_id: integer,
            expected_revision: revision,
          }),
      });
    case "verify":
      return shape(value, {
        action: text,
        exitId: id,
        body: (body) =>
          shape(body, {
            ...scope,
            observed_ip: (v) => text(v) && v.trim().length > 0 && v.length <= 45,
            fixed: yes,
            exclusive: yes,
          }),
      });
    case "reclaim":
    case "candidate_cleanup":
      return shape(value, {
        action: text,
        exitId: id,
        body: (body) =>
          shape(body, {
            ...scope,
            reclaim_purpose: (v) => v === "retained_old" || v === "candidate_cleanup",
            connections_stopped: yes,
            old_config_rejected: yes,
          }),
      });
    case "resolve_write":
    case "stop_evidence":
    case "close_evidence": {
      const resolve = value.action === "resolve_write";
      const purpose = resolve
        ? "resolve_write"
        : value.action === "stop_evidence"
          ? "stop"
          : "close";
      return shape(value, {
        action: text,
        body: (body) =>
          shape(body, {
            ...evidence,
            operation_id: id,
            resource_fingerprint: digest,
            purpose: (v) => v === purpose,
            authorization_removed: resolve ? nil : yes,
            connections_stopped: resolve ? nil : yes,
            old_config_rejected: resolve ? nil : yes,
            usage_observed_at: resolve ? nil : time,
            usage_total_bytes: resolve ? nil : count,
            usage_raw_bytes: resolve ? nil : count,
            usage_lifetime_offset: resolve ? nil : count,
            usage_evidence_digest: resolve ? nil : digest,
            action: resolve
              ? (v) =>
                  ["stop_old", "set_target_group", "restore", "close_access"].includes(String(v))
              : nil,
            attempt: resolve ? revision : nil,
            result: resolve ? (v) => v === "applied" || v === "not_applied" : nil,
          }),
      });
    }
    default:
      return false;
  }
}

export function readPendingReplacement(
  storage: Storage,
  serviceId: string,
  userId: number
): PendingReplacement | null {
  const raw = storage.getItem(key(serviceId));
  if (raw === null) return null;
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw { error: "services_storage_failed" };
  }
  if (
    !record(value) ||
    value.serviceId !== serviceId ||
    value.userId !== userId ||
    !text(value.snapshot) ||
    !validReplacementWrite(value.write)
  )
    throw { error: "services_storage_failed" };
  return { serviceId, userId, snapshot: value.snapshot, write: value.write };
}
export function savePendingReplacement(storage: Storage, pending: PendingReplacement): void {
  if (!validReplacementWrite(pending.write)) throw { error: "replacement_invalid_evidence" };
  storage.setItem(key(pending.serviceId), JSON.stringify(pending));
}
export function clearPendingReplacement(storage: Storage, serviceId: string): void {
  storage.removeItem(key(serviceId));
}
export function canReplayReplacement(
  pending: PendingReplacement,
  current: ReplacementState
): boolean {
  if (pending.serviceId !== current.service_id || pending.snapshot !== replacementSnapshot(current))
    return false;
  return pending.write.action === "start"
    ? current.draft?.allowed_to_start === true
    : replacementAvailable(current, pending.write.action);
}
