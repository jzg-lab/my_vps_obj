import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { setTimeout } from "node:timers/promises";
import { expect, test, type Page, type TestInfo } from "@playwright/test";
import type { components, operations, paths } from "../src/lib/api/openapi.generated";

let apiResponses: { path: string; status: number; retryAfter: string | null }[];

test.beforeEach(async ({ page }, info) => {
  // The local API allows 120 requests/account per 60s; each browser flow needs its own window.
  info.setTimeout(info.timeout + 60_000);
  await setTimeout(60_000);
  apiResponses = [];
  page.on("response", (response) => {
    const path = new URL(response.url()).pathname;
    if (!path.startsWith("/api/")) return;
    apiResponses.push({
      path:
        path.startsWith("/api/admin/console/") || path === "/api/admin/services"
          ? path
          : "/api/[other]",
      status: response.status(),
      retryAfter: response.headers()["retry-after"] ?? null,
    });
  });
});

test.afterEach(async ({ page }, info) => {
  const path = info.outputPath("http-statuses.json");
  writeFileSync(
    path,
    JSON.stringify(
      {
        finishedAt: new Date().toISOString(),
        viewport: page.viewportSize(),
        annotations: info.annotations,
        responses: apiResponses,
      },
      null,
      2
    )
  );
  await info.attach("http-statuses", {
    path,
    contentType: "application/json",
  });
  expect(apiResponses.filter((response) => response.status === 429)).toEqual([]);
});

async function login(page: Page, email: string, info: TestInfo) {
  await page.goto("/home");
  await expect(page.locator(".auth-screen")).toBeVisible({ timeout: 20_000 });
  const locale = await localeFor(page);
  await page.getByRole("button", { name: locale.wa_login_use_password, exact: true }).click();
  await expect(page.locator('input[autocomplete="current-password"]')).toBeVisible();
  await page.screenshot({
    path: info.outputPath("login.png"),
    fullPage: true,
    animations: "disabled",
  });
  await page.locator('input[autocomplete="email"]').fill(email);
  await page.locator('input[autocomplete="current-password"]').fill("Minishop-Dev-2026!");
  const pendingLogin = page.waitForResponse(
    (response) => new URL(response.url()).pathname === "/api/auth/email/password"
  );
  await page.getByRole("button", { name: locale.wa_login_password_submit, exact: true }).click();
  const response = await pendingLogin;
  expect(response.status()).toBe(200);
  expect((await response.json()).ok).toBe(true);
  await expect(page.locator(".auth-screen")).toHaveCount(0);
  await expect(page.locator(".app-shell")).toBeVisible();
}

async function localeFor(page: Page): Promise<Record<string, string>> {
  const lang = (await page.locator("html").getAttribute("lang"))?.toLowerCase() || "en";
  expect(["en", "ru", "zh-hans"]).toContain(lang);
  return JSON.parse(readFileSync(resolve(__dirname, `../../locales/${lang}.json`), "utf8"));
}

async function fits(page: Page) {
  expect(await page.evaluate(() => document.body.scrollWidth - innerWidth)).toBeLessThanOrEqual(2);
}

async function accountLanguage(page: Page): Promise<string> {
  const response = await page.context().request.get("/api/me?fresh=true");
  expect(response.status()).toBe(200);
  const account =
    (await response.json()) as operations["get_me_route"]["responses"][200]["content"]["application/json"];
  expect(account.user.email).toBe("runes.admin@example.com");
  expect(account.user.is_admin).toBe(true);
  const language = account.user.language_code;
  expect(language).toBeTruthy();
  return language!;
}

async function setAccountLanguage(page: Page, language: string, info: TestInfo, restoring = false) {
  const context = page.context();
  const csrf = (await context.cookies()).find((cookie) => cookie.name === "rw_webapp_csrf");
  if (!csrf) throw new Error("The local authenticated session has no CSRF cookie.");
  const update = () =>
    context.request.post("/api/account/language", {
      headers: { "X-CSRF-Token": csrf.value },
      data: { language },
    });
  let response = await update();
  const retryAfter = response.headers()["retry-after"] ?? null;
  apiResponses.push({ path: "/api/account/language", status: response.status(), retryAfter });
  if (restoring && response.status() === 429 && Number(retryAfter) > 0) {
    const delay = Number(retryAfter) * 1000;
    info.setTimeout(info.timeout + delay + 10_000);
    await setTimeout(delay);
    response = await update();
    apiResponses.push({
      path: "/api/account/language",
      status: response.status(),
      retryAfter: response.headers()["retry-after"] ?? null,
    });
  }
  expect(response.status()).toBe(200);
  expect((await response.json()).language).toBe(language);
  expect(await accountLanguage(page)).toBe(language);
  await page.goto("/home");
  await expect(page.locator(".app-shell")).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", language);
}

for (const width of [1440, 390]) {
  for (const language of ["account", "zh-hans"]) {
    test(`real administrator console round trip at ${width}px${language === "zh-hans" ? " in zh-hans" : ""}`, async ({
      context,
      page,
    }, info) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.setViewportSize({ width, height: 1000 });
      await login(page, "runes.admin@example.com", info);
      const originalLanguage = language === "zh-hans" ? await accountLanguage(page) : null;
      if (originalLanguage)
        info.annotations.push({ type: "original-language", description: originalLanguage });
      try {
        if (originalLanguage) await setAccountLanguage(page, language, info);
        const listResponse = await context.request.get("/api/admin/console/services?page_size=1");
        expect(listResponse.status()).toBe(200);
        const list = (await listResponse.json()) as components["schemas"]["ConsoleServiceListOut"];
        expect(
          list.total,
          "This QA requires an existing local service fixture; it creates no services."
        ).toBeGreaterThan(0);
        const service = list.services[0].service;

        await page.goto("/home");
        await expect(page.locator(".app-shell")).toBeVisible();
        const locale = await localeFor(page);
        const at = (key: string) => locale[`admin_${key}`];
        info.annotations.push({
          type: "account-language",
          description: (await page.locator("html").getAttribute("lang")) || "unknown",
        });
        if (width < 800) {
          await page.getByRole("button", { name: locale.wa_nav_settings, exact: true }).click();
          await page.locator('[data-webapp-action="open-admin-panel"]').click();
        } else await page.locator(".rail-admin-entry").click();
        await expect(page.locator('.console-overview[aria-busy="false"]')).toBeVisible();
        await expect(page.locator('[data-console-metric="services"]')).toContainText(
          String(list.total)
        );
        await fits(page);
        await page.screenshot({
          path: info.outputPath(`overview-${width}.png`),
          fullPage: true,
          animations: "disabled",
        });
        await page.locator('[data-console-metric="nodes"]').scrollIntoViewIfNeeded();
        await page.screenshot({
          path: info.outputPath(`overview-bottom-${width}.png`),
          fullPage: true,
          animations: "disabled",
        });

        if (width < 800) await page.getByRole("button", { name: at("menu"), exact: true }).click();
        const overviewGroup = page.locator('[data-admin-nav-group="overview"]');
        const overviewLink = page.locator('[data-admin-section="console-overview"]');
        await expect(overviewGroup).toHaveAttribute("aria-expanded", "true");
        await expect(overviewLink).toHaveAttribute("aria-current", "page");
        const controlledId = await overviewGroup.getAttribute("aria-controls");
        expect(controlledId).toBeTruthy();
        const controlledNavigation = page.locator(`[id="${controlledId}"]`);
        await overviewGroup.focus();
        await page.keyboard.press("Enter");
        await expect(overviewGroup).toHaveAttribute("aria-expanded", "false");
        await expect(controlledNavigation).toBeHidden();
        await expect(overviewLink).toBeHidden();
        await expect(page.locator(".console-overview")).toBeVisible();
        await page.keyboard.press("Space");
        await expect(overviewGroup).toHaveAttribute("aria-expanded", "true");
        await expect(overviewLink).toBeVisible();
        const nodesGroup = page.locator('[data-admin-nav-group="nodes"]');
        await nodesGroup.click();
        await expect(nodesGroup).toHaveAttribute("aria-expanded", "false");
        await expect(page.locator('[data-admin-section="nodes"]')).toBeHidden();
        await fits(page);
        await page.screenshot({
          path: info.outputPath(`navigation-collapsed-${width}.png`),
          fullPage: true,
          animations: "disabled",
        });
        await nodesGroup.click();
        await expect(nodesGroup).toHaveAttribute("aria-expanded", "true");
        if (width < 800) {
          await page.keyboard.press("Escape");
          const menu = page.getByRole("button", { name: at("menu"), exact: true });
          await expect(menu).toHaveAttribute("aria-expanded", "false");
          await expect(menu).toBeFocused();
          await expect(page.locator(".admin-sidebar")).not.toBeInViewport();
          await expect(page.locator(".admin-sidebar-backdrop")).toHaveCount(0);
        }

        await page.goto("/admin/services");
        const services = page.locator(".console-services");
        await expect(services).toHaveAttribute("aria-busy", "false");
        await services.getByRole("textbox", { name: at("console_search") }).fill(service.id);
        await services.getByRole("button", { name: at("search"), exact: true }).click();
        await expect(services.locator("tbody tr")).toHaveCount(1);
        await expect(services.locator("tbody tr")).toContainText(service.id);
        await fits(page);
        await page.screenshot({
          path: info.outputPath(`service-search-${width}.png`),
          fullPage: true,
          animations: "disabled",
        });
        await services.locator("tbody tr td").nth(1).getByRole("button").click();
        const detail = page.getByRole("dialog", { name: at("console_service_detail") });
        await expect(detail.getByText(service.id, { exact: true })).toBeVisible();
        await expect(
          detail.getByRole("heading", { name: at("console_terms_snapshot") })
        ).toBeVisible();
        expect(
          await detail.locator(".dialog-card").evaluate((el) => el.scrollWidth - el.clientWidth)
        ).toBeLessThanOrEqual(2);
        await page.reload();
        await expect(detail.getByText(service.id, { exact: true })).toBeVisible();
        await detail.screenshot({
          path: info.outputPath(`service-${width}.png`),
          animations: "disabled",
        });
        const resources = detail.getByRole("region", {
          name: at("console_nodes_resources"),
          exact: true,
        });
        await expect(resources).toHaveAttribute("aria-busy", "false");
        await expect(resources.getByRole("alert")).toHaveCount(0);
        await expect(
          resources.getByText(at("console_nodes_resource_scope"), { exact: true })
        ).toBeVisible();
        await resources.scrollIntoViewIfNeeded();
        await detail.screenshot({
          path: info.outputPath(`resources-${width}.png`),
          animations: "disabled",
        });
        await detail
          .getByRole("button", { name: at("services_view_history"), exact: true })
          .click();
        const history = page.getByRole("dialog", { name: at("services_order_history") });
        await expect(history).toBeVisible();
        await expect(history.locator(".service-orders")).toHaveAttribute("aria-busy", "false");
        await expect(history.getByRole("alert")).toHaveCount(0);
        await history.screenshot({
          path: info.outputPath(`history-${width}.png`),
          animations: "disabled",
        });
        await page.keyboard.press("Escape");
        await expect(detail).toBeVisible();
        await page.keyboard.press("Escape");
        await expect(services.getByRole("textbox", { name: at("console_search") })).toHaveValue(
          service.id
        );
        await services.getByRole("button", { name: at("status"), exact: true }).click();
        await expect(page.getByRole("listbox")).toBeVisible();
        await expect(
          page.getByRole("option", { name: at("console_filter_expiring"), exact: true })
        ).toBeVisible();
        await page.screenshot({
          path: info.outputPath(`service-filter-${width}.png`),
          fullPage: true,
          animations: "disabled",
        });
        await page.keyboard.press("Escape");

        const pendingNodes = page.waitForResponse(
          (response) => new URL(response.url()).pathname === "/api/admin/console/nodes"
        );
        await page.goto("/admin/nodes");
        const nodesResponse = await pendingNodes;
        expect(
          nodesResponse.status(),
          `Retry-After: ${nodesResponse.headers()["retry-after"] || "none"}`
        ).toBe(200);
        const nodes = page.locator(".console-nodes");
        await expect(nodes).toHaveAttribute("aria-busy", "false");
        await expect(nodes.locator(".node-sources")).toBeVisible();
        await fits(page);
        await page.screenshot({
          path: info.outputPath(`nodes-${width}.png`),
          fullPage: true,
          animations: "disabled",
        });
        await page.reload();
        await expect(nodes).toHaveAttribute("aria-busy", "false");
        await expect(nodes.locator(".node-sources")).toBeVisible();
        const pendingCatalog = page.waitForResponse(
          (response) => new URL(response.url()).pathname === "/api/admin/console/resources/catalog"
        );
        await page.goto("/admin/node-resources");
        const catalogResponse = await pendingCatalog;
        expect(catalogResponse.status()).toBe(200);
        const catalog =
          (await catalogResponse.json()) as components["schemas"]["ConsoleResourceCatalogOut"];
        expect(catalog.execution_available).toBe(false);
        const resourceList = page.locator(".console-resources");
        await expect(resourceList).toHaveAttribute("aria-busy", "false");
        await expect(resourceList.locator(".catalog-status")).toBeVisible();
        await expect(resourceList.locator(".catalog-table tbody tr")).toHaveCount(
          catalog.groups.length
        );
        await fits(page);
        await page.screenshot({
          path: info.outputPath(`node-resources-${width}.png`),
          fullPage: true,
          animations: "disabled",
        });
        const group = catalog.groups[0];
        if (group?.id) {
          const trigger = resourceList
            .locator(`[data-resource-id="${group.id}"]`)
            .getByRole("button");
          await trigger.focus();
          await page.keyboard.press("Enter");
          const resourceDetail = page.getByRole("dialog", { name: at("console_catalog_detail") });
          await expect(resourceDetail.getByText(group.id, { exact: true })).toBeVisible();
          await page.reload();
          await expect(resourceDetail.getByText(group.id, { exact: true })).toBeVisible();
          expect(
            await resourceDetail
              .locator(".dialog-card")
              .evaluate((el) => el.scrollWidth - el.clientWidth)
          ).toBeLessThanOrEqual(2);
          await resourceDetail.screenshot({
            path: info.outputPath(`node-resource-detail-${width}.png`),
            animations: "disabled",
          });
          await page.keyboard.press("Escape");
          await expect(resourceDetail).toHaveCount(0);
          await expect(trigger).toBeFocused();
        }
        await resourceList
          .getByRole("button", { name: at("console_catalog_kind"), exact: true })
          .click();
        await expect(page.getByRole("listbox")).toBeVisible();
        await page.screenshot({
          path: info.outputPath(`node-resource-filter-${width}.png`),
          fullPage: true,
          animations: "disabled",
        });
        await page.getByRole("option", { name: at("console_nodes_hosts"), exact: true }).click();
        await expect(resourceList.locator(".catalog-table tbody tr")).toHaveCount(
          catalog.hosts.length
        );
        await fits(page);
        if (width < 800) await page.getByRole("button", { name: at("menu"), exact: true }).click();
        await page.getByRole("button", { name: at("exit"), exact: true }).click();
        await expect(page.locator(".admin-screen-wrap")).toHaveCount(0);
        await expect(
          width < 800
            ? page.locator('[data-webapp-action="open-admin-panel"]')
            : page.locator(".rail-admin-entry")
        ).toBeVisible();
        await fits(page);
        await page.screenshot({
          path: info.outputPath(`returned-${width}.png`),
          fullPage: true,
          animations: "disabled",
        });
        expect(errors).toEqual([]);
      } finally {
        if (originalLanguage) {
          await setAccountLanguage(page, originalLanguage, info, true);
          info.annotations.push({ type: "restored-language", description: originalLanguage });
          await page.screenshot({
            path: info.outputPath(`restored-language-${width}.png`),
            fullPage: true,
            animations: "disabled",
          });
        }
      }
    });
  }

  test(`real customer summary and detail round trip at ${width}px`, async ({ page }, info) => {
    const errors: string[] = [];
    const serviceOwners: (string | null)[] = [];
    const serviceFailures: number[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.pathname === "/api/admin/services")
        serviceOwners.push(url.searchParams.get("user_id"));
    });
    page.on("response", (response) => {
      if (new URL(response.url()).pathname === "/api/admin/services" && response.status() >= 400) {
        serviceFailures.push(response.status());
      }
    });
    await page.setViewportSize({ width, height: 1000 });
    await login(page, "runes.admin@example.com", info);
    const locale = await localeFor(page);
    const at = (key: string) => locale[`admin_${key}`];
    const responsePending = page.waitForResponse(
      (response) => new URL(response.url()).pathname === "/api/admin/users"
    );
    await page.goto("/admin/users");
    const response = await responsePending;
    expect(response.status()).toBe(200);
    const payload =
      (await response.json()) as paths["/api/admin/users"]["get"]["responses"][200]["content"]["application/json"];
    expect(payload.ok).toBe(true);
    const customer = payload.users.find((row) => row.independent_services.total > 0);
    expect(customer, "An existing local fixture must own a service.").toBeDefined();
    if (!customer) throw new Error("Missing local customer fixture.");
    const row = page.locator(
      width < 800
        ? `[data-mobile-user-id="${customer.user_id}"]`
        : `tr[data-user-id="${customer.user_id}"]`
    );
    await expect(
      row.locator(`[data-customer-service-total="${customer.independent_services.total}"]`)
    ).toBeVisible();
    await expect(row.getByText(at("console_customers_activity_uncollected"))).toBeVisible();
    const trigger = row.locator("summary");
    await trigger.focus();
    await page.keyboard.press("Enter");
    await expect(row.locator("details")).toHaveAttribute("open", "");
    await expect(page).toHaveURL(/\/admin\/users(?:\?.*)?$/);
    await row.locator(".summary-detail .summary-meta").dblclick();
    await page.keyboard.press("Enter");
    await expect(row.locator("details")).toHaveAttribute("open", "");
    await expect(page).toHaveURL(/\/admin\/users(?:\?.*)?$/);
    await fits(page);
    await row.screenshot({ path: info.outputPath(`customer-summary-${width}.png`) });
    await trigger.click();
    const collapsed = row.locator("details");
    await expect(collapsed).not.toHaveAttribute("open", "");
    const box = await collapsed.boundingBox();
    const triggerBox = await trigger.boundingBox();
    if (!box || !triggerBox) throw new Error("Missing customer summary geometry.");
    expect(box.width).toBeGreaterThan(triggerBox.width + 8);
    await collapsed.click({ position: { x: box.width - 4, y: box.height / 2 } });
    await expect(page.locator(".user-services")).toBeVisible();
    await page.reload();
    await expect(page.locator(".user-services")).toBeVisible();
    await page.getByRole("button", { name: at("user_back"), exact: true }).click();
    await expect(row).toBeVisible();
    await fits(page);
    expect(serviceOwners).toContain(String(customer.user_id));
    expect(serviceOwners).not.toContain("0");
    expect(serviceFailures).toEqual([]);
    expect(errors).toEqual([]);
  });

  test(`real read-only global operations and diagnostics in zh-hans at ${width}px`, async ({
    context,
    page,
  }, info) => {
    const errors: string[] = [];
    const blockedWrites: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/api/admin/**", async (route) => {
      if (route.request().method() === "GET") await route.continue();
      else {
        blockedWrites.push(new URL(route.request().url()).pathname);
        await route.abort("blockedbyclient");
      }
    });
    await page.setViewportSize({ width, height: 1000 });
    await login(page, "runes.admin@example.com", info);
    const originalLanguage = await accountLanguage(page);
    info.annotations.push({ type: "original-language", description: originalLanguage });
    try {
      await setAccountLanguage(page, "zh-hans", info);
      const locale = await localeFor(page);
      const at = (key: string) => locale[`admin_${key}`];
      const response = await context.request.get(
        "/api/admin/console/services?q=Local%20QA&page_size=200"
      );
      expect(response.status()).toBe(200);
      const services =
        (await response.json()) as paths["/api/admin/console/services"]["get"]["responses"][200]["content"]["application/json"];
      expect(services.ok).toBe(true);
      const existing = services.services.find(
        ({ service, customer }) =>
          service.name.startsWith("Local QA") &&
          service.resource_type === "shared" &&
          customer.user_id !== null
      );
      if (!existing)
        throw new Error("Existing owned Local QA shared service required; no records are created.");
      const service = existing.service;
      const host = page.locator(".console-operations");
      const readGlobal = async (
        action: () => Promise<unknown>,
        filters: Record<string, string>
      ) => {
        const pending = page.waitForResponse((response) => {
          const url = new URL(response.url());
          return (
            url.pathname === "/api/admin/console/operations" &&
            Object.entries(filters).every(([key, value]) => url.searchParams.get(key) === value)
          );
        });
        await action();
        const response = await pending;
        expect(response.status()).toBe(200);
        expect(response.headers()["cache-control"]).toBe("private, no-store");
        const data =
          (await response.json()) as paths["/api/admin/console/operations"]["get"]["responses"][200]["content"]["application/json"];
        expect(data.ok).toBe(true);
        await expect(host).toHaveAttribute("aria-busy", "false");
        await expect(host.getByRole("alert")).toHaveCount(0);
        await expect(host.locator(".admin-list-toolbar-summary strong")).toHaveText(
          String(data.total)
        );
        await expect(host.locator(".admin-pagination-summary")).toHaveText(
          `${at("console_global_count")} ${data.total}`
        );
        await expect(host.locator("tbody tr")).toHaveCount(data.operations.length);
        expect(data.total).toBeGreaterThanOrEqual(data.operations.length);
        for (const operation of data.operations) {
          const row = host.locator(
            `[data-operation-key="${operation.record_type}:${operation.id}"]`
          );
          await expect(row).toContainText(operation.service_id);
          await expect(row.locator(".admin-badge")).toHaveText(
            at(`console_ops_status_${operation.status}`)
          );
          if (operation.record_type === "order") {
            expect(operation.needs_attention).toBe(false);
            await expect(row).toContainText(at("console_ops_history_unknown"));
          }
        }
        if (!data.operations.length)
          await expect(host.getByText(at("console_global_empty"), { exact: true })).toBeVisible();
        await fits(page);
        return data;
      };
      await readGlobal(() => page.goto("/admin/console-operations"), { status: "all" });
      const filters = { service_id: service.id, user_id: String(existing.customer.user_id) };
      await host
        .getByRole("textbox", { name: at("console_global_service_id"), exact: true })
        .fill(filters.service_id);
      await host
        .getByRole("textbox", { name: at("console_global_customer_id"), exact: true })
        .fill(filters.user_id);
      let data = await readGlobal(
        () => host.getByRole("button", { name: at("search"), exact: true }).click(),
        filters
      );
      const total = data.total;
      expect(total, "Existing activation history must not disappear.").toBeGreaterThan(0);
      expect(
        data.operations.every(
          (item) =>
            item.service_id === service.id && item.customer.user_id === existing.customer.user_id
        )
      ).toBe(true);
      if (data.next_cursor) {
        data = await readGlobal(
          () => host.getByRole("button", { name: at("services_next"), exact: true }).click(),
          { ...filters, cursor: data.next_cursor }
        );
        expect(data.total).toBe(total);
      } else
        info.annotations.push({
          type: "coverage",
          description: "Existing service has one operations page; no multipage data manufactured.",
        });
      const listUrl = page.url();
      await page.screenshot({
        path: info.outputPath(`global-operations-${width}.png`),
        fullPage: true,
        animations: "disabled",
      });
      const first = data.operations[0];
      expect(first).toBeDefined();
      await host
        .locator(`[data-operation-key="${first.record_type}:${first.id}"]`)
        .getByTitle(at("console_global_open_service"), { exact: true })
        .click();
      const detail = page.getByRole("dialog", { name: at("console_service_detail"), exact: true });
      await expect(detail.getByText(service.id, { exact: true })).toBeVisible();
      expect(
        await detail.locator(".dialog-card").evaluate((el) => el.scrollWidth - el.clientWidth)
      ).toBeLessThanOrEqual(2);
      const diagnosticPending = page.waitForResponse(
        (response) =>
          new URL(response.url()).pathname ===
          `/api/admin/console/services/${service.id}/diagnostics`
      );
      const historyPending = page.waitForResponse(
        (response) =>
          new URL(response.url()).pathname ===
          `/api/admin/console/services/${service.id}/operations`
      );
      await detail.getByRole("button", { name: at("console_ops_title"), exact: true }).click();
      const diagnosticResponse = await diagnosticPending;
      const historyResponse = await historyPending;
      expect(diagnosticResponse.status()).toBe(200);
      expect(historyResponse.status()).toBe(200);
      const diagnostic =
        (await diagnosticResponse.json()) as components["schemas"]["ConsoleServiceDiagnosticsOut"];
      const history =
        (await historyResponse.json()) as components["schemas"]["ConsoleServiceOperationsOut"];
      expect(diagnostic.service_id).toBe(service.id);
      expect(diagnostic.data_plane_verified).toBe(false);
      expect(history.service_id).toBe(service.id);
      expect(history.total).toBe(total);
      const dialog = page.getByRole("dialog", { name: at("console_ops_title"), exact: true });
      await expect(dialog.locator(".service-diagnostics")).toHaveAttribute("aria-busy", "false");
      await expect(dialog.getByRole("alert")).toHaveCount(0);
      await expect(
        dialog.getByText(at("console_ops_data_plane_unverified"), { exact: true })
      ).toBeVisible();
      const diagnosticRegion = dialog.getByRole("region", {
        name: at("console_ops_diagnostics"),
        exact: true,
      });
      await expect(
        diagnosticRegion.getByText(at(`console_ops_remote_${diagnostic.remote.availability}`), {
          exact: true,
        })
      ).toBeVisible();
      if (diagnostic.remote.raw_used_bytes === null)
        await expect(
          diagnosticRegion
            .locator("dt")
            .filter({ hasText: at("console_ops_raw_usage") })
            .locator("+ dd")
        ).toHaveText(at("console_unknown"));
      const records = dialog.getByRole("region", {
        name: at("console_ops_operations"),
        exact: true,
      });
      await expect(records.locator("tbody tr")).toHaveCount(history.operations.length);
      await expect(records.locator(".admin-pagination-count").last()).toHaveText(
        `${at("console_ops_operations")} ${history.total}`
      );
      for (const operation of history.operations) {
        const kind = operation.phase === null ? "order" : "execution";
        const row = records.locator(`[data-operation-key="${kind}:${operation.id}"]`);
        await expect(row.locator(".admin-badge")).toHaveText(
          at(`console_ops_status_${operation.status}`)
        );
        if (kind === "order") await expect(row.getByRole("button")).toHaveCount(0);
      }
      await fits(page);
      expect(
        await dialog.locator(".dialog-card").evaluate((el) => el.scrollWidth - el.clientWidth)
      ).toBeLessThanOrEqual(2);
      expect(
        await dialog.locator(".dialog-card").evaluate((el) => {
          const box = el.getBoundingClientRect();
          return box.left >= -2 && box.right <= innerWidth + 2;
        })
      ).toBe(true);
      await diagnosticRegion.scrollIntoViewIfNeeded();
      await dialog.screenshot({
        path: info.outputPath(`diagnostics-${width}.png`),
        animations: "disabled",
      });
      await records.scrollIntoViewIfNeeded();
      await dialog.screenshot({
        path: info.outputPath(`operation-history-${width}.png`),
        animations: "disabled",
      });
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      await expect(detail).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(detail).toHaveCount(0);
      await expect(page).toHaveURL(listUrl);
      await expect(
        host.getByRole("textbox", { name: at("console_global_service_id"), exact: true })
      ).toHaveValue(service.id);
      await expect(
        host.getByRole("textbox", { name: at("console_global_customer_id"), exact: true })
      ).toHaveValue(filters.user_id);
      await expect(host.locator(".admin-list-toolbar-summary strong")).toHaveText(String(total));
      await expect(host.locator("tbody tr")).toHaveCount(data.operations.length);
      await host.getByRole("button", { name: at("status"), exact: true }).click();
      await expect(page.getByRole("listbox")).toBeVisible();
      expect(
        await page.getByRole("listbox").evaluate((el) => {
          const box = el.getBoundingClientRect();
          return box.left >= -2 && box.right <= innerWidth + 2;
        })
      ).toBe(true);
      await fits(page);
      await page.screenshot({
        path: info.outputPath(`operations-filter-${width}.png`),
        fullPage: true,
        animations: "disabled",
      });
      const unknown = await readGlobal(
        () =>
          page.getByRole("option", { name: at("console_ops_status_unknown"), exact: true }).click(),
        { ...filters, status: "unknown" }
      );
      expect(unknown.operations.every((item) => item.status === "unknown")).toBe(true);
      const attention = await readGlobal(
        () =>
          host.getByRole("checkbox", { name: at("console_global_attention"), exact: true }).check(),
        { ...filters, status: "unknown", needs_attention: "true" }
      );
      expect(attention.total).toBeLessThanOrEqual(unknown.total);
      expect(
        attention.operations.every(
          (item) =>
            item.record_type === "execution" && item.needs_attention && item.status === "unknown"
        )
      ).toBe(true);
      await host.getByRole("button", { name: at("console_global_archived"), exact: true }).click();
      const empty = await readGlobal(
        () =>
          page
            .getByRole("option", { name: at("console_global_archived_only"), exact: true })
            .click(),
        { ...filters, archived: "only", needs_attention: "true" }
      );
      expect(empty.total).toBe(0);
      await page.screenshot({
        path: info.outputPath(`operations-empty-${width}.png`),
        fullPage: true,
        animations: "disabled",
      });
    } finally {
      await setAccountLanguage(page, originalLanguage, info, true);
      info.annotations.push({ type: "restored-language", description: originalLanguage });
    }
    expect(blockedWrites).toEqual([]);
    expect(errors).toEqual([]);
  });

  test(`real regular account cannot enter console at ${width}px`, async ({
    context,
    page,
  }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await login(page, "runes.active@example.com", info);
    await page.goto("/home");
    await expect(page.locator(".app-shell")).toBeVisible();
    await expect(page.locator(".rail-admin-entry")).toHaveCount(0);
    if (width < 800) {
      const locale = await localeFor(page);
      await page.getByRole("button", { name: locale.wa_nav_settings, exact: true }).click();
      await expect(page.locator('[data-webapp-action="open-admin-panel"]')).toHaveCount(0);
    }
    await page.screenshot({
      path: info.outputPath(`regular-account-${width}.png`),
      fullPage: true,
      animations: "disabled",
    });
    for (const path of [
      "summary",
      "services",
      "operations",
      "nodes",
      `services/${"0".repeat(32)}`,
      `services/${"0".repeat(32)}/resources`,
      "nodes/00000000-0000-4000-8000-000000000000",
    ]) {
      const response = await context.request.get(`/api/admin/console/${path}`);
      apiResponses.push({
        path: `/api/admin/console/${path}`,
        status: response.status(),
        retryAfter: response.headers()["retry-after"] ?? null,
      });
      expect(response.status()).toBe(403);
      expect((await response.json()).ok).toBe(false);
    }
    for (const path of ["console-overview", "services", "nodes", "console-operations"]) {
      await page.goto(`/admin/${path}`);
      await expect(page.locator(".app-shell")).toBeVisible();
      await expect(page.locator(".admin-screen-wrap")).toHaveCount(0);
      await expect(page.locator(".console-nodes")).toHaveCount(0);
      await expect(page.locator(".console-operations")).toHaveCount(0);
    }
    await fits(page);
    await page.screenshot({
      path: info.outputPath(`regular-rejected-${width}.png`),
      fullPage: true,
      animations: "disabled",
    });
  });
}
