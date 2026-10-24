import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import ru from "../../../../../locales/ru.json";
import { accountOperationFixture } from "$lib/admin/consoleAccountOperationsFixtures";
import AccountOperationTable from "./AccountOperationTable.svelte";
import AccountOperationDetail from "./AccountOperationDetail.svelte";
import AccountOperationList from "./AccountOperationList.svelte";
import ConsoleOperationsSection from "../ConsoleOperationsSection.svelte";

const at = (key: string) => key;
const onOpenUserCard = () => {
  throw new Error("SSR must not navigate");
};
const api = async () => {
  throw new Error("SSR must not request audit records");
};

describe("account audit browser consumers", () => {
  it("uses full-label wrapping for the selected Russian unknown status", () => {
    vi.stubGlobal("window", { location: { search: "?account_status=unknown" } });
    try {
      const locale: Record<string, string> = ru;
      const html = render(AccountOperationList, {
        props: { api, at: (key: string) => locale[`admin_${key}`] || key, onOpenUserCard },
      }).body;
      expect(html).toContain("admin-select-trigger admin-select-wrap");
      expect(html).toContain(ru.admin_console_ops_status_unknown);
    } finally {
      vi.unstubAllGlobals();
    }
  });
  it("renders the real table with distinct actor/target, intended change and execution evidence", () => {
    const operation = accountOperationFixture({
      target_id: -42,
      user_id: 910002,
      actor_id: -7,
      attempt_count: 0,
    });
    const html = render(AccountOperationTable, {
      props: { operations: [operation], at, onOpenUserCard, onOpenOperation: () => {} },
    }).body;
    for (const value of [
      operation.id,
      "-42",
      "-7",
      "910002",
      "account_ops_unbanned",
      "account_ops_banned",
      "console_ops_status_unknown",
      "console_ops_attempt_count",
      "account_ops_error_access",
      "account_ops_review_customer",
      "console_ops_first_failed_at",
    ])
      expect(html).toContain(value);
    expect(html).toMatch(/console_ops_attempt_count[^<]*: 0/);
    expect(html).not.toContain("console_ops_status_succeeded");
  });
  it.each([
    { archived: true, user_id: 910002 },
    { archived: false, user_id: null },
  ])("never offers live navigation for archived or detached history %j", (state) => {
    const html = render(AccountOperationTable, {
      props: {
        operations: [accountOperationFixture({ ...state, before_banned: null, actor_id: null })],
        at,
        onOpenUserCard,
      },
    }).body;
    expect(html).toContain("services_history_title");
    expect(html).toContain("console_unknown");
    expect(html).not.toContain("account_ops_review_customer");
    expect(html).not.toContain("account_ops_current_customer");
    expect(html).not.toContain("<button");
  });
  it("never renders unknown raw errors or adds a new retry command", () => {
    const html = render(AccountOperationTable, {
      props: {
        operations: [
          accountOperationFixture({ error_code: "private-token", needs_attention: false }),
        ],
        at,
        onOpenUserCard,
      },
    }).body;
    expect(html).toContain("account_ops_error_unconfirmed");
    expect(html).not.toContain("private-token");
    expect(html).not.toContain("account_access_retry");
    expect(html).not.toContain("account_ops_review_customer");
  });
  it("renders the shared list and defers the portal dialog without SSR requests", () => {
    const list = render(AccountOperationList, { props: { api, at, onOpenUserCard } }).body;
    expect(list).toContain("account-operations-list");
    expect(list).toContain("admin-list-toolbar");
    expect(list).toContain("account_ops_source");
    expect(list).toContain("console_global_archived");
    expect(list).toContain("console_global_attention");
    const detail = render(AccountOperationDetail, {
      props: { api, at, operationId: "a".repeat(32), onOpenUserCard, onclose: () => {} },
    }).body;
    // Portal content mounts in the browser; browser regressions cover its controls and return path.
    expect(detail).not.toContain("account-operation-detail");
    expect(detail).not.toContain("a".repeat(32));
    const shell = render(ConsoleOperationsSection, { props: { api, at, onOpenUserCard } }).body;
    expect(shell).toContain("resource_ops_view");
  });
});
