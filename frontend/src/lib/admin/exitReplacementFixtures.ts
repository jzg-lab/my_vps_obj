import { consoleNodeServiceFixture } from "./consoleNodesFixtures";
import type { DedicatedExit } from "./servicePlans";
import type { ReplacementDraft, ReplacementState, ReplacementFields } from "./exitReplacement";
import type { components } from "../api/openapi.generated";

export function replacementFixture() {
  const stamp = "2026-10-22T00:00:00Z";
  const detail: components["schemas"]["ConsoleServiceDetailOut"] = {
    ...structuredClone(consoleNodeServiceFixture),
    service: {
      ...consoleNodeServiceFixture.service,
      id: "a".repeat(32),
      user_id: 910002,
      name: "Replacement fixture",
      resource_type: "dedicated",
      exit_ip: "192.0.2.10",
      exit_verified: true,
      revision: 4,
      replacement_order_id: null,
      usage_error: null,
      sync_pending: false,
      status: "active",
      connection_state: "ready",
      desired_status: "active",
      usage_total_bytes: 73,
      used_bytes: 73,
      last_usage_sync_at: stamp,
      cycle_pending: false,
    },
    terms: {
      ...consoleNodeServiceFixture.terms,
      resource_type: "dedicated",
      resource_pool: "dedicated-fixture",
      squad_uuids: ["10000000-0000-4000-8000-000000000001"],
    },
  };
  const affected: components["schemas"]["ConsoleServiceDetailOut"] = {
    ...structuredClone(consoleNodeServiceFixture),
    terms: {
      ...consoleNodeServiceFixture.terms,
      squad_uuids: ["10000000-0000-4000-8000-000000000005"],
    },
    service: {
      ...consoleNodeServiceFixture.service,
      id: "8".repeat(32),
      user_id: 910003,
      name: "Neighboring service fixture",
    },
    customer: {
      user_id: 910003,
      minishop_id: null,
      username: null,
      email: null,
      first_name: null,
      last_name: null,
      is_banned: false,
    },
  };
  const old: DedicatedExit = {
    id: "b".repeat(32),
    revision: 2,
    label: "Original fixture exit",
    ip_address: "192.0.2.10",
    resource_pool: "dedicated-fixture",
    squad_uuid: "10000000-0000-4000-8000-000000000001",
    service_id: detail.service.id,
    hold_order_id: null,
    hold_service_id: null,
    enabled: true,
    verified_at: stamp,
  };
  const candidate: DedicatedExit = {
    ...old,
    id: "c".repeat(32),
    label: "Candidate fixture exit",
    ip_address: "192.0.2.20",
    service_id: null,
    squad_uuid: "10000000-0000-4000-8000-000000000002",
    verified_at: null,
  };
  const held: DedicatedExit = {
    ...candidate,
    id: "d".repeat(32),
    label: "Held fixture exit",
    ip_address: "192.0.2.30",
    hold_order_id: "e".repeat(32),
    hold_service_id: "f".repeat(32),
  };
  const draft: ReplacementDraft = {
    old_exit: { ...old, scope_fingerprint: old.id.repeat(2) },
    candidate_exit: { ...candidate, scope_fingerprint: candidate.id.repeat(2) },
    allowed_to_start: true,
    resource_fingerprint: "1".repeat(64),
    coverage: "complete",
    block_reasons: [],
    observed_at: stamp,
    sources: (
      ["metadata", "nodes", "hosts", "groups", "profiles", "services", "authorizations"] as const
    ).map((source) => ({ source, availability: "available", observed_at: stamp })),
    impacts: [
      {
        service_id: affected.service.id,
        customer_id: affected.service.user_id,
        service_name: affected.service.name,
        group_ids: affected.terms.squad_uuids ?? [],
        kind: "possible_reload",
      },
      {
        service_id: "f".repeat(32),
        customer_id: null,
        service_name: null,
        group_ids: ["10000000-0000-4000-8000-000000000003"],
        kind: "possible_reload",
      },
      {
        service_id: null,
        customer_id: null,
        service_name: null,
        group_ids: ["10000000-0000-4000-8000-000000000004"],
        kind: "possible_reload",
      },
    ],
  };
  const progress: components["schemas"]["ReplacementProgress"] = {
    version: 2,
    stage: "awaiting_confirmation",
    pending_action: null,
    stop_audit_id: "5".repeat(32),
    verification_audit_id: null,
    confirmation_audit_id: null,
    binding_audit_id: null,
    restore_result: "not_requested",
    restore_block_reasons: [],
  };
  const state: ReplacementState = {
    service_id: detail.service.id,
    service_revision: detail.service.revision,
    observed_at: stamp,
    draft: null,
    replacement: {
      ...draft,
      gate_active: true,
      requested_resource_fingerprint: draft.resource_fingerprint!,
      current_exit_id: old.id,
      switch_result: "pending",
      restore_requested: false,
      old_resource_state: "current",
      candidate_exit: { ...draft.candidate_exit, revision: 3, hold_order_id: "2".repeat(32) },
      old_stop: {
        audit_id: "5".repeat(32),
        observed_at: stamp,
        provenance: "administrator",
        valid: true,
      },
      candidate_verification: null,
      operation: {
        id: "3".repeat(32),
        service_id: detail.service.id,
        order_id: "2".repeat(32),
        kind: "replace_exit",
        phase: "exit_replace",
        source: "administrator",
        actor_id: 42,
        status: "pending",
        target_revision: detail.service.revision,
        attempt_count: 1,
        created_at: stamp,
        attempted_at: stamp,
        first_failed_at: null,
        completed_at: null,
        error_code: null,
        retryable: true,
        retry_block_reason: null,
        replacement_progress: progress,
      },
      progress,
      accounting: {
        usage_total_bytes: 73,
        usage_raw_bytes: 23,
        usage_lifetime_offset: 50,
        observed_at: stamp,
        error_code: null,
        cycle_pending: false,
      },
      allowed_actions: ["retry", "stop_evidence", "verify"],
    },
  };
  const fields: ReplacementFields = {
    checkedAt: "2026-10-23T01:00:00Z",
    digest: "6".repeat(64),
    observedIp: candidate.ip_address,
    usageAt: "2026-10-23T01:01:00Z",
    total: "73",
    raw: "23",
    offset: "50",
    usageDigest: "7".repeat(64),
    result: "",
    authorizationRemoved: true,
    connectionsStopped: true,
    oldConfigRejected: true,
    fixed: true,
    exclusive: true,
    confirmed: true,
  };
  return { detail, affected, old, candidate, held, draft, state, fields };
}
