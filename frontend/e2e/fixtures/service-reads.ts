import { readFileSync } from "node:fs";
import type { Page, Route } from "@playwright/test";
import type { components } from "../../src/lib/api/openapi.generated";
import { installAdminShellFixture } from "./admin-shell";
import { DEV_MOCK } from "../../src/lib/webapp/previewMock/devMock";

export const time = "2026-10-24T01:00:00Z";
export const nextTime = "2026-10-25T01:00:00Z";
export const service: components["schemas"]["UserServiceOut"] = {
  id: "a".repeat(32),
  user_id: 42,
  plan_id: "1".repeat(32),
  plan_revision: 1,
  revision: 1,
  desired_status: "active",
  sync_pending: false,
  sync_error: null,
  sync_confirmed_at: time,
  name: "HTTP independent service A",
  description: "",
  resource_type: "shared",
  traffic_rule: "monthly",
  quota_bytes: 100 * 2 ** 30,
  used_bytes: 23 * 2 ** 30,
  starts_at: time,
  expires_at: "2027-01-24T01:00:00Z",
  cycle_started_at: time,
  cycle_ends_at: "2026-11-24T01:00:00Z",
  last_usage_sync_at: time,
  usage_error: null,
  usage_total_bytes: 23 * 2 ** 30,
  cycle_pending: false,
  status: "active",
  connection_state: "ready",
  exit_ip: null,
  exit_verified: false,
  replacement_order_id: null,
};
export const customer: components["schemas"]["ConsoleCustomerOut"] = {
  user_id: 42,
  minishop_id: "ms_shell_customer",
  username: "shell_private_customer",
  email: "shell-private@example.test",
  first_name: "Shell Private Customer",
  last_name: null,
  is_banned: false,
};
const terms: components["schemas"]["ServicePlanTerms"] = {
  name: "Original terms",
  description: "",
  resource_type: "shared",
  traffic_rule: "monthly",
  quota_bytes: service.quota_bytes,
  validity_days: 90,
  price: "29.90",
  currency: "CNY",
  squad_uuids: [],
  resource_pool: null,
};

export type Surface = "user" | "customer" | "global" | "detail";
type Failure = 0 | 401 | 403 | 429 | 503 | "offline";
export const serviceReadEvidence = new WeakMap<Page, { pageErrors: string[] }>();

// Real fetch/session handling; only the HTTP server responses are fixtures.
export async function installServiceReads(page: Page, surface: Surface, language = "en") {
  const shell = await installAdminShellFixture(page, language);
  shell.state.admin = surface !== "user";
  const copy: Record<string, string> = JSON.parse(
    readFileSync(`../locales/${language}.json`, "utf8")
  );
  await page.addInitScript(
    (language) => localStorage.setItem("rw_minishop_demo_language", language),
    language
  );
  await page.clock.setFixedTime(new Date("2026-10-25T02:00:00Z"));
  const state = {
    failure: 0 as Failure,
    detailFailure: 0 as Failure,
    reads: 0,
    detailReads: 0,
    services: [structuredClone(service)],
    total: 1,
    observedAt: time,
    requests: [] as string[],
    writes: [] as string[],
    released: 0,
    responses: [] as {
      request: string;
      failure: Failure;
      services: { id: string; used_bytes: number; last_usage_sync_at: string | null }[];
      total: number;
      observedAt: string;
      accountId: number;
    }[],
    pageErrors: [] as string[],
    shell: shell.state,
    accountId: 42,
    authenticated: true,
    authRequests: [] as string[],
    subscriptionReads: 0,
    profileReads: [] as { accountId: number; admin: boolean; fresh: boolean }[],
  };
  serviceReadEvidence.set(page, state);
  page.on("pageerror", (error) => state.pageErrors.push(error.message));
  let pending: Promise<void> | null = null;
  let release = () => {};
  async function respond(route: Route, failure: Failure, json: unknown) {
    if (failure === "offline") return route.abort("failed");
    return route.fulfill({
      status: failure || 200,
      json: failure
        ? {
            ok: false,
            error:
              failure === 403
                ? "forbidden"
                : failure === 401
                  ? "unauthorized"
                  : "fixture_unavailable",
          }
        : json,
      headers: { "Cache-Control": "no-store" },
    });
  }
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (!/^(GET|HEAD)$/.test(request.method()) && !path.startsWith("/api/auth/"))
      state.writes.push(`${request.method()} ${path}`);
    if (path === "/api/me") {
      if (url.searchParams.has("fresh")) shell.state.roleChecks++;
      state.profileReads.push({
        accountId: state.accountId,
        admin: shell.state.admin,
        fresh: url.searchParams.has("fresh"),
      });
      const profile = structuredClone(DEV_MOCK.data);
      return route.fulfill({
        json: {
          ...profile,
          user: {
            ...profile.user,
            id: state.accountId,
            email: `account-${state.accountId}@example.test`,
            is_admin: shell.state.admin,
            language_code: language,
          },
        },
      });
    }
    if (path === "/api/auth/logout") {
      state.authenticated = false;
      shell.state.logoutCalls++;
      state.authRequests.push(path);
      return route.fulfill({ json: { ok: true } });
    }
    if (path === "/api/auth/session")
      return route.fulfill({
        json: {
          ok: true,
          authenticated: state.authenticated,
          csrf_token: `account-${state.accountId}-session`,
        },
      });
    if (path === "/api/auth/email/request") {
      state.authRequests.push(path);
      return route.fulfill({ json: { ok: true } });
    }
    if (path === "/api/auth/email/verify") {
      state.authRequests.push(path);
      state.authenticated = true;
      return route.fulfill({
        json: { ok: true, csrf_token: `account-${state.accountId}-session` },
      });
    }
    if (/^\/api\/services\/[a-f0-9]{32}\/subscription$/.test(path)) {
      state.subscriptionReads++;
      return route.fulfill({
        json: {
          ok: true,
          subscription: {
            service_id: service.id,
            subscription_url: "https://subscription.example.test/private-service-a",
          },
        },
      });
    }
    if (path === "/api/admin/users/42" || path === "/api/admin/users/43") {
      const id = path.endsWith("43") ? 43 : 42;
      return route.fulfill({
        json: {
          ok: true,
          user: { ...customer, user_id: id },
          active_subscription: null,
          subscriptions: [],
          balance: {
            ok: true,
            enabled: false,
            amount: "0",
            amount_minor: 0,
            currency: "USD",
            currency_scale: 2,
            sources: [],
            topup_min_amount: 0,
            topup_max_amount: 0,
            topup_presets: [],
          },
          hwid_devices: { current_devices: null, max_devices: null },
          log_count: 0,
          notification_preferences: {
            marketing_email: false,
            marketing_telegram: false,
            system_email: false,
            system_telegram: false,
          },
          recent_payments: [],
          referral: { invitees_total: 0 },
          telegram_notifications: { status: "unknown" },
          trial: { active: false, used: false, count: 0 },
          total_paid: 0,
          vpn_connection_status: "unknown",
        },
      });
    }
    const list = [
      "/api/services",
      "/api/service-catalog",
      "/api/admin/services",
      "/api/admin/console/services",
    ].includes(path);
    const detail = /^\/api\/(?:admin\/console\/)?services\/[a-f0-9]{32}$/.test(path);
    if (list || detail) {
      state.requests.push(`${request.method()} ${path}${url.search}`);
      const failure = detail ? state.detailFailure : state.failure;
      const snapshot = structuredClone(state.services);
      const total = state.total;
      const observed_at = state.observedAt;
      const accountId = state.accountId;
      if (detail) state.detailReads++;
      else state.reads++;
      const waiting = pending;
      pending = null;
      if (waiting) await waiting;
      try {
        state.responses.push({
          request: `${request.method()} ${path}${url.search}`,
          failure,
          services: snapshot.map(({ id, used_bytes, last_usage_sync_at }) => ({
            id,
            used_bytes,
            last_usage_sync_at,
          })),
          total,
          observedAt: observed_at,
          accountId,
        });
        if (detail)
          return await respond(route, failure, {
            ok: true,
            service: snapshot[0],
            customer,
            connection: null,
            terms,
          });
        return await respond(route, failure, {
          ok: true,
          services:
            path === "/api/admin/console/services"
              ? snapshot.map((service) => ({ service, customer }))
              : snapshot,
          plans: [],
          total,
          page: Number(url.searchParams.get("page") || 0),
          page_size: 25,
          observed_at,
          expiring_within_days: 7,
        });
      } finally {
        if (waiting) state.released++;
      }
    }
    if (path.endsWith("/resources")) {
      const resources: components["schemas"]["ConsoleServiceResourcesOut"] = {
        service_id: service.id,
        status: "active",
        connection_state: "ready",
        currently_eligible: true,
        configured_group_ids: [],
        groups: [],
        hosts: [],
        nodes: [],
        coverage: "complete",
        sources: [],
        local_observed_at: time,
        association_basis: "persisted_service_scope_not_live_connections",
        remote_authorization_verified: false,
      };
      return route.fulfill({ json: { ok: true, ...resources } });
    }
    return route.fallback();
  });
  const root = () =>
    surface === "user"
      ? page.locator(".services-screen")
      : surface === "customer"
        ? page.locator(".user-services")
        : surface === "detail"
          ? page.locator(".console-service-detail")
          : page.locator(".console-services");
  const label = (key: string) =>
    surface === "user" ? copy[`wa_services_${key}`] : shell.label(key);
  return {
    ...shell,
    shellState: shell.state,
    state,
    copy,
    root,
    label,
    async goto() {
      if (surface === "user") {
        await page.goto("/demo/runtime/settings?mock=services&theme_preview=dark");
        await page
          .locator("nav")
          .getByRole("button", { name: copy.wa_services_nav, exact: true })
          .click();
      } else {
        const section = surface === "customer" ? "users/42" : "services";
        await page.goto(
          `/demo/runtime/admin/${section}?mock=services&theme_preview=dark${surface === "detail" ? `&service_id=${service.id}` : ""}`
        );
      }
    },
    refresh: () =>
      root()
        .getByRole("button", { name: label("refresh"), exact: true })
        .first()
        .click(),
    holdNext() {
      pending = new Promise<void>((resolve) => {
        release = resolve;
      });
    },
    release() {
      release();
    },
  };
}
