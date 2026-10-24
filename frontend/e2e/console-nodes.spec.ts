import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import {
  consoleNodeFixture,
  consoleNodeDetailFixture,
  consoleServiceResourcesFixture,
  consoleNodeServiceFixture,
} from "../src/lib/admin/consoleNodesFixtures";

const locale: Record<string, string> = JSON.parse(readFileSync("../locales/ru.json", "utf8"));
const label = (key: string) => locale[`admin_${key}`];
const url = "/demo/runtime/admin/nodes?mock=services&theme_preview=dark";
const customer = consoleNodeServiceFixture.customer!;

async function installNodesApi(page: Page, mode = "normal", language = "ru") {
  await page.addInitScript(
    ({ node, detail, resources, service, mode, language }) => {
      localStorage.setItem("rw_minishop_demo_language", language);
      type Reply = Record<string, unknown>;
      type Props = { api: (path: string, options?: RequestInit) => Promise<Reply> };
      type Bundle = { mount: (target: HTMLElement, props: Props) => unknown };
      const rows = Array.from({ length: 26 }, (_, index) => ({
        ...node,
        id: index === 0 ? node.id : `${String(index).padStart(8, "0")}-0000-0000-0000-000000000001`,
        name: index === 0 ? node.name : `Other node ${index}`,
        status: index === 0 ? "unknown" : "online",
        users_online: index === 0 ? null : 0,
        users_online_quality: index === 0 ? "missing" : "unverified_zero",
        traffic_used_bytes: index === 0 ? null : 0,
      }));
      let bundle: Bundle | undefined;
      let failOnce = mode === "failure";
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
                if (request.pathname.startsWith("/admin/console/nodes/")) {
                  const selectedNode = rows.find((row) => request.pathname.endsWith(`/${row.id}`));
                  return selectedNode
                    ? { ok: true, ...detail, node: selectedNode }
                    : { ok: false, error: "node_not_found" };
                }
                if (
                  request.pathname === `/admin/console/services/${resources.service_id}/resources`
                )
                  return { ok: true, ...resources };
                if (request.pathname === `/admin/console/services/${resources.service_id}`)
                  return { ok: true, ...service };
                if (
                  request.pathname === "/admin/services" &&
                  request.searchParams.get("user_id") === String(service.service.user_id)
                )
                  return { ok: true, services: [service.service], total: 1 };
                if (request.pathname === "/admin/console/services")
                  return {
                    ok: true,
                    services: [{ service: service.service, customer: service.customer }],
                    total: 1,
                    page: 0,
                    page_size: 25,
                    observed_at: node.observed_at,
                    expiring_within_days: 7,
                  };
                if (request.pathname === "/admin/console/nodes") {
                  if (failOnce) {
                    failOnce = false;
                    throw new Error("node_inventory_unavailable");
                  }
                  const query = request.searchParams.get("q") || "";
                  const status = request.searchParams.get("status") || "all";
                  const selected =
                    mode === "empty" || mode === "unavailable"
                      ? []
                      : rows.filter(
                          (row) =>
                            row.name.includes(query) && (status === "all" || row.status === status)
                        );
                  const page = Number(request.searchParams.get("page") || 0);
                  const availability =
                    mode === "unavailable"
                      ? "unavailable"
                      : mode === "stale"
                        ? "stale"
                        : "available";
                  return {
                    ok: true,
                    nodes: selected.slice(page * 25, (page + 1) * 25),
                    total: mode === "unavailable" || mode === "stale" ? null : selected.length,
                    page,
                    page_size: 25,
                    coverage:
                      mode === "unavailable"
                        ? "unavailable"
                        : mode === "stale"
                          ? "stale"
                          : "complete",
                    sources: detail.sources.map((source) => ({ ...source, availability })),
                    cache_ttl_seconds: 15,
                  };
                }
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
      resources: consoleServiceResourcesFixture,
      service: consoleNodeServiceFixture,
      mode,
      language,
    }
  );
}

for (const width of [320, 1440]) {
  for (const language of ["en", "ru", "zh-hans"]) {
    test(`node names and IDs remain readable in both tables at ${width}px in ${language}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 1000 });
      await installNodesApi(page, "normal", language);
      for (const section of ["console-overview", "nodes"]) {
        await page.goto(`/demo/runtime/admin/${section}?mock=services&theme_preview=dark`);
        const row = page.locator(`[data-node-id="${consoleNodeFixture.id}"]`);
        for (const [selector, value] of [
          [".admin-entity-link-label", consoleNodeFixture.name],
          [".admin-entity-link-id", consoleNodeFixture.id],
        ]) {
          const text = row.locator(selector);
          await expect(text).toBeVisible();
          await expect(text).toHaveText(value);
          expect(await text.evaluate((node) => node.clientWidth)).toBeGreaterThan(40);
          expect(
            await text.evaluate((node) => node.scrollWidth - node.clientWidth)
          ).toBeLessThanOrEqual(1);
          expect(
            await text.evaluate((node) => node.scrollHeight - node.clientHeight)
          ).toBeLessThanOrEqual(1);
        }
        await row
          .locator("td")
          .first()
          .screenshot({
            path: testInfo.outputPath(`${section}-node-identity.png`),
            animations: "disabled",
          });
        expect(
          await page.evaluate(() => document.body.scrollWidth - innerWidth)
        ).toBeLessThanOrEqual(2);
      }
    });
  }
}

for (const [width, language] of [
  [1440, "ru"],
  [390, "ru"],
  [1440, "zh-hans"],
  [390, "zh-hans"],
] as const) {
  const locale: Record<string, string> = JSON.parse(
    readFileSync(`../locales/${language}.json`, "utf8")
  );
  const label = (key: string) => locale[`admin_${key}`];
  test(`node inventory, filters, pagination and bidirectional links at ${width}px in ${language}`, async ({
    page,
  }, testInfo) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 1000 });
    await installNodesApi(page, "normal", language);
    await page.goto(url);
    const section = page.locator(".console-nodes");
    await expect(section.locator("tbody tr")).toHaveCount(25);
    await expect(section.locator(".admin-list-toolbar-summary strong")).toHaveText("26");
    await section.getByRole("button", { name: label("services_next"), exact: true }).click();
    await expect(section.locator("tbody tr")).toHaveCount(1);
    await expect(page).toHaveURL(/nodes_page=1/);
    await page.goBack();
    await expect(section.locator("tbody tr")).toHaveCount(25);
    await section
      .getByRole("textbox", { name: label("console_nodes_search") })
      .fill("HK inventory node");
    await section.getByRole("button", { name: label("search"), exact: true }).click();
    await expect(section.locator("tbody tr")).toHaveCount(1);
    const select = section.getByRole("button", {
      name: label("console_node_metrics_control_status"),
      exact: true,
    });
    await select.click();
    await expect(
      page.getByRole("option", { name: label("console_nodes_status_unknown"), exact: true })
    ).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath(`nodes-menu-${width}.png`),
      fullPage: true,
      animations: "disabled",
    });
    await page.keyboard.press("Escape");
    await select.click();
    await page
      .getByRole("option", { name: label("console_nodes_status_unknown"), exact: true })
      .click();
    await expect(page).toHaveURL(/nodes_status=unknown/);
    await section.getByRole("button", { name: /HK inventory node/ }).click();
    const detail = page.getByRole("region", { name: label("console_nodes_detail") });
    await expect(detail).toBeVisible();
    await expect(
      detail.getByText(label("console_nodes_association_scope"), { exact: true })
    ).toBeVisible();
    await expect(detail.getByRole("link", { name: /Shared service/ })).toHaveAttribute(
      "href",
      /service_id=aaaaaaaa/
    );
    const customerLink = detail.getByRole("link", { name: String(customer.user_id), exact: true });
    const customerUrl = new URL((await customerLink.getAttribute("href"))!);
    expect(customerUrl.pathname).toBe(`/demo/runtime/admin/users/${customer.user_id}`);
    expect(customerUrl.searchParams.get("mock")).toBe("services");
    expect(customerUrl.searchParams.get("nodes_q")).toBe("HK inventory node");
    expect(customerUrl.searchParams.get("nodes_status")).toBe("unknown");
    const detailUrl = page.url();
    const newTab = page.context().waitForEvent("page", { timeout: 10000 });
    await customerLink.click({ modifiers: ["ControlOrMeta"] });
    const directPage = await newTab;
    await expect(directPage.locator(".admin-user-hero")).toContainText(customer.minishop_id!);
    await expect(directPage.locator(".user-services")).toBeVisible();
    await directPage.close();
    await expect(page).toHaveURL(detailUrl);
    await page.reload();
    await expect(
      detail.getByRole("heading", { name: "HK inventory node", exact: true })
    ).toBeFocused();
    await expect(page).toHaveURL(detailUrl);
    await detail.screenshot({ path: testInfo.outputPath(`node-detail-${width}.png`) });
    expect(
      await page.evaluate(() => document.body.scrollWidth - window.innerWidth)
    ).toBeLessThanOrEqual(2);
    await detail.getByRole("link", { name: /Shared service/ }).click();
    const service = page.getByRole("dialog", { name: label("console_service_detail") });
    await expect(
      service.getByRole("heading", { name: "Shared service", exact: true })
    ).toBeVisible();
    await expect(
      service.getByText(label("console_nodes_resource_scope"), { exact: true })
    ).toBeVisible();
    await service.getByRole("link", { name: /HK inventory node/ }).scrollIntoViewIfNeeded();
    await service.screenshot({ path: testInfo.outputPath(`node-service-resources-${width}.png`) });
    expect(
      await service
        .locator(".dialog-card")
        .evaluate((element) => element.scrollWidth - element.clientWidth)
    ).toBeLessThanOrEqual(2);
    await service.getByRole("link", { name: /HK inventory node/ }).click();
    await expect(detail).toBeVisible();
    await expect(page).toHaveURL(/service_id=aaaaaaaa/);
    await expect(page).toHaveURL(/nodes_status=unknown/);
    await page.reload();
    await expect(detail).toBeVisible();
    await page.goBack();
    await expect(service).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(detailUrl);
    await customerLink.click();
    const userServices = page.locator(".user-services");
    await expect(userServices).toBeVisible();
    await expect(page.locator(".admin-user-hero")).toContainText(customer.minishop_id!);
    await expect(page).toHaveURL(
      (value) => value.pathname === `/demo/runtime/admin/users/${customer.minishop_id}`
    );
    await expect(
      userServices.getByText(consoleNodeServiceFixture.service.id, { exact: true })
    ).toBeVisible();
    const loadedCustomerUrl = page.url();
    await page.reload();
    await expect(page.locator(".admin-user-hero")).toContainText(customer.minishop_id!);
    await expect(userServices.getByText("Shared service", { exact: true })).toBeVisible();
    await expect(page).toHaveURL(loadedCustomerUrl);
    expect(new URL(page.url()).searchParams.get("nodes_q")).toBe("HK inventory node");
    expect(new URL(page.url()).searchParams.get("nodes_status")).toBe("unknown");
    await page.screenshot({
      path: testInfo.outputPath(`node-customer-${width}.png`),
      fullPage: true,
      animations: "disabled",
    });
    expect(
      await page.evaluate(() => document.body.scrollWidth - window.innerWidth)
    ).toBeLessThanOrEqual(2);
    await userServices
      .getByRole("button", { name: label("console_service_detail"), exact: true })
      .click();
    await expect(
      service.getByRole("heading", { name: "Shared service", exact: true })
    ).toBeVisible();
    await service.getByRole("link", { name: /HK inventory node/ }).click();
    await expect(detail).toBeVisible();
    await expect(page).toHaveURL(/nodes_status=unknown/);
    await page.goBack();
    await expect(service).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(loadedCustomerUrl);
    await expect(page.locator(".admin-user-hero")).toContainText(customer.minishop_id!);
    await page.goBack();
    await expect(page).toHaveURL(detailUrl);
    await expect(detail).toBeVisible();
    await page.goForward();
    await expect(page).toHaveURL(loadedCustomerUrl);
    await expect(userServices.getByText("Shared service", { exact: true })).toBeVisible();
    await expect(page.locator(".admin-user-hero")).toContainText(customer.minishop_id!);
    await page.getByRole("button", { name: label("user_back"), exact: true }).click();
    await expect(page).toHaveURL(detailUrl);
    await expect(detail).toBeVisible();
    await detail.getByRole("button", { name: label("console_nodes_back"), exact: true }).click();
    await expect(section.getByRole("textbox")).toHaveValue("HK inventory node");
    await expect(select).toHaveText(label("console_nodes_status_unknown"));
    await page.reload();
    await expect(section.locator("tbody tr")).toHaveCount(1);
    await expect(section.getByRole("textbox")).toHaveValue("HK inventory node");
    await expect(select).toHaveText(label("console_nodes_status_unknown"));
    expect(
      await page.evaluate(() => document.body.scrollWidth - window.innerWidth)
    ).toBeLessThanOrEqual(2);
    expect(errors).toEqual([]);
  });
}

for (const width of [1440, 390]) {
  test(`node customer return retains a nonzero inventory page at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await installNodesApi(page);
    await page.goto(`${url}&nodes_q=node&nodes_page=1`);
    const section = page.locator(".console-nodes");
    await expect(section.locator("tbody tr")).toHaveCount(1);
    await section.getByRole("button", { name: /Other node 25/ }).click();
    const detailUrl = page.url();
    const detail = page.getByRole("region", { name: label("console_nodes_detail") });
    await detail.getByRole("link", { name: String(customer.user_id), exact: true }).click();
    await expect(page.locator(".admin-user-hero")).toContainText(customer.minishop_id!);
    await page.reload();
    await expect(page.locator(".admin-user-hero")).toContainText(customer.minishop_id!);
    await page.getByRole("button", { name: label("user_back"), exact: true }).click();
    await expect(page).toHaveURL(detailUrl);
    await detail.getByRole("button", { name: label("console_nodes_back"), exact: true }).click();
    await page.reload();
    await expect(page).toHaveURL(/nodes_page=1/);
    await expect(section.getByRole("textbox")).toHaveValue("node");
    await expect(section.locator("tbody tr")).toHaveCount(1);
    await expect(section.getByRole("button", { name: /Other node 25/ })).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath(`node-return-page-${width}.png`),
      fullPage: true,
    });
  });

  for (const source of ["users", "logs", "payments"]) {
    test(`${source} opens one customer history entry and returns at ${width}px`, async ({
      page,
    }, testInfo) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(
        `/demo/runtime/admin/${source}?mock=services&theme_preview=dark${source === "users" ? "&users_filter=active" : ""}`
      );
      const opener = page
        .locator(
          source === "users"
            ? "tr[data-user-id]:visible, .admin-user-mobile-card:visible"
            : source === "logs"
              ? ".admin-logs-user-btn:visible"
              : ".admin-payments-user-btn:visible"
        )
        .first();
      await expect(opener).toBeVisible();
      const sourceUrl = page.url();
      const historyLength = await page.evaluate(() => window.history.length);
      await opener.click();
      await expect(page).toHaveURL(/\/admin\/users\/ms_[0-9a-f]{32}(?:[?#].*)?$/);
      const customerUrl = page.url();
      const customerId = new URL(customerUrl).pathname.split("/").pop()!;
      await expect(page.locator(".admin-user-hero")).toContainText(customerId);
      expect(await page.evaluate(() => window.history.length)).toBe(historyLength + 1);
      await page.reload();
      await expect(page.locator(".admin-user-hero")).toContainText(customerId);
      await page.goBack();
      await expect(page).toHaveURL(sourceUrl);
      await expect(opener).toBeVisible();
      await page.goForward();
      await expect(page).toHaveURL(customerUrl);
      await expect(page.locator(".admin-user-hero")).toContainText(customerId);
      await page.getByRole("button", { name: label("user_back"), exact: true }).click();
      await expect(page).toHaveURL(sourceUrl);
      await expect(opener).toBeVisible();
      await page.screenshot({
        path: testInfo.outputPath(`${source}-returned-${width}.png`),
        fullPage: true,
      });
      expect(errors).toEqual([]);
    });
  }
}

for (const mode of ["empty", "unavailable", "stale", "failure"]) {
  test(`node ${mode} state remains distinct and failed reads can retry`, async ({ page }) => {
    await installNodesApi(page, mode);
    await page.goto(url);
    const section = page.locator(".console-nodes");
    if (mode === "failure") {
      await expect(section.getByRole("alert")).toHaveText(label("console_nodes_load_failed"));
      await section.getByRole("button", { name: label("refresh"), exact: true }).click();
      await expect(section.locator("tbody tr")).toHaveCount(25);
    } else {
      const key =
        mode === "empty"
          ? "console_nodes_empty"
          : mode === "unavailable"
            ? "console_nodes_inventory_unavailable"
            : "console_nodes_coverage_stale";
      await expect(section.getByText(label(key), { exact: true })).toBeVisible();
      if (mode !== "empty")
        await expect(section.locator(".admin-list-toolbar-summary")).toHaveCount(0);
    }
  });
}
