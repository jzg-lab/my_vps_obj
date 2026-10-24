import type { components } from "$lib/api/openapi.generated";
import type { CatalogResource } from "$lib/admin/consoleResources";
import { consoleNodeFixture } from "$lib/admin/consoleNodesFixtures";
import {
  resourceEvidenceBody,
  resourceRecovery,
  type ResourceOperation,
  type ResourceStart,
} from "$lib/admin/resourceOperations";
import { validResourceChange } from "$lib/admin/resourceIntent";
import {
  canonicalResource,
  type ResourceChange,
  type ResourcePreview,
} from "../../../admin/sections/nodes/resourcePreview";
import {
  consoleResourceCatalogFixture,
  consoleResourceDraftPreviewFixture,
  consoleResourcePreviewFixture,
} from "./consoleResourcePreview";
import { initialDraft } from "../../../admin/sections/nodes/resourceDraftPreview";

const operations = new Map<string, ResourceOperation>();
const intents = new Map<string, { body: ResourceStart; id: string }>();
const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value));
const now = () => new Date().toISOString();
const error = (value: string, status = 409) => ({ ok: false as const, error: value, status });
const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);

export function resourceOperationPreviewFixture(change: ResourceChange): ResourcePreview {
  const catalog = consoleResourceCatalogFixture();
  let preview = consoleResourcePreviewFixture({
    operation: "node_disable",
    target_id: consoleNodeFixture.id,
    force_restart: false,
  });
  if (
    change.operation === "node_enable" ||
    change.operation === "node_disable" ||
    change.operation === "node_restart"
  )
    preview = consoleResourcePreviewFixture(change);
  else if (change.operation === "group_inbounds")
    preview = consoleResourceDraftPreviewFixture(change);
  else if (change.operation === "host_update") {
    const initial = initialDraft(catalog, { kind: "host", id: change.target_id });
    if (initial?.operation === "host_update") {
      const patch = {
        ...initial.patch,
        ...Object.fromEntries(Object.entries(change.patch).filter(([, value]) => value != null)),
      };
      preview = consoleResourceDraftPreviewFixture({ ...initial, patch });
      if (preview.proposed) {
        preview.proposed.address = change.patch.address ?? preview.proposed.address;
        preview.proposed.port = change.patch.port ?? preview.proposed.port;
      }
      preview.change = {
        ...change,
        patch: {
          address: null,
          port: null,
          group_ids: null,
          group_mode: null,
          inbound_id: null,
          profile_id: null,
          node_ids: null,
          is_disabled: null,
          is_hidden: null,
          ...change.patch,
        },
      };
    } else
      preview = {
        ...preview,
        change: {
          ...change,
          patch: {
            address: null,
            port: null,
            group_ids: null,
            group_mode: null,
            inbound_id: null,
            profile_id: null,
            node_ids: null,
            is_disabled: null,
            is_hidden: null,
            ...change.patch,
          },
        },
        current: null,
        proposed: null,
        blockers: ["target_not_found"],
        coverage: "partial",
        fingerprint: null,
      };
  } else if (
    change.operation === "node_create" ||
    change.operation === "group_create" ||
    change.operation === "host_create"
  ) {
    const proposed: components["schemas"]["ResourceValuesOut"] = {
      id: null,
      name: change.name,
      kind:
        change.operation === "node_create"
          ? "node"
          : change.operation === "group_create"
            ? "group"
            : "host",
      address: "address" in change ? change.address : null,
      port: "port" in change ? change.port : null,
      profile_id: "profile_id" in change ? change.profile_id : null,
      inbound_ids: change.operation === "host_create" ? [change.inbound_id] : change.inbound_ids,
      node_ids: change.operation === "host_create" ? change.node_ids : [],
      group_ids: change.operation === "host_create" ? change.group_ids : [],
      group_mode: change.operation === "host_create" ? change.group_mode : null,
      is_disabled:
        change.operation === "host_create"
          ? change.is_disabled
          : change.operation === "node_create"
            ? false
            : null,
      is_hidden: change.operation === "host_create" ? change.is_hidden : null,
      force_restart: null,
    };
    const inbounds = new Set(proposed.inbound_ids);
    const selectedGroups = catalog.groups
      .filter((group): group is CatalogResource => typeof group.id === "string")
      .filter(
        (group) =>
          group.inbound_ids.some((id) => inbounds.has(id)) &&
          (change.operation !== "host_create" ||
            (change.group_mode === "ALLOW_ONLY"
              ? change.group_ids.includes(group.id)
              : !change.group_ids.includes(group.id)))
      );
    const groupIds = selectedGroups.map((group) => group.id);
    const services = preview.direct.services.filter((service) =>
      service.group_ids.some((id) => groupIds.includes(id))
    );
    const customers = [...new Set(services.map((service) => service.customer_id))];
    const direct = {
      ...preview.direct,
      group_ids: groupIds,
      services,
      customer_ids: customers,
      service_total: services.length,
      customer_total: customers.length,
      node_ids: catalog.nodes
        .filter((node): node is CatalogResource => typeof node.id === "string")
        .filter(
          (node) =>
            node.inbound_ids.some((id) => inbounds.has(id)) &&
            (change.operation !== "host_create" ||
              !change.node_ids.length ||
              change.node_ids.includes(node.id))
        )
        .map((node) => node.id),
      profile_ids: catalog.profiles
        .filter((profile) => profile.inbounds.some((inbound) => inbounds.has(inbound.id)))
        .map((profile) => profile.id),
    };
    const validInbounds = [...inbounds].every((id) =>
      catalog.profiles.some(
        (profile) =>
          (!proposed.profile_id || proposed.profile_id === profile.id) &&
          profile.inbounds.some((inbound) => inbound.id === id)
      )
    );
    preview = {
      ...preview,
      change: copy(change),
      current: null,
      proposed,
      direct,
      affected_service_ids: services.map((service) => service.service_id),
      affected_customer_ids: customers,
      coverage: validInbounds ? "complete" : "partial",
      blockers: validInbounds ? [] : ["unknown_proposed_inbound"],
      recovery: "creation_requires_explicit_reconciliation_no_automatic_delete",
    };
  }
  // Deterministic demo fingerprint, never a claim of backend hashing or observed state.
  let hash = 2166136261;
  for (const character of canonicalResource(change))
    hash = Math.imul(hash ^ character.charCodeAt(0), 16777619);
  return {
    ...preview,
    execution_available: preview.coverage === "complete",
    fingerprint:
      preview.coverage === "complete" ? (hash >>> 0).toString(16).padStart(8, "0").repeat(8) : null,
  };
}
export function resourceOperationFixture(
  change: ResourceChange = {
    operation: "node_disable",
    target_id: consoleNodeFixture.id,
    force_restart: false,
  }
): ResourceOperation {
  const preview = resourceOperationPreviewFixture(change);
  return {
    id: "c".repeat(32),
    actor_id: 910001,
    status: "pending",
    version: 1,
    change: preview.change,
    target_id: "target_id" in change ? change.target_id : null,
    recovery_of: null,
    preview,
    attempts: [],
    observation: null,
    evidence: [],
    gate_active: true,
    error_code: null,
    created_at: now(),
    completed_at: null,
    can_retry: false,
    requires_manual_reconciliation: false,
  };
}
export function resetResourceOperationsDemo() {
  operations.clear();
  intents.clear();
}
export function seedResourceOperationDemo(operation: ResourceOperation) {
  operations.set(operation.id, copy(operation));
}

export function consoleResourceOperationsDemoResponse(path: string, options: RequestInit): unknown {
  const url = new URL(path, "https://demo.invalid");
  const route = url.pathname;
  const method = options.method ?? "GET";
  if (
    !route.startsWith("/admin/console/resources/") &&
    route !== "/admin/console/nodes/onboarding/deployment"
  )
    return undefined;
  const previewRequest = [
    "/admin/console/resources/preview",
    "/admin/console/resources/revalidate",
  ].includes(route);
  const invalidBody = () =>
    error(previewRequest ? "invalid_resource_change" : "invalid_resource_operation_request", 400);
  let body: unknown = {};
  try {
    if (typeof options.body === "string") body = JSON.parse(options.body);
  } catch {
    return invalidBody();
  }
  if (!record(body)) return invalidBody();
  if (route === "/admin/console/resources/catalog" && method === "GET")
    return url.search
      ? error("invalid_resource_catalog_query", 400)
      : { ok: true, ...consoleResourceCatalogFixture(), execution_available: true };
  if (previewRequest && method === "POST") {
    const revalidate = route.endsWith("/revalidate");
    if (
      !validResourceChange(body.change) ||
      Object.keys(body).some(
        (key) => key !== "change" && !(revalidate && key === "expected_fingerprint")
      ) ||
      (revalidate &&
        (typeof body.expected_fingerprint !== "string" ||
          !/^[a-f0-9]{64}$/.test(body.expected_fingerprint)))
    )
      return invalidBody();
    const preview = resourceOperationPreviewFixture(body.change);
    if (route.endsWith("/preview")) return { ok: true, ...preview };
    const reason =
      preview.coverage !== "complete"
        ? "incomplete"
        : body.expected_fingerprint === preview.fingerprint
          ? "unchanged"
          : "changed";
    return { ok: true, valid: reason === "unchanged", reason, preview };
  }
  if (route === "/admin/console/nodes/onboarding/deployment" && method === "POST") {
    const value = body.management_port;
    if (
      Object.keys(body).some((key) => key !== "management_port") ||
      typeof value !== "number" ||
      !Number.isInteger(value) ||
      value < 1 ||
      value > 65535
    )
      return error("invalid_resource_operation_request", 400);
    return {
      ok: true,
      panel_version: "3.4.5",
      recorded_node_version: "3.4.2",
      management_port: value,
      credential_semantics: "new_node_certificate_existing_panel_ca",
      installation_performed: false,
      secret_key: "DEMO-NOT-A-REAL-NODE-CREDENTIAL",
    } satisfies components["schemas"]["ConsoleNodeDeploymentOut"] & { ok: true };
  }
  if (route === "/admin/console/resources/operations") {
    if (method === "GET") {
      const rows = [...operations.values()].reverse();
      const offset = Number(url.searchParams.get("offset") ?? 0);
      const limit = Number(url.searchParams.get("limit") ?? 25);
      if (
        [...url.searchParams.keys()].some((key) => !["offset", "limit"].includes(key)) ||
        !Number.isSafeInteger(offset) ||
        offset < 0 ||
        !Number.isSafeInteger(limit) ||
        limit < 1 ||
        limit > 100
      )
        return error("invalid_resource_operation_request", 400);
      return { ok: true, items: copy(rows.slice(offset, offset + limit)), total: rows.length };
    }
    if (
      method !== "POST" ||
      Object.keys(body).some(
        (key) => !["change", "idempotency_key", "expected_fingerprint", "recovery_of"].includes(key)
      ) ||
      !validResourceChange(body.change) ||
      typeof body.idempotency_key !== "string" ||
      !body.idempotency_key ||
      body.idempotency_key.length > 128 ||
      typeof body.expected_fingerprint !== "string" ||
      !/^[a-f0-9]{64}$/.test(body.expected_fingerprint) ||
      (body.recovery_of != null &&
        (typeof body.recovery_of !== "string" || !/^[a-f0-9]{32}$/.test(body.recovery_of)))
    )
      return error("invalid_resource_operation_request", 400);
    const intent: ResourceStart = {
      change: body.change,
      idempotency_key: body.idempotency_key,
      expected_fingerprint: body.expected_fingerprint,
      recovery_of: typeof body.recovery_of === "string" ? body.recovery_of : null,
    };
    const previous = intents.get(intent.idempotency_key);
    if (previous)
      return canonicalResource(previous.body) === canonicalResource(intent)
        ? { ok: true, duplicate: true, operation: copy(operations.get(previous.id)!) }
        : error("resource_idempotency_conflict");
    if ([...operations.values()].some((row) => row.gate_active))
      return error("resource_operation_in_progress");
    const preview = resourceOperationPreviewFixture(intent.change);
    if (preview.coverage !== "complete" || preview.blockers.length)
      return error("resource_sources_incomplete");
    if (preview.fingerprint !== intent.expected_fingerprint)
      return error("resource_preview_changed");
    if (intent.recovery_of) {
      const original = operations.get(intent.recovery_of);
      if (
        !original ||
        canonicalResource(resourceRecovery(original)) !== canonicalResource(intent.change)
      )
        return error("resource_recovery_invalid");
    }
    const operation = {
      ...resourceOperationFixture(intent.change),
      id: crypto.randomUUID().replaceAll("-", ""),
      recovery_of: intent.recovery_of,
    };
    operations.set(operation.id, operation);
    intents.set(intent.idempotency_key, { body: copy(intent), id: operation.id });
    return { ok: true, duplicate: false, operation: copy(operation) };
  }
  const match =
    /^\/admin\/console\/resources\/operations\/([a-f0-9]{32})(?:\/(retry|reconcile|evidence))?$/.exec(
      route
    );
  if (!match) return undefined;
  const operation = operations.get(match[1]);
  if (!operation) return error("resource_operation_not_found", 404);
  if (!match[2] && method === "GET") return { ok: true, ...copy(operation) };
  if (!match[2] || method !== "POST") return error("method_not_allowed", 405);
  const fields =
    match[2] === "retry"
      ? ["expected_version", "expected_fingerprint"]
      : match[2] === "evidence"
        ? [
            "expected_version",
            "attempt",
            "result",
            "target_id",
            "evidence_digest",
            "checked_at",
            "original_request_terminated",
          ]
        : ["expected_version"];
  if (
    Object.keys(body).some((key) => !fields.includes(key)) ||
    !Number.isSafeInteger(body.expected_version) ||
    Number(body.expected_version) < 1
  )
    return error("invalid_resource_operation_request", 400);
  if (body.expected_version !== operation.version) return error("resource_operation_changed");
  if (match[2] === "retry") {
    if (
      !operation.can_retry ||
      operation.status !== "failed" ||
      operation.error_code !== "resource_write_rejected"
    )
      return error("resource_retry_not_allowed");
    if ([...operations.values()].some((row) => row.gate_active))
      return error("resource_operation_in_progress");
    if (
      body.expected_fingerprint !== operation.preview.fingerprint ||
      resourceOperationPreviewFixture(operation.change).fingerprint !==
        operation.preview.fingerprint
    )
      return error("resource_preview_changed");
    operation.status = "pending";
    operation.can_retry = false;
    operation.gate_active = true;
    operation.completed_at = null;
    operation.error_code = null;
  } else if (operation.status !== "unknown") return error("resource_retry_not_allowed");
  else if (match[2] === "reconcile") {
    // Tests seed authoritative readback explicitly; the demo never invents worker execution.
    if (
      operation.observation?.configuration === "matched" &&
      operation.attempts.at(-1)?.receipt === "accepted"
    ) {
      operation.status = "succeeded";
      operation.completed_at = now();
      operation.gate_active = false;
      operation.error_code = null;
      operation.requires_manual_reconciliation = false;
    } else {
      operation.error_code =
        operation.observation?.configuration === "different"
          ? "resource_partial_write"
          : "resource_manual_reconciliation_required";
      operation.requires_manual_reconciliation = true;
    }
  } else if (match[2] === "evidence") {
    if (
      !["applied", "not_applied", "partial", "externally_removed"].includes(String(body.result)) ||
      typeof body.evidence_digest !== "string" ||
      typeof body.checked_at !== "string"
    )
      return error("resource_evidence_invalid", 400);
    const result =
      body.result === "applied"
        ? "applied"
        : body.result === "not_applied"
          ? "not_applied"
          : body.result === "externally_removed"
            ? "externally_removed"
            : "partial";
    const evidence = resourceEvidenceBody(
      operation,
      result,
      body.evidence_digest,
      body.checked_at,
      typeof body.target_id === "string" ? body.target_id : "",
      body.original_request_terminated === true
    );
    if (!evidence || body.attempt !== evidence.attempt)
      return error("resource_evidence_invalid", 400);
    const observed = operation.observation;
    if (!observed || observed.configuration === "unavailable")
      return error("resource_sources_incomplete");
    if (
      (result === "applied" && observed.configuration !== "matched") ||
      (result === "externally_removed" &&
        (observed.configuration !== "missing" || observed.values !== null)) ||
      (result === "partial" &&
        (!observed.values || operation.change.operation === "node_restart")) ||
      (result === "not_applied" &&
        (operation.change.operation.endsWith("_create")
          ? observed.values !== null
          : canonicalResource(observed.values) !== canonicalResource(operation.preview.current))) ||
      (evidence.target_id &&
        ((operation.target_id && evidence.target_id !== operation.target_id) ||
          (observed.values && evidence.target_id !== observed.values.id)))
    )
      return error("resource_evidence_invalid");
    operation.evidence.push({
      actor_id: 910001,
      attempt: evidence.attempt,
      result,
      target_id: evidence.target_id ?? null,
      evidence_digest: evidence.evidence_digest,
      observed_at: evidence.checked_at,
      recorded_at: now(),
      provenance: "administrator_attestation",
      original_request_terminated: result === "externally_removed" ? true : null,
    });
    operation.status = result === "applied" ? "succeeded" : "failed";
    operation.gate_active = false;
    operation.completed_at = now();
    operation.requires_manual_reconciliation = false;
    operation.error_code =
      result === "not_applied"
        ? "resource_write_rejected"
        : result === "partial"
          ? "resource_partial_write"
          : result === "externally_removed"
            ? "resource_target_removed"
            : null;
    operation.can_retry = result === "not_applied";
    if (evidence.target_id) {
      operation.target_id = evidence.target_id;
      observed.correlation = "administrator_attestation";
    }
  }
  operation.version++;
  return { ok: true, duplicate: false, operation: copy(operation) };
}
