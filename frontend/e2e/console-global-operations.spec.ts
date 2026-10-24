import { expect, test, type Page } from "@playwright/test";
import { operationLabels, type OperationsLanguage } from "./fixtures/consoleServiceOperations";
import { operationFixture } from "../src/lib/admin/consoleServiceOperationsFixtures";
import { consoleNodeServiceFixture } from "../src/lib/admin/consoleNodesFixtures";
import { consoleGlobalOperationsDemoResponse } from "../src/lib/webapp/mockApi/consoleGlobalOperations";
import {
  createConsoleServiceOperationsDemo,
  type ConsoleServiceOperationsDemoState,
} from "../src/lib/webapp/mockApi/consoleServiceOperations";
import { demoAdminUserById } from "../src/lib/webapp/mockApi/users";

declare global {
  interface Window {
    __globalOperationsRequest: (
      path: string,
      method: string
    ) => Promise<{ handled: boolean; value?: unknown }>;
  }
}

async function installFixture(page: Page, language: OperationsLanguage) {
  const service = {
    ...consoleNodeServiceFixture.service,
    user_id: 910001,
    name: "Global operations fixture",
    revision: 3,
  };
  const archived = {
    ...service,
    id: "f".repeat(32),
    user_id: null,
    name: "Archived operations fixture",
  };
  const state: ConsoleServiceOperationsDemoState = {
    owner: 0,
    services: [service],
    archived: [archived],
    plans: [],
    exits: [],
    orders: [
      {
        id: operationFixture.id,
        service_id: service.id,
        user_id: 910002,
        kind: "activate",
        actor_id: 7,
        created_at: operationFixture.created_at,
        snapshot: { secret: "private-order-snapshot" },
      },
    ],
    operations: [
      ...Array.from({ length: 27 }, (_, index) => ({
        ...operationFixture,
        id: index === 0 ? operationFixture.id : index.toString(16).padStart(32, "0"),
        service_id: service.id,
        phase: index === 5 ? ("usage" as const) : ("entitlement" as const),
        status:
          index === 1
            ? ("unknown" as const)
            : index === 2
              ? ("succeeded" as const)
              : index === 3 || index === 4
                ? ("pending" as const)
                : ("failed" as const),
        error_code: index === 2 || index === 3 ? null : "private-error-token",
        completed_at: index === 2 ? "2026-10-24T01:03:00Z" : null,
      })),
      {
        ...operationFixture,
        id: "e".repeat(32),
        service_id: archived.id,
        status: "unknown",
        retryable: false,
      },
    ],
  };
  const calls: { path: string; method: string }[] = [];
  const errors: string[] = [];
  let fail = false;
  let hold = false;
  let release: (() => void) | undefined;
  const single = createConsoleServiceOperationsDemo();
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/*", (route) =>
    ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname)
      ? route.continue()
      : route.abort()
  );
  await page.exposeFunction("__globalOperationsRequest", async (path: string, method: string) => {
    calls.push({ path, method });
    const url = new URL(path, "https://fixture.invalid");
    if (url.pathname === "/admin/console/operations") {
      if (fail) return { handled: true, value: { ok: false, error: "private-api-token" } };
      const value = consoleGlobalOperationsDemoResponse(path, { method }, state);
      if (hold) {
        hold = false;
        await new Promise<void>((resolve) => {
          release = resolve;
        });
      }
      return { handled: true, value };
    }
    const detail = [service, archived].find(
      (item) => url.pathname === `/admin/console/services/${item.id}`
    );
    if (detail) {
      const user = detail.user_id === null ? undefined : demoAdminUserById(detail.user_id);
      return {
        handled: true,
        value: {
          ok: true,
          service: detail,
          customer: {
            user_id: detail.user_id,
            minishop_id: user?.minishop_id ?? null,
            first_name: user?.first_name ?? null,
            last_name: user?.last_name ?? null,
            username: user?.username ?? null,
            email: user?.email ?? null,
            is_banned: user ? false : null,
          },
          terms: consoleNodeServiceFixture.terms,
          connection: null,
        },
      };
    }
    const value = single(path, { method }, state);
    return value === undefined ? { handled: false } : { handled: true, value };
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
                const response = await window.__globalOperationsRequest(
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
    state,
    service,
    archived,
    calls,
    errors,
    failReads: (value: boolean) => {
      fail = value;
    },
    holdNext: () => {
      hold = true;
    },
    release: () => release?.(),
    held: () => Boolean(release),
  };
}

const base = "/demo/runtime/admin/console-operations?mock=services&theme_preview=dark";
for (const width of [1440, 390]) {
  for (const language of ["zh-hans", "en", "ru"] as const) {
    test(`global operations filters, cursor totals, detail returns and archives ${language} ${width}px`, async ({
      page,
    }, info) => {
      const at = operationLabels(language);
      const fixture = await installFixture(page, language);
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(base);
      const host = page.getByRole("region", { name: at("console_global_title"), exact: true });
      const select = async (label: string, option: string) => {
        await host.getByRole("button", { name: at(label), exact: true }).click();
        await page.getByRole("option", { name: at(option), exact: true }).click();
      };
      await expect(host.locator("tbody tr")).toHaveCount(25);
      await expect(host.locator(".admin-pagination-summary")).toContainText("29");
      await host.getByRole("button", { name: at("services_next"), exact: true }).click();
      await expect(host.locator("tbody tr")).toHaveCount(4);
      await expect(host.locator(".admin-pagination-summary")).toContainText("29");
      await expect(
        host.locator(`[data-operation-key="execution:${operationFixture.id}"]`)
      ).toBeVisible();
      await expect(
        host.locator(`[data-operation-key="order:${operationFixture.id}"]`)
      ).toBeVisible();
      await expect(
        host.getByRole("button", { name: at("console_ops_retry"), exact: true })
      ).toHaveCount(0);
      const listUrl = page.url();
      await page.reload();
      await expect(host.locator("tbody tr")).toHaveCount(4);
      const row = host.locator(`[data-operation-key="execution:${operationFixture.id}"]`);
      await row.getByTitle(at("console_global_open_service"), { exact: true }).click();
      const detail = page.getByRole("dialog", { name: at("console_service_detail"), exact: true });
      await expect(detail).toContainText(fixture.service.name);
      const detailUrl = new URL(listUrl);
      detailUrl.searchParams.set("detail_service_id", fixture.service.id);
      await expect(page).toHaveURL(detailUrl.href);
      expect(fixture.errors).toEqual([]);
      await detail.getByRole("button", { name: at("console_ops_title"), exact: true }).click();
      const diagnostics = page.getByRole("dialog", { name: at("console_ops_title"), exact: true });
      await expect(diagnostics).toContainText(at("console_ops_remote_unconfigured"));
      await expect(
        diagnostics.locator(`[data-operation-key="execution:${operationFixture.id}"]`)
      ).toHaveCount(1);
      const historicalOperation = diagnostics.locator(
        `[data-operation-key="order:${operationFixture.id}"]`
      );
      await expect(historicalOperation).toContainText(at("console_ops_history_unknown"));
      await expect(historicalOperation.getByRole("button")).toHaveCount(0);
      expect(fixture.errors).toEqual([]);
      await page.keyboard.press("Escape");
      await expect(diagnostics).toHaveCount(0);
      await page.keyboard.press("Escape");
      await expect(detail).toHaveCount(0);
      await expect(page).toHaveURL(listUrl);
      await row.locator("td").first().getByRole("button").click();
      await expect(page.locator(".admin-user-detail-page")).toBeVisible();
      await page.getByRole("button", { name: at("user_back"), exact: true }).click();
      await expect(page).toHaveURL(listUrl);
      await expect(host.locator("tbody tr")).toHaveCount(4);
      await host.getByRole("button", { name: at("services_previous"), exact: true }).click();
      await expect(host.locator("tbody tr")).toHaveCount(25);
      await select("status", "console_ops_status_unknown");
      await expect(host.locator("tbody tr")).toHaveCount(3);
      await host
        .getByRole("checkbox", { name: at("console_global_attention"), exact: true })
        .check();
      await expect(host.locator("tbody tr")).toHaveCount(2);
      await expect(host.locator('tbody [data-operation-key^="order:"]')).toHaveCount(0);
      await expect(host.locator("tbody")).not.toContainText(at("console_global_order"));
      await expect(host.locator("tbody")).not.toContainText(at("console_ops_status_failed"));
      await select("console_global_archived", "console_global_archived_only");
      await expect(host.locator("tbody tr")).toHaveCount(1);
      await expect(host).toContainText(at("services_history_title"));
      await expect(host.locator("tbody tr td").first().getByRole("button")).toHaveCount(0);
      await select("console_global_archived", "console_global_archived_exclude");
      await host
        .getByRole("textbox", { name: at("console_global_customer_id"), exact: true })
        .fill("910001");
      await host
        .getByRole("textbox", { name: at("console_global_service_id"), exact: true })
        .fill(fixture.service.id);
      await host.getByRole("button", { name: at("search"), exact: true }).click();
      await expect(host.locator("tbody tr")).toHaveCount(1);
      await expect
        .poll(() =>
          fixture.calls.some(
            (call) =>
              call.path.includes("user_id=910001") &&
              call.path.includes(`service_id=${fixture.service.id}`)
          )
        )
        .toBe(true);
      await host.getByRole("button", { name: at("console_global_phase"), exact: true }).click();
      await page.screenshot({
        path: info.outputPath(`global-phase-menu-${language}-${width}.png`),
        animations: "disabled",
      });
      await page.getByRole("option", { name: at("console_ops_phase_usage"), exact: true }).click();
      await expect(host).toContainText(at("console_global_empty"));
      await expect(host.locator(".admin-pagination-summary")).toContainText("0");
      await host.getByRole("button", { name: at("console_global_reset"), exact: true }).click();
      await expect(host.locator("tbody tr")).toHaveCount(25);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
      ).toBeLessThanOrEqual(2);
      expect(
        await host.evaluate((node) => node.scrollWidth - node.clientWidth)
      ).toBeLessThanOrEqual(2);
      await page.screenshot({
        path: info.outputPath(`global-operations-${language}-${width}.png`),
        animations: "disabled",
      });
      await expect(host).not.toContainText("private-");
      expect(fixture.calls.filter((call) => call.method !== "GET")).toEqual([]);
      expect(fixture.errors).toEqual([]);
    });
  }
  test(`loading, stale responses, failure recovery and attention overview at ${width}px`, async ({
    page,
  }) => {
    const at = operationLabels("zh-hans");
    const fixture = await installFixture(page, "zh-hans");
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/demo/runtime/admin/console-overview?mock=services&theme_preview=dark");
    await page
      .getByRole("button", { name: at("console_global_attention_entry"), exact: true })
      .click();
    await expect(page).toHaveURL(/console-operations.*needs_attention=true/);
    const host = page.getByRole("region", { name: at("console_global_title"), exact: true });
    await expect(host.locator("tbody tr")).toHaveCount(25);
    await host.getByRole("button", { name: at("console_global_reset"), exact: true }).click();
    await expect(host.locator(".admin-pagination-summary")).toContainText("29");
    fixture.holdNext();
    await host.getByRole("button", { name: at("refresh"), exact: true }).click();
    await expect.poll(fixture.held).toBe(true);
    await expect(host.getByRole("status")).toContainText(at("loading"));
    await expect(host.locator(".admin-pagination-summary")).toHaveCount(0);
    await host.getByRole("button", { name: at("status"), exact: true }).click();
    await page
      .getByRole("option", { name: at("console_ops_status_succeeded"), exact: true })
      .click();
    await expect(host.locator("tbody tr")).toHaveCount(1);
    fixture.release();
    await expect(host.locator("tbody tr")).toHaveCount(1);
    await expect(host).not.toContainText(at("console_ops_status_failed"));
    fixture.failReads(true);
    await host.getByRole("button", { name: at("refresh"), exact: true }).click();
    await expect(host.getByRole("alert")).toContainText(at("console_ops_load_failed"));
    await expect(host.locator("tbody tr")).toHaveCount(0);
    await expect(host.locator(".admin-pagination-summary")).toHaveCount(0);
    await expect(host).not.toContainText("private-api-token");
    fixture.failReads(false);
    await host.getByRole("button", { name: at("refresh"), exact: true }).click();
    await expect(host.locator("tbody tr")).toHaveCount(1);
    await page.goBack();
    await expect(host.locator("tbody tr")).toHaveCount(25);
    expect(fixture.errors).toEqual([]);
  });
}
