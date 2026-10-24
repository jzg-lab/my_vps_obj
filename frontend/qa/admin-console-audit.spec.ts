import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { setTimeout } from "node:timers/promises";
import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";
import type { components, paths } from "../src/lib/api/openapi.generated";
import { serviceBytes } from "../src/lib/admin/servicePlans";

type Accounts = components["schemas"]["ConsoleAccountOperationsOut"];
type Nodes = components["schemas"]["ConsoleNodesListOut"];
type Assets = components["schemas"]["ConsoleNodeAssetsListOut"];
type Account = paths["/api/me"]["get"]["responses"][200]["content"]["application/json"];
type Label = (key: string) => string;
const accountPath = "/api/admin/console/account-operations";
const nodesPath = "/api/admin/console/nodes";
const assetsPath = "/api/admin/console/node-assets";
const adminEmail = "runes.admin@example.com";
let responses: { path: string; status: number; retryAfter: string | null }[];
let errors: string[];
let blocked: string[];
let requestCount: number;
let language: string | null;

test.beforeEach(async ({ context, page, baseURL }, info) => {
  if (!baseURL || !["localhost", "127.0.0.1", "[::1]"].includes(new URL(baseURL).hostname))
    throw new Error("Live audit QA requires the isolated loopback development stack.");
  // Match the existing live QA: 120 requests/account per 60s, with a fresh window per case.
  info.setTimeout(info.timeout + 60_000);
  responses = [];
  errors = [];
  blocked = [];
  requestCount = 0;
  language = null;
  await setTimeout(60_000);
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/")) requestCount++;
  });
  page.on("response", (response) => {
    const path = new URL(response.url()).pathname;
    if (path.startsWith("/api/"))
      responses.push({
        path,
        status: response.status(),
        retryAfter: response.headers()["retry-after"] ?? null,
      });
  });
  await context.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const login = request.method() === "POST" && url.pathname === "/api/auth/email/password";
    if (url.origin === new URL(baseURL).origin && (request.method() === "GET" || login))
      await route.continue();
    else {
      blocked.push(`${request.method()} ${url.pathname}`);
      await route.abort("blockedbyclient");
    }
  });
});

test.afterEach(async ({ page }, info) => {
  await info.attach("http-statuses", {
    body: JSON.stringify({ responses, requestCount, blocked, errors, language }, null, 2),
    contentType: "application/json",
  });
  expect.soft(responses.filter(({ status }) => status === 429)).toEqual([]);
  expect
    .soft(requestCount, "Stay inside the existing 120-request account budget.")
    .toBeLessThanOrEqual(120);
  expect.soft(blocked, "No business, language or role writes are permitted.").toEqual([]);
  expect.soft(errors).toEqual([]);
  if (language) await expect.soft(page.locator("html")).toHaveAttribute("lang", language);
});

async function localeFor(page: Page) {
  const lang = (await page.locator("html").getAttribute("lang"))?.toLowerCase() || "en";
  expect(["en", "ru", "zh-hans"]).toContain(lang);
  return JSON.parse(
    readFileSync(resolve(__dirname, `../../locales/${lang}.json`), "utf8")
  ) as Record<string, string>;
}

async function login(page: Page, info: TestInfo) {
  await page.goto("/home");
  await expect(page.locator(".auth-screen")).toBeVisible({ timeout: 20_000 });
  const loginLocale = await localeFor(page);
  await page.getByRole("button", { name: loginLocale.wa_login_use_password, exact: true }).click();
  await page.locator('input[autocomplete="email"]').fill(adminEmail);
  await page.locator('input[autocomplete="current-password"]').fill("Minishop-Dev-2026!");
  const pending = page.waitForResponse(
    (response) => new URL(response.url()).pathname === "/api/auth/email/password"
  );
  await page
    .getByRole("button", { name: loginLocale.wa_login_password_submit, exact: true })
    .click();
  const response = await pending;
  expect(response.status()).toBe(200);
  expect((await response.json()).ok).toBe(true);
  await expect(page.locator(".auth-screen")).toHaveCount(0);
  await expect(page.locator(".app-shell")).toBeVisible();
  const me = await page.context().request.get("/api/me?fresh=true");
  requestCount++;
  responses.push({
    path: "/api/me",
    status: me.status(),
    retryAfter: me.headers()["retry-after"] ?? null,
  });
  expect(me.status()).toBe(200);
  const account = (await me.json()) as Account;
  expect(account.ok).toBe(true);
  expect(account.user.email).toBe(adminEmail);
  expect(account.user.is_admin).toBe(true);
  language = account.user.language_code ?? null;
  expect(["en", "ru", "zh-hans"]).toContain(language);
  expect(Number.isSafeInteger(account.user.id)).toBe(true);
  await expect(page.locator("html")).toHaveAttribute("lang", language!);
  info.annotations.push({ type: "unchanged-account-language", description: language! });
  const locale = await localeFor(page);
  const at: Label = (key) => {
    const value = locale[`admin_${key}`];
    expect(value, `Missing ${language} translation: admin_${key}`).toBeTruthy();
    return value;
  };
  return { at, userId: String(account.user.id) };
}

async function read<T>(
  page: Page,
  path: string,
  action: () => Promise<unknown>,
  filters: Record<string, string> = {}
): Promise<T> {
  const [response] = await Promise.all([
    page.waitForResponse((response) => {
      const url = new URL(response.url());
      return (
        response.request().method() === "GET" &&
        url.pathname === path &&
        Object.entries(filters).every(([key, value]) => url.searchParams.get(key) === value)
      );
    }),
    action(),
  ]);
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.ok).toBe(true);
  return body as T;
}

async function capture(page: Page, info: TestInfo, name: string, surface?: Locator) {
  expect(
    await page.evaluate(
      () => Math.max(document.body.scrollWidth, document.documentElement.scrollWidth) - innerWidth
    )
  ).toBeLessThanOrEqual(2);
  if (surface) {
    await expect(surface).toBeVisible();
    expect(
      await surface.evaluate((element) => {
        const box = element.getBoundingClientRect();
        return (
          box.left >= -2 &&
          box.right <= innerWidth + 2 &&
          element.scrollWidth - element.clientWidth <= 2
        );
      })
    ).toBe(true);
  }
  await page.screenshot({
    path: info.outputPath(`${name}.png`),
    fullPage: true,
    animations: "disabled",
  });
}

async function choose(
  page: Page,
  host: Locator,
  at: Label,
  field: string,
  option: string,
  info: TestInfo
) {
  await host.getByRole("button", { name: at(field), exact: true }).click();
  const menu = page.locator('.admin-select-content[data-state="open"]');
  await capture(page, info, `${field}-${option}-menu`, menu);
  await menu.getByRole("option", { name: at(option), exact: true }).click();
}

async function accountList(host: Locator, data: Accounts, at: Label) {
  await expect(host).toHaveAttribute("aria-busy", "false");
  await expect(host.getByRole("alert")).toHaveCount(0);
  await expect(host.locator(".admin-list-toolbar-summary strong")).toHaveText(String(data.total));
  await expect(host.locator(".admin-pagination-count")).toHaveText([
    `${at("services_page")} ${data.page + 1} ${at("services_of")} ${Math.max(1, Math.ceil(data.total / data.page_size))}`,
    `${at("account_ops_count")} ${data.total}`,
  ]);
  await expect(host.locator("tbody tr")).toHaveCount(data.operations.length);
  expect(data.total).toBeGreaterThanOrEqual(data.operations.length);
  if (!data.operations.length)
    await expect(host.getByText(at("account_ops_empty"), { exact: true })).toBeVisible();
  for (const operation of data.operations) {
    const row = host.locator(`[data-account-operation-id="${operation.id}"]`);
    await expect(row.locator("[data-account-target] > span")).toHaveText(
      String(operation.target_id)
    );
    await expect(row.locator(".admin-badge")).toHaveText(
      at(`console_ops_status_${operation.status}`)
    );
    await expect(row.locator(".admin-badge + small")).toHaveText(
      `${at("console_ops_attempt_count")}: ${operation.attempt_count}`
    );
    if (operation.archived || operation.user_id === null) {
      await expect(row.getByTitle(at("account_ops_open_customer"), { exact: true })).toHaveCount(0);
      await expect(
        row.getByRole("button", { name: at("account_ops_review_customer"), exact: true })
      ).toHaveCount(0);
    }
  }
}

for (const width of [1440, 390]) {
  test.describe(`live audit at ${width}px`, () => {
    test.use({ viewport: { width, height: 1000 } });

    test("account operations show real totals, filters and optional existing detail", async ({
      page,
    }, info) => {
      const { at, userId } = await login(page, info);
      const host = page.locator(".account-operations-list");
      const initial = await read<Accounts>(page, accountPath, () =>
        page.goto("/admin/console-operations?operations_view=accounts")
      );
      await accountList(host, initial, at);
      await capture(page, info, "account-list");
      const first = initial.operations[0];
      if (first) {
        const detail = await read<{
          operation: components["schemas"]["ConsoleAccountOperationOut"];
        }>(page, `${accountPath}/${first.id}`, () =>
          host
            .locator(`[data-account-operation-id="${first.id}"] [data-account-record] button`)
            .click()
        );
        expect(detail.operation.id).toBe(first.id);
        const dialog = page.getByRole("dialog", { name: at("account_ops_detail"), exact: true });
        await expect(dialog.locator(".account-operation-detail")).toHaveAttribute(
          "aria-busy",
          "false"
        );
        await expect(dialog.getByRole("alert")).toHaveCount(0);
        await expect(dialog.locator("[data-account-operation-code]")).toHaveText(first.id);
        await expect(dialog.locator(".admin-badge")).toHaveText(
          at(`console_ops_status_${detail.operation.status}`)
        );
        await capture(page, info, "account-detail", dialog.locator(".dialog-card"));
        await page.keyboard.press("Escape");
        await expect(dialog).toHaveCount(0);
        await accountList(host, initial, at);
      } else
        info.annotations.push({
          type: "coverage",
          description:
            "No real account audit records: empty state asserted; detail branch not exercised or manufactured.",
        });

      const filters: Record<string, string> = {
        status: "unknown",
        source: "all",
        archived: "all",
        needs_attention: "false",
      };
      let data = await read<Accounts>(
        page,
        accountPath,
        () => choose(page, host, at, "status", "console_ops_status_unknown", info),
        filters
      );
      expect(data.operations.every((item) => item.status === "unknown")).toBe(true);
      await accountList(host, data, at);
      filters.source = "administrator";
      data = await read<Accounts>(
        page,
        accountPath,
        () => choose(page, host, at, "account_ops_source", "console_ops_administrator", info),
        filters
      );
      expect(data.operations.every((item) => item.source === "administrator")).toBe(true);
      await accountList(host, data, at);
      filters.archived = "exclude";
      data = await read<Accounts>(
        page,
        accountPath,
        () =>
          choose(
            page,
            host,
            at,
            "console_global_archived",
            "console_global_archived_exclude",
            info
          ),
        filters
      );
      expect(data.operations.every((item) => !item.archived)).toBe(true);
      await accountList(host, data, at);
      filters.needs_attention = "true";
      data = await read<Accounts>(
        page,
        accountPath,
        () =>
          host.getByRole("checkbox", { name: at("console_global_attention"), exact: true }).check(),
        filters
      );
      expect(data.operations.every((item) => item.needs_attention)).toBe(true);
      await accountList(host, data, at);
      filters.user_id = String(first?.target_id ?? userId);
      filters.actor_id = String(first?.actor_id ?? userId);
      await host
        .getByRole("textbox", { name: at("account_ops_target"), exact: true })
        .fill(filters.user_id);
      await host
        .getByRole("textbox", { name: at("services_actor"), exact: true })
        .fill(filters.actor_id);
      data = await read<Accounts>(
        page,
        accountPath,
        () => host.getByRole("button", { name: at("search"), exact: true }).click(),
        filters
      );
      expect(
        data.operations.every(
          (item) =>
            String(item.target_id) === filters.user_id && String(item.actor_id) === filters.actor_id
        )
      ).toBe(true);
      await accountList(host, data, at);
      data = await read<Accounts>(page, accountPath, () => page.reload(), filters);
      await accountList(host, data, at);
      await expect(host.getByRole("button", { name: at("status"), exact: true })).toHaveText(
        at("console_ops_status_unknown")
      );
      await expect(
        host.getByRole("textbox", { name: at("account_ops_target"), exact: true })
      ).toHaveValue(filters.user_id);
      await expect(
        host.getByRole("textbox", { name: at("services_actor"), exact: true })
      ).toHaveValue(filters.actor_id);
      await capture(page, info, "account-filtered");
    });

    test("node today, 7d and 30d windows match real response evidence", async ({ page }, info) => {
      const { at } = await login(page, info);
      const host = page.locator(".console-nodes");
      for (const preset of ["today", "7d", "30d"] as const) {
        const data = await read<Nodes>(
          page,
          nodesPath,
          () =>
            preset === "today"
              ? page.goto("/admin/nodes")
              : choose(
                  page,
                  host,
                  at,
                  "console_nodes_window_label",
                  `console_nodes_window_${preset}`,
                  info
                ),
          { traffic_window: preset }
        );
        await expect(host).toHaveAttribute("aria-busy", "false");
        await expect(host.getByRole("alert")).toHaveCount(0);
        await expect(host.locator("tbody tr")).toHaveCount(data.nodes.length);
        await expect(
          host.getByRole("button", { name: at("console_nodes_window_label"), exact: true })
        ).toHaveText(at(`console_nodes_window_${preset}`));
        if (data.total !== null)
          await expect(host.locator(".admin-list-toolbar-summary strong")).toHaveText(
            String(data.total)
          );
        expect(
          data.traffic,
          "The real API must include the selected window's evidence."
        ).not.toBeNull();
        const traffic = data.traffic!;
        expect(traffic.preset).toBe(preset);
        expect(traffic.timezone).toBe("UTC");
        expect(traffic.history_completeness).toBe("unknown_not_service_billing");
        const duration =
          Date.parse(`${traffic.end_date}T00:00:00Z`) -
          Date.parse(`${traffic.start_date}T00:00:00Z`);
        expect(duration / 86_400_000 + 1).toBe(preset === "today" ? 1 : preset === "7d" ? 7 : 30);
        for (const boundary of [traffic.start_at, traffic.end_at])
          await expect(host.locator("[data-traffic-boundaries]")).toContainText(
            new Date(boundary).toISOString().replace("T", " ").replace("Z", " UTC")
          );
        await expect(host.locator(".window-evidence .admin-badge")).toHaveText(
          at(`console_nodes_availability_${traffic.availability}`)
        );
        await expect(host.locator(".window-evidence")).toContainText(
          at("console_nodes_window_source")
        );
        await expect(host.locator(".window-evidence")).toContainText(
          at("console_nodes_window_history")
        );
        if (!data.nodes.length) {
          const key =
            data.coverage === "unavailable"
              ? "console_nodes_inventory_unavailable"
              : data.total === 0
                ? "console_nodes_empty"
                : "console_nodes_no_known_matches";
          await expect(host.getByText(at(key), { exact: true })).toBeVisible();
        }
        for (const [index, node] of data.nodes.entries()) {
          const cell = host.locator("td[data-window-quality]").nth(index);
          await expect(host.locator("tbody tr").nth(index)).toContainText(node.id);
          if (traffic.availability === "unavailable" || traffic.availability === "unconfigured") {
            await expect(cell).toHaveAttribute("data-window-quality", "missing");
            await expect(cell).toHaveText(at("console_nodes_window_missing"));
          } else if (
            node.window_traffic_quality !== "reported" ||
            node.window_traffic_bytes === null
          ) {
            await expect(cell).toHaveText(
              at(
                node.window_traffic_quality === "invalid"
                  ? "console_nodes_window_invalid"
                  : "console_nodes_window_missing"
              )
            );
          } else {
            await expect(cell).toHaveAttribute("data-window-quality", "reported");
            await expect(cell).toContainText(serviceBytes(node.window_traffic_bytes));
          }
        }
        await capture(page, info, `node-window-${preset}`);
      }
    });

    test("pending inventory opens and cancels registration without persisting", async ({
      page,
    }, info) => {
      const { at } = await login(page, info);
      const data = await read<Assets>(page, assetsPath, () =>
        page.goto("/admin/nodes?nodes_view=unmanaged")
      );
      const host = page.getByRole("region", {
        name: at("console_node_assets_pending"),
        exact: true,
      });
      await expect(host).toHaveAttribute("aria-busy", "false");
      await expect(host.getByRole("alert")).toHaveCount(0);
      await expect(host.locator(".admin-list-toolbar-summary strong")).toHaveText(
        String(data.total)
      );
      await expect(host.locator("tbody tr")).toHaveCount(data.items.length);
      await expect(host).toContainText(at("console_node_assets_scope"));
      if (!data.items.length)
        await expect(
          host.getByText(at("console_node_assets_empty"), { exact: true })
        ).toBeVisible();
      for (const item of data.items) {
        const row = host.locator(`[data-asset-id="${item.id}"]`);
        await expect(row).toContainText(item.name);
        await expect(row).toContainText(item.address);
        await expect(row.locator(".admin-badge")).toHaveText(at("console_node_assets_unmanaged"));
      }
      await capture(page, info, "pending-inventory");
      const add = host.getByRole("button", { name: at("console_node_assets_add"), exact: true });
      await add.click();
      const dialog = page.getByRole("dialog", { name: at("console_node_assets_add"), exact: true });
      await expect(
        dialog.getByRole("button", { name: at("console_node_assets_save"), exact: true })
      ).toBeDisabled();
      for (const key of ["name", "address", "notes"])
        await expect(
          dialog.getByRole("textbox", { name: at(`console_node_assets_${key}`), exact: true })
        ).toHaveValue("");
      await expect(dialog).toContainText(at("console_node_assets_scope"));
      await capture(page, info, "pending-registration", dialog.locator(".dialog-card"));
      await dialog
        .getByRole("button", { name: at("cancel"), exact: true })
        .last()
        .click();
      await expect(dialog).toHaveCount(0);
      await expect(add).toBeFocused();
      await expect(host.locator("tbody tr")).toHaveCount(data.items.length);
      await expect(host.locator(".admin-list-toolbar-summary strong")).toHaveText(
        String(data.total)
      );
      await capture(page, info, "pending-cancelled");
    });

    test("advanced maintenance explicitly reports an unconfigured destination", async ({
      page,
    }, info) => {
      const { at } = await login(page, info);
      const data = await read<components["schemas"]["ConsoleMaintenanceOut"]>(
        page,
        "/api/admin/console/maintenance",
        () => page.goto("/admin/advanced-maintenance")
      );
      expect(
        data.destination,
        "This case requires an unconfigured local destination; it does not edit configuration."
      ).toBeNull();
      const host = page.getByRole("region", { name: at("maintenance_title"), exact: true });
      await expect(host).toHaveAttribute("aria-busy", "false");
      await expect(host.getByRole("alert")).toHaveCount(0);
      await expect(host.getByRole("status")).toHaveText(at("maintenance_unconfigured"));
      await expect(host).toContainText(at("maintenance_auth"));
      await expect(host.getByRole("link")).toHaveCount(0);
      await capture(page, info, "maintenance-unconfigured", host);
    });
  });
}
