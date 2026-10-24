import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import type { components } from "../src/lib/api/openapi.generated";

const locale: Record<string, string> = JSON.parse(readFileSync("../locales/ru.json", "utf8"));
const label = (key: string) => locale[`admin_${key}`];
const url = (section: string) => `/demo/runtime/admin/${section}?mock=services&theme_preview=dark`;
const serviceId = "a".repeat(32);

async function installConsoleApi(
  page: Page,
  mode: "normal" | "unknown" | "partial" | "failure" | "revoked" | "unconnected" = "normal",
  language = "ru"
) {
  await page.addInitScript(
    ({ mode, serviceId, language }) => {
      localStorage.setItem("rw_minishop_demo_language", language);
      type Row = Record<string, unknown>;
      type Props = { api: (path: string, options?: RequestInit) => Promise<Row> };
      type Bundle = { mount: (target: HTMLElement, props: Props) => unknown };
      const time = "2026-10-24T01:00:00Z";
      const customer: components["schemas"]["ConsoleCustomerOut"] = {
        user_id: 910001,
        minishop_id: "MS-910001",
        username: "alice",
        email: null,
        first_name: "Alice",
        last_name: null,
        is_banned: false,
      };
      const base: Omit<components["schemas"]["UserServiceOut"], "id"> = {
        revision: 1,
        desired_status: "active",
        sync_pending: false,
        sync_error: null,
        sync_confirmed_at: time,
        user_id: customer.user_id,
        plan_id: "plan-a",
        plan_revision: 1,
        name: "Independent A",
        description: "",
        resource_type: mode === "unconnected" ? "dedicated" : "shared",
        traffic_rule: "monthly",
        quota_bytes: 2147483648,
        used_bytes: 0,
        starts_at: time,
        expires_at: "2026-11-24T01:00:00Z",
        cycle_started_at: time,
        cycle_ends_at: "2026-11-24T01:00:00Z",
        last_usage_sync_at: mode === "unknown" ? null : time,
        usage_error: null,
        usage_total_bytes: 0,
        cycle_pending: false,
        status: "active",
        connection_state: mode === "unconnected" ? "pending" : "ready",
        exit_ip: null,
        exit_verified: false,
        replacement_order_id: null,
      };
      const rows = Array.from({ length: 26 }, (_, i) => ({
        customer,
        service: {
          ...base,
          id: i === 0 ? serviceId : i.toString(16).padStart(32, "0"),
          name: i === 0 ? base.name : `Independent ${i + 1}`,
        },
      }));
      const summary: components["schemas"]["ConsoleSummaryOut"] & { ok: true } = {
        ok: true,
        observed_at: time,
        refresh_mode: "read_only_local_records",
        timezone: "Asia/Shanghai",
        customers: { total: 1, with_services: 1, banned: 0, source: "business_accounts" },
        services: {
          total: 26,
          by_status: { active: 26 },
          entitlement_valid: 26,
          delivery_ready: 26,
          archived: 3,
          source: "nonarchived_services",
        },
        usage: {
          confirmed_used_bytes: mode === "unknown" ? null : 0,
          services_total: 26,
          services_sampled: mode === "unknown" ? 0 : mode === "partial" ? 1 : 26,
          services_with_errors: 0,
          oldest_sample_at: mode === "unknown" ? null : time,
          latest_sample_at: mode === "unknown" ? null : time,
          availability:
            mode === "unknown" ? "unknown" : mode === "partial" ? "partial" : "available",
          source: "persisted_service_usage",
          scope: "current_period_upload_plus_download_business_payload",
          unit: "bytes",
          freshness: "last_confirmed_observation",
        },
        health: {
          delivery_pending: 0,
          delivery_failed: 0,
          sync_pending: 0,
          sync_failed: 1,
          usage_failed: 0,
          usage_unobserved: 0,
          cycle_pending: 0,
          account_sync_pending: 0,
          account_sync_failed: 0,
          latest_success_at: time,
          latest_attempt_at: time,
          oldest_pending_since: null,
          pending_time_unavailable_reason: "enqueue_time_not_recorded",
          source: "local_service_and_account_sync_records",
          scope: "including_archived_services",
        },
        exits: {
          total: 0,
          available: 0,
          occupied: 0,
          pending_verification: 0,
          pending_reclaim: 0,
          disabled: 0,
          unverified_total: 0,
          source: "dedicated_exit_inventory",
          overlap: "pending_reclaim_subset_of_occupied_disabled_may_overlap",
        },
      };
      let summaryRequests = 0;
      let bundle: Bundle | undefined;
      Object.defineProperty(window, "SubscriptionWebAppAdmin", {
        configurable: true,
        get: () => bundle,
        set(value: Bundle) {
          const mount = value.mount;
          value.mount = (target, props) =>
            mount(target, {
              ...props,
              api: async (path, options) => {
                const request = new URL(path, "https://fixture.test");
                if (request.pathname === "/admin/console/summary") {
                  if (mode === "revoked" && summaryRequests++ > 0)
                    return { ok: false, error: "forbidden" };
                  if (mode === "failure" || (mode !== "revoked" && summaryRequests++ > 0))
                    throw new Error("fixture_source_unavailable");
                  return summary;
                }
                if (request.pathname === "/admin/console/nodes")
                  return {
                    ok: true,
                    nodes: [],
                    total: mode === "failure" ? null : 0,
                    page: 0,
                    page_size: 5,
                    coverage: mode === "failure" ? "unavailable" : "complete",
                    sources: [
                      {
                        source: "nodes",
                        availability: mode === "failure" ? "unavailable" : "available",
                        attempted_at: time,
                        last_success_at: mode === "failure" ? null : time,
                        error: mode === "failure" ? "request_failed" : null,
                      },
                    ],
                    cache_ttl_seconds: 30,
                  };
                if (request.pathname === "/admin/console/services") {
                  const q = request.searchParams.get("q") || "";
                  const status = request.searchParams.get("status");
                  const filtered = rows.filter(
                    (row) =>
                      row.service.name.includes(q) &&
                      (!status ||
                        status === "all" ||
                        (status === "usage_unconfirmed"
                          ? !row.service.last_usage_sync_at || Boolean(row.service.usage_error)
                          : row.service.status === status))
                  );
                  const page = Number(request.searchParams.get("page") || 0);
                  return {
                    ok: true,
                    services: filtered.slice(page * 25, (page + 1) * 25),
                    total: filtered.length,
                    page,
                    page_size: 25,
                    observed_at: time,
                    expiring_within_days: 7,
                  };
                }
                if (request.pathname === `/admin/console/services/${serviceId}`) {
                  const detail: components["schemas"]["ConsoleServiceDetailOut"] = {
                    ...rows[0],
                    service: {
                      ...rows[0].service,
                      sync_error: "secret-sync-error-must-not-be-rendered",
                      usage_error: "secret-usage-error-must-not-be-rendered",
                    },
                    connection:
                      mode === "unconnected"
                        ? null
                        : {
                            panel_user_uuid: "11111111-1111-4111-8111-111111111111",
                            last_error: "secret-error-must-not-be-rendered",
                            attempted_at: time,
                            sync_attempted_at: "2026-10-24T02:00:00Z",
                            usage_attempted_at: null,
                            revoked_at: null,
                          },
                    terms: {
                      name: "Original terms",
                      description: "Original description",
                      resource_type: mode === "unconnected" ? "dedicated" : "shared",
                      traffic_rule: "monthly",
                      quota_bytes: 1073741824,
                      validity_days: 30,
                      price: "29.90",
                      currency: "CNY",
                      ...(mode === "unconnected"
                        ? {}
                        : { squad_uuids: ["22222222-2222-4222-8222-222222222222"] }),
                      resource_pool: mode === "unconnected" ? "original-pool" : null,
                    },
                  };
                  return { ok: true, ...detail };
                }
                if (request.pathname.endsWith("/resources"))
                  return {
                    ok: true,
                    service_id: serviceId,
                    status: "active",
                    connection_state: "ready",
                    currently_eligible: true,
                    configured_group_ids: [],
                    groups: [],
                    nodes: [],
                    hosts: [],
                    association_basis: "persisted_service_scope_not_live_connections",
                    remote_authorization_verified: false,
                    coverage: "complete",
                    sources: [],
                    local_observed_at: time,
                  };
                if (request.pathname === "/admin/services")
                  return {
                    ok: true,
                    services: rows.slice(0, 25).map((row) => row.service),
                    total: rows.length,
                  };
                if (request.pathname === "/admin/service-orders")
                  return { ok: true, orders: [], total: 0 };
                return props.api(path, options);
              },
            });
          bundle = value;
        },
      });
    },
    { mode, serviceId, language }
  );
}

for (const width of [1440, 390]) {
  for (const language of ["ru", "en", "zh-hans"] as const) {
    const locale: Record<string, string> = JSON.parse(
      readFileSync(`../locales/${language}.json`, "utf8")
    );
    const label = (key: string) => locale[`admin_${key}`];
    test(`global services search, pagination, detail and history survive browser navigation at ${width}px in ${language}`, async ({
      page,
    }, testInfo) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.setViewportSize({ width, height: 1000 });
      await installConsoleApi(page, "normal", language);
      await page.goto(url("services"));
      const section = page.locator(".console-services");
      await expect(section.locator("tbody tr")).toHaveCount(25);
      await expect(section.locator(".admin-list-toolbar-summary strong")).toHaveText("26");
      await section.getByRole("button", { name: label("services_next"), exact: true }).click();
      await expect(page).toHaveURL(/page=1/);
      await expect(section.locator("tbody tr")).toHaveCount(1);
      await page.goBack();
      await expect(section.locator("tbody tr")).toHaveCount(25);
      await section.getByRole("textbox", { name: label("console_search") }).fill("Independent A");
      await section.getByRole("button", { name: label("search"), exact: true }).click();
      await expect(section.locator("tbody tr")).toHaveCount(1);
      await section.getByRole("button", { name: /Independent A/ }).click();
      await expect(page).toHaveURL(/service_id=/);
      const detail = page.getByRole("dialog", { name: label("console_service_detail") });
      await expect(detail.getByText(serviceId, { exact: true })).toBeVisible();
      await expect(
        detail.getByText("11111111-1111-4111-8111-111111111111", { exact: true })
      ).toBeVisible();
      await expect(detail.getByText("Original terms", { exact: true })).toBeVisible();
      await expect(detail.getByText("29.90 CNY", { exact: true })).toBeVisible();
      const terms = detail.getByRole("region", { name: label("console_terms_snapshot") });
      await expect(terms.getByText("1 GiB", { exact: true })).toBeVisible();
      await expect(terms.getByText("Original description", { exact: true })).toBeVisible();
      await expect(detail.getByText("0 B / 2 GiB", { exact: true })).toBeVisible();
      await expect(
        terms.getByText("22222222-2222-4222-8222-222222222222", { exact: true })
      ).toBeVisible();
      const connection = detail.getByRole("region", { name: label("console_connection_details") });
      await expect(
        connection.getByText(label("console_connection_attempted_at")).locator("..")
      ).toContainText("2026-10-24 09:00");
      await expect(
        connection.getByText(label("console_connection_sync_attempted_at")).locator("..")
      ).toContainText("2026-10-24 10:00");
      await expect(
        connection.getByText(label("console_connection_error"), { exact: true })
      ).toBeVisible();
      expect(
        await detail.locator(".dialog-card").evaluate((el) => el.scrollWidth - el.clientWidth)
      ).toBeLessThanOrEqual(2);
      await expect(
        detail.getByText(label("console_connection_usage_attempted_at")).locator("..")
      ).toContainText(label("console_unknown"));
      await expect(detail.getByText("secret-error-must-not-be-rendered")).toHaveCount(0);
      await expect(detail.getByText("secret-sync-error-must-not-be-rendered")).toHaveCount(0);
      await expect(detail.getByText("secret-usage-error-must-not-be-rendered")).toHaveCount(0);
      await expect(
        detail.getByText(label("console_filter_sync_error"), { exact: true })
      ).toBeVisible();
      await expect(detail.getByText(label("services_usage_stale"), { exact: true })).toBeVisible();
      await terms.screenshot({
        path: testInfo.outputPath(`service-terms-${width}-${language}.png`),
      });
      await page.reload();
      await expect(detail.getByText(serviceId, { exact: true })).toBeVisible();
      await detail
        .getByRole("button", { name: label("services_view_history"), exact: true })
        .click();
      await expect(
        page.getByRole("dialog", { name: label("services_order_history") })
      ).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(detail).toBeVisible();
      await detail.screenshot({
        path: testInfo.outputPath(`service-detail-${width}-${language}.png`),
      });
      await page.keyboard.press("Escape");
      await expect(page).not.toHaveURL(/service_id=/);
      await expect(section.getByRole("textbox")).toHaveValue("Independent A");
      await page.reload();
      await expect(section.locator("tbody tr")).toHaveCount(1);
      const select = section.locator(`button[aria-label="${label("status")}"]`);
      await select.click();
      await expect(
        page.getByRole("option", { name: label("console_filter_expiring"), exact: true })
      ).toBeVisible();
      await page.keyboard.press("Escape");
      expect(
        await page.evaluate(() => document.body.scrollWidth - window.innerWidth)
      ).toBeLessThanOrEqual(2);
      expect(errors).toEqual([]);
    });

    test(`customer services reach resource details at ${width}px in ${language}`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 1000 });
      await installConsoleApi(page, "normal", language);
      await page.goto(url("services"));
      await page
        .locator(".console-services tbody tr")
        .first()
        .getByRole("button", { name: /Alice/ })
        .click();
      await expect(page).toHaveURL(/admin\/users\/ms_/);
      const customerUrl = page.url();
      await page
        .locator(".user-services tbody tr")
        .first()
        .getByRole("button", { name: label("console_service_detail"), exact: true })
        .click();
      await expect(page).toHaveURL(/admin\/services.*user_id=910001/);
      const detail = page.getByRole("dialog", { name: label("console_service_detail") });
      await expect(
        detail.getByText(label("console_nodes_resource_scope"), { exact: true })
      ).toBeVisible();
      await page.goBack();
      await expect(page).toHaveURL(customerUrl);
      await expect(page.locator(".user-services")).toBeVisible();
    });

    test(`normal-site admin entrance and return keep the account at ${width}px in ${language}`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 1000 });
      await installConsoleApi(page, "normal", language);
      await page.goto("/demo/runtime/app/?mock=services&theme_preview=dark");
      if (width < 800) {
        await page.getByRole("button", { name: locale.wa_nav_settings, exact: true }).click();
        await page.locator('[data-webapp-action="open-admin-panel"]').click();
      } else await page.locator(".rail-admin-entry").click();
      await expect(page.locator('[data-admin-active-section="console-overview"]')).toBeVisible();
      if (width < 800) await page.getByRole("button", { name: label("menu"), exact: true }).click();
      await page.getByRole("button", { name: label("exit"), exact: true }).click();
      await expect(page.locator(".admin-screen-wrap")).toHaveCount(0);
      await expect(
        width < 800
          ? page.locator('[data-webapp-action="open-admin-panel"]')
          : page.locator(".rail-admin-entry")
      ).toBeVisible();
    });

    test(`overview distinguishes confirmed zero and stale data at ${width}px in ${language}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 1000 });
      await installConsoleApi(page, "normal", language);
      await page.goto(url("stats"));
      await expect(page.locator('[data-admin-active-section="console-overview"]')).toBeVisible();
      const usage = page.locator('[data-console-metric="usage"]');
      await expect(usage.getByText("0 B", { exact: true })).toBeVisible();
      await page
        .locator(".console-overview")
        .getByRole("button", { name: label("refresh"), exact: true })
        .click();
      await expect(page.getByText(label("console_refresh_failed"), { exact: true })).toBeVisible();
      await expect(usage.getByText("0 B", { exact: true })).toBeVisible();
      await page.screenshot({
        path: testInfo.outputPath(`overview-stale-${width}-${language}.png`),
        fullPage: true,
      });
      expect(
        await page.evaluate(() => document.body.scrollWidth - window.innerWidth)
      ).toBeLessThanOrEqual(2);
      const health = page.locator('[data-console-metric="health"]');
      await expect(health.getByText(label("console_health_source"), { exact: true })).toBeVisible();
      await expect(
        health.getByText(label("console_health_sync_failed"), { exact: true }).locator("..")
      ).toContainText("1");
      await expect(
        page
          .locator('[data-console-metric="services"]')
          .getByText(label("console_service_source"), { exact: true })
      ).toBeVisible();
      await health.screenshot({
        path: testInfo.outputPath(`overview-health-${width}-${language}.png`),
      });
      await health
        .getByRole("button", { name: label("services_history_title"), exact: true })
        .click();
      await expect(page).toHaveURL(/admin\/service-history/);
    });
  }
}

for (const mode of ["unknown", "partial", "failure"] as const) {
  test(`overview shows ${mode} without inventing a healthy zero`, async ({ page }) => {
    await installConsoleApi(page, mode);
    await page.goto(url("console-overview"));
    if (mode === "failure") {
      await expect(page.getByText(label("console_local_failed"), { exact: true })).toBeVisible();
      await expect(page.locator('[data-console-metric="usage"]')).toHaveCount(0);
      await expect(
        page.getByText(label("console_nodes_coverage_unavailable"), { exact: true })
      ).toBeVisible();
    } else {
      const usage = page.locator('[data-console-metric="usage"]');
      await expect(
        usage.getByText(label(`console_availability_${mode}`), { exact: true })
      ).toBeVisible();
      if (mode === "unknown") {
        await expect(usage.locator("strong")).toHaveText(label("console_unknown"));
        await expect(
          usage.getByText(`${label("console_usage_errors")}: 0`, { exact: true })
        ).toBeVisible();
        await expect(
          usage.getByRole("button", { name: `${label("console_usage_errors")}: 0`, exact: true })
        ).toHaveCount(0);
        await usage
          .getByRole("button", { name: label("console_filter_usage_unconfirmed"), exact: true })
          .click();
        await expect(page).toHaveURL(/status=usage_unconfirmed/);
        await expect(
          page.locator(".console-services .admin-list-toolbar-summary strong")
        ).toHaveText("26");
      }
    }
  });
}

test("revoked administrator loses cached overview values", async ({ page }) => {
  await installConsoleApi(page, "revoked");
  await page.goto(url("console-overview"));
  await expect(page.locator('[data-console-metric="usage"]')).toBeVisible();
  await page
    .locator(".console-overview")
    .getByRole("button", { name: label("refresh"), exact: true })
    .click();
  await expect(page.locator('[data-console-metric="usage"]')).toHaveCount(0);
  await expect(page.getByText(label("console_local_failed"), { exact: true })).toBeVisible();
});

for (const width of [1440, 390]) {
  test(`service without connection or snapshot groups stays readable at ${width}px`, async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 1000 });
    await installConsoleApi(page, "unconnected");
    await page.goto(`${url("services")}&service_id=${serviceId}`);
    const detail = page.getByRole("dialog", { name: label("console_service_detail") });
    const connection = detail.getByRole("region", { name: label("console_connection_details") });
    await expect(
      connection.getByText(label("console_connection_identity")).locator("..")
    ).toContainText(label("console_unknown"));
    const terms = detail.getByRole("region", { name: label("console_terms_snapshot") });
    await expect(
      terms.getByText(label("services_squads"), { exact: true }).locator("..")
    ).toContainText("—");
    await expect(terms.getByText("Original terms", { exact: true })).toBeVisible();
    await expect(terms.getByText("original-pool", { exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });
}
