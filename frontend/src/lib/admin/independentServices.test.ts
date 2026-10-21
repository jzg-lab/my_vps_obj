import { describe, expect, it } from "vitest";
import { independentAccountFilters, independentSettingsSections } from "./independentServices";
import { DEFAULT_USERS_ROUTE_FILTERS, type UsersFilter } from "./usersRouteFilters";
import type { AdminSettingsSection } from "./settingsSections";

describe("independent admin policy", () => {
  it.each<UsersFilter>(["trial", "paid", "free", "active_subscription", "panel_linked"])(
    "clears stale %s subscription filters from bookmarked user lists",
    (usersFilter) => {
      expect(
        independentAccountFilters({
          usersFilter,
          usersPanelStatus: "limited",
          usersPremiumTraffic: "critical",
        })
      ).toEqual(DEFAULT_USERS_ROUTE_FILTERS);
    }
  );

  it("keeps account and identity filters", () => {
    expect(
      independentAccountFilters({ ...DEFAULT_USERS_ROUTE_FILTERS, usersFilter: "banned" })
    ).toEqual({ ...DEFAULT_USERS_ROUTE_FILTERS, usersFilter: "banned" });
    expect(
      independentAccountFilters({ ...DEFAULT_USERS_ROUTE_FILTERS, usersFilter: "email_linked" })
    ).toEqual({ ...DEFAULT_USERS_ROUTE_FILTERS, usersFilter: "email_linked" });
  });

  it("removes competing pricing and account quota settings without removing panel access or login", () => {
    const section = (id: string, keys: string[]): AdminSettingsSection => ({
      id,
      fields: keys.map((key) => ({ key, label: key })),
    });
    const sections = [
      section("general", ["WEBAPP_TITLE", "GIFTS_ENABLED", "USER_TRAFFIC_STRATEGY"]),
      section("remnawave", [
        "PANEL_API_URL",
        "PANEL_API_KEY",
        "PANEL_WEBHOOK_SECRET",
        "USER_SQUAD_UUIDS",
        "USER_EXTERNAL_SQUAD_UUID",
      ]),
      section("payments", ["YOOKASSA_ENABLED"]),
      section("devices", ["USER_TRAFFIC_LIMIT_GB"]),
      section("trial", ["TRIAL_DAYS"]),
      section("pricing", ["MONTH_PRICE_1"]),
      section("referral", ["REFERRAL_DAYS"]),
      section("login_methods", ["AUTH_EMAIL_ENABLED"]),
      section("support", ["SUPPORT_ENABLED"]),
      section("backups", ["BACKUP_ENABLED"]),
    ];
    expect(independentSettingsSections(sections)).toEqual([
      section("general", ["WEBAPP_TITLE"]),
      section("remnawave", ["PANEL_API_URL", "PANEL_API_KEY"]),
      ...sections.slice(7),
    ]);
    expect(sections[0].fields).toHaveLength(3);
  });
});
