import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import en from "../../../../../locales/en.json";
import ru from "../../../../../locales/ru.json";
import zh from "../../../../../locales/zh-hans.json";
import { operationFixture } from "$lib/admin/consoleServiceOperationsFixtures";
import { consoleNodeServiceFixture } from "$lib/admin/consoleNodesFixtures";
import type { GlobalOperation } from "$lib/admin/consoleGlobalOperations";
import { resolveLocaleKey } from "$lib/webapp/constants";
import GlobalOperationTable from "./GlobalOperationTable.svelte";
import ConsoleOperationsSection from "../ConsoleOperationsSection.svelte";
import type { ApiClient } from "$lib/webapp/publicApi";
import { vi } from "vitest";

const operation: GlobalOperation = {
  ...operationFixture,
  record_type: "execution",
  needs_attention: true,
  service_revision: 3,
  service_name: "Test service",
  archived: false,
  customer: consoleNodeServiceFixture.customer,
  last_success_at: "2026-10-23T01:00:00Z",
};
const renderRows = (rows: GlobalOperation[], at = (key: string) => key) =>
  render(GlobalOperationTable, {
    props: { at, operations: rows, onOpenService: () => {}, onOpenUserCard: () => {} },
  }).body;

describe("global operation evidence and existing shared entity components", () => {
  it("renders both record types with the same ID and never offers a direct retry", () => {
    const html = renderRows([
      operation,
      {
        ...operation,
        record_type: "order",
        needs_attention: false,
        status: "unknown",
        phase: null,
      },
    ]);
    expect(html).toContain(`data-operation-key="execution:${operation.id}"`);
    expect(html).toContain(`data-operation-key="order:${operation.id}"`);
    expect(html).toContain("console_ops_history_unknown");
    expect(html).toContain("console_global_phase_success");
    expect(html).toContain("admin-entity-link");
    expect(html).not.toContain("console_ops_retry");
  });
  it("shows execution unknown as unconfirmed, never as failed, and hides unsafe codes", () => {
    const html = renderRows([
      {
        ...operation,
        status: "unknown",
        error_code: "https://private-token.invalid",
        kind: "private-kind",
        retry_block_reason: "private-retry",
      },
    ]);
    expect(html).toContain("console_ops_status_unknown");
    expect(html).toContain("console_ops_unclassified_error");
    expect(html).not.toContain("console_ops_status_failed");
    expect(html).not.toContain("private-");
  });
  it("has no customer link for archives even if a malformed response retains old identity", () => {
    const html = renderRows([
      {
        ...operation,
        archived: true,
        customer: { ...operation.customer, first_name: "StaleIdentity" },
      },
    ]);
    expect(html).toContain("services_history_title");
    expect(html).not.toContain("StaleIdentity");
    expect([...html.matchAll(/<button\b/g)]).toHaveLength(1);
  });
  it.each([en, ru, zh])("renders all new labels using the integrated locale", (locale) => {
    const dictionary: Record<string, string> = locale;
    const at = (key: string) => {
      const value = dictionary[resolveLocaleKey(`admin_${key}`)];
      expect(value, key).toBeTruthy();
      return value;
    };
    const html = renderRows(
      [operation, { ...operation, record_type: "order", status: "unknown", id: "d".repeat(32) }],
      at
    );
    expect(html).toContain(dictionary.admin_console_global_phase_success);
    expect(html).not.toContain("console_global_");
    const section = render(ConsoleOperationsSection, {
      props: { at, api: vi.fn() as ApiClient["api"], onOpenUserCard: () => {} },
    }).body;
    expect(section).toContain('aria-busy="true"');
    expect(section).toContain(at("console_global_customer_id"));
    expect(section).toContain(at("console_global_service_id"));
    expect(section).toContain(at("console_global_attention"));
    expect(section).not.toContain("admin-pagination-summary");
    for (const [key, value] of Object.entries(dictionary)) {
      if (key.startsWith("admin_console_global_")) expect(value, key).toBeTruthy();
    }
  });
});
