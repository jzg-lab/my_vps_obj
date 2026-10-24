import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { Page } from "@playwright/test";
import { DEV_MOCK } from "../../src/lib/webapp/previewMock/devMock";

export async function installAdminShellFixture(page: Page, language = "en") {
  const locale = JSON.parse(
    readFileSync(resolve(__dirname, `../../../locales/${language}.json`), "utf8")
  ) as Record<string, string>;
  const state = { admin: true, denied: false, roleChecks: 0, listReads: 0, logoutCalls: 0 };
  const maintenance: { destination: string | null; reads: number } = {
    destination: null,
    reads: 0,
  };
  let hold: Promise<void> | null = null;
  let release = () => {};
  const profile = () => ({
    ...structuredClone(DEV_MOCK.data),
    user: { ...DEV_MOCK.data.user, id: 7, is_admin: state.admin, language_code: language },
  });
  const config = {
    ...DEV_MOCK.config,
    language,
    serviceModel: "independent",
    telegramLoginBotId: 0,
    telegramOAuthClientId: 0,
    authProviders: ["email"],
    adminJsAsset: "/demo/runtime/subscription_webapp_admin.js",
    adminCssAsset: "/demo/runtime/subscription_webapp_admin.css",
  };
  const safeJson = (value: unknown) => JSON.stringify(value).replaceAll("<", "\\u003c");
  // Disable App's demo transport so the real shared request/session layer handles HTTP 403.
  await page.route(/\/demo\/runtime\/(?:admin|settings)(?:\/|\?|$)/, async (route) => {
    if (route.request().resourceType() !== "document") return route.continue();
    const response = await route.fetch();
    const html = (await response.text())
      .replace(
        "<head>",
        `<head><script id="webapp-config" type="application/json">${safeJson(config)}</script>`
      )
      .replace(
        /<script id="i18n" type="application\/json">[\s\S]*?<\/script>/,
        `<script id="i18n" type="application/json">${safeJson({ [language]: locale })}</script>`
      );
    await route.fulfill({ response, body: html });
  });
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const json = (payload: unknown, status = 200) =>
      route.fulfill({ status, json: payload, headers: { "Cache-Control": "no-store" } });
    if (path === "/api/auth/session")
      return json({ ok: true, authenticated: true, csrf_token: "shell-test-session" });
    if (path === "/api/auth/logout") {
      state.logoutCalls += 1;
      return json({ ok: true });
    }
    if (path === "/api/me") {
      if (url.searchParams.has("fresh")) state.roleChecks += 1;
      return json(profile());
    }
    if (path === "/api/i18n") return json({ ok: true, i18n: { [language]: locale } });
    if (path === "/api/admin/users") {
      state.listReads += 1;
      const oldRequest = hold;
      hold = null;
      if (oldRequest) await oldRequest;
      else if (state.denied || !state.admin) return json({ ok: false, error: "forbidden" }, 403);
      return json({
        ok: true,
        users: [
          {
            user_id: 42,
            minishop_id: "ms_shell_customer",
            first_name: "Shell Private Customer",
            username: "shell_private_customer",
            email: "shell-private@example.test",
            is_banned: false,
            registration_date: "2026-10-20T12:00:00Z",
          },
        ],
        total: 1,
      });
    }
    if (path === "/api/admin/console/maintenance") {
      maintenance.reads += 1;
      if (!state.admin) return json({ ok: false, error: "forbidden" }, 403);
      return json({ ok: true, destination: maintenance.destination });
    }
    if (path === "/api/admin/settings" && url.searchParams.has("features_only"))
      return json({ ok: true, features: [] });
    if (path === "/api/admin/health") return json({ ok: true, alerts: [] });
    if (path === "/api/admin/support/stats") return json({ ok: true, unread_count: 0 });
    if (path === "/api/admin/plugins/runtime")
      return json({ ok: true, plugins: [], generation: 0 });
    if (path === "/api/services") return json({ ok: true, services: [], total: 0 });
    return json({ ok: false, error: "shell_fixture_unhandled" }, 404);
  });
  return {
    state,
    maintenance,
    label: (key: string) => locale[`admin_${key}`],
    holdNextList() {
      hold = new Promise<void>((resolve) => {
        release = resolve;
      });
    },
    releaseList() {
      release();
    },
  };
}
