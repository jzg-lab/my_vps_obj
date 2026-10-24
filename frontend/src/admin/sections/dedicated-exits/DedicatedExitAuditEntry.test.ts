import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { components } from "$lib/api/openapi.generated";
import DedicatedExitAuditEntry from "./DedicatedExitAuditEntry.svelte";

function entry(action: string, evidence: Record<string, unknown>) {
  const item: components["schemas"]["ExitAuditOut"] = {
    id: "audit1",
    exit_id: "exit1",
    service_id: "actual-service",
    actor_id: 42,
    action,
    created_at: "2026-10-24T08:00:00Z",
    evidence,
  };
  return render(DedicatedExitAuditEntry, {
    props: {
      item,
      at: (key: string) => key,
      currentUrl: "https://console.test/admin/dedicated-exits?exit_id=exit1&exit_audit_page=1",
      onOpenService: vi.fn(),
    },
  }).body;
}

describe("dedicated exit audit action rendering", () => {
  it.each(["verify", "reclaim"])("preserves the %s label and manual evidence note", (action) => {
    const html = entry(action, { evidence: "Manual observation note" });
    expect(html).toContain(`<strong>services_exit_${action}</strong>`);
    expect(html).toContain("Manual observation note");
  });

  it.each([
    "replace_reserve",
    "replace_stop",
    "replace_verify",
    "replace_confirm",
    "replace_bind",
    "replace_write_result",
    "replace_cleanup",
    "replace_close_stop",
    "replace_reclaim",
    "replace_dispatch_skip",
  ])("renders %s as replacement, never reclaim or raw evidence", (action) => {
    const html = entry(action, {
      evidence: "private replacement evidence",
      request_sha256: "private-request-digest",
      result: { raw: "private upstream payload" },
    });
    expect(html).toContain(`<strong>replacement_audit_${action.slice("replace_".length)}</strong>`);
    expect(html).not.toContain("services_exit_reclaim");
    expect(html).not.toContain("private");
    expect(html).toContain("exit_service_id=actual-service");
    expect(html).toContain("exit_audit_page=1");
    expect(html).toContain("services_exit_actor");
  });

  it.each(["future_action", "replace_unrecognized"])(
    "keeps %s unknown without exposing payloads",
    (action) => {
      const html = entry(action, { evidence: "private unknown record" });
      expect(html).toContain("<strong>console_unknown</strong>");
      expect(html).not.toContain("services_exit_reclaim");
      expect(html).not.toContain("console_ops_phase_exit_replace");
      expect(html).not.toContain("private");
      expect(html).not.toContain(action);
    }
  );

  it("does not stringify structured manual evidence", () => {
    expect(entry("verify", { evidence: { payload: "private data" } })).not.toContain("private");
  });
});
