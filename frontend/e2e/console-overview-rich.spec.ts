import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import {
  consoleNodeFixture,
  consoleNodeDetailFixture,
  consoleNodeTrafficFixture,
} from "../src/lib/admin/consoleNodesFixtures";

async function install(page: Page, language: string) {
  await page.addInitScript(
    ({ node, detail, traffic, language }) => {
      localStorage.setItem("rw_minishop_demo_language", language);
      type Reply = Record<string, unknown>;
      type Props = { api: (path: string, options?: RequestInit) => Promise<Reply> };
      type Bundle = { mount: (target: HTMLElement, props: Props) => unknown };
      const harness = { fail: false, paths: [] as string[] };
      Object.defineProperty(window, "overviewHarness", { value: harness });
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
                const url = new URL(path, "https://fixture.test");
                harness.paths.push(path);
                if (url.pathname === "/admin/console/nodes") {
                  if (harness.fail) throw new Error("fixture_unavailable");
                  const preset = url.searchParams.get("traffic_window") || "today";
                  return {
                    ok: true,
                    nodes: [
                      {
                        ...node,
                        name: "Zero node",
                        status: "online",
                        window_traffic_bytes: 0,
                        window_traffic_quality: "reported",
                      },
                      { ...node, id: "second", name: "Missing node" },
                    ],
                    total: 10,
                    page: 0,
                    page_size: 5,
                    coverage: "partial",
                    sources: detail.sources,
                    traffic: {
                      ...traffic,
                      preset,
                      start_at: preset === "7d" ? "2026-10-18T00:00:00Z" : traffic.start_at,
                    },
                    cache_ttl_seconds: 15,
                  };
                }
                if (url.pathname.startsWith("/admin/console/nodes/")) {
                  const second = url.pathname.endsWith("/second");
                  if (!second) await new Promise((resolve) => setTimeout(resolve, 80));
                  return {
                    ok: true,
                    ...detail,
                    node: {
                      ...node,
                      id: second ? "second" : node.id,
                      name: second ? "Missing node" : "Zero node",
                    },
                    services: second
                      ? []
                      : [
                          ...detail.services,
                          { ...detail.services[0], id: "second", name: "Second service" },
                        ],
                  };
                }
                if (
                  url.pathname === "/admin/console/operations" &&
                  url.searchParams.get("limit") === "4"
                )
                  return {
                    ok: true,
                    total: 1,
                    observed_at: node.observed_at,
                    next_cursor: null,
                    operations: [
                      {
                        id: "todo-fixture",
                        record_type: "execution",
                        service_id: "a".repeat(32),
                        service_name: "Review this service",
                        phase: "delivery",
                        status: "failed",
                        error_code: "private-token-must-not-display",
                        first_failed_at: node.observed_at,
                        created_at: node.observed_at,
                      },
                    ],
                  };
                if (url.pathname === "/admin/support/tickets")
                  return {
                    ok: true,
                    tickets: [
                      {
                        ticket_id: 123,
                        subject: "Connection drops",
                        user_id: 910002,
                        priority: "high",
                        category: "technical",
                        status: "awaiting_admin",
                        last_message_at: node.observed_at,
                      },
                    ],
                    total: 1,
                  };
                return props.api(path, options);
              },
            });
          bundle = value;
        },
      });
    },
    {
      node: consoleNodeFixture,
      detail: consoleNodeDetailFixture,
      traffic: consoleNodeTrafficFixture,
      language,
    }
  );
}

for (const width of [1440, 390])
  for (const language of ["en", "ru", "zh-hans"]) {
    const locale = JSON.parse(readFileSync(`../locales/${language}.json`, "utf8"));
    const at = (key: string) => locale[`admin_${key}`];
    test(`overview keeps brief traffic and feedback, with detail-only graphs excluded at ${width}px in ${language}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 950 });
      await install(page, language);
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.goto(
        "/demo/runtime/admin/console-overview?mock=services&theme_preview=dark&nodes_view=unmanaged"
      );
      const chart = page.locator('[data-overview-chart="traffic"]');
      const todos = page.locator("[data-overview-todos]");
      await expect(todos).toContainText("Review this service");
      await expect(todos).toContainText(at("console_ops_unclassified_error"));
      await expect(todos).not.toContainText("private-token-must-not-display");
      expect(
        await todos.evaluate((node) =>
          Boolean(
            node.compareDocumentPosition(document.querySelector(".operations-priority")!) &
            Node.DOCUMENT_POSITION_FOLLOWING
          )
        )
      ).toBe(true);
      await todos
        .getByRole("button", { name: at("console_global_open_service"), exact: true })
        .click();
      await expect(page).toHaveURL(/detail_service_id=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/);
      await expect(page).toHaveURL(/needs_attention=true/);
      await page.goBack();
      await page.getByRole("button", { name: at("console_check_unknown"), exact: true }).click();
      await expect(page).toHaveURL(/nodes_status=unknown/);
      await page.goBack();
      await page.getByRole("button", { name: at("console_check_offline"), exact: true }).click();
      await expect(page).toHaveURL(/nodes_status=offline/);
      await page.goBack();

      await expect(chart).toContainText(at("console_visual_history_missing"));
      await expect(page.locator('[data-ticket-id="123"]')).toContainText("Connection drops");
      await expect(page.locator("[data-overview-relations]")).toHaveCount(0);
      await expect(page.locator("[data-customer-relations]")).toHaveCount(0);
      await expect(page.locator(".metric-history-card")).toHaveCount(0);
      await expect(page.locator("[data-overview-chart=services]")).toHaveCount(0);
      await expect(page.getByRole("region", { name: at("console_visual_topics") })).toBeVisible();
      await expect(chart.locator("[data-overview-window]")).toContainText("2026-10-18");
      await page.evaluate(() => {
        (window as typeof window & { overviewHarness: { fail: boolean } }).overviewHarness.fail =
          true;
      });
      await page
        .locator(".overview-intro")
        .getByRole("button", { name: at("refresh"), exact: true })
        .click();
      await expect(chart).toContainText(at("console_stale"));
      await expect(chart.locator("[data-overview-window]")).toContainText("2026-10-18");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true
      );
      await page.screenshot({ path: testInfo.outputPath("overview-aligned.png"), fullPage: true });
      await page.evaluate(() => {
        (window as typeof window & { overviewHarness: { fail: boolean } }).overviewHarness.fail =
          false;
      });
      await page
        .locator("[data-console-metric=nodes]")
        .getByRole("button", { name: at("console_open_nodes"), exact: true })
        .click();
      await expect(page).toHaveURL(/section=nodes/);
      await expect(page.locator(".node-detail")).toHaveCount(0);
      await expect(page.locator(".metric-history-card")).toHaveCount(0);
      await expect(page.locator(".console-nodes [data-node-traffic-comparison]")).toBeVisible();
      expect(errors).toEqual([]);
    });
  }
