import { beforeEach, describe, expect, it } from "vitest";
import { createApiClient, unwrap } from "../publicApi";
import { consoleNodeFixture } from "$lib/admin/consoleNodesFixtures";
import {
  resourceEvidence,
  resourceReconcile,
  resourceRetry,
  readResourceOperation,
  type ResourceOperation,
} from "$lib/admin/resourceOperations";
import { consoleResourceCatalogFixture } from "./consoleResourcePreview";
import {
  consoleResourceOperationsDemoResponse as response,
  resetResourceOperationsDemo,
  resourceOperationFixture,
  resourceOperationPreviewFixture,
  seedResourceOperationDemo,
} from "./consoleResourceOperations";

const api = createApiClient({ mockApi: response }).api;
const change = { operation: "group_create", name: "New group", inbound_ids: [] } as const;
const draft = () => ({ ...change, inbound_ids: [] });
const post = (path: string, body: unknown) =>
  response(path, { method: "POST", body: JSON.stringify(body) });
const start = (key = "original-intent") =>
  api("/admin/console/resources/operations", {
    method: "POST" as const,
    body: JSON.stringify({
      change: draft(),
      expected_fingerprint: resourceOperationPreviewFixture(draft()).fingerprint,
      idempotency_key: key,
    }),
  }).then(unwrap);
function unknown(receipt: "unknown" | "accepted" = "unknown"): ResourceOperation {
  const operation = resourceOperationFixture();
  operation.status = "unknown";
  operation.attempts = [
    { number: 1, receipt, started_at: new Date(Date.now() - 60000).toISOString() },
  ];
  operation.error_code = "resource_write_unknown";
  operation.requires_manual_reconciliation = true;
  operation.observation = {
    configuration: "matched",
    values: operation.preview.proposed,
    observed_at: new Date().toISOString(),
    runtime: "unverified",
    correlation: "known_uuid",
    restart: "not_requested",
  };
  return operation;
}
beforeEach(resetResourceOperationsDemo);
describe("resource operation demo contracts", () => {
  it.each(["preview", "revalidate"])(
    "uses the real invalid_resource_change error for invalid %s bodies",
    (action) => {
      for (const body of [
        "{",
        "null",
        "[]",
        "{}",
        JSON.stringify({ change: { operation: "private_command" } }),
        JSON.stringify({ change: draft(), expected_fingerprint: "bad" }),
        JSON.stringify({ change: draft(), arbitrary: true }),
      ]) {
        expect(response(`/admin/console/resources/${action}`, { method: "POST", body })).toEqual({
          ok: false,
          error: "invalid_resource_change",
          status: 400,
        });
      }
      const host = consoleResourceCatalogFixture().hosts[0];
      expect(
        post(`/admin/console/resources/${action}`, {
          change: {
            operation: "host_update",
            target_id: host.id,
            patch: { port: 443, address: null },
          },
          expected_fingerprint: "a".repeat(64),
        })
      ).toMatchObject({ error: "invalid_resource_change" });
    }
  );

  it("leaves unrelated routes to the public dispatcher", () => {
    for (const path of ["/admin/users", "/admin/console/resources/future", "/admin/console/nodes"])
      expect(response(path, {})).toBeUndefined();
  });

  it("scopes create impacts to selected inbounds rather than unrelated example services", () => {
    const empty = resourceOperationPreviewFixture(draft());
    expect(empty.direct.services).toEqual([]);
    expect(empty.affected_customer_ids).toEqual([]);
    const selected = resourceOperationPreviewFixture({
      ...draft(),
      inbound_ids: [...consoleNodeFixture.inbound_ids],
    });
    expect(selected.direct.services).toHaveLength(1);
    expect(selected.affected_customer_ids).toEqual(selected.direct.customer_ids);
  });

  it("supports typed create previews and partial Host edits without mutating catalog", async () => {
    const catalog = consoleResourceCatalogFixture();
    const host = catalog.hosts[0];
    for (const change of [
      draft(),
      {
        operation: "node_create",
        name: "New node",
        address: "node.example",
        port: 2222,
        profile_id: catalog.profiles[0].id,
        inbound_ids: [catalog.profiles[0].inbounds[0].id],
      },
      {
        operation: "host_create",
        name: "New route",
        address: "route.example",
        port: 443,
        profile_id: host.profile_id,
        inbound_id: host.inbound_ids[0],
        node_ids: [],
        group_mode: "EXCLUDE",
        group_ids: [],
        is_disabled: true,
        is_hidden: false,
      },
      { operation: "host_update", target_id: host.id, patch: { port: 8443 } },
    ]) {
      const preview = unwrap(
        await api("/admin/console/resources/preview", {
          method: "POST",
          body: JSON.stringify({ change }),
        })
      );
      expect(preview).toMatchObject({ execution_available: true, coverage: "complete" });
      const revalidated = unwrap(
        await api("/admin/console/resources/revalidate", {
          method: "POST",
          body: JSON.stringify({ change, expected_fingerprint: preview.fingerprint }),
        })
      );
      expect(revalidated).toMatchObject({ valid: true, reason: "unchanged" });
      if (change.operation.endsWith("_create")) expect(preview.current).toBeNull();
      else expect(preview.proposed).toMatchObject({ address: host.address, port: 8443 });
    }
    expect(consoleResourceCatalogFixture()).toEqual(catalog);
  });

  it("records pending once and resolves exact idempotent replay before the busy gate", async () => {
    const first = await start();
    expect(first).toMatchObject({
      duplicate: false,
      operation: { status: "pending", gate_active: true, completed_at: null, attempts: [] },
    });
    const duplicate = await start();
    expect(duplicate).toMatchObject({
      duplicate: true,
      operation: { id: first.operation.id, status: "pending", version: 1, attempts: [] },
    });
    expect(unwrap(await api("/admin/console/resources/operations")).total).toBe(1);
    expect(await start("another-intent").catch((error: unknown) => error)).toMatchObject({
      error: "resource_operation_in_progress",
    });
    expect(
      post("/admin/console/resources/operations", {
        change: { ...draft(), name: "Different" },
        idempotency_key: "original-intent",
        expected_fingerprint: "a".repeat(64),
      })
    ).toMatchObject({ error: "resource_idempotency_conflict" });
  });

  it("rejects unsafe list/start/recovery inputs without creating records", async () => {
    expect(response("/admin/console/resources/operations?limit=101", {})).toMatchObject({
      error: "invalid_resource_operation_request",
    });
    expect(response("/admin/console/resources/catalog?extra=1", {})).toMatchObject({
      error: "invalid_resource_catalog_query",
    });
    expect(
      post("/admin/console/resources/operations", {
        change: draft(),
        idempotency_key: "a".repeat(129),
        expected_fingerprint: "a".repeat(64),
      })
    ).toMatchObject({ error: "invalid_resource_operation_request" });
    expect(
      post("/admin/console/resources/operations", {
        change: draft(),
        idempotency_key: "key",
        expected_fingerprint: resourceOperationPreviewFixture(draft()).fingerprint,
        recovery_of: "f".repeat(32),
      })
    ).toMatchObject({ error: "resource_recovery_invalid" });
    expect(unwrap(await api("/admin/console/resources/operations")).total).toBe(0);
  });

  it("never treats matching readback alone as completion of an unknown write", async () => {
    const operation = unknown();
    seedResourceOperationDemo(operation);
    const result = await resourceReconcile(api, operation);
    expect(result.operation).toMatchObject({
      status: "unknown",
      gate_active: true,
      version: 2,
      error_code: "resource_manual_reconciliation_required",
      requires_manual_reconciliation: true,
    });
    expect(result.operation.attempts).toEqual(operation.attempts);
    operation.attempts[0].receipt = "accepted";
    seedResourceOperationDemo(operation);
    expect((await resourceReconcile(api, operation)).operation).toMatchObject({
      status: "succeeded",
      gate_active: false,
    });
  });

  it("requires real seeded readback for manual attestation and keeps its provenance", async () => {
    const operation = unknown();
    operation.observation = null;
    seedResourceOperationDemo(operation);
    const body = {
      expected_version: 1,
      attempt: 1,
      result: "applied" as const,
      target_id: null,
      original_request_terminated: null,
      evidence_digest: "a".repeat(64),
      checked_at: new Date(Date.now() - 1000).toISOString(),
    };
    expect(
      await resourceEvidence(api, operation.id, body).catch((error: unknown) => error)
    ).toMatchObject({ error: "resource_sources_incomplete" });
    expect((await readResourceOperation(api, operation.id)).evidence).toEqual([]);
    operation.observation = unknown().observation;
    seedResourceOperationDemo(operation);
    const result = await resourceEvidence(api, operation.id, body);
    expect(result.operation).toMatchObject({
      status: "succeeded",
      gate_active: false,
      observation: { runtime: "unverified" },
    });
    expect(result.operation.evidence[0]).toMatchObject({
      provenance: "administrator_attestation",
      evidence_digest: body.evidence_digest,
      observed_at: body.checked_at,
    });
    expect(
      await resourceEvidence(api, operation.id, body).catch((error: unknown) => error)
    ).toMatchObject({ error: "resource_operation_changed" });
  });

  it("refuses contradictory manual evidence and unsupported per-record methods", async () => {
    const operation = unknown();
    seedResourceOperationDemo(operation);
    expect(
      await resourceEvidence(api, operation.id, {
        expected_version: 1,
        attempt: 1,
        result: "not_applied",
        target_id: null,
        original_request_terminated: null,
        evidence_digest: "a".repeat(64),
        checked_at: new Date(Date.now() - 1000).toISOString(),
      }).catch((error: unknown) => error)
    ).toMatchObject({ error: "resource_evidence_invalid" });
    expect(
      post(`/admin/console/resources/operations/${operation.id}`, { expected_version: 1 })
    ).toMatchObject({ error: "method_not_allowed" });
    expect((await readResourceOperation(api, operation.id)).version).toBe(1);
  });

  it("retries only a rejected unchanged original operation, once for the expected version", async () => {
    const operation = resourceOperationFixture();
    Object.assign(operation, {
      status: "failed",
      can_retry: true,
      gate_active: false,
      error_code: "resource_write_rejected",
      completed_at: new Date().toISOString(),
    });
    seedResourceOperationDemo(operation);
    expect(
      await resourceRetry(api, operation, "f".repeat(64)).catch((error: unknown) => error)
    ).toMatchObject({ error: "resource_preview_changed" });
    const result = await resourceRetry(api, operation, operation.preview.fingerprint!);
    expect(result.operation).toMatchObject({
      id: operation.id,
      version: 2,
      status: "pending",
      gate_active: true,
      completed_at: null,
      attempts: [],
    });
    expect(
      await resourceRetry(api, operation, operation.preview.fingerprint!).catch(
        (error: unknown) => error
      )
    ).toMatchObject({ error: "resource_operation_changed" });
  });

  it("does not retry partial writes or an original whose inventory fingerprint changed", async () => {
    const operation = resourceOperationFixture();
    Object.assign(operation, {
      status: "failed",
      can_retry: true,
      gate_active: false,
      error_code: "resource_partial_write",
    });
    seedResourceOperationDemo(operation);
    expect(
      await resourceRetry(api, operation, operation.preview.fingerprint!).catch(
        (error: unknown) => error
      )
    ).toMatchObject({ error: "resource_retry_not_allowed" });
    operation.error_code = "resource_write_rejected";
    operation.preview.fingerprint = "e".repeat(64);
    seedResourceOperationDemo(operation);
    expect(
      await resourceRetry(api, operation, operation.preview.fingerprint).catch(
        (error: unknown) => error
      )
    ).toMatchObject({ error: "resource_preview_changed" });
  });

  it("returns only an explicit demo deployment credential, with no installation or operation", async () => {
    const before = structuredClone(consoleNodeFixture);
    expect(
      post("/admin/console/nodes/onboarding/deployment", { management_port: 2222 })
    ).toMatchObject({
      ok: true,
      panel_version: "3.4.5",
      recorded_node_version: "3.4.2",
      installation_performed: false,
      secret_key: "DEMO-NOT-A-REAL-NODE-CREDENTIAL",
    });
    expect(
      post("/admin/console/nodes/onboarding/deployment", { management_port: "2222" })
    ).toMatchObject({ error: "invalid_resource_operation_request" });
    expect(unwrap(await api("/admin/console/resources/operations")).items).toEqual([]);
    expect(consoleNodeFixture).toEqual(before);
  });
});
