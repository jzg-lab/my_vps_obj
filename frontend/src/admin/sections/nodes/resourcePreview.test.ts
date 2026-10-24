import { get } from "svelte/store";
import { describe, expect, it } from "vitest";
import { createApiClient, type MockApi } from "$lib/webapp/publicApi";
import { consoleNodeFixture } from "$lib/admin/consoleNodesFixtures";
import { consoleResourcePreviewFixture } from "$lib/webapp/mockApi/consoleResourcePreview";
import {
  canReviewPreview,
  createResourcePreview,
  type NodeChange,
  type ResourcePreview,
} from "./resourcePreview";

const change: NodeChange = {
  operation: "node_disable",
  target_id: consoleNodeFixture.id,
  force_restart: false,
};
const result = (draft: NodeChange = change) => ({
  ok: true,
  ...consoleResourcePreviewFixture(draft),
});
function harness() {
  const calls: Array<{
    path: string;
    options: RequestInit;
    resolve: (value: unknown) => void;
    reject: (error: Error) => void;
  }> = [];
  const mockApi: MockApi = (path, options) =>
    new Promise<unknown>((resolve, reject) => {
      calls.push({ path, options, resolve, reject });
    });
  const preview = createResourcePreview(createApiClient({ mockApi }).api);
  return { preview, calls };
}

describe("read-only resource preview state", () => {
  it("does not read or confirm without an explicit draft", async () => {
    const { preview, calls } = harness();
    preview.confirm(true);
    await preview.load();
    await preview.revalidate();
    expect(calls).toHaveLength(0);
    expect(get(preview).confirmed).toBe(false);
  });

  it("uses the generated request shape, allows review only after a complete response, and coalesces busy clicks", async () => {
    const { preview, calls } = harness();
    preview.setChange(change);
    const pending = preview.load();
    await preview.load();
    preview.confirm(true);
    expect(get(preview)).toMatchObject({ busy: "preview", preview: null, confirmed: false });
    expect(calls).toHaveLength(1);
    expect(calls[0].path).toBe("/admin/console/resources/preview");
    expect(calls[0].options.method).toBe("POST");
    expect(JSON.parse(String(calls[0].options.body))).toEqual({ change });
    calls[0].resolve(result());
    await pending;
    preview.confirm(true);
    expect(get(preview)).toMatchObject({ busy: null, failed: false, confirmed: true });
    expect(get(preview).preview?.execution_available).toBe(false);
    preview.setChange({ ...change });
    expect(get(preview).confirmed).toBe(true);
  });

  it.each(["draft", "target", "close"] as const)(
    "clears old results and review when the %s changes",
    async (mode) => {
      const { preview, calls } = harness();
      preview.setChange(change);
      const pending = preview.load();
      calls[0].resolve(result());
      await pending;
      preview.confirm(true);
      preview.setChange(
        mode === "close"
          ? null
          : {
              ...change,
              ...(mode === "draft"
                ? { operation: "node_restart" as const }
                : { target_id: "10000000-0000-0000-0000-000000000002" }),
            }
      );
      expect(get(preview)).toMatchObject({
        preview: null,
        confirmed: false,
        validation: null,
        failed: false,
      });
    }
  );

  it.each(["success", "failure"] as const)(
    "ignores a late %s even when the transport ignores AbortSignal",
    async (late) => {
      const { preview, calls } = harness();
      preview.setChange(change);
      const old = preview.load();
      const next: NodeChange = { ...change, operation: "node_restart", force_restart: true };
      preview.setChange(next);
      const fresh = preview.load();
      expect(calls[0].options.signal?.aborted).toBe(true);
      calls[1].resolve(result(next));
      await fresh;
      preview.confirm(true);
      if (late === "success") calls[0].resolve(result());
      else calls[0].reject(new Error("late_transport_failure"));
      await old;
      expect(get(preview)).toMatchObject({
        preview: { change: next },
        confirmed: true,
        failed: false,
        busy: null,
      });
    }
  );

  it.each(["unchanged", "changed", "incomplete", "failed"] as const)(
    "handles %s revalidation without retaining unsafe confirmation",
    async (reason) => {
      const { preview, calls } = harness();
      preview.setChange(change);
      const first = preview.load();
      calls[0].resolve(result());
      await first;
      preview.confirm(true);
      const pending = preview.revalidate();
      expect(get(preview)).toMatchObject({ busy: "revalidate", confirmed: false, preview: null });
      expect(calls[1].path).toBe("/admin/console/resources/revalidate");
      expect(calls[1].options.method).toBe("POST");
      expect(JSON.parse(String(calls[1].options.body))).toEqual({
        change,
        expected_fingerprint: result().fingerprint,
      });
      if (reason === "failed") calls[1].reject(new Error("remote_secret_must_not_be_rendered"));
      else
        calls[1].resolve({
          ok: true,
          valid: reason === "unchanged",
          reason,
          preview: {
            ...result(),
            ...(reason === "changed" ? { fingerprint: "c".repeat(64) } : {}),
            ...(reason === "incomplete"
              ? { coverage: "partial", fingerprint: null, blockers: ["services_unavailable"] }
              : {}),
          },
        });
      await pending;
      expect(get(preview).validation).toBe(reason);
      expect(get(preview).confirmed).toBe(reason === "unchanged");
      expect(get(preview).failed).toBe(reason === "failed");
      expect(JSON.stringify(get(preview))).not.toContain("remote_secret");
    }
  );

  it("ignores late revalidation after another operation is selected", async () => {
    const { preview, calls } = harness();
    preview.setChange(change);
    const first = preview.load();
    calls[0].resolve(result());
    await first;
    preview.confirm(true);
    const pending = preview.revalidate();
    const next: NodeChange = { ...change, operation: "node_enable" };
    preview.setChange(next);
    calls[1].resolve({ ok: true, valid: true, reason: "unchanged", preview: result() });
    await pending;
    expect(calls[1].options.signal?.aborted).toBe(true);
    expect(get(preview)).toMatchObject({
      change: next,
      confirmed: false,
      preview: null,
      validation: null,
      busy: null,
    });
  });

  it.each([
    { coverage: "partial" as const },
    { blockers: ["services_unavailable"] },
    { fingerprint: null },
    { current: null },
    { proposed: null },
    { remote_authorization_verified: false },
  ])("refuses review and revalidation for incomplete evidence %j", async (patch) => {
    const { preview, calls } = harness();
    preview.setChange(change);
    const pending = preview.load();
    calls[0].resolve({ ...result(), ...patch });
    await pending;
    preview.confirm(true);
    await preview.revalidate();
    expect(canReviewPreview(get(preview).preview)).toBe(false);
    expect(get(preview).confirmed).toBe(false);
    expect(calls).toHaveLength(1);
  });

  it.each(["change", "current", "proposed"] as const)(
    "rejects a mismatched response %s",
    async (field) => {
      const { preview, calls } = harness();
      preview.setChange(change);
      const pending = preview.load();
      const wrong: ResourcePreview = consoleResourcePreviewFixture(change);
      if (field === "change") wrong.change = { ...change, target_id: "another-node" };
      else if (wrong[field]) wrong[field] = { ...wrong[field], id: "another-node" };
      calls[0].resolve({ ok: true, ...wrong });
      await pending;
      expect(get(preview)).toMatchObject({ failed: true, preview: null, confirmed: false });
    }
  );

  it("aborts on destroy and does not publish a delayed result", async () => {
    const { preview, calls } = harness();
    preview.setChange(change);
    const pending = preview.load();
    preview.destroy();
    expect(calls[0].options.signal?.aborted).toBe(true);
    const state = get(preview);
    calls[0].resolve(result());
    await pending;
    expect(get(preview)).toBe(state);
    await preview.load();
    expect(calls).toHaveLength(1);
  });

  it("retries a failed read without an execution endpoint", async () => {
    const { preview, calls } = harness();
    preview.setChange(change);
    const first = preview.load();
    calls[0].resolve({ ok: false, error: "read_failed" });
    await first;
    expect(get(preview).failed).toBe(true);
    const retry = preview.load();
    calls[1].resolve(result());
    await retry;
    expect(get(preview)).toMatchObject({
      failed: false,
      confirmed: false,
      preview: { execution_available: false },
    });
    expect(calls.map((call) => call.path)).toEqual(
      Array(2).fill("/admin/console/resources/preview")
    );
  });
});
