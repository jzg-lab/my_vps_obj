import { readFileSync } from "node:fs";
import { render } from "svelte/server";
import type { ComponentProps } from "svelte";
import { afterEach, describe, expect, it, vi } from "vitest";
import AdminPanelLayout from "./AdminPanelLayout.svelte";
import { ADMIN_SECTIONS } from "./sections/registry";

vi.mock("$lib/admin/context", () => ({
  getUsersStore: () => ({ openedUser: null }),
  getPaymentsStore: () => ({ openedPaymentId: null }),
  getTariffsStore: () => ({ tariffEditorOpen: false, tariffDeleteOpen: false }),
  getHealthStore: () => ({ alerts: [], healthLoading: false }),
}));

const noop = () => {};
const text = () => "";
function layoutProps(language: string, active: string): ComponentProps<typeof AdminPanelLayout> {
  const locale: Record<string, string> = JSON.parse(
    readFileSync(new URL(`../../../locales/${language}.json`, import.meta.url), "utf8")
  );
  const at = (key: string, params: Record<string, unknown> = {}, fallback = key) =>
    (locale[`admin_${key}`] || fallback).replace(/\{(\w+)\}/g, (match, key: string) =>
      params[key] === undefined ? match : String(params[key])
    );
  const users = ADMIN_SECTIONS.find((section) => section.id === "users")!;
  const nodes = ADMIN_SECTIONS.find((section) => section.id === "nodes")!;
  return {
    api: vi.fn().mockResolvedValue({ ok: true }),
    active,
    activeSectionComponent: null,
    activeSectionLoading: false,
    availableFeatures: [],
    adsStore: { setCreateOpen: noop },
    appFaviconUrl: "",
    appFaviconUseCustom: false,
    appRepositoryUrl: "",
    appVersion: "test",
    at,
    brand: {},
    brandTitle: "Test",
    currentLang: language,
    documentsStore: { openCreateDocument: noop },
    dirtyCount: 0,
    fmtDate: text,
    fmtDateShort: text,
    fmtMoney: text,
    featureAvailable: true,
    featuresResolved: true,
    initialTicketId: null,
    languageBusy: false,
    languageOptions: [],
    logsStore: {},
    meta: { title: active, subtitle: "" },
    NAV_GROUPS: [
      { id: "customers", order: 1, label: "Customers", items: [{ ...users, label: "Users" }] },
      { id: "nodes", order: 2, label: "Nodes", items: [{ ...nodes, label: "Nodes" }] },
      {
        id: "sample-tools",
        order: 3,
        label: "Sample tools",
        items: [{ ...users, id: "sample-report", group: "sample-tools", label: "Sample report" }],
      },
    ],
    onClose: noop,
    onCloseUser: noop,
    onExportPayments: noop,
    onLanguageChange: noop,
    onOpenPaymentUserCard: noop,
    onOpenPaymentPromoCard: noop,
    onOpenPartnerCard: noop,
    onOpenPaymentCard: noop,
    onOpenSettingsPath: noop,
    onOpenUserCard: noop,
    onOpenUsersFilter: noop,
    onUsersFiltersChange: noop,
    onSaveSettings: noop,
    onSaveTranslations: noop,
    onSetActive: noop,
    onSettingsPathChange: noop,
    openTelegramProfileLink: () => false,
    paymentStatusVariant: () => "muted",
    panelStatusBadge: () => ({ label: "", variant: "muted" }),
    promosStore: { setCreateOpen: noop },
    resolvedAvatarUrl: text,
    routePrefix: "/demo/runtime",
    settingsPath: [],
    settingsSaving: false,
    settingsStore: { saveSettings: noop },
    sidebarOpen: false,
    statsStore: { triggerSync: noop },
    supportStore: {},
    syncBusy: false,
    tariffsStore: { openCreateTariff: noop },
    translationsDirtyCount: 0,
    translationsSaving: false,
    translationsStore: { saveTranslations: noop },
    trafficLeftLabel: text,
    trafficOfLabel: text,
    trafficPercentValue: () => 0,
    userDisplayName: text,
    userInitials: text,
    userSecondaryName: text,
    userTelegramProfileLink: text,
    userTelegramProfileLinkKind: text,
    warmSectionComponent: noop,
    t: text,
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("admin navigation disclosures", () => {
  for (const language of ["en", "ru", "zh-hans"]) {
    it.each(["users", "nodes", "sample-report"])(
      `renders expanded core/plugin groups and the current %s page in ${language}`,
      (active) => {
        vi.stubGlobal("window", { location: { search: "" } });
        const props = layoutProps(language, active);
        const html = render(AdminPanelLayout, { props }).body;
        const toggles = [...html.matchAll(/<button\b[^>]*data-admin-nav-group="[^"]+"[^>]*>/g)];
        expect(toggles).toHaveLength(3);
        const controlledIds = toggles.map(([tag]) => {
          expect(tag).toContain('aria-expanded="true"');
          expect(tag).toContain('type="button"');
          const id = tag.match(/aria-controls="([^"]+)"/)?.[1];
          expect(id).toBeTruthy();
          expect(html).toContain(`<nav id="${id}"`);
          return id;
        });
        expect(new Set(controlledIds).size).toBe(3);
        expect(html).not.toMatch(/<nav\b[^>]*\bhidden\b/);
        expect(html).toMatch(new RegExp(`aria-current="page"[^>]*data-admin-section="${active}"`));
        expect(html.match(/aria-current="page"/g)).toHaveLength(1);
        for (const key of ["nav_group_collapse", "nav_group_expand"]) {
          const label = props.at(key, { group: "Nodes" });
          expect(label).not.toBe(key);
          expect(label).not.toBe("Nodes");
          expect(label).not.toContain("{group}");
          expect(label).toContain("Nodes");
        }
      }
    );
  }
});
