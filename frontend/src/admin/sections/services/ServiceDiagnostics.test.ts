import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import {
  diagnosticsFixture,
  operationFixture,
  operationsFixture,
} from "$lib/admin/consoleServiceOperationsFixtures";
import ServiceDiagnostics from "./ServiceDiagnostics.svelte";
import ServiceOperationList from "./ServiceOperationList.svelte";

const at = (key: string) => key;
const noop = () => {};
const retryButtons = (html: string) =>
  [...html.matchAll(/<button\b[^>]*>[\s\S]*?<\/button>/g)].filter(([button]) =>
    button.includes("console_ops_retry")
  );
describe("diagnostics never normalizes unknown observations", () => {
  it("renders goals, unknown remote times, and the unverified data-plane boundary", () => {
    const html = render(ServiceDiagnostics, { props: { at, data: diagnosticsFixture } }).body;
    for (const key of [
      "console_ops_target_access",
      "console_ops_access_disabled",
      "console_ops_remote_unavailable",
      "console_unknown",
      "console_ops_remote_scope",
      "console_ops_data_plane_unverified",
    ])
      expect(html).toContain(key);
    expect(html).not.toContain("0 B");
  });
  it("does not render raw errors, unknown next steps or unknown status fields", () => {
    const html = render(ServiceDiagnostics, {
      props: {
        at,
        data: {
          ...diagnosticsFixture,
          status: "private-url",
          errors: { unknown: "secret-token" },
          remote: { ...diagnosticsFixture.remote, error: "remote-token" },
          next_steps: ["unsafe-command"],
        },
      },
    }).body;
    for (const token of ["private-url", "secret-token", "remote-token", "unsafe-command"])
      expect(html).not.toContain(token);
    expect(html).toContain("console_ops_unclassified_error");
    expect(html).toContain("console_ops_next_unknown");
  });
});
describe("operations preserve status, server totals and retry boundaries", () => {
  const view = (readonly = false) =>
    render(ServiceOperationList, {
      props: {
        at,
        data: {
          ...operationsFixture,
          total: 51,
          operations: [
            operationFixture,
            {
              ...operationFixture,
              id: "legacy",
              status: "unknown",
              retryable: false,
              attempt_count: null,
              attempted_at: null,
              first_failed_at: null,
              completed_at: null,
              retry_block_reason: "historical_result_unknown",
            },
          ],
        },
        pending: {},
        readonly,
        disabled: false,
        onretry: noop,
        onpage: noop,
      },
    }).body;
  it("uses total 51 rather than two visible rows and preserves unknown historical times", () => {
    const html = view();
    expect(html).toContain("51");
    expect(html).toContain("console_ops_status_failed");
    expect(html).toContain("console_ops_status_unknown");
    expect(html).toContain("console_ops_history_unknown");
    expect(html).toContain("console_unknown");
    expect(retryButtons(html)).toHaveLength(1);
  });
  it("never offers business retries for archived/readonly consumers", () => {
    expect(retryButtons(view(true))).toHaveLength(0);
  });
  it.each(["pending", "unknown", "failed", "succeeded", "superseded"] as const)(
    "renders a distinct %s result",
    (status) => {
      const html = render(ServiceOperationList, {
        props: {
          at,
          data: {
            ...operationsFixture,
            operations: [{ ...operationFixture, status, retryable: false }],
          },
          pending: {},
          readonly: false,
          disabled: false,
          onretry: noop,
          onpage: noop,
        },
      }).body;
      expect(html).toContain(`console_ops_status_${status}`);
      expect(retryButtons(html)).toHaveLength(0);
    }
  );
});
