import { describe, expect, it, vi } from "vitest";
import { replacementFixture } from "./exitReplacementFixtures";
import {
  emptyReplacementFields,
  replacementAvailable,
  replacementInteger,
  replacementTime,
  replacementDigest,
  replacementSnapshot,
  replacementWrite,
  startReplacementWrite,
  postReplacement,
  readReplacement,
  replacementLabel,
} from "./exitReplacement";
import {
  canReplayReplacement,
  readPendingReplacement,
  savePendingReplacement,
  validReplacementWrite,
  replacementRejected,
} from "./exitReplacementPending";

describe("replacement evidence and immutable commands", () => {
  it.each([
    "invalid_exit_evidence",
    "invalid_replacement_request",
    "exit_replacement_hold_changed",
    "exit_unavailable",
    "invalid_idempotency_key",
    "invalid_payload",
    "invalid_service_retry_query",
    "exit_replacement_sources_incomplete",
  ])("unlocks editable evidence for the explicit rejection %s", (error) => {
    expect(replacementRejected({ ok: false, error })).toBe(true);
    expect(replacementRejected({ error, status: 400 })).toBe(true);
    expect(replacementRejected({ error, status: 503 })).toBe(false);
  });
  it.each([
    new Error("timeout"),
    { status: 503, error: "exit_replacement_sources_incomplete" },
    { error: "exit_replacement_write_unknown" },
    { error: "future_code" },
  ])("keeps uncertain requests immutable: %j", (failure) => {
    expect(replacementRejected(failure)).toBe(false);
  });
  it.each(["", " ", " 1", "+1", "-1", "1.1", "1e3", "01", "0x10", "9007199254740992"])(
    "rejects unsafe count %j",
    (raw) => {
      expect(() => replacementInteger(raw)).toThrow();
    }
  );
  it.each(["0", "73", "9007199254740991"])("retains exact integer %s", (raw) => {
    expect(replacementInteger(raw)).toBe(Number(raw));
  });
  it("never initializes evidence times, digests or counters", () => {
    const fields = emptyReplacementFields();
    for (const key of [
      "checkedAt",
      "digest",
      "total",
      "raw",
      "offset",
      "usageAt",
      "usageDigest",
    ] as const)
      expect(fields[key]).toBe("");
    expect(fields.confirmed).toBe(false);
    expect(() => replacementTime("2999-01-01T00:00:00Z")).toThrow();
    expect(() => replacementTime("invalid")).toThrow();
    expect(() => replacementDigest("PRIVATE")).toThrow();
  });
  it("constructs only the administrator branch of existing verify/reclaim unions", () => {
    const { state, fields } = replacementFixture();
    const write = replacementWrite(state, 910002, "verify", fields);
    expect(validReplacementWrite(write)).toBe(true);
    expect(write.body).toMatchObject({
      replacement_operation_id: state.replacement!.operation.id,
      evidence_digest: fields.digest,
      fixed: true,
      exclusive: true,
    });
    expect(write.body).not.toHaveProperty("provenance");
    expect(write.body).not.toHaveProperty("evidence");
    expect(
      validReplacementWrite({ ...write, body: { ...write.body, provenance: "machine" } })
    ).toBe(false);
  });
  it("requires all actual stop attestations and metering after stop", () => {
    const { state, fields } = replacementFixture();
    expect(validReplacementWrite(replacementWrite(state, 910002, "stop_evidence", fields))).toBe(
      true
    );
    for (const patch of [
      { connectionsStopped: false },
      { authorizationRemoved: false },
      { oldConfigRejected: false },
      { total: "1e3" },
      { usageAt: "2026-10-22T00:00:00Z" },
      { digest: "" },
    ])
      expect(() =>
        replacementWrite(state, 910002, "stop_evidence", { ...fields, ...patch })
      ).toThrow();
  });
  it("uses backend actions and blocks retries even if a stale allowed list accompanies an unknown write", () => {
    const { state, fields } = replacementFixture();
    state.replacement!.progress.pending_action = "stop_old";
    state.replacement!.allowed_actions = ["retry", "resolve_write"];
    expect(replacementAvailable(state, "retry")).toBe(false);
    expect(() => replacementWrite(state, 910002, "retry", fields)).toThrow();
    expect(() => replacementWrite(state, 910002, "resolve_write", fields)).toThrow();
    const write = replacementWrite(state, 910002, "resolve_write", {
      ...fields,
      result: "not_applied",
    });
    expect(write.body).toMatchObject({
      purpose: "resolve_write",
      action: "stop_old",
      attempt: 1,
      usage_total_bytes: null,
      result: "not_applied",
    });
    expect(validReplacementWrite(write)).toBe(true);
  });
  it("requires both current evidence references for one confirmation and restoration request", () => {
    const { state, fields } = replacementFixture();
    const row = state.replacement!;
    row.allowed_actions.push("confirm");
    expect(() => replacementWrite(state, 910002, "confirm", fields)).toThrow();
    row.candidate_verification = {
      audit_id: "8".repeat(32),
      observed_at: fields.checkedAt,
      provenance: "machine",
      valid: true,
    };
    const write = replacementWrite(state, 910002, "confirm", fields);
    expect(validReplacementWrite(write)).toBe(true);
    expect(write.body).toMatchObject({
      confirm_replace_and_request_restore: true,
      old_stop_audit_id: row.old_stop!.audit_id,
      candidate_verify_audit_id: row.candidate_verification.audit_id,
    });
    row.resource_fingerprint = "9".repeat(64);
    expect(() => replacementWrite(state, 910002, "confirm", fields)).toThrow();
  });
  it("keeps cleanup requests and explicit hold release scoped", () => {
    const { state, fields } = replacementFixture();
    const row = state.replacement!;
    row.allowed_actions = ["candidate_cleanup"];
    expect(
      validReplacementWrite(
        replacementWrite(state, 910002, "candidate_cleanup", fields, row.candidate_exit.id)
      )
    ).toBe(true);
    expect(() =>
      replacementWrite(state, 910002, "candidate_cleanup", fields, row.old_exit.id)
    ).toThrow();
    row.allowed_actions = ["reclaim"];
    expect(() => replacementWrite(state, 910002, "reclaim", fields, row.old_exit.id)).toThrow();
    row.old_exit.hold_order_id = row.operation.order_id;
    expect(replacementWrite(state, 910002, "reclaim", fields, row.old_exit.id).body).toMatchObject({
      reclaim_purpose: "retained_old",
    });
  });
  it("prevents start without the authoritative complete draft", () => {
    const { state, draft } = replacementFixture();
    state.replacement = null;
    state.draft = draft;
    expect(validReplacementWrite(startReplacementWrite(state, 910002, "Recorded fault"))).toBe(
      true
    );
    draft.coverage = "partial";
    expect(() => startReplacementWrite(state, 910002, "Recorded fault")).toThrow();
  });
  it("keeps unknown codes out of labels", () => {
    expect(replacementLabel("stage", "secret upstream error")).toBe("console_unknown");
    expect(replacementLabel("__proto__", "constructor")).toBe("console_unknown");
  });
});

describe("replacement request reconciliation", () => {
  it("preserves the exact command across storage and rejects owner changes", () => {
    const { state, fields } = replacementFixture();
    const pending = {
      serviceId: state.service_id,
      userId: 910002,
      snapshot: replacementSnapshot(state),
      write: replacementWrite(state, 910002, "verify", fields),
    };
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => {
        values.set(key, value);
      },
    } as Storage;
    savePendingReplacement(storage, pending);
    expect(readPendingReplacement(storage, state.service_id, 910002)).toEqual(pending);
    expect(() => readPendingReplacement(storage, state.service_id, 42)).toThrow();
    expect(canReplayReplacement(pending, state)).toBe(true);
    state.replacement!.progress.version++;
    expect(canReplayReplacement(pending, state)).toBe(false);
  });
  it("invalidates a draft when fresh server permission is withdrawn", () => {
    const { state, draft } = replacementFixture();
    state.replacement = null;
    state.draft = draft;
    const displayed = replacementSnapshot(state);
    draft.allowed_to_start = false;
    expect(replacementSnapshot(state)).not.toBe(displayed);
  });
  it.each(["service", "resource", "fingerprint", "scope", "operation"])(
    "never silently replays after %s changes",
    (kind) => {
      const { state, fields } = replacementFixture();
      const pending = {
        serviceId: state.service_id,
        userId: 910002,
        snapshot: replacementSnapshot(state),
        write: replacementWrite(state, 910002, "verify", fields),
      };
      if (kind === "service") state.service_revision++;
      if (kind === "resource") state.replacement!.candidate_exit.revision++;
      if (kind === "fingerprint") state.replacement!.resource_fingerprint = "9".repeat(64);
      if (kind === "scope") state.replacement!.candidate_exit.scope_fingerprint = "9".repeat(64);
      if (kind === "operation") state.replacement!.operation.id = "9".repeat(32);
      expect(canReplayReplacement(pending, state)).toBe(false);
    }
  );
  it("uses the scoped HTTP paths and replays byte-identical payloads", async () => {
    const { state, fields } = replacementFixture();
    const api = vi.fn().mockResolvedValue({ ok: true });
    const write = replacementWrite(state, 910002, "verify", fields);
    await postReplacement(api, state.service_id, write);
    await postReplacement(api, state.service_id, write);
    expect(api.mock.calls[0]).toEqual(api.mock.calls[1]);
    expect(api.mock.calls[0][0]).toBe(
      `/admin/dedicated-exits/${state.replacement!.candidate_exit.id}/verify`
    );
    await readReplacement(api, state.service_id, { operation_id: state.replacement!.operation.id });
    expect(api.mock.calls.at(-1)?.[0]).toContain(
      `/exit-replacement?operation_id=${state.replacement!.operation.id}`
    );
  });
});
