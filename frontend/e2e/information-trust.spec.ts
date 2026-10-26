import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { consoleNodeDetailFixture } from "../src/lib/admin/consoleNodesFixtures";
import type { UserService } from "../src/lib/webapp/independentServices";
import { installAdminShellFixture } from "./fixtures/admin-shell";

const query = "?mock=services&delivery=1&trust_demo=1&theme_preview=dark";

async function prepare(page: Page, language: string) {
  await page.route("**/*", (route) => {
    const host = new URL(route.request().url()).hostname;
    return host === "localhost" || host === "127.0.0.1" ? route.continue() : route.abort();
  });
  await page.addInitScript((language) => {
    localStorage.setItem("rw_minishop_demo_language", language);
  }, language);
}

async function installNodeEvidence(page: Page) {
  await page.addInitScript((fixture) => {
    type Props = { api: (path: string, options?: RequestInit) => Promise<unknown> };
    type Bundle = { mount: (target: HTMLElement, props: Props) => unknown };
    let bundle: Bundle | undefined;
    let summaryReads = 0;
    let nodeReads = 0;
    const node = {
      ...fixture.node,
      status: "online",
      users_online: 3,
      users_online_quality: "reported",
      system: { ...fixture.node.system, load_1m: 1.5, memory_used_bytes: 0 },
    };
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
              if (request.pathname === "/admin/console/summary" && summaryReads++ > 0)
                throw new Error("fixture_summary_unavailable");
              if (request.pathname === "/admin/console/nodes") {
                if (nodeReads++ > 0) throw new Error("fixture_node_unavailable");
                return {
                  ok: true,
                  nodes: [node],
                  total: 1,
                  page: 0,
                  page_size: 5,
                  coverage: "partial",
                  sources: fixture.sources,
                  cache_ttl_seconds: 15,
                };
              }
              if (request.pathname === `/admin/console/nodes/${node.id}`)
                return { ok: true, ...fixture, node };
              return props.api(path, options);
            },
          });
        bundle = value;
      },
    });
  }, consoleNodeDetailFixture);
}

for (const width of [320, 390, 1440]) {
  for (const language of ["en", "ru", "zh-hans"]) {
    const copy: Record<string, string> = JSON.parse(
      readFileSync(`../locales/${language}.json`, "utf8")
    );
    const at = (key: string) => copy[`admin_${key}`];

    test(`service evidence distinguishes unknown, old and independent balances at ${width}px in ${language}`, async ({
      page,
    }, info) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await prepare(page, language);
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(`/demo/runtime/services${query}`);
      const cards = page.locator("[data-service-id]");
      await expect(cards).toHaveCount(10);
      await expect(cards.first()).toContainText("117 GiB / 100 GiB");
      await expect(cards.first().locator("[data-service-remaining]")).toHaveText("0 B");
      await expect(cards.nth(2).locator("[data-service-remaining]")).toHaveText("100 GiB");
      await expect(cards.nth(2)).toContainText(copy.wa_services_status_active);
      const unknown = cards.nth(4);
      await expect(unknown.locator("[data-service-usage]")).toHaveText(
        `${copy.wa_services_usage_unknown} / 100 GiB`
      );
      await expect(unknown.locator("[data-service-remaining]")).toHaveText(
        copy.wa_services_usage_unknown
      );
      await expect(unknown.locator("progress")).toHaveCount(0);
      await expect(unknown).toContainText(copy.wa_services_usage_missing);
      const old = cards.nth(1);
      await expect(old).toContainText("23 GiB / 100 GiB");
      await expect(old.locator("[data-service-remaining]")).toContainText("77 GiB");
      await expect(old).toContainText(copy.wa_services_usage_stale);
      await expect(old).toContainText("2026-10-22 12:00");
      await expect(old.locator("[data-service-reset]")).toHaveText(
        copy.wa_services_expires_before_reset
      );
      await expect(cards.nth(6).locator("[data-service-reset]")).toHaveText(
        copy.wa_services_no_further_reset
      );
      const trigger = old.getByRole("button", { name: copy.wa_services_details, exact: true });
      await trigger.focus();
      await page.keyboard.press("Enter");
      const dialog = page.getByRole("dialog");
      await expect(dialog).toContainText(copy.wa_services_expires_before_reset);
      await expect(dialog).not.toContainText(copy.wa_services_monthly_hint);
      await expect(dialog).toContainText(copy.wa_services_connection_unmeasured);
      await expect(dialog).toContainText(copy.wa_services_help_evidence);
      await dialog.screenshot({
        path: info.outputPath("service-evidence.png"),
        animations: "disabled",
      });
      expect(
        await dialog.evaluate((node) => node.scrollWidth - node.clientWidth)
      ).toBeLessThanOrEqual(2);
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      await expect(trigger).toBeFocused();
      expect(await page.evaluate(() => document.body.scrollWidth - innerWidth)).toBeLessThanOrEqual(
        2
      );
      expect(errors).toEqual([]);
    });

    test(`overview and node evidence retain time and avoid current green after failure at ${width}px in ${language}`, async ({
      page,
    }, info) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await prepare(page, language);
      await installNodeEvidence(page);
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(`/demo/runtime/admin/console-overview${query}`);
      const overview = page.locator(".console-overview");
      await overview.locator(".overview-details > summary").click();
      await expect(overview.locator("[data-summary-observed-at]")).toBeVisible();
      const stamp = (await overview.locator("[data-summary-observed-at]").innerText()).match(
        /\d{4}-\d{2}-\d{2} \d{2}:\d{2}/
      )?.[0];
      expect(stamp).toBeTruthy();
      await expect(overview).toContainText(at("console_usage_aggregate_scope"));
      await expect(overview).toContainText(at("console_health_links_scope"));
      await expect(overview).toContainText(at("console_latest_any_success"));
      await overview
        .getByRole("button", { name: at("console_nodes_view_table"), exact: true })
        .click();
      const row = overview.locator(`[data-node-id="${consoleNodeDetailFixture.node.id}"]`);
      await expect(row).toContainText(at("console_nodes_status_online"));
      await overview.getByRole("button", { name: at("refresh"), exact: true }).click();
      await expect(overview.getByRole("alert")).toHaveCount(2);
      await expect(overview.locator("[data-summary-observed-at]")).toContainText(stamp!);
      await expect(row).toContainText(at("console_nodes_status_unknown"));
      await expect(row).toContainText(
        at("console_nodes_previous_control").replace("{status}", at("console_nodes_status_online"))
      );
      await expect(row).toContainText("2026-10-24 16:00");
      await expect(row).toContainText(at("console_stale"));
      await overview.locator("[data-console-metric=nodes] > details > summary").click();
      await overview.locator(".node-provenance summary").click();
      for (const [target, filename] of [
        [overview.locator("[data-summary-observed-at]"), "overview-old-evidence.png"],
        [overview.locator(".node-sources li").first(), "overview-old-source.png"],
        [
          row.locator("td").filter({
            hasText: at("console_nodes_previous_control").replace(
              "{status}",
              at("console_nodes_status_online")
            ),
          }),
          "overview-old-node-status.png",
        ],
        [row.locator("td").filter({ hasText: "2026-10-24 16:00" }), "overview-old-node-time.png"],
      ] as const) {
        await target.scrollIntoViewIfNeeded();
        await expect(target).toBeInViewport({ ratio: 0.9 });
        await page.screenshot({ path: info.outputPath(filename), animations: "disabled" });
      }
      await row.getByRole("button", { name: /HK inventory node/ }).click();
      const detail = page.getByRole("region", { name: at("console_nodes_detail") });
      await expect(detail).toContainText(at("console_node_metrics_control_scope"));
      await expect(detail).toContainText(at("console_node_metrics_probe_missing"));
      await expect(detail).toContainText(at("console_node_metrics_sample_unknown"));
      await expect(detail).toContainText(at("console_node_metrics_memory_scope"));
      await expect(detail).toContainText(at("console_nodes_association_scope"));
      await expect(detail).toContainText(at("console_nodes_online"));
      const metrics = detail.locator(".node-system-metrics");
      await expect(metrics).toContainText(at("console_node_metrics_network_scope"));
      for (const [target, filename] of [
        [metrics.locator(".metrics-observation"), "node-observation-evidence.png"],
        [
          metrics.getByText(at("console_node_metrics_memory_scope"), { exact: true }),
          "node-memory-evidence.png",
        ],
        [
          metrics.getByText(at("console_node_metrics_network_scope"), { exact: true }),
          "node-network-evidence.png",
        ],
        [
          metrics.getByRole("region", {
            name: at("console_node_metrics_connectivity"),
            exact: true,
          }),
          "node-proxy-evidence.png",
        ],
      ] as const) {
        await target.scrollIntoViewIfNeeded();
        await expect(target).toBeInViewport({ ratio: 0.9 });
        await page.screenshot({ path: info.outputPath(filename), animations: "disabled" });
      }
      expect(await page.evaluate(() => document.body.scrollWidth - innerWidth)).toBeLessThanOrEqual(
        2
      );
      expect(errors).toEqual([]);
    });
  }
}

test("failed service detail retries and returns keyboard focus to its original card", async ({
  page,
}) => {
  const copy: Record<string, string> = JSON.parse(readFileSync("../locales/en.json", "utf8"));
  await prepare(page, "en");
  await page.setViewportSize({ width: 390, height: 1000 });
  const fixture = await installAdminShellFixture(page);
  fixture.state.admin = false;
  const service: UserService = {
    id: "a".repeat(32),
    user_id: 7,
    plan_id: "1".repeat(32),
    plan_revision: 1,
    name: "Retry evidence service",
    description: "",
    resource_type: "shared",
    traffic_rule: "total",
    quota_bytes: 100 * 2 ** 30,
    used_bytes: 0,
    starts_at: "2026-10-22T04:00:00Z",
    expires_at: "2027-01-20T04:00:00Z",
    cycle_started_at: null,
    cycle_ends_at: null,
    last_usage_sync_at: null,
    usage_total_bytes: null,
    usage_error: null,
    cycle_pending: false,
    status: "pending",
    connection_state: "pending",
    revision: 1,
    desired_status: "active",
    sync_pending: false,
    sync_error: null,
    sync_confirmed_at: null,
    exit_ip: null,
    exit_verified: false,
    replacement_order_id: null,
  };
  let detailReads = 0;
  await page.route(/\/api\/services(?:\/[^/?]+)?(?:\?|$)/, (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/services")
      return route.fulfill({ json: { ok: true, services: [service], total: 1 } });
    detailReads += 1;
    return detailReads === 1
      ? route.fulfill({ status: 503, json: { ok: false, error: "fixture_detail_unavailable" } })
      : route.fulfill({ json: { ok: true, service } });
  });
  // Reuse the real HTTP shell fixture; the docs demo transport does not issue HTTP detail calls.
  await page.goto("/demo/runtime/settings?mock=services&theme_preview=dark");
  await page
    .locator("nav")
    .getByRole("button", { name: copy.wa_services_nav, exact: true })
    .click();
  const trigger = page
    .locator(`[data-service-id="${service.id}"]`)
    .getByRole("button", { name: copy.wa_services_details, exact: true });
  await trigger.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("alert")).toContainText(copy.wa_services_load_failed);
  await expect(dialog.getByRole("alert")).toContainText(copy.wa_services_snapshot_unknown);
  expect(detailReads).toBe(1);
  await dialog.getByRole("button", { name: copy.wa_services_retry, exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(dialog).toContainText(service.name);
  await expect(dialog.getByRole("alert")).toHaveCount(0);
  expect(detailReads).toBe(2);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
});
