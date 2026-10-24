import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

async function prepare(page: Page, language: string, missing = false) {
  await page.route("**/*", (route) => {
    const host = new URL(route.request().url()).hostname;
    return host === "127.0.0.1" || host === "localhost" ? route.continue() : route.abort();
  });
  await page.addInitScript(
    ({ language, missing }) => {
      localStorage.setItem("rw_minishop_demo_language", language);
      const calls: string[] = [];
      Object.defineProperty(window, "__customerSummaryCalls", { value: calls });
      type Props = { api: (path: string, options?: RequestInit) => Promise<unknown> };
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
                calls.push(path);
                const result = await props.api(path, options);
                if (
                  missing &&
                  path.split("?")[0] === "/admin/users" &&
                  result &&
                  typeof result === "object" &&
                  "users" in result &&
                  Array.isArray(result.users)
                ) {
                  const users: unknown[] = result.users;
                  return {
                    ...result,
                    users: users.map((user, index) => {
                      if (index !== 0 || !user || typeof user !== "object") return user;
                      return { ...user, independent_services: undefined };
                    }),
                  };
                }
                return result;
              },
            });
          bundle = value;
        },
      });
    },
    { language, missing }
  );
}

const rows = (page: Page, width: number) =>
  page.locator(width > 720 ? "tr[data-user-id]" : "[data-mobile-user-id]");
const customerList =
  "/demo/runtime/admin/users?mock=services&delivery=1&cycle_pending=1&theme_preview=dark";

for (const width of [1440, 390]) {
  for (const language of ["en", "zh-hans", "ru"]) {
    const locale: Record<string, string> = JSON.parse(
      readFileSync(`../locales/${language}.json`, "utf8")
    );
    const label = (key: string) => locale[`admin_${key}`];

    test(`customer summary and existing list controls at ${width}px in ${language}`, async ({
      page,
    }, info) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.setViewportSize({ width, height: 1000 });
      await prepare(page, language);
      await page.goto(customerList);
      const list = rows(page, width);
      await expect(list).toHaveCount(25);
      expect(await list.first().locator("[data-customer-service-total]").count()).toBe(1);
      await expect(
        list.first().getByText(label("console_customers_activity_uncollected"))
      ).toBeVisible();
      const firstId = await list
        .first()
        .getAttribute(width > 720 ? "data-user-id" : "data-mobile-user-id");
      await page.locator(".admin-pagination-nav").last().click();
      await expect(list.first()).not.toHaveAttribute(
        width > 720 ? "data-user-id" : "data-mobile-user-id",
        firstId!
      );
      await expect(list).toHaveCount(25);
      await page.locator(".admin-pagination-nav").first().click();
      await expect(list.first()).toHaveAttribute(
        width > 720 ? "data-user-id" : "data-mobile-user-id",
        firstId!
      );

      const search = page.getByPlaceholder(label("users_search_placeholder"));
      await search.fill("910001");
      await search.press("Enter");
      await expect(list).toHaveCount(1);
      const row = list.first();
      await expect(row.locator('[data-customer-service-total="12"]')).toBeVisible();
      await expect(row.locator('[data-service-state="exhausted"]')).toBeVisible();
      await expect(row.locator('[data-service-alert="sync_error"]')).toContainText("1");
      await expect(row.locator('[data-service-alert="pending"]')).toBeVisible();
      await expect(row.locator('[data-service-alert="unobserved"]')).toBeVisible();
      await expect(row.locator('[data-service-health="sync_error"]')).not.toBeVisible();
      const collapsedHeight = (await row.boundingBox())!.height;
      expect(collapsedHeight).toBeLessThan(width > 720 ? 180 : 340);
      await info.attach("summary-density", {
        body: JSON.stringify({ width, language, services: 12, collapsedHeight }),
        contentType: "application/json",
      });
      await page.screenshot({ path: info.outputPath("summary-collapsed.png"), fullPage: false });
      const listUrl = page.url();
      const trigger = row.locator("summary");
      await trigger.focus();
      await page.keyboard.press("Enter");
      await expect(row.locator("details")).toHaveAttribute("open", "");
      await expect(page).toHaveURL(listUrl);
      await expect(row.locator('[data-service-health="sync_error"]')).toContainText("1");
      await expect(row.locator('[data-service-health="cycle_pending"]')).toContainText("1");
      await expect(row.locator('[data-service-observation="sync"]')).toHaveText(
        label("console_customers_no_observation")
      );
      await expect(row.locator('[data-service-observation="usage"]')).toContainText(
        "2026-10-22 12:00"
      );
      await row.locator('[data-service-observation="usage"] time').first().dblclick();
      expect(
        await page.evaluate(() => window.getSelection()?.toString().length ?? 0)
      ).toBeGreaterThan(0);
      await expect(row.locator("details")).toBeFocused();
      await expect(page).toHaveURL(listUrl);
      for (const key of ["Enter", "Space"]) {
        await page.keyboard.press(key);
        await expect(page).toHaveURL(listUrl);
        await expect(row.locator("details")).toHaveAttribute("open", "");
      }
      await page.screenshot({ path: info.outputPath("summary-expanded.png"), fullPage: false });
      await trigger.click();
      await expect(row.locator("details")).not.toHaveAttribute("open", "");
      await expect(page).toHaveURL(listUrl);
      await trigger.click();
      await expect(row.locator("details")).toHaveAttribute("open", "");
      await expect(page).toHaveURL(listUrl);
      await trigger.click();
      await expect(row.locator("details")).not.toHaveAttribute("open", "");
      await trigger.focus();
      await page.keyboard.press("Space");
      await expect(row.locator("details")).toHaveAttribute("open", "");
      await page.keyboard.press("Space");
      await expect(row.locator("details")).not.toHaveAttribute("open", "");
      const calls = await page.evaluate(
        () => Reflect.get(window, "__customerSummaryCalls") as string[]
      );
      expect(calls.filter((path) => /^\/admin\/services(?:\?|\/)/.test(path))).toEqual([]);
      expect(calls.some((path) => path.includes("page=1") && path.includes("page_size=25"))).toBe(
        true
      );

      const detailsBox = (await row.locator("details").boundingBox())!;
      const triggerBox = (await trigger.boundingBox())!;
      const blank = {
        x: (triggerBox.x + triggerBox.width + detailsBox.x + detailsBox.width) / 2,
        y: triggerBox.y + triggerBox.height / 2,
      };
      expect(blank.x).toBeGreaterThan(triggerBox.x + triggerBox.width);
      expect(
        await page.evaluate(({ x, y }) => document.elementFromPoint(x, y)?.tagName, blank)
      ).toBe("DETAILS");
      await page.mouse.click(blank.x, blank.y);
      await expect(page).toHaveURL(/\/admin\/users\/ms_/);
      await expect(page.locator(".admin-user-hero")).toBeVisible();
      await page.getByRole("button", { name: label("user_back"), exact: true }).click();
      await expect(page).toHaveURL(listUrl);
      await expect(list).toHaveCount(1);
      await expect(search).toHaveValue("910001");

      for (const key of ["Enter", "Space"]) {
        await row.focus();
        await page.keyboard.press(key);
        await expect(page).toHaveURL(/\/admin\/users\/ms_/);
        await expect(page.locator(".admin-user-hero")).toBeVisible();
        await page.getByRole("button", { name: label("user_back"), exact: true }).click();
        await expect(page).toHaveURL(listUrl);
      }

      await row.locator(".admin-user-cell").click();
      await expect(page).toHaveURL(/\/admin\/users\/ms_/);
      await expect(page.locator(".admin-user-hero")).toBeVisible();
      await page.getByRole("button", { name: label("user_back"), exact: true }).click();
      await expect(list).toHaveCount(1);
      await expect(search).toHaveValue("910001");
      await search.fill("");
      await search.press("Enter");
      await expect(list).toHaveCount(25);
      const initialListUrl = page.url();
      await expect(list.first().locator('[data-customer-service-total="0"]')).toBeVisible();
      await list.first().click();
      await expect(page).toHaveURL(/\/admin\/users\/ms_/);
      await expect(page.locator(".admin-user-hero")).toBeVisible();
      await page.getByRole("button", { name: label("user_back"), exact: true }).click();
      await expect(page).toHaveURL(initialListUrl);
      await expect(list).toHaveCount(25);

      if (width < 721)
        await page.getByRole("button", { name: label("users_filters_open"), exact: true }).click();
      const filter = page.getByRole("button", { name: label("filter"), exact: true });
      await filter.click();
      await expect(
        page.getByRole("option", { name: label("filter_banned"), exact: true })
      ).toBeVisible();
      await page.screenshot({ path: info.outputPath("filter-open.png"), fullPage: false });
      await page.keyboard.press("Escape");
      if (width < 721) await expect(page.getByRole("dialog")).toBeVisible();
      await filter.click();
      await page.getByRole("option", { name: label("filter_banned"), exact: true }).click();
      if (width < 721) await page.getByRole("button", { name: label("done"), exact: true }).click();
      await expect(list).toHaveCount(0);
      await page.goto(customerList + "&issues_demo=1");
      await search.fill("review.2@example.com");
      await search.press("Enter");
      await expect(list).toHaveCount(1);
      await expect(list.first()).toContainText(label("services_status_account_banned"));
      await expect(list.first().locator('[data-customer-service-total="0"]')).toBeVisible();
      await expect(list.first().locator('[data-service-alert="sync_error"]')).toHaveCount(0);
      if (width < 721) {
        await page.getByRole("button", { name: label("menu"), exact: true }).click();
        await expect(page.getByRole("button", { name: label("exit"), exact: true })).toBeVisible();
        await page.keyboard.press("Escape");
      }
      expect(await page.evaluate(() => document.body.scrollWidth - innerWidth)).toBeLessThanOrEqual(
        2
      );
      expect(errors).toEqual([]);
    });
  }

  test(`missing summary stays unknown beside known zero at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await prepare(page, "zh-hans", true);
    await page.goto(customerList);
    const list = rows(page, width);
    await expect(list).toHaveCount(25);
    await expect(list.first().locator("[data-customer-summary-unknown]")).toBeVisible();
    await expect(list.first().locator("[data-customer-service-total]")).toHaveCount(0);
    await expect(list.nth(1).locator('[data-customer-service-total="0"]')).toBeVisible();
    await page.screenshot({ path: info.outputPath("unknown-and-zero.png"), fullPage: false });
  });

  test(`legacy list keeps subscription columns at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await prepare(page, "en");
    await page.goto("/demo/runtime/admin/users?theme_preview=dark");
    await expect(rows(page, width)).toHaveCount(25);
    await expect(page.locator("[data-customer-service-total]")).toHaveCount(0);
    await expect(
      page.locator(width > 720 ? ".admin-users-cell-premium" : ".admin-user-mobile-metrics").first()
    ).toBeVisible();
  });
}
