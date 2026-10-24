import { describe, expect, it } from "vitest";
import { createExitReplacementDemo, type ReplacementDemoState } from "./exitReplacement";
import { replacementFixture } from "$lib/admin/exitReplacementFixtures";
import {
  replacementWrite,
  replacementSnapshot,
  startReplacementWrite,
  type ReplacementState,
  type ReplacementWrite,
} from "$lib/admin/exitReplacement";

function setup() {
  const fixture = replacementFixture();
  const model: ReplacementDemoState = {
    services: [fixture.detail.service, fixture.affected.service],
    archived: [],
    exits: [fixture.old, fixture.candidate, fixture.held],
    audits: [],
    topology: fixture.draft,
  };
  const demo = createExitReplacementDemo();
  const base = `/admin/console/services/${fixture.detail.service.id}`;
  function read(candidate = false): ReplacementState {
    const result = demo.respond(
      `${base}/exit-replacement${candidate ? `?candidate_exit_id=${fixture.candidate.id}` : ""}`,
      {},
      model
    );
    if (!result?.ok || !("service_revision" in result))
      throw new Error("Expected replacement state");
    return result;
  }
  function send(write: ReplacementWrite) {
    const path =
      write.action === "start"
        ? `${base}/exit-replacement`
        : write.action === "confirm"
          ? `${base}/exit-replacement/confirm`
          : write.action === "retry"
            ? `${base}/operations/${write.operationId}/retry`
            : "exitId" in write
              ? `/admin/dedicated-exits/${write.exitId}/${write.action === "verify" ? "verify" : "reclaim"}`
              : `${base}/exit-replacement/evidence`;
    return demo.respond(path, { method: "POST", body: JSON.stringify(write.body) }, model);
  }
  const start = () => send(startReplacementWrite(read(true), 910002, "Recorded failure"));
  const submit = (action: Parameters<typeof replacementWrite>[2], exitId?: string) =>
    send(replacementWrite(read(), 910002, action, fixture.fields, exitId));
  const row = () => {
    const value = [...demo.replacements.values()][0];
    if (!value) throw new Error("Missing operation");
    return value;
  };
  return { fixture, model, demo, base, read, send, start, submit, row };
}

describe("typed replacement mock preserves the frozen contract", () => {
  it("does not intercept unrelated routes or ordinary verify requests", () => {
    const { demo, model } = setup();
    expect(demo.respond("/admin/console/summary", {}, model)).toBeUndefined();
    expect(
      demo.respond("/admin/dedicated-exits/b/verify", { method: "POST", body: "{}" }, model)
    ).toBeUndefined();
  });
  it("defaults to incomplete coverage rather than fabricated runtime observations", () => {
    const { model, read } = setup();
    delete model.topology;
    expect(read(true).draft).toMatchObject({
      coverage: "partial",
      allowed_to_start: false,
      resource_fingerprint: null,
    });
  });
  it("preserves known, missing and external identities in draft and operation projections", () => {
    const { fixture, read, start } = setup();
    expect(read(true).draft?.impacts).toEqual(fixture.draft.impacts);
    expect(fixture.draft.impacts?.every((impact) => impact.kind === "possible_reload")).toBe(true);
    expect(
      fixture.draft.impacts?.some((impact) => impact.service_id === fixture.detail.service.id)
    ).toBe(false);
    expect(fixture.draft.impacts?.[0]).toMatchObject({
      service_id: fixture.affected.service.id,
      customer_id: fixture.affected.service.user_id,
      service_name: fixture.affected.service.name,
    });
    start();
    expect(read().replacement?.impacts).toEqual(fixture.draft.impacts);
    expect(read().replacement?.impacts?.[1]).toMatchObject({
      service_id: "f".repeat(32),
      customer_id: null,
      service_name: null,
    });
    expect(read().replacement?.impacts?.[2]).toMatchObject({
      service_id: null,
      customer_id: null,
      service_name: null,
    });
  });
  it.each([0, 2])("blocks a draft with direct authorization conflict at impact %s", (index) => {
    const { fixture, read, send, model, demo } = setup();
    const write = startReplacementWrite(read(true), 910002, "Recorded failure");
    fixture.draft.impacts![index].kind = "direct_authorization";
    fixture.draft.impacts![index].group_ids = [fixture.old.squad_uuid];
    fixture.draft.block_reasons = ["exit_replacement_authorization_conflict"];
    expect(read(true).draft).toMatchObject({
      allowed_to_start: false,
      block_reasons: ["exit_replacement_authorization_conflict"],
    });
    expect(send(write)).toMatchObject({
      ok: false,
      error: "exit_replacement_authorization_conflict",
    });
    expect(model.audits).toHaveLength(0);
    expect(demo.operations).toHaveLength(0);
    expect(fixture.candidate.hold_order_id).toBeNull();
  });
  it("does not invalidate confirmation for a display-name-only change", () => {
    const { fixture, read, start, submit, send } = setup();
    start();
    submit("stop_evidence");
    submit("verify");
    const before = read();
    const fingerprint = before.replacement!.resource_fingerprint;
    const snapshot = replacementSnapshot(before);
    const write = replacementWrite(before, 910002, "confirm", fixture.fields);
    fixture.draft.impacts![0].service_name = "Updated display name";
    expect(read().replacement?.resource_fingerprint).toBe(fingerprint);
    expect(replacementSnapshot(read())).toBe(snapshot);
    expect(send(write)).toMatchObject({ accepted: true });
  });
  it("refuses stale confirmation when the server changes the ownership fingerprint", () => {
    const { fixture, read, start, submit, send, model } = setup();
    start();
    submit("stop_evidence");
    submit("verify");
    const write = replacementWrite(read(), 910002, "confirm", fixture.fields);
    fixture.draft.impacts![0].customer_id = 910004;
    fixture.draft.resource_fingerprint = "9".repeat(64);
    expect(send(write)).toMatchObject({ ok: false, error: "exit_replacement_scope_changed" });
    expect(model.audits.some((item) => item.action === "replace_confirm")).toBe(false);
    expect(read().replacement?.impacts?.[0].customer_id).toBe(910004);
  });
  it.each(["held", "bound", "disabled", "pool"])("refuses the %s candidate", (fault) => {
    const { fixture, read } = setup();
    if (fault === "held") fixture.candidate.hold_order_id = "f".repeat(32);
    if (fault === "bound") fixture.candidate.service_id = "f".repeat(32);
    if (fault === "disabled") fixture.candidate.enabled = false;
    if (fault === "pool") fixture.candidate.resource_pool = "another-pool";
    expect(read(true).draft?.allowed_to_start).toBe(false);
  });
  it("reserves once, keeps original binding and never treats acceptance as remote success", () => {
    const { fixture, read, send, row, model } = setup();
    const write = startReplacementWrite(read(true), 910002, "Recorded failure");
    expect(send(write)).toMatchObject({ accepted: true, duplicate: false });
    expect(send(write)).toMatchObject({ accepted: true, duplicate: true });
    expect(model.audits).toHaveLength(1);
    expect(fixture.old.service_id).toBe(fixture.detail.service.id);
    expect(fixture.candidate.service_id).toBeNull();
    expect(fixture.candidate.hold_order_id).toBe(row().operation.order_id);
    expect(row().operation.attempted_at).toBeNull();
    expect(row().old_stop).toBeNull();
    expect(row().progress.restore_result).toBe("not_requested");
  });
  it("rejects changed payload reuse and obsolete versions before effects", () => {
    const { start, send, submit, read, fixture, model } = setup();
    start();
    const write = replacementWrite(read(), 910002, "stop_evidence", fixture.fields);
    submit("stop_evidence");
    expect(send(write)).toMatchObject({ ok: false, error: "exit_replacement_version_changed" });
    const verified = replacementWrite(read(), 910002, "verify", fixture.fields);
    send(verified);
    expect(
      send({
        ...verified,
        body: { ...verified.body, evidence_digest: "a".repeat(64) },
      } as typeof verified)
    ).toMatchObject({ ok: false, error: "idempotency_conflict" });
    expect(model.audits.map((item) => item.action)).toEqual([
      "replace_verify",
      "replace_stop",
      "replace_reserve",
    ]);
  });
  it("uses only explicit administrator evidence and records a pending confirm/restore", () => {
    const { start, submit, read, fixture, demo, model, base } = setup();
    const before = structuredClone(fixture.detail.service);
    start();
    submit("stop_evidence");
    submit("verify");
    const body = replacementWrite(read(), 910002, "confirm", fixture.fields);
    expect(submit("confirm")).toMatchObject({
      accepted: true,
      replacement: {
        switch_result: "pending",
        restore_requested: true,
        progress: { restore_result: "pending" },
      },
    });
    expect(read().replacement?.old_stop?.provenance).toBe("administrator");
    expect(fixture.old.service_id).toBe(before.id);
    for (const field of ["used_bytes", "quota_bytes", "expires_at", "desired_status"] as const)
      expect(fixture.detail.service[field]).toEqual(before[field]);
    expect(
      demo.respond(
        `${base}/exit-replacement/evidence`,
        { method: "POST", body: JSON.stringify({ ...body.body, provenance: "machine" }) },
        model
      )
    ).toMatchObject({ ok: false });
  });
  it("keeps an unknown dispatched write unresolved and refuses ordinary retry", () => {
    const { start, row, read, demo, model, base, fixture, send } = setup();
    start();
    row().progress.pending_action = "stop_old";
    row().operation.status = "unknown";
    row().operation.attempt_count = 2;
    expect(read().replacement?.allowed_actions).toEqual(["resolve_write"]);
    expect(
      demo.respond(
        `${base}/operations/${row().operation.id}/retry`,
        {
          method: "POST",
          body: JSON.stringify({
            user_id: 910002,
            expected_revision: fixture.detail.service.revision,
            idempotency_key: "no-retry",
          }),
        },
        model
      )
    ).toMatchObject({ ok: false, error: "exit_replacement_write_unknown" });
    expect(
      send(
        replacementWrite(read(), 910002, "resolve_write", {
          ...fixture.fields,
          result: "not_applied",
        })
      )
    ).toMatchObject({ accepted: true });
    expect(read().replacement?.operation.status).toBe("failed");
    const operation = row().operation.id;
    send(replacementWrite(read(), 910002, "retry", fixture.fields));
    expect(row().operation.id).toBe(operation);
    expect(row().operation.attempt_count).toBe(2);
  });
  it("does not release a failed candidate at cleanup request or closing evidence", () => {
    const { start, fixture, row, submit, read } = setup();
    start();
    expect(read().replacement?.allowed_actions).not.toContain("candidate_cleanup");
    fixture.detail.service.desired_status = "paused";
    submit("candidate_cleanup", fixture.candidate.id);
    expect(row().progress.stage).toBe("closing");
    expect(fixture.candidate.hold_order_id).toBe(row().operation.order_id);
    submit("close_evidence");
    expect(row().progress.stage).toBe("closed");
    expect(fixture.candidate.hold_order_id).toBe(row().operation.order_id);
    expect(read().replacement?.allowed_actions).toEqual(["reclaim"]);
    submit("reclaim", fixture.candidate.id);
    expect(fixture.candidate.hold_order_id).toBeNull();
    expect(fixture.old.service_id).toBe(fixture.detail.service.id);
  });
  it("reclaims old hold only explicitly after a fixture supplies a completed binding", () => {
    const { start, row, fixture, submit, read } = setup();
    start();
    const operation = row().operation.order_id;
    fixture.old.service_id = null;
    fixture.old.hold_order_id = operation;
    fixture.candidate.hold_order_id = null;
    fixture.candidate.service_id = fixture.detail.service.id;
    fixture.detail.service.replacement_order_id = null;
    row().progress.stage = "completed";
    row().progress.binding_audit_id = "8".repeat(32);
    row().progress.restore_result = "restricted";
    row().progress.restore_block_reasons = ["service_paused"];
    expect(read().replacement).toMatchObject({
      switch_result: "confirmed",
      old_resource_state: "held",
      progress: { restore_result: "restricted" },
    });
    submit("reclaim", fixture.old.id);
    expect(read().replacement?.old_resource_state).toBe("released");
    expect(fixture.candidate.service_id).toBe(fixture.detail.service.id);
    expect(row().progress.restore_result).toBe("restricted");
  });
  it("keeps archived services read only", () => {
    const { fixture, read, send } = setup();
    const write = startReplacementWrite(read(true), 910002, "Recorded failure");
    fixture.detail.service.user_id = null;
    expect(read(true).draft?.allowed_to_start).toBe(false);
    expect(send(write)).toMatchObject({ ok: false, error: "service_not_editable" });
  });
});
