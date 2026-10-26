import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test, type Page } from "@playwright/test";
import {
  consoleNodeFixture,
  consoleNodeDetailFixture,
  consoleNodeTrafficFixture,
} from "../src/lib/admin/consoleNodesFixtures";

type TrafficMode = "normal" | "stale" | "unavailable" | "unconfigured" | "invalid";
type TrafficHarness = { requests: string[]; delaySevenDays: boolean; release: (() => void) | null };
type TrafficWindow = typeof window & { nodeTrafficHarness: TrafficHarness };
const url = "/demo/runtime/admin/nodes?mock=services&theme_preview=dark";

async function installTrafficApi(page: Page, language: string, mode: TrafficMode = "normal") {
  await page.addInitScript(
    ({ node, detail, traffic, language, mode }) => {
      localStorage.setItem("rw_minishop_demo_language", language);
      const harness: TrafficHarness = { requests: [], delaySevenDays: false, release: null };
      Object.defineProperty(window, "nodeTrafficHarness", { value: harness });
      type Reply = Record<string, unknown>;
      type Props = { api: (path: string, options?: RequestInit) => Promise<Reply> };
      type Bundle = { mount: (target: HTMLElement, props: Props) => unknown };
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
                if (!request.pathname.startsWith("/admin/console/nodes"))
                  return props.api(path, options);
                harness.requests.push(path);
                const requested = request.searchParams.get("traffic_window");
                const preset = requested === "7d" || requested === "30d" ? requested : "today";
                const days = preset === "today" ? 1 : preset === "7d" ? 7 : 30;
                const start = new Date(traffic.start_at);
                start.setUTCDate(start.getUTCDate() - days + 1);
                const unavailable = mode === "unavailable" || mode === "unconfigured";
                const windowTraffic = {
                  ...traffic,
                  preset,
                  start_at: start.toISOString(),
                  start_date: start.toISOString().slice(0, 10),
                  availability: mode === "normal" || mode === "invalid" ? "partial" : mode,
                  inventory_nodes: 26,
                  matched_nodes: unavailable ? 0 : mode === "invalid" ? 24 : 25,
                  last_success_at: unavailable ? null : traffic.last_success_at,
                  attempted_at: "2026-10-24T09:00:00Z",
                  error:
                    mode === "stale" || mode === "unavailable"
                      ? "request_failed"
                      : mode === "invalid"
                        ? "invalid_response"
                        : mode === "unconfigured"
                          ? "not_configured"
                          : null,
                };
                const rows = Array.from({ length: 26 }, (_, index) => ({
                  ...node,
                  id:
                    index === 0
                      ? node.id
                      : `${String(index).padStart(8, "0")}-0000-0000-0000-000000000001`,
                  name: index === 0 ? node.name : `Window node ${index}`,
                  traffic_used_bytes: 4096,
                  window_traffic_bytes:
                    unavailable || index === 0 || (mode === "invalid" && index === 2)
                      ? null
                      : index === 1
                        ? 0
                        : days * 1024,
                  window_traffic_quality:
                    mode === "invalid" && index === 2
                      ? "invalid"
                      : unavailable || index === 0
                        ? "missing"
                        : "reported",
                }));
                if (preset === "7d" && harness.delaySevenDays) {
                  harness.delaySevenDays = false;
                  // Deliberately ignore abort to verify the consumer's late-response guard.
                  await new Promise<void>((resolve) => {
                    harness.release = resolve;
                  });
                }
                const page = Number(request.searchParams.get("page") || 0);
                if (request.pathname !== "/admin/console/nodes") {
                  const selected = rows.find((row) => request.pathname.endsWith(`/${row.id}`));
                  return selected
                    ? { ok: true, ...detail, node: selected, page, traffic: windowTraffic }
                    : { ok: false, error: "node_not_found" };
                }
                const query = request.searchParams.get("q")?.toLowerCase() ?? "";
                const status = request.searchParams.get("status") ?? "all";
                const selected = rows.filter(
                  (row) =>
                    row.name.toLowerCase().includes(query) &&
                    (status === "all" || row.status === status)
                );
                return {
                  ok: true,
                  nodes: selected.slice(page * 25, (page + 1) * 25),
                  total: selected.length,
                  page,
                  page_size: 25,
                  coverage: "complete",
                  sources: detail.sources.map((source) => ({
                    ...source,
                    availability: "available",
                    error: null,
                  })),
                  cache_ttl_seconds: 15,
                  traffic: windowTraffic,
                };
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
      mode,
    }
  );
}

for (const language of ["en", "ru", "zh-hans"]) {
  const locale: Record<string, string> = JSON.parse(
    readFileSync(resolve(__dirname, `../../locales/${language}.json`), "utf8")
  );
  const label = (key: string) => locale[`admin_${key}`];
  for (const width of [1440, 390]) {
    test(`node UTC windows preserve list/detail state at ${width}px in ${language}`, async ({
      page,
    }, testInfo) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.setViewportSize({ width, height: 1000 });
      await installTrafficApi(page, language);
      await page.goto(`${url}&nodes_q=node&nodes_page=1`);
      const section = page.locator(".console-nodes");
      const selector = section.getByRole("button", {
        name: label("console_nodes_window_label"),
        exact: true,
      });
      await expect(section.locator("tbody tr")).toHaveCount(1);
      await expect(section.locator(".admin-list-toolbar-summary strong")).toHaveText("26");
      await selector.focus();
      await page.keyboard.press("Enter");
      const option = page.getByRole("option", {
        name: label("console_nodes_window_7d"),
        exact: true,
      });
      await expect(option).toBeVisible();
      await page.screenshot({
        path: testInfo.outputPath(`node-window-menu-${language}-${width}.png`),
        fullPage: true,
        animations: "disabled",
      });
      expect(
        await option.evaluate((element) => element.scrollWidth - element.clientWidth)
      ).toBeLessThanOrEqual(2);
      await page.keyboard.press("Escape");
      await expect(selector).toBeFocused();
      await selector.click();
      await option.click();
      await expect(page).toHaveURL(/nodes_traffic_window=7d/);
      await expect(section.locator("td[data-window-quality]")).toHaveText("7 KiB");
      await expect(section.locator("[data-traffic-boundaries]")).toContainText(
        "2026-10-18 00:00:00.000 UTC"
      );
      const listRequest = await page.evaluate(() =>
        (window as TrafficWindow).nodeTrafficHarness.requests.at(-1)!
      );
      expect(Object.fromEntries(new URL(listRequest, "https://fixture.test").searchParams)).toEqual(
        { q: "node", status: "all", page: "1", page_size: "25", traffic_window: "7d" }
      );
      await section
        .locator("[data-node-card-id]")
        .getByRole("button", { name: /Window node 25/ })
        .click();
      const detail = page.getByRole("region", { name: label("console_nodes_detail"), exact: true });
      await expect(detail).toBeVisible();
      await expect(detail.locator("td[data-window-quality]")).toHaveText("7 KiB");
      await selector.click();
      await page
        .getByRole("option", { name: label("console_nodes_window_30d"), exact: true })
        .click();
      await expect(detail.locator("td[data-window-quality]")).toHaveText("30 KiB");
      await expect(section.locator("[data-traffic-boundaries]")).toContainText(
        "2026-09-25 00:00:00.000 UTC"
      );
      const detailRequest = await page.evaluate(() =>
        (window as TrafficWindow).nodeTrafficHarness.requests.at(-1)!
      );
      expect(new URL(detailRequest, "https://fixture.test").pathname).toMatch(
        /\/admin\/console\/nodes\/00000025-/
      );
      expect(
        Object.fromEntries(new URL(detailRequest, "https://fixture.test").searchParams)
      ).toEqual({ page: "0", page_size: "25", traffic_window: "30d" });
      await page.reload();
      await expect(selector).toHaveText(label("console_nodes_window_30d"));
      await expect(detail.locator("td[data-window-quality]")).toHaveText("30 KiB");
      await detail.getByRole("button", { name: label("console_nodes_back"), exact: true }).click();
      await expect(
        section.getByRole("textbox", { name: label("console_nodes_search") })
      ).toHaveValue("node");
      await expect(section.locator("tbody tr")).toHaveCount(1);
      await expect(page).toHaveURL(/nodes_page=1/);
      await expect(selector).toHaveText(label("console_nodes_window_30d"));
      await page.goBack();
      await expect(detail).toBeVisible();
      await expect(selector).toHaveText(label("console_nodes_window_30d"));
      await page.goBack();
      await expect(selector).toHaveText(label("console_nodes_window_7d"));
      await expect(detail.locator("td[data-window-quality]")).toHaveText("7 KiB");
      await page.screenshot({
        path: testInfo.outputPath(`node-window-detail-${language}-${width}.png`),
        fullPage: true,
        animations: "disabled",
      });
      expect(
        await page.evaluate(() => document.body.scrollWidth - window.innerWidth)
      ).toBeLessThanOrEqual(2);
      expect(errors).toEqual([]);
    });
  }
}

const locale: Record<string, string> = JSON.parse(
  readFileSync(resolve(__dirname, "../../locales/en.json"), "utf8")
);
const label = (key: string) => locale[`admin_${key}`];
for (const mode of ["stale", "unavailable", "unconfigured", "invalid"] as const) {
  test(`window ${mode} does not erase inventory or replace missing totals with zero`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 1000 });
    await installTrafficApi(page, "en", mode);
    await page.goto(url);
    const section = page.locator(".console-nodes");
    await expect(section.locator(".admin-list-toolbar-summary strong")).toHaveText("26");
    await expect(section.locator("tbody tr")).toHaveCount(25);
    const evidence = section.locator(".window-evidence");
    await expect(evidence).toContainText(
      label(`console_nodes_availability_${mode === "invalid" ? "partial" : mode}`)
    );
    await expect(section.locator("td[data-window-quality]").first()).toHaveText(
      label("console_nodes_window_missing")
    );
    if (mode === "stale") {
      await expect(section.locator("td[data-window-quality]").nth(1)).toContainText("0 B");
      await expect(section.locator("td[data-window-quality]").nth(1)).toContainText(
        label("console_nodes_availability_stale")
      );
      await expect(evidence).toContainText(label("console_nodes_window_request_failed"));
    } else if (mode === "invalid") {
      await expect(section.locator("td[data-window-quality]").nth(2)).toHaveText(
        label("console_nodes_window_invalid")
      );
      await expect(evidence).toContainText(label("console_nodes_window_invalid_response"));
    } else {
      await expect(section.locator('td[data-window-quality="missing"]')).toHaveCount(25);
      await expect(section.locator('td[data-window-quality="reported"]')).toHaveCount(0);
      await expect(evidence).toContainText(
        label(
          `console_nodes_window_${mode === "unconfigured" ? "not_configured" : "request_failed"}`
        )
      );
    }
  });
}

test("a late seven-day response cannot overwrite the selected thirty-day window", async ({
  page,
}) => {
  await installTrafficApi(page, "en");
  await page.goto(url);
  const section = page.locator(".console-nodes");
  const selector = section.getByRole("button", {
    name: label("console_nodes_window_label"),
    exact: true,
  });
  await expect(section.locator("tbody tr")).toHaveCount(25);
  await page.evaluate(() => {
    (window as TrafficWindow).nodeTrafficHarness.delaySevenDays = true;
  });
  await selector.click();
  await page.getByRole("option", { name: label("console_nodes_window_7d"), exact: true }).click();
  await expect
    .poll(() => page.evaluate(() => !!(window as TrafficWindow).nodeTrafficHarness.release))
    .toBe(true);
  await selector.click();
  await page.getByRole("option", { name: label("console_nodes_window_30d"), exact: true }).click();
  await expect(section.locator("td[data-window-quality]").nth(2)).toHaveText("30 KiB");
  await page.evaluate(async () => {
    (window as TrafficWindow).nodeTrafficHarness.release?.();
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
  });
  await expect(section.locator("td[data-window-quality]").nth(2)).toHaveText("30 KiB");
  await expect(selector).toHaveText(label("console_nodes_window_30d"));
  await expect(section.locator("[data-traffic-boundaries]")).toContainText(
    "2026-09-25 00:00:00.000 UTC"
  );
});
