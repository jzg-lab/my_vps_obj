import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import {
  consoleNodeFixture,
  consoleNodeDetailFixture,
  consoleServiceResourcesFixture,
  consoleNodeServiceFixture,
  consoleNodeTrafficFixture,
} from "../src/lib/admin/consoleNodesFixtures";

const locale: Record<string, string> = JSON.parse(readFileSync("../locales/ru.json", "utf8"));
const label = (key: string) => locale[`admin_${key}`];
const url = "/demo/runtime/admin/nodes?mock=services&theme_preview=dark";
const customer = consoleNodeServiceFixture.customer!;

async function installNodesApi(page: Page, mode = "normal", language = "ru") {
  await page.addInitScript(
    ({ node, detail, resources, service, traffic, mode, language }) => {
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
      type LocalNodeMetadata = {
        display_name: string | null;
        region: string | null;
        provider: string | null;
      };
      const metadataStorageKey = "rw_demo_managed_node_metadata";
      let localMetadata = JSON.parse(localStorage.getItem(metadataStorageKey) || "{}") as Record<
        string,
        LocalNodeMetadata
      >;
      const withLocalMetadata = <T extends (typeof rows)[number]>(node: T) => ({
        ...node,
        ...(localMetadata[node.id] ?? { display_name: null, region: null, provider: null }),
      });
      const services =
        mode === "visual"
          ? [
              service.service,
              { ...service.service, id: "b".repeat(32), name: "Tokyo independent service" },
            ]
          : [service.service];
      let bundle: Bundle | undefined;
      let failOnce = mode === "failure";
      let failSecondHistory = false;
      window.addEventListener("fixture-history-failure", () => {
        failSecondHistory = true;
      });
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
                if (request.pathname.endsWith("/metadata")) {
                  const nodeId = request.pathname.split("/").at(-2) || "";
                  if (options?.method === "PUT") {
                    const fields = JSON.parse(String(options.body || "{}")) as LocalNodeMetadata;
                    localMetadata[nodeId] = fields;
                    localStorage.setItem(metadataStorageKey, JSON.stringify(localMetadata));
                    return {
                      ok: true,
                      node_id: nodeId,
                      ...fields,
                      updated_at: "2026-10-27T00:00:00Z",
                    };
                  }
                  if (options?.method === "DELETE") {
                    delete localMetadata[nodeId];
                    localStorage.setItem(metadataStorageKey, JSON.stringify(localMetadata));
                    return { ok: true, node_id: nodeId, deleted: true };
                  }
                }
                if (
                  mode === "visual" &&
                  request.pathname.endsWith(`/services/${"b".repeat(32)}/resources`)
                )
                  return {
                    ok: true,
                    ...resources,
                    service_id: "b".repeat(32),
                    nodes: [{ ...node, id: "second", name: "Tokyo node" }],
                  };
                if (mode === "visual" && request.pathname.endsWith("/traffic")) {
                  const second = request.pathname.includes("b".repeat(32));
                  if (second && failSecondHistory) throw new Error("history_unavailable");
                  return {
                    ok: true,
                    service_id: second ? "b".repeat(32) : service.service.id,
                    start_date: "2026-10-23",
                    end_date: "2026-10-24",
                    availability: "partial",
                    days: [
                      { date: "2026-10-23", bytes: second ? 0 : 2 ** 30 },
                      { date: "2026-10-24", bytes: second ? null : 2 ** 31 },
                    ],
                  };
                }
                if (request.pathname.startsWith("/admin/console/nodes/")) {
                  const selectedNode = rows.find((row) => request.pathname.endsWith(`/${row.id}`));
                  return selectedNode
                    ? {
                        ok: true,
                        ...detail,
                        node: withLocalMetadata(selectedNode),
                        ...(mode === "visual" ? { traffic } : {}),
                      }
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
                  return { ok: true, services, total: services.length };
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
                    nodes: selected.slice(page * 25, (page + 1) * 25).map(withLocalMetadata),
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
      node:
        mode === "visual"
          ? {
              ...consoleNodeFixture,
              window_traffic_bytes: 7 * 1024 ** 3,
              window_traffic_quality: "reported",
              daily_traffic: [1, 1.4, 0.8, 1.5, 0.9, 0.4, 1].map((value, day) => ({
                date: `2026-10-${20 + day}`,
                bytes: value * 1024 ** 3,
              })),
              speed_history: [3, 5, 4, 8, 6, 5].map((value, index) => ({
                sampled_at: `2026-10-26T${String(3 + index * 2).padStart(2, "0")}:00:00Z`,
                rx_bytes_per_second: value * 1024 ** 2,
                tx_bytes_per_second: (value / 2) * 1024 ** 2,
              })),
            }
          : consoleNodeFixture,
      traffic: {
        ...consoleNodeTrafficFixture,
        preset: "7d",
        start_date: "2026-10-20",
        end_date: "2026-10-26",
        start_at: "2026-10-20T00:00:00Z",
        end_at: "2026-10-26T23:59:59Z",
      },
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
        const copy: Record<string, string> = JSON.parse(
          readFileSync(`../locales/${language}.json`, "utf8")
        );
        await page
          .getByRole("button", { name: copy.admin_console_nodes_view_table, exact: true })
          .click();
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
    await section
      .locator("[data-node-card-id]")
      .getByRole("button", { name: /HK inventory node/ })
      .click();
    const detail = page.getByRole("region", { name: label("console_nodes_detail") });
    await expect(detail).toBeVisible();
    await expect(detail.locator("[data-node-daily-traffic]")).toContainText(
      label("console_visual_history_missing")
    );
    await expect(detail.locator("[data-node-daily-traffic]")).toContainText(
      label("console_node_daily_scope")
    );
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
      service.getByRole("heading", { name: "Shared service", level: 3, exact: true })
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
    const relations = userServices.locator("[data-customer-relations]");
    await expect(relations.locator(".customer-identity")).toContainText(String(customer.user_id));
    await expect(relations.locator(".relation-service")).toHaveAttribute(
      "href",
      /service_id=aaaaaaaa/
    );
    await expect(relations.locator(".relation-nodes a")).toHaveAttribute(
      "href",
      new RegExp(`node_id=${consoleNodeFixture.id}`)
    );
    await expect(relations).toContainText(label("console_customer_relations_scope"));
    await expect(page.locator(".admin-user-hero")).toContainText(customer.minishop_id!);
    await expect(page).toHaveURL(
      (value) => value.pathname === `/demo/runtime/admin/users/${customer.minishop_id}`
    );
    await userServices.locator(":scope > details > summary").click();
    await expect(
      userServices
        .locator(":scope > details")
        .getByText(consoleNodeServiceFixture.service.id, { exact: true })
    ).toBeVisible();
    const loadedCustomerUrl = page.url();
    await page.reload();
    await expect(page.locator(".admin-user-hero")).toContainText(customer.minishop_id!);
    await expect(
      userServices
        .locator(".customer-service-summaries")
        .getByRole("heading", { name: "Shared service", exact: true })
    ).toBeVisible();
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
    await userServices.locator(":scope > details > summary").click();
    await userServices
      .getByRole("button", { name: label("console_service_detail"), exact: true })
      .click();
    await expect(
      service.getByRole("heading", { name: "Shared service", level: 3, exact: true })
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
    await expect(
      userServices
        .locator(".customer-service-summaries")
        .getByRole("heading", { name: "Shared service", exact: true })
    ).toBeVisible();
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
  test(`managed node labels save locally and clear cleanly at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await installNodesApi(page);
    await page.goto(url);
    const section = page.locator(".console-nodes");
    const card = section.locator(`[data-node-card-id="${consoleNodeFixture.id}"]`);
    await card.getByRole("button", { name: /HK inventory node/ }).click();
    const detail = page.getByRole("region", { name: label("console_nodes_detail") });
    const edit = detail.getByRole("button", {
      name: label("console_nodes_metadata_edit"),
      exact: true,
    });
    await edit.click();
    const dialog = page.getByRole("dialog", { name: label("console_nodes_metadata_title") });
    await expect(dialog).toBeVisible();
    await dialog
      .getByRole("textbox", { name: label("console_nodes_display_name"), exact: true })
      .fill("Tokyo relay");
    await dialog
      .getByRole("textbox", { name: label("console_nodes_region"), exact: true })
      .fill("Tokyo");
    await dialog
      .getByRole("textbox", { name: label("console_nodes_provider"), exact: true })
      .fill("Example Networks");
    await dialog
      .getByRole("button", { name: label("console_nodes_metadata_save"), exact: true })
      .click();
    await expect(dialog).not.toBeVisible();
    await expect(detail.getByRole("heading", { name: "Tokyo relay", exact: true })).toBeVisible();
    await expect(detail).toContainText("Tokyo");
    await expect(detail).toContainText("Example Networks");
    await expect(edit).toBeFocused();
    await page.screenshot({
      path: testInfo.outputPath(`node-metadata-saved-${width}.png`),
      fullPage: true,
      animations: "disabled",
    });

    await page.reload();
    await expect(detail.getByRole("heading", { name: "Tokyo relay", exact: true })).toBeVisible();
    await edit.click();
    const clearDialog = page.getByRole("dialog", { name: label("console_nodes_metadata_title") });
    await clearDialog.screenshot({
      path: testInfo.outputPath(`node-metadata-dialog-${width}.png`),
      animations: "disabled",
    });
    const surface = clearDialog.locator(".dialog-card");
    await expect(surface).toBeVisible();
    expect(
      await surface.evaluate((element) => element.scrollWidth - element.clientWidth)
    ).toBeLessThanOrEqual(2);
    expect(await page.evaluate(() => document.body.scrollWidth - innerWidth)).toBeLessThanOrEqual(
      2
    );
    await clearDialog
      .getByRole("button", { name: label("console_nodes_metadata_clear"), exact: true })
      .click();
    await expect(clearDialog).not.toBeVisible();
    await expect(
      detail.getByRole("heading", { name: "HK inventory node", exact: true })
    ).toBeVisible();
  });

  test(`node customer return retains a nonzero inventory page at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await installNodesApi(page);
    await page.goto(`${url}&nodes_q=node&nodes_page=1`);
    const section = page.locator(".console-nodes");
    await expect(section.locator("tbody tr")).toHaveCount(1);
    await section
      .locator("[data-node-card-id]")
      .getByRole("button", { name: /Other node 25/ })
      .click();
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
    await expect(
      section.locator("[data-node-card-id]").getByRole("button", { name: /Other node 25/ })
    ).toBeVisible();
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

for (const width of [390, 1440]) {
  test(`node cards are the default and can switch to an audit table at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await installNodesApi(page, "normal", "zh-hans");
    await page.goto(url);
    const copy: Record<string, string> = JSON.parse(
      readFileSync("../locales/zh-hans.json", "utf8")
    );
    const section = page.locator(".console-nodes");
    const card = section.locator(`[data-node-card-id="${consoleNodeFixture.id}"]`);
    await expect(card).toBeVisible();
    await expect(section.locator("table.admin-table-fixed")).toBeHidden();
    await expect(card).not.toContainText(copy.admin_console_node_visuals_history);
    await expect(card).toContainText(copy.admin_console_unknown);
    await card.screenshot({ path: testInfo.outputPath("node-card-default.png") });
    await expect(card.locator("[data-copyable-value]")).toBeHidden();
    await card.locator(".node-auxiliary summary").click();
    await expect(card.locator("[data-copyable-value]")).toHaveText(consoleNodeFixture.id);
    await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
    await card.locator("[data-copyable-value]").click();
    await expect
      .poll(() => page.evaluate(() => navigator.clipboard.readText()))
      .toBe(consoleNodeFixture.id);
    await expect(
      section.getByRole("status").filter({ hasText: copy.admin_value_copied })
    ).toBeVisible();
    await card.locator(".node-auxiliary summary").click();
    await section
      .getByRole("button", { name: copy.admin_console_nodes_view_table, exact: true })
      .click();
    await expect(section.locator("table.admin-table-fixed")).toBeVisible();
    await expect(card).toBeHidden();
    await section
      .getByRole("button", { name: copy.admin_console_nodes_view_cards, exact: true })
      .click();
    await card.getByRole("button", { name: /HK inventory node/ }).click();
    await expect(page.getByRole("region", { name: copy.admin_console_nodes_detail })).toBeVisible();
    await expect(page.locator("[data-node-metric-visuals]")).toBeVisible();
    expect(await page.evaluate(() => document.body.scrollWidth - innerWidth)).toBeLessThanOrEqual(
      2
    );
  });
}

for (const width of [1440, 390]) {
  test(`customer relations and node history stay on their own detail pages at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await installNodesApi(page, "visual", "zh-hans");
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(
      `/demo/runtime/admin/users/${customer.user_id}?mock=services&theme_preview=dark`
    );
    const relations = page.locator("[data-customer-relations]");
    await expect(relations.locator(".relation-service")).toHaveCount(2);
    await expect(relations.locator(".relation-nodes a")).toHaveCount(2);
    await expect(relations).toContainText("Tokyo independent service");
    await expect(relations).toContainText("Tokyo node");
    await relations.screenshot({ path: testInfo.outputPath(`customer-relations-${width}.png`) });
    expect(await page.evaluate(() => document.body.scrollWidth - innerWidth)).toBeLessThanOrEqual(
      2
    );
    const usage = page.locator(".customer-usage");
    await expect(usage.locator("canvas")).toBeVisible();
    await expect(page.locator(".customer-service-summaries .quota")).toHaveCount(2);
    await usage.locator("summary").click();
    await expect(usage.locator("tbody tr").first().locator("td")).toHaveText([
      "10-23",
      "1 GiB",
      "0 B",
    ]);
    await expect(usage.locator("tbody tr").last().locator("td").last()).not.toHaveText("0 B");
    await usage.screenshot({ path: testInfo.outputPath(`customer-usage-${width}.png`) });
    await page.locator(".customer-service-summaries").screenshot({
      path: testInfo.outputPath(`customer-quotas-${width}.png`),
    });
    await page.evaluate(() => window.dispatchEvent(new Event("fixture-history-failure")));
    await usage.getByRole("button", { name: "刷新", exact: true }).click();
    await expect(usage).toHaveAttribute("aria-busy", "false");
    await expect(usage.locator("tbody tr").first().locator("td").nth(1)).toHaveText("1 GiB");
    await expect(usage.locator("tbody tr").first().locator("td").last()).not.toHaveText("0 B");
    await expect(
      usage.getByRole("status").filter({ hasText: "Tokyo independent service" })
    ).toBeVisible();
    await relations.locator(".relation-nodes a").first().click();
    const metrics = page.locator(".node-system-metrics");
    const speed = metrics.locator(".metric-history-card");
    const daily = metrics.locator("[data-node-daily-traffic]");
    await expect(speed.locator("canvas")).toBeVisible();
    await expect(daily.locator("canvas")).toBeVisible();
    await expect(speed.locator("[data-speed-summary]")).toContainText("67.1 Mbps");
    await expect(daily).toContainText("7 GiB");
    await speed.screenshot({ path: testInfo.outputPath(`node-speed-${width}.png`) });
    await page.screenshot({ path: testInfo.outputPath(`node-page-${width}.png`) });
    await daily.screenshot({ path: testInfo.outputPath(`node-daily-${width}.png`) });
    const order = await metrics.evaluate((element) => {
      const speed = element.querySelector(".metric-history-card")!.getBoundingClientRect();
      const daily = element.querySelector("[data-node-daily-traffic]")!.getBoundingClientRect();
      const technical = element.querySelector("[data-node-metric]")!.getBoundingClientRect();
      return speed.bottom <= daily.top && daily.bottom <= technical.top;
    });
    expect(order).toBe(true);
    expect(await page.evaluate(() => document.body.scrollWidth - innerWidth)).toBeLessThanOrEqual(
      2
    );
    await expect(metrics.getByRole("heading", { name: "节点日流量", exact: true })).toBeVisible();
    if (width < 1024) await page.locator(".admin-mobile-toggle").click();
    await page.locator('.admin-sidebar [data-admin-section="nodes"]').click();
    await expect(page).not.toHaveURL(/node_id=/);
    await expect(page.locator(".node-detail")).toHaveCount(0);
    await expect(page.locator(".metric-history-card")).toHaveCount(0);
    await expect(page.locator("[data-node-traffic-comparison]")).toBeVisible();
    await page
      .locator(`[data-node-card-id="${consoleNodeFixture.id}"]`)
      .getByRole("button", { name: /HK inventory node/ })
      .click();
    await expect(page.locator(".metric-history-card")).toBeVisible();
    expect(errors).toEqual([]);
  });
}
