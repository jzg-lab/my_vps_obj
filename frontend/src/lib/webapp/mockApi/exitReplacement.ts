import type { components } from "$lib/api/openapi.generated";
import type { DedicatedExit, UserService } from "$lib/admin/servicePlans";
import type { ServiceOperation } from "$lib/admin/consoleServiceOperations";
import type {
  Replacement,
  ReplacementDraft,
  ReplacementExit,
  ReplacementState,
  ReplacementWrite,
} from "$lib/admin/exitReplacement";
import { validReplacementWrite } from "../../admin/exitReplacementPending";
import { jsonBody } from "../demoMockRuntime";

type Audit = components["schemas"]["ExitAuditOut"];
export type ReplacementDemoState = {
  services: UserService[];
  archived: UserService[];
  exits: DedicatedExit[];
  audits: Audit[];
  topology?: Pick<
    ReplacementDraft,
    "coverage" | "sources" | "block_reasons" | "impacts" | "resource_fingerprint" | "observed_at"
  >;
};
type Response =
  | { ok: false; error: string }
  | ({ ok: true } & (
      | ReplacementState
      | components["schemas"]["ConsoleExitReplacementAcceptedOut"]
      | components["schemas"]["ConsoleServiceRetryOut"]
      | { exit: DedicatedExit; audit: Audit; duplicate: boolean }
    ));
const id = () => crypto.randomUUID().replaceAll("-", "");
const reject = (error: string): Response => ({ ok: false, error });

// This demo accepts declarations only. Runner observations must be supplied by a test fixture.
export function createExitReplacementDemo() {
  const replacements = new Map<string, Replacement>();
  const operations: ServiceOperation[] = [];
  const receipts = new Map<string, { request: string; response: Response }>();
  function topology(state: ReplacementDemoState) {
    if (state.topology) {
      const { coverage, sources, block_reasons, impacts, resource_fingerprint, observed_at } =
        state.topology;
      return { coverage, sources, block_reasons, impacts, resource_fingerprint, observed_at };
    }
    return {
      coverage: "partial" as const,
      sources: [],
      block_reasons: ["exit_replacement_sources_incomplete"],
      impacts: [],
      resource_fingerprint: null,
      observed_at: new Date().toISOString(),
    };
  }
  function exit(resource: DedicatedExit, state: ReplacementDemoState): ReplacementExit {
    const { hold_service_id: _owner, ...row } = resource;
    return {
      ...row,
      scope_fingerprint: topology(state).coverage === "complete" ? resource.id.repeat(2) : null,
    };
  }
  function project(
    row: Replacement,
    service: UserService,
    state: ReplacementDemoState
  ): Replacement {
    const old = state.exits.find((item) => item.id === row.old_exit.id);
    const candidate = state.exits.find((item) => item.id === row.candidate_exit.id);
    if (old) row.old_exit = exit(old, state);
    if (candidate) row.candidate_exit = exit(candidate, state);
    Object.assign(row, topology(state));
    row.gate_active = service.replacement_order_id === row.operation.order_id;
    row.allowed_actions = [];
    if (row.progress.pending_action) row.allowed_actions.push("resolve_write");
    else if (row.gate_active) {
      row.allowed_actions.push("retry");
      if (["stopping_old", "awaiting_confirmation", "switching"].includes(row.progress.stage))
        row.allowed_actions.push("stop_evidence");
      if (row.progress.stage === "awaiting_confirmation") {
        row.allowed_actions.push("verify");
        if (row.candidate_verification) row.allowed_actions.push("confirm");
      }
      if (row.progress.stage === "closing") row.allowed_actions.push("close_evidence");
      if (
        !row.progress.binding_audit_id &&
        ["paused", "cancelled"].includes(service.desired_status)
      )
        row.allowed_actions.push("candidate_cleanup");
    }
    if (
      !row.gate_active &&
      (old?.hold_order_id === row.operation.order_id ||
        candidate?.hold_order_id === row.operation.order_id)
    )
      row.allowed_actions.push("reclaim");
    row.operation.retryable = row.allowed_actions.includes("retry");
    row.operation.retry_block_reason = row.progress.pending_action
      ? "exit_replacement_write_unknown"
      : row.gate_active
        ? null
        : "operation_not_retryable";
    row.operation.replacement_progress = row.progress;
    row.current_exit_id = state.exits.find((item) => item.service_id === service.id)?.id ?? null;
    row.old_resource_state =
      old?.hold_order_id === row.operation.order_id
        ? "held"
        : old?.service_id === service.id
          ? "current"
          : "released";
    row.switch_result = row.progress.binding_audit_id
      ? "confirmed"
      : row.progress.pending_action
        ? "unknown"
        : ["closing", "closed"].includes(row.progress.stage)
          ? "interrupted"
          : row.gate_active
            ? "pending"
            : "not_started";
    for (const evidence of [row.old_stop, row.candidate_verification])
      if (evidence)
        evidence.valid = row.resource_fingerprint === row.requested_resource_fingerprint;
    return row;
  }
  function respond(
    path: string,
    options: RequestInit,
    state: ReplacementDemoState
  ): Response | undefined {
    const url = new URL(path, "https://demo.invalid");
    const method = options.method ?? "GET";
    const route = url.pathname.match(
      /^\/admin\/console\/services\/([^/]+)\/exit-replacement(?:\/(confirm|evidence))?$/
    );
    const scoped = url.pathname.match(/^\/admin\/dedicated-exits\/([^/]+)\/(verify|reclaim)$/);
    const retry = url.pathname.match(
      /^\/admin\/console\/services\/([^/]+)\/operations\/([^/]+)\/retry$/
    );
    const body = jsonBody(options);
    if (
      !route &&
      !(scoped && "replacement_operation_id" in body) &&
      !(retry && replacements.has(retry[2]))
    )
      return undefined;
    if ((route?.[2] || scoped || retry) && method !== "POST")
      return reject("invalid_replacement_request");
    const serviceId = route?.[1] ?? retry?.[1] ?? body.service_id;
    const service = [...state.services, ...state.archived].find((item) => item.id === serviceId);
    if (!service) return reject("service_not_found");
    let row = [...replacements.values()]
      .filter((item) => item.operation.service_id === service.id)
      .at(-1);
    const operationId =
      method === "GET"
        ? url.searchParams.get("operation_id")
        : (body.operation_id ?? body.replacement_operation_id ?? retry?.[2]);
    if (operationId) {
      row = replacements.get(String(operationId));
      if (!row || row.operation.service_id !== service.id) return reject("operation_not_found");
    }
    if (row) project(row, service, state);
    if (method === "GET") {
      const candidateId = url.searchParams.get("candidate_exit_id");
      if (operationId && candidateId) return reject("invalid_replacement_query");
      const result: ReplacementState = {
        service_id: service.id,
        service_revision: service.revision,
        observed_at: new Date().toISOString(),
        draft: null,
        replacement: row ?? null,
      };
      if (candidateId) {
        const old = state.exits.find((item) => item.service_id === service.id);
        const candidate = state.exits.find((item) => item.id === candidateId);
        if (!old || !candidate || old.id === candidate.id) return reject("exit_unavailable");
        result.replacement = null;
        result.draft = {
          ...topology(state),
          old_exit: exit(old, state),
          candidate_exit: exit(candidate, state),
          allowed_to_start:
            service.user_id !== null &&
            service.desired_status !== "cancelled" &&
            service.connection_state !== "revoked" &&
            !service.replacement_order_id &&
            !candidate.service_id &&
            !candidate.hold_order_id &&
            candidate.enabled &&
            candidate.resource_pool === old.resource_pool &&
            topology(state).coverage === "complete" &&
            topology(state).block_reasons.length === 0,
        };
      }
      return structuredClone({ ok: true, ...result });
    }
    if (method !== "POST" || url.search || service.user_id === null)
      return reject("service_not_editable");
    if ("user_id" in body && service.user_id !== body.user_id)
      return reject("idempotency_owner_changed");
    const write: unknown = scoped
      ? {
          action:
            scoped[2] === "verify" ? "verify" : row?.gate_active ? "candidate_cleanup" : "reclaim",
          exitId: scoped[1],
          body,
        }
      : retry
        ? { action: "retry", operationId: retry[2], body }
        : {
            action: !route?.[2]
              ? "start"
              : route[2] === "confirm"
                ? "confirm"
                : body.purpose === "stop"
                  ? "stop_evidence"
                  : body.purpose === "close"
                    ? "close_evidence"
                    : "resolve_write",
            body,
          };
    if (!validReplacementWrite(write)) return reject("invalid_replacement_request");
    const receiptKey = `${service.id}:${write.body.idempotency_key}`;
    const request = JSON.stringify([url.pathname, write.body]);
    const previous = receipts.get(receiptKey);
    if (previous)
      return previous.request === request
        ? structuredClone({ ...previous.response, duplicate: true })
        : reject("idempotency_conflict");
    const response = apply(write, row, service, state);
    if (response.ok) receipts.set(receiptKey, { request, response: structuredClone(response) });
    return structuredClone(response);
  }
  function audit(
    state: ReplacementDemoState,
    service: UserService,
    resource: DedicatedExit,
    action: string,
    write: ReplacementWrite
  ): Audit {
    const entry: Audit = {
      id: id(),
      exit_id: resource.id,
      service_id: service.id,
      actor_id: 42,
      action,
      evidence: { ...write.body },
      created_at: new Date().toISOString(),
    };
    state.audits.unshift(entry);
    return entry;
  }
  function apply(
    write: ReplacementWrite,
    row: Replacement | undefined,
    service: UserService,
    state: ReplacementDemoState
  ): Response {
    const body = write.body;
    if ("user_id" in body && body.user_id !== service.user_id)
      return reject("idempotency_owner_changed");
    if (
      (write.action === "start" || write.action === "confirm" || write.action === "retry") &&
      write.body.expected_revision !== service.revision
    )
      return reject("service_revision_changed");
    if (write.action === "start") {
      const body = write.body;
      const old = state.exits.find(
        (item) => item.id === body.old_exit_id && item.service_id === service.id
      );
      const candidate = state.exits.find((item) => item.id === body.new_exit_id);
      if (
        service.replacement_order_id ||
        service.desired_status === "cancelled" ||
        !old ||
        !candidate ||
        old === candidate ||
        candidate.service_id ||
        candidate.hold_order_id ||
        !candidate.enabled ||
        candidate.resource_pool !== old.resource_pool
      )
        return reject("exit_unavailable");
      if (
        old.revision !== body.expected_old_exit_revision ||
        candidate.revision !== body.expected_new_exit_revision
      )
        return reject("exit_revision_changed");
      if (
        topology(state).coverage !== "complete" ||
        body.expected_resource_fingerprint !== topology(state).resource_fingerprint
      )
        return reject("exit_replacement_scope_changed");
      const blocker = topology(state).block_reasons[0];
      if (blocker) return reject(blocker);
      const progress: Replacement["progress"] = {
        version: 1,
        stage: "stopping_old",
        pending_action: null,
        stop_audit_id: null,
        verification_audit_id: null,
        confirmation_audit_id: null,
        binding_audit_id: null,
        restore_result: "not_requested",
        restore_block_reasons: [],
      };
      const operation: ServiceOperation = {
        id: id(),
        service_id: service.id,
        order_id: id(),
        kind: "replace_exit",
        phase: "exit_replace",
        source: "administrator",
        actor_id: 42,
        target_revision: service.revision,
        status: "pending",
        attempt_count: 0,
        created_at: new Date().toISOString(),
        attempted_at: null,
        first_failed_at: null,
        completed_at: null,
        error_code: null,
        retryable: true,
        retry_block_reason: null,
        replacement_progress: progress,
      };
      candidate.hold_order_id = operation.order_id;
      candidate.hold_service_id = service.id;
      candidate.revision++;
      service.replacement_order_id = operation.order_id;
      service.sync_pending = true;
      row = {
        ...topology(state),
        operation,
        progress,
        gate_active: true,
        requested_resource_fingerprint: body.expected_resource_fingerprint,
        old_exit: exit(old, state),
        candidate_exit: exit(candidate, state),
        current_exit_id: old.id,
        switch_result: "pending",
        restore_requested: false,
        old_resource_state: "current",
        old_stop: null,
        candidate_verification: null,
        accounting: {
          usage_total_bytes: service.usage_total_bytes,
          usage_raw_bytes: null,
          usage_lifetime_offset: 0,
          observed_at: service.last_usage_sync_at,
          error_code: service.usage_error,
          cycle_pending: service.cycle_pending,
        },
        allowed_actions: [],
      };
      replacements.set(operation.id, row);
      operations.push(operation);
      audit(state, service, candidate, "replace_reserve", write);
    } else {
      if (!row || !row.allowed_actions.includes(write.action))
        return reject(
          row?.progress.pending_action
            ? "exit_replacement_write_unknown"
            : "operation_not_retryable"
        );
      if (write.action === "retry")
        return {
          ok: true,
          accepted: true,
          duplicate: false,
          operation: row.operation,
          retry_order_id: id(),
        };
      if (
        "expected_operation_version" in body &&
        body.expected_operation_version !== row.progress.version
      )
        return reject("exit_replacement_version_changed");
      const { old_exit: oldExit, candidate_exit: candidateExit } = row;
      const old = state.exits.find((item) => item.id === oldExit.id);
      const candidate = state.exits.find((item) => item.id === candidateExit.id);
      if (!old || !candidate) return reject("exit_unavailable");
      if ("checked_at" in body && Date.parse(body.checked_at) > Date.now())
        return reject("exit_replacement_evidence_invalid");
      if (
        write.action === "verify" ||
        write.action === "reclaim" ||
        write.action === "candidate_cleanup"
      ) {
        const resource = state.exits.find((item) => item.id === write.exitId);
        if (
          !resource ||
          (resource !== old && resource !== candidate) ||
          resource.revision !== write.body.expected_revision
        )
          return reject("exit_revision_changed");
        if (write.body.scope_fingerprint !== exit(resource, state).scope_fingerprint)
          return reject("exit_replacement_scope_changed");
        let action: string;
        if (write.action === "verify") {
          if (resource !== candidate || write.body.observed_ip !== candidate.ip_address)
            return reject("exit_replacement_evidence_invalid");
          action = "replace_verify";
        } else if (write.action === "candidate_cleanup") {
          if (
            resource !== candidate ||
            write.body.reclaim_purpose !== "candidate_cleanup" ||
            row.progress.binding_audit_id ||
            !["paused", "cancelled"].includes(service.desired_status)
          )
            return reject("exit_replacement_pause_required");
          row.progress.stage = "closing";
          action = "replace_cleanup";
        } else {
          if (
            resource.hold_order_id !== row.operation.order_id ||
            resource.service_id ||
            (write.body.reclaim_purpose === "retained_old") !== (resource === old)
          )
            return reject("exit_replacement_hold_changed");
          resource.hold_order_id = null;
          resource.hold_service_id = null;
          resource.revision++;
          action = "replace_reclaim";
        }
        const entry = audit(state, service, resource, action, write);
        if (write.action === "verify") {
          candidate.verified_at = write.body.checked_at;
          candidate.revision++;
          row.candidate_verification = {
            audit_id: entry.id,
            observed_at: write.body.checked_at,
            provenance: "administrator",
            valid: true,
          };
          row.progress.verification_audit_id = entry.id;
        }
        row.progress.version++;
        project(row, service, state);
        return { ok: true, exit: resource, audit: entry, duplicate: false };
      }
      if (write.action === "confirm") {
        if (
          write.body.expected_resource_fingerprint !== row.resource_fingerprint ||
          row.resource_fingerprint !== row.requested_resource_fingerprint ||
          write.body.expected_old_exit_revision !== old.revision ||
          write.body.expected_new_exit_revision !== candidate.revision ||
          write.body.old_stop_audit_id !== row.old_stop?.audit_id ||
          write.body.candidate_verify_audit_id !== row.candidate_verification?.audit_id
        )
          return reject("exit_replacement_scope_changed");
        row.progress.confirmation_audit_id = audit(
          state,
          service,
          candidate,
          "replace_confirm",
          write
        ).id;
        row.restore_requested = true;
        row.progress.stage = "switching";
        row.progress.restore_result = "pending";
      } else {
        if (!("purpose" in write.body)) return reject("invalid_replacement_request");
        const evidence = write.body;
        if (evidence.resource_fingerprint !== row.resource_fingerprint)
          return reject("exit_replacement_scope_changed");
        if (write.action === "resolve_write") {
          if (
            evidence.action !== row.progress.pending_action ||
            evidence.attempt !== row.operation.attempt_count
          )
            return reject("exit_replacement_version_changed");
          row.progress.pending_action = null;
          row.operation.status = evidence.result === "not_applied" ? "failed" : "pending";
          audit(state, service, old, "replace_write_result", write);
        } else {
          if (
            !evidence.usage_observed_at ||
            evidence.usage_observed_at < evidence.checked_at ||
            Date.parse(evidence.usage_observed_at) > Date.now()
          )
            return reject("exit_replacement_evidence_invalid");
          const entry = audit(
            state,
            service,
            old,
            write.action === "stop_evidence" ? "replace_stop" : "replace_close_stop",
            write
          );
          row.accounting = {
            usage_total_bytes: evidence.usage_total_bytes,
            usage_raw_bytes: evidence.usage_raw_bytes,
            usage_lifetime_offset: evidence.usage_lifetime_offset ?? 0,
            observed_at: evidence.usage_observed_at,
            error_code: null,
            cycle_pending: false,
          };
          if (write.action === "stop_evidence") {
            row.progress.stop_audit_id = entry.id;
            row.old_stop = {
              audit_id: entry.id,
              observed_at: evidence.checked_at,
              provenance: "administrator",
              valid: true,
            };
            row.progress.stage = "awaiting_confirmation";
          } else {
            row.progress.stage = "closed";
            service.replacement_order_id = null;
          }
        }
      }
      row.progress.version++;
    }
    return {
      ok: true,
      accepted: true,
      duplicate: false,
      replacement: project(row, service, state),
    };
  }
  return { respond, replacements, operations };
}
