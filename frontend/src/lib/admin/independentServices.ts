import type { UsersRouteFilters } from "./usersRouteFilters";
import type { AdminSettingsSection } from "./settingsSections";

export const RETIRED_ADMIN_SECTIONS = new Set(["stats", "tariffs", "promos", "gifts", "partners"]);

export const INDEPENDENT_ACCOUNT_FILTERS = new Set([
  "all",
  "active",
  "banned",
  "active_today",
  "tg_linked",
  "no_tg",
  "email_linked",
  "no_email",
]);

const RETIRED_SETTINGS_SECTIONS = new Set(["pricing", "payments", "trial", "referral", "devices"]);
const RETIRED_SETTING_KEYS = new Set([
  "GIFTS_ENABLED",
  "USER_TRAFFIC_STRATEGY",
  "PANEL_WEBHOOK_SECRET",
  "USER_SQUAD_UUIDS",
  "USER_EXTERNAL_SQUAD_UUID",
]);

export function independentSettingsSections(
  sections: AdminSettingsSection[]
): AdminSettingsSection[] {
  return sections
    .filter((section) => !RETIRED_SETTINGS_SECTIONS.has(section.id))
    .map((section) => ({
      ...section,
      fields: section.fields.filter((field) => !RETIRED_SETTING_KEYS.has(field.key)),
    }))
    .filter((section) => section.fields.length > 0);
}

export function independentAccountFilters(filters: UsersRouteFilters): UsersRouteFilters {
  return {
    usersFilter: INDEPENDENT_ACCOUNT_FILTERS.has(filters.usersFilter) ? filters.usersFilter : "all",
    usersPanelStatus: "all",
    usersPremiumTraffic: "all",
  };
}
