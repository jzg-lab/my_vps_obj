import { expect, test, type Page } from "@playwright/test";
import { accountOperationFixture } from "../src/lib/admin/consoleAccountOperationsFixtures";
import { consoleAccountOperationsDemoResponse } from "../src/lib/webapp/mockApi/consoleAccountOperations";
import { capture, choose, labels, query, type Language } from "./fixtures/resource-operations";

declare global {
  interface Window {
    __accountOperationsRequest: (
      path: string,
      method: string
    ) => Promise<{ handled: boolean; value?: unknown }>;
  }
}

// Explicit mock audit rows exercise browser consumers, not account synchronization or backend persistence.
async function installAccounts(page: Page, language: Language) {
  const archived = accountOperationFixture({
    id: "d".repeat(32),
    user_id: null,
    archived: true,
    needs_attention: false,
    error_code: "private-history-token",
  });
  const worker = accountOperationFixture({
    id: "e".repeat(32),
    source: "worker",
    actor_id: null,
    before_banned: null,
    status: "pending",
    attempt_count: 0,
    attempted_at: null,
    first_failed_at: null,
    error_code: null,
    needs_attention: false,
  });
  const success = accountOperationFixture({
    id: "f".repeat(32),
    status: "succeeded",
    before_banned: true,
    desired_banned: false,
    needs_attention: false,
    completed_at: "2026-10-24T00:03:00Z",
    error_code: null,
  });
  const records = [
    ...Array.from({ length: 26 }, (_, index) =>
      accountOperationFixture({ id: (index + 1).toString(16).padStart(32, "0") })
    ),
    archived,
    worker,
    success,
  ];
  const calls: { path: string; method: string }[] = [];
  const errors: string[] = [];
  const unexpected: string[] = [];
  let fail = false;
  let hold = false;
  let release: (() => void) | undefined;
  page.on("pageerror", (error) => errors.push(error.message));
  await page.context().route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith("/api/")) {
      unexpected.push(url.pathname);
      return route.abort();
    }
    return ["localhost", "127.0.0.1"].includes(url.hostname) ? route.continue() : route.abort();
  });
  await page.exposeFunction("__accountOperationsRequest", async (path: string, method: string) => {
    calls.push({ path, method });
    if (path === "/admin/users/910002/access-sync")
      return {
        handled: true,
        value: {
          ok: true,
          access_sync: {
            pending: true,
            last_error: "panel_access_unconfirmed",
            attempted_at: records[0].attempted_at,
          },
        },
      };
    const value = consoleAccountOperationsDemoResponse(path, { method }, records);
    if (value === undefined) return { handled: false };
    if (fail) return { handled: true, value: { ok: false, error: "private-api-token" } };
    if (hold && path.startsWith("/admin/console/account-operations?")) {
      hold = false;
      await new Promise<void>((resolve) => {
        release = resolve;
      });
    }
    return { handled: true, value };
  });
  await page.addInitScript(
    ({ language }) => {
      localStorage.setItem("rw_minishop_demo_language", language);
      type Props = { api: (path: string, options?: RequestInit) => Promise<unknown> };
      type Bundle = { mount: (target: HTMLElement, props: Props) => unknown };
      let bundle: Bundle | undefined;
      Object.defineProperty(window, "SubscriptionWebAppAdmin", {
        configurable: true,
        get: () => bundle,
        set(value: Bundle) {
          const mount = value.mount.bind(value);
          value.mount = (target, props) =>
            mount(target, {
              ...props,
              api: async (path, options = {}) => {
                const response = await window.__accountOperationsRequest(
                  path,
                  options.method ?? "GET"
                );
                return response.handled ? response.value : props.api(path, options);
              },
            });
          bundle = value;
        },
      });
    },
    { language }
  );
  return {
    records,
    archived,
    worker,
    success,
    calls,
    failReads: (value: boolean) => {
      fail = value;
    },
    holdNext: () => {
      hold = true;
      release = undefined;
    },
    held: () => release !== undefined,
    release: () => release?.(),
    finish: () => {
      expect(errors).toEqual([]);
      expect(unexpected).toEqual([]);
      expect(calls.filter((call) => call.method !== "GET")).toEqual([]);
    },
  };
}

const base = `/demo/runtime/admin/console-operations${query}&operations_view=accounts&status=failed&phase=usage&user_id=910001`;
for (const language of ["en", "ru", "zh-hans"] as const)
  for (const width of [1440, 390]) {
    const at = labels(language);
    test.describe(`${language} account operations at ${width}`, () => {
      test.use({ viewport: { width, height: 1000 }, timezoneId: "UTC" });
      const root = (page: Page) => page.locator(".account-operations-list");
      const detail = (page: Page) =>
        page.getByRole("dialog", { name: at("account_ops_detail"), exact: true });

      test("filters and true totals survive view switches, pagination, refresh and customer return", async ({
        page,
      }, info) => {
        const fixture = await installAccounts(page, language);
        await page.goto(base);
        const host = root(page);
        await expect(host.locator("tbody tr")).toHaveCount(25);
        await expect(host.locator(".admin-pagination-summary")).toContainText(
          `${at("account_ops_count")} 29`
        );
        await host.getByRole("button", { name: at("services_next"), exact: true }).click();
        await expect(host.locator("tbody tr")).toHaveCount(4);
        await expect(page).toHaveURL(/account_page=1/);
        await page.reload();
        await expect(host.locator("tbody tr")).toHaveCount(4);
        await choose(page, host, at("status"), at("console_ops_status_unknown"), info, true);
        await choose(page, host, at("account_ops_source"), at("console_ops_administrator"));
        await choose(
          page,
          host,
          at("console_global_archived"),
          at("console_global_archived_exclude")
        );
        await host
          .getByRole("checkbox", { name: at("console_global_attention"), exact: true })
          .check();
        await host
          .getByRole("textbox", { name: at("account_ops_target"), exact: true })
          .fill("910002");
        await host.getByRole("textbox", { name: at("services_actor"), exact: true }).fill("910001");
        await host.getByRole("button", { name: at("search"), exact: true }).click();
        await expect(host).toHaveAttribute("aria-busy", "false");
        await expect(host.locator(".admin-pagination-summary")).toContainText(
          `${at("account_ops_count")} 26`
        );
        await expect
          .poll(() =>
            fixture.calls.some(({ path }) => {
              const url = new URL(path, "https://fixture.invalid");
              const params = url.searchParams;
              return (
                url.pathname === "/admin/console/account-operations" &&
                params.get("status") === "unknown" &&
                params.get("source") === "administrator" &&
                params.get("archived") === "exclude" &&
                params.get("needs_attention") === "true" &&
                params.get("user_id") === "910002" &&
                params.get("actor_id") === "910001"
              );
            })
          )
          .toBe(true);
        await host.getByRole("button", { name: at("services_next"), exact: true }).click();
        await expect(host.locator("tbody tr")).toHaveCount(1);
        const listUrl = page.url();
        const trigger = host.locator("[data-account-record] button");
        await trigger.focus();
        await trigger.press("Enter");
        const record = detail(page);
        await expect(record.locator(".account-operation-detail")).toHaveAttribute(
          "aria-busy",
          "false"
        );
        await expect(record).toContainText(at("console_ops_status_unknown"));
        await expect(record).toContainText(at("account_ops_scope"));
        await expect(record.locator("[data-account-operation-code]")).toHaveText(
          new URL(page.url()).searchParams.get("account_operation_id")!
        );
        await capture(page, record, info, "account-detail");
        const detailUrl = page.url();
        await page.reload();
        await expect(record.locator(".account-operation-detail")).toHaveAttribute(
          "aria-busy",
          "false"
        );
        await record
          .getByRole("button", { name: at("account_ops_review_customer"), exact: true })
          .click();
        await expect(page.locator(".admin-user-detail-page")).toBeVisible();
        const access = page.locator(".access-status");
        await expect(
          access.getByRole("button", { name: at("account_access_retry"), exact: true })
        ).toBeVisible();
        await page.getByRole("button", { name: at("user_back"), exact: true }).click();
        await expect(page).toHaveURL(detailUrl);
        await expect(record).toBeVisible();
        await record.locator(".dialog-close-button").click();
        await expect(page).toHaveURL(listUrl);
        await expect(trigger).toBeFocused();
        await choose(
          page,
          page.locator(".admin-content"),
          at("resource_ops_view"),
          at("resource_ops_service_view")
        );
        await expect(page.locator(".console-operations")).toBeVisible();
        expect(new URL(page.url()).searchParams.get("status")).toBe("failed");
        expect(new URL(page.url()).searchParams.get("phase")).toBe("usage");
        expect(new URL(page.url()).searchParams.get("user_id")).toBe("910001");
        await choose(
          page,
          page.locator(".admin-content"),
          at("resource_ops_view"),
          at("resource_ops_title")
        );
        await expect(page.locator(".resource-operations-list")).toBeVisible();
        await choose(
          page,
          page.locator(".admin-content"),
          at("resource_ops_view"),
          at("account_ops_title")
        );
        await expect(host.locator("tbody tr")).toHaveCount(1);
        await expect(
          host.getByRole("textbox", { name: at("account_ops_target"), exact: true })
        ).toHaveValue("910002");
        await expect(
          host.getByRole("textbox", { name: at("services_actor"), exact: true })
        ).toHaveValue("910001");
        await expect(
          host.getByRole("checkbox", { name: at("console_global_attention"), exact: true })
        ).toBeChecked();
        await page.goBack();
        await expect(page.locator(".resource-operations-list")).toBeVisible();
        await page.goForward();
        await expect(host.locator("tbody tr")).toHaveCount(1);
        await capture(page, host, info, "account-filters-returned");
        fixture.finish();
      });

      test("archived records never link active customers and worker history stays unknown when unobserved", async ({
        page,
      }, info) => {
        const fixture = await installAccounts(page, language);
        await page.goto(`${base}&account_archived=only`);
        const host = root(page);
        await expect(host.locator("tbody tr")).toHaveCount(1);
        const row = host.locator(`[data-account-operation-id="${fixture.archived.id}"]`);
        await expect(row.locator("[data-account-target]")).toContainText("910002");
        await expect(row.locator("[data-account-target] button")).toHaveCount(0);
        await expect(row).toContainText(at("services_history_title"));
        await expect(row).toContainText(at("account_ops_error_unconfirmed"));
        await expect(row).not.toContainText("private-");
        await row.locator("[data-account-record] button").click();
        const record = detail(page);
        await expect(record.locator("tbody tr")).toHaveCount(1);
        await expect(record.locator("tbody button")).toHaveCount(0);
        await expect(record).not.toContainText("private-");
        await capture(page, record, info, "account-archived-detail");
        await page.reload();
        await expect(record.locator("tbody tr")).toHaveCount(1);
        await expect(record.locator("tbody button")).toHaveCount(0);
        await record.locator(".dialog-close-button").click();
        await host.getByRole("button", { name: at("console_global_reset"), exact: true }).click();
        await choose(page, host, at("account_ops_source"), at("console_ops_worker"), info);
        await expect(host.locator("tbody tr")).toHaveCount(1);
        const worker = host.locator(`[data-account-operation-id="${fixture.worker.id}"]`);
        await expect(worker.locator("td").nth(2)).toContainText(at("console_unknown"));
        await expect(worker.locator("td").nth(3)).toContainText(at("console_unknown"));
        await expect(worker).toContainText(`${at("console_ops_attempt_count")}: 0`);
        await expect(
          worker.getByRole("button", { name: at("account_ops_review_customer"), exact: true })
        ).toHaveCount(0);
        await choose(page, host, at("status"), at("console_ops_status_succeeded"));
        await expect(host).toContainText(at("account_ops_empty"));
        await expect(host.locator(".admin-pagination-summary")).toContainText(
          `${at("account_ops_count")} 0`
        );
        fixture.finish();
      });

      test("failure clears data, stale responses cannot overwrite filters, and invalid IDs do not broaden reads", async ({
        page,
      }, info) => {
        const fixture = await installAccounts(page, language);
        await page.goto(base);
        const host = root(page);
        await expect(host.locator("tbody tr")).toHaveCount(25);
        fixture.holdNext();
        try {
          await host.getByRole("button", { name: at("refresh"), exact: true }).click();
          await expect.poll(fixture.held).toBe(true);
          await expect(host.locator("tbody tr")).toHaveCount(0);
          await expect(host.locator(".admin-pagination-summary")).toHaveCount(0);
          await choose(page, host, at("status"), at("console_ops_status_succeeded"));
          await expect(host.locator("tbody tr")).toHaveCount(1);
        } finally {
          fixture.release();
        }
        await expect(
          host.locator(`[data-account-operation-id="${fixture.success.id}"]`)
        ).toBeVisible();
        fixture.failReads(true);
        await host.getByRole("button", { name: at("refresh"), exact: true }).click();
        await expect(host.getByRole("alert")).toHaveText(at("account_ops_load_failed"));
        await expect(host.locator("tbody tr")).toHaveCount(0);
        await expect(host.locator(".admin-pagination-summary")).toHaveCount(0);
        await expect(host).not.toContainText("private-");
        fixture.failReads(false);
        await host.getByRole("button", { name: at("refresh"), exact: true }).click();
        await expect(host.locator("tbody tr")).toHaveCount(1);
        await host.locator("[data-account-record] button").click();
        const record = detail(page);
        await expect(record.locator("tbody tr")).toHaveCount(1);
        fixture.failReads(true);
        await record.getByRole("button", { name: at("refresh"), exact: true }).click();
        await expect(record.getByRole("alert")).toHaveText(at("account_ops_detail_failed"));
        await expect(record.locator("tbody tr")).toHaveCount(0);
        await expect(record).not.toContainText("private-");
        fixture.failReads(false);
        await record.getByRole("button", { name: at("refresh"), exact: true }).click();
        await expect(record.locator("tbody tr")).toHaveCount(1);
        await record.locator(".dialog-close-button").click();
        const count = fixture.calls.filter((call) =>
          call.path.startsWith("/admin/console/account-operations?")
        ).length;
        await host
          .getByRole("textbox", { name: at("account_ops_target"), exact: true })
          .fill("1e3");
        await host.getByRole("button", { name: at("search"), exact: true }).click();
        await expect(host.getByRole("alert")).toHaveText(at("account_ops_invalid_filters"));
        expect(
          fixture.calls.filter((call) => call.path.startsWith("/admin/console/account-operations?"))
            .length
        ).toBe(count);
        await capture(page, host, info, "account-invalid-filter");
        fixture.finish();
      });
    });
  }
