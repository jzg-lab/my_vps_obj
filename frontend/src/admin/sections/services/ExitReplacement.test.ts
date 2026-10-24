import { readFileSync } from "node:fs";
import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import { replacementFixture } from "$lib/admin/exitReplacementFixtures";
import { replacementLabels } from "$lib/admin/exitReplacement";
import { exitAuditActionKeys } from "../dedicated-exits/auditAction";
import { consoleServiceErrorKey } from "$lib/admin/consoleServiceOperations";
import { resolveLocaleKey } from "$lib/webapp/constants";
import ExitReplacementStatus from "./ExitReplacementStatus.svelte";
import ExitReplacementForm from "./ExitReplacementForm.svelte";
const at = (key: string) => key;

describe("replacement separates declarations, binding, restoration and holds", () => {
  it("shows restricted restoration separately from confirmed binding and old hold", () => {
    const { state } = replacementFixture();
    Object.assign(state.replacement!, {
      switch_result: "confirmed",
      old_resource_state: "held",
      restore_requested: true,
    });
    Object.assign(state.replacement!.progress, {
      stage: "completed",
      restore_result: "restricted",
      restore_block_reasons: ["service_paused"],
    });
    const html = render(ExitReplacementStatus, { props: { data: state, at } }).body;
    for (const key of [
      "replacement_switch_confirmed",
      "replacement_restore_restricted",
      "replacement_old_held",
      "services_status_paused",
      "replacement_administrator_evidence",
      "console_resource_reload",
    ])
      expect(html).toContain(key);
    expect(html).not.toContain("replacement_restore_enabled");
  });
  it("does not expose unknown codes, request fingerprints, evidence digests or raw errors", () => {
    const { state } = replacementFixture();
    Object.assign(state.replacement!.progress, {
      stage: "private-stage",
      restore_result: "private-restore",
      restore_block_reasons: ["private-block"],
    });
    state.replacement!.operation.error_code = "private-server-secret";
    state.replacement!.block_reasons = ["private-blocker"];
    Object.assign(state.replacement!.sources[0], { availability: "private-availability" });
    const html = render(ExitReplacementStatus, { props: { data: state, at } }).body;
    expect(html).toContain("console_unknown");
    expect(html).toContain("console_ops_unclassified_error");
    expect(html).not.toContain("private-");
    expect(html).not.toContain(state.replacement!.requested_resource_fingerprint);
  });
  it.each([
    "stop_evidence",
    "verify",
    "confirm",
    "resolve_write",
    "reclaim",
    "close_evidence",
  ] as const)("starts %s with no invented evidence or enabled submit", (action) => {
    const { state } = replacementFixture();
    state.replacement!.allowed_actions.push(action);
    const html = render(ExitReplacementForm, {
      props: { at, data: state, action, userId: 910002, disabled: false, onsubmit: vi.fn() },
    }).body;
    expect(html).toMatch(
      /<button\b[^>]*type="submit"[^>]*disabled|<button\b[^>]*disabled[^>]*type="submit"/
    );
    expect(html).not.toMatch(/value="(?:73|23|50)"/);
  });
  it.each(["en", "ru", "zh-hans"])("provides replacement and audit labels in %s", (language) => {
    const locale: Record<string, string> = JSON.parse(
      readFileSync(new URL(`../../../../../locales/${language}.json`, import.meta.url), "utf8")
    );
    const files = [
      "ServiceExitReplacementDialog.svelte",
      "ExitReplacementStatus.svelte",
      "ExitReplacementImpact.svelte",
      "ExitReplacementForm.svelte",
    ];
    const direct = files.flatMap((name) =>
      [...readFileSync(new URL(name, import.meta.url), "utf8").matchAll(/at\("([^"]+)"/g)].map(
        (match) => match[1]
      )
    );
    for (const key of new Set([
      ...direct,
      ...Object.values(replacementLabels).flatMap(Object.values),
      ...exitAuditActionKeys,
    ]))
      expect(locale[resolveLocaleKey(`admin_${key}`)], key).toBeTruthy();
  });
  it("preserves both SHA-256 quantifiers in native input validation", () => {
    const { state } = replacementFixture();
    const html = render(ExitReplacementForm, {
      props: {
        at,
        data: state,
        action: "stop_evidence",
        userId: 910002,
        disabled: false,
        onsubmit: vi.fn(),
      },
    }).body;
    expect(html.match(/pattern="\[0-9a-f\]\{64\}"/g)).toHaveLength(2);
  });
  it.each([
    "exit_replacement_scope_changed",
    "exit_replacement_version_changed",
    "exit_replacement_stage_changed",
  ])("maps %s to fresh review, not automatic retry", (code) => {
    expect(consoleServiceErrorKey(code)).toBe("replacement_changed");
  });
});
