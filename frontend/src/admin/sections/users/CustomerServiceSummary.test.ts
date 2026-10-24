import { readFileSync } from "node:fs";
import { render } from "svelte/server";
import type { ComponentProps } from "svelte";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { components } from "$lib/api/openapi.generated";
import { createUsersStore } from "$lib/admin/stores/usersStore";
import CustomerServiceSummary from "./CustomerServiceSummary.svelte";
import UsersView from "./UsersView.svelte";

const model = vi.hoisted(() => ({ independent: true }));
vi.mock("$lib/admin/context", () => ({ getAdminServiceModel: () => model }));
const at = (key: string, params?: Record<string, unknown>) =>
  key + (params ? JSON.stringify(params) : "");
const summary: components["schemas"]["ConsoleCustomerServicesOut"] = {
  total: 7,
  by_status: {
    active: 1,
    pending: 1,
    paused: 1,
    cancelled: 1,
    expired: 1,
    exhausted: 1,
    account_banned: 1,
  },
  sync_error: 2,
  sync_pending: 2,
  cycle_pending: 1,
  sync_unobserved: 3,
  usage_unobserved: 4,
  oldest_sync_confirmed_at: "2026-10-22T01:00:00Z",
  latest_sync_confirmed_at: "2026-10-24T01:00:00Z",
  oldest_usage_sync_at: null,
  latest_usage_sync_at: null,
  observed_at: "2026-10-24T02:00:00Z",
  activity: "not_collected",
  source: "local_independent_service_records",
  scope: "current_owner_excludes_archived",
};
const renderSummary = (value: typeof summary | null = summary) =>
  render(CustomerServiceSummary, { props: { at, summary: value } }).body;
const noop = () => {};
function viewProps(): ComponentProps<typeof UsersView> {
  return {
    at,
    usersStore: { updateState: noop, loadUsers: noop, openUser: noop },
    onOpenUserCard: noop,
    usersTable: { rows: [{ user_id: 42, is_banned: true, independent_services: summary }] },
    usersFilterSheetOpen: false,
    usersFilter: "all",
    usersPanelStatus: "all",
    usersPremiumTraffic: "all",
    usersQuery: "",
    usersTotal: 1,
    usersPage: 0,
    usersPageCount: 1,
    usersLoading: false,
    USERS_PAGE_SIZE: 25,
    USERS_FILTER_OPTIONS: [],
    USERS_PANEL_STATUS_OPTIONS: [],
    USERS_PREMIUM_TRAFFIC_OPTIONS: [],
    activeUsersFilterCount: 0,
    activeUserFilterChips: [],
    userTableHeaders: ["user", "independent_services", "account", "registration"],
    userTableWidths: ["24%", "46%", "15%", "15%"],
    userTableColumnCount: 4,
    userBalanceEnabled: true,
    partnerBalanceEnabled: true,
    updateUsersFilter: noop,
    updateUsersPanelStatus: noop,
    updateUsersPremiumTraffic: noop,
    updateToolbarUsersFilter: noop,
    updateToolbarPanelStatus: noop,
    updateToolbarPremiumTraffic: noop,
    resetUsersFilters: noop,
    clearUsersFilter: noop,
    handleUsersSearchInput: noop,
    handleUsersSearchKeydown: noop,
    userTableColumns: () =>
      ["user", "independent_services", "account", "registration"].map((key) => ({
        key,
        label: key,
      })),
    sortState: () => "none",
    sortTitle: () => "",
    toggleUsersSortForColumn: noop,
    resolvedAvatarUrl: () => "",
    panelStatusBadge: () => ({ label: "account banned", variant: "danger" }),
    userInitials: () => "AB",
    userDisplayName: () => "Customer",
    userSecondaryName: () => "",
    premiumTrafficBadgeVariant: () => "muted",
    premiumTrafficBadgeText: () => "",
    rowPaymentsTotal: () => "0",
    rowBalance: () => "0",
    fmtDateShort: () => "2020-01-01",
  };
}

describe("customer service summary", () => {
  beforeEach(() => {
    model.independent = true;
  });
  it("keeps all nonzero business states and failures visible, with counts and times collapsed", () => {
    const html = renderSummary();
    const collapsed = html.slice(0, html.indexOf("<details"));
    for (const state of Object.keys(summary.by_status))
      expect(collapsed).toContain(`data-service-state="${state}"`);
    expect(collapsed).toContain('data-service-alert="sync_error"');
    expect(collapsed).toContain('data-service-alert="pending"');
    expect(collapsed).toContain('data-service-alert="unobserved"');
    expect(collapsed).not.toContain("2026-10-");
    expect(html).not.toMatch(/<details[^>]*\bopen\b/);
    expect(html).toMatch(/<details[^>]*tabindex="-1"/);
    expect(html).toContain('data-service-health="sync_error"');
    expect(html).toContain("2026-10-22 09:00");
    expect(html).toContain("2026-10-24 09:00");
    expect(html).toContain("console_customers_no_observation");
    expect(html).toContain("console_customers_activity_uncollected");
    expect(html).not.toContain("total_anomal");
  });
  it("distinguishes unknown from zero and never infers an observation", () => {
    const unknown = renderSummary(null);
    expect(unknown).toContain("data-customer-summary-unknown");
    expect(unknown).not.toContain("data-customer-service-total");
    const zero = renderSummary({
      ...summary,
      total: 0,
      by_status: Object.fromEntries(Object.keys(summary.by_status).map((key) => [key, 0])),
      sync_error: 0,
      sync_pending: 0,
      cycle_pending: 0,
      sync_unobserved: 0,
      usage_unobserved: 0,
    });
    expect(zero).toContain('data-customer-service-total="0"');
    expect(zero).not.toContain("data-service-state");
    expect(zero).not.toContain("data-service-alert");
    expect(zero).toContain("console_customers_activity_uncollected");
  });
  it("renders the shared summary in actual desktop rows and mobile cards", () => {
    const html = render(UsersView, { props: viewProps() }).body;
    expect(html.match(/data-customer-service-total="7"/g)).toHaveLength(2);
    expect(html).toContain('data-user-id="42"');
    expect(html).toContain('data-mobile-user-id="42"');
    expect(html).toContain("account banned");
    expect(html).toContain("console_customers_scope");
    expect(html).not.toContain("users_col_payments_count");
  });
  it("preserves legacy metrics without showing the independent summary", () => {
    model.independent = false;
    const html = render(UsersView, { props: viewProps() }).body;
    expect(html).not.toContain("data-customer-service-total");
    for (const key of [
      "users_col_user_balance",
      "users_col_partner_balance",
      "users_col_payments_total",
      "users_col_payments_count",
      "users_col_invited",
      "users_col_subscription_expires",
    ])
      expect(html).toContain(key);
  });
  it("passes the generated summary through the existing store in one list request", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      users: [{ user_id: 42, independent_services: summary }],
      total: 1,
    });
    const store = createUsersStore({ api, at, onToast: noop });
    await store.loadUsers();
    expect(store.users[0].independent_services).toEqual(summary);
    expect(api).toHaveBeenCalledTimes(1);
    expect(api.mock.calls[0][0]).toMatch(/^\/admin\/users\?/);
  });
  it.each(["en", "ru", "zh-hans"])(
    "provides every summary label including dynamic fields in %s",
    (language) => {
      const locale: Record<string, string> = JSON.parse(
        readFileSync(new URL(`../../../../../locales/${language}.json`, import.meta.url), "utf8")
      );
      const source = readFileSync(
        new URL("./CustomerServiceSummary.svelte", import.meta.url),
        "utf8"
      );
      const keys = [...source.matchAll(/at\("(console_customers_[^"]+)"/g)].map(
        (match) => match[1]
      );
      keys.push(
        ...[
          "sync_error",
          "sync_pending",
          "cycle_pending",
          "sync_unobserved",
          "usage_unobserved",
          "sync_times",
          "usage_times",
          "scope",
          "account_status",
          "account_not_banned",
          "services",
        ].map((key) => `console_customers_${key}`)
      );
      keys.push(...Object.keys(summary.by_status).map((state) => `services_status_${state}`));
      for (const key of keys) expect(locale[`admin_${key}`], key).toBeTruthy();
    }
  );
});
