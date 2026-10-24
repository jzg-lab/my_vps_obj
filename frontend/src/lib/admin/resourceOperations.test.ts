import { describe, expect, it } from "vitest";
import { consoleNodeFixture } from "./consoleNodesFixtures";
import {
  resourceEvidenceBody,
  resourceErrorKey,
  resourceRejected,
  resourceRecovery,
  resourceOperationsUrl,
} from "./resourceOperations";
import {
  resourceOperationFixture,
  resourceOperationPreviewFixture,
} from "$lib/webapp/mockApi/consoleResourceOperations";
import { resourceEndpoint, resourcePort, validResourceChange } from "./resourceIntent";
import { canReviewPreview } from "../../admin/sections/nodes/resourcePreview";

describe("resource operation contracts", () => {
  it("allows complete create previews without inventing a current resource", () => {
    const preview = resourceOperationPreviewFixture({
      operation: "group_create",
      name: "New group",
      inbound_ids: [],
    });
    expect(preview.current).toBeNull();
    expect(preview.proposed?.id).toBeNull();
    expect(canReviewPreview(preview)).toBe(true);
    expect(canReviewPreview({ ...preview, coverage: "partial" })).toBe(false);
    expect(canReviewPreview({ ...preview, remote_authorization_verified: false })).toBe(false);
  });
  it.each([0, 65536, 1.5, NaN, Infinity, "443", "1e3", "0x100"])("rejects unsafe port %s", (port) =>
    expect(resourcePort(port)).toBe(false)
  );
  it.each(["host.example", "192.0.2.1", "2001:db8::1"])(
    "accepts an endpoint %s without a URL",
    (endpoint) => expect(resourceEndpoint(endpoint)).toBe(true)
  );
  it.each(["https://host.example", "host/path", "host:443", "host?secret=1", "bad address"])(
    "rejects endpoint %s",
    (endpoint) => expect(resourceEndpoint(endpoint)).toBe(false)
  );
  it("validates all create branches and rejects secrets or arbitrary stored request fields", () => {
    expect(
      validResourceChange({ operation: "group_create", name: "New-group", inbound_ids: [] })
    ).toBe(true);
    expect(
      validResourceChange({ operation: "group_create", name: "Default-Squad", inbound_ids: [] })
    ).toBe(false);
    expect(validResourceChange({ operation: "group_create", name: "中文", inbound_ids: [] })).toBe(
      false
    );
    const node = {
      operation: "node_create",
      name: "Test node",
      address: "node.example",
      port: 2222,
      profile_id: consoleNodeFixture.profile_id,
      inbound_ids: consoleNodeFixture.inbound_ids,
    };
    expect(validResourceChange(node)).toBe(true);
    expect(validResourceChange({ ...node, secret_key: "private" })).toBe(false);
    const host = {
      operation: "host_create",
      name: "Test route",
      address: "route.example",
      port: 443,
      profile_id: consoleNodeFixture.profile_id,
      inbound_id: consoleNodeFixture.inbound_ids[0],
      node_ids: [],
      group_ids: [],
      group_mode: "EXCLUDE",
      is_disabled: true,
      is_hidden: false,
    };
    expect(validResourceChange(host)).toBe(true);
    expect(validResourceChange({ ...host, group_mode: "ALLOW_ONLY" })).toBe(false);
    expect(
      validResourceChange({
        operation: "host_update",
        target_id: consoleNodeFixture.id,
        patch: { profile_id: consoleNodeFixture.profile_id },
      })
    ).toBe(false);
  });
  it("distinguishes explicit validation rejection from ambiguous 503 and timeout", () => {
    expect(resourceRejected({ error: "invalid_resource_operation_request", status: 400 })).toBe(
      true
    );
    expect(resourceRejected({ error: "resource_evidence_invalid", status: 409 })).toBe(true);
    expect(resourceRejected({ error: "resource_sources_incomplete", status: 503 })).toBe(false);
    expect(resourceRejected(new Error("timeout"))).toBe(false);
    expect(resourceRejected({ error: "resource_write_unknown" })).toBe(false);
    expect(resourceErrorKey({ error: "private_secret_message" })).toBe(
      "resource_ops_error_unknown"
    );
  });
  it("builds only safe restoration fields and never compensates a pending or unknown write", () => {
    const operation = resourceOperationFixture();
    expect(resourceRecovery(operation)).toBeNull();
    operation.status = "succeeded";
    operation.gate_active = false;
    expect(resourceRecovery(operation)).toEqual({
      operation: "node_enable",
      target_id: consoleNodeFixture.id,
      force_restart: false,
    });
    operation.status = "unknown";
    expect(resourceRecovery(operation)).toBeNull();
    const host = resourceOperationFixture({
      operation: "host_update",
      target_id: "50000000-0000-0000-0000-000000000001",
      patch: { port: 8443 },
    });
    host.status = "succeeded";
    host.gate_active = false;
    expect(resourceRecovery(host)).toEqual({
      operation: "host_update",
      target_id: host.target_id,
      patch: { port: 443 },
    });
    const create = resourceOperationFixture({
      operation: "group_create",
      name: "Test group",
      inbound_ids: [],
    });
    create.status = "succeeded";
    create.gate_active = false;
    expect(resourceRecovery(create)).toBeNull();
  });
  it("binds manual evidence to the real last attempt and observed time", () => {
    const operation = resourceOperationFixture({
      operation: "group_create",
      name: "Test group",
      inbound_ids: [],
    });
    const started = new Date(Date.now() - 60000).toISOString();
    const checked = new Date(Date.now() - 1000).toISOString();
    operation.status = "unknown";
    operation.attempts = [{ number: 3, receipt: "unknown", started_at: started }];
    expect(resourceEvidenceBody(operation, "applied", "a".repeat(64), checked, "")).toBeNull();
    expect(
      resourceEvidenceBody(operation, "not_applied", "a".repeat(64), checked, "")
    ).toMatchObject({ attempt: 3, expected_version: 1, target_id: null, checked_at: checked });
    expect(
      resourceEvidenceBody(operation, "partial", "a".repeat(64), checked, consoleNodeFixture.id)
    ).toMatchObject({ target_id: consoleNodeFixture.id });
    for (const time of [
      "",
      "broken",
      new Date(Date.now() + 60000).toISOString(),
      new Date(Date.now() - 120000).toISOString(),
    ])
      expect(resourceEvidenceBody(operation, "not_applied", "a".repeat(64), time, "")).toBeNull();
    expect(resourceEvidenceBody(operation, "not_applied", "bad", checked, "")).toBeNull();
    expect(resourceEvidenceBody(operation, "", "a".repeat(64), checked, "")).toBeNull();
  });
  it("links global records without discarding service filters or return context", () => {
    const url = resourceOperationsUrl(
      "https://console.test/app/admin/nodes?user_id=42&cursor=previous&mock=services",
      "/app",
      "a".repeat(32)
    );
    expect(url.pathname).toBe("/app/admin/console-operations");
    expect(url.searchParams.get("operations_view")).toBe("resources");
    expect(url.searchParams.get("resource_operation_id")).toBe("a".repeat(32));
    expect(url.searchParams.get("user_id")).toBe("42");
    expect(url.searchParams.get("cursor")).toBe("previous");
  });
  it("requires known target and terminated request evidence before closing an external deletion", () => {
    const operation = resourceOperationFixture();
    operation.status = "unknown";
    operation.attempts = [
      { number: 2, receipt: "unknown", started_at: new Date(Date.now() - 60000).toISOString() },
    ];
    const checked = new Date(Date.now() - 1000).toISOString();
    const target = operation.target_id!;
    const evidence = (id: string, terminated: boolean) =>
      resourceEvidenceBody(
        operation,
        "externally_removed",
        "a".repeat(64),
        checked,
        id,
        terminated
      );
    expect(evidence(target, false)).toBeNull();
    expect(evidence("", true)).toBeNull();
    expect(evidence("50000000-0000-0000-0000-000000000099", true)).toBeNull();
    operation.attempts[0].started_at = new Date(Date.now() - 10 * 60 * 1000).toISOString();
    expect(
      resourceEvidenceBody(
        operation,
        "externally_removed",
        "a".repeat(64),
        new Date(Date.now() - 6 * 60 * 1000).toISOString(),
        target,
        true
      )
    ).toBeNull();
    expect(evidence(target, true)).toMatchObject({
      target_id: target,
      result: "externally_removed",
      original_request_terminated: true,
      expected_version: operation.version,
      attempt: 2,
    });
    operation.status = "failed";
    operation.gate_active = false;
    operation.error_code = "resource_target_removed";
    expect(resourceRecovery(operation)).toBeNull();
    expect(resourceErrorKey(operation.error_code)).toBe("resource_ops_error_removed");
    operation.status = "unknown";
    operation.target_id = null;
    expect(evidence(target, true)).toBeNull();
  });
});
