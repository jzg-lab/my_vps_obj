import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

const root = "/demo/runtime/admin";
const query = "?mock=services&theme_preview=dark";

async function openSidebar(page: Page, width: number) {
  if (width >= 1024) return;
  const toggle = page.locator(".admin-mobile-toggle");
  if ((await toggle.getAttribute("aria-expanded")) !== "true") await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator(".admin-sidebar")).toHaveCSS("transform", "matrix(1, 0, 0, 1, 0, 0)");
}

for (const width of [1440, 390]) {
  for (const language of ["en", "ru", "zh-hans"]) {
    test(`navigation groups support keyboard and route recovery at ${width}px in ${language}`, async ({
      page,
    }, testInfo) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      const copy: Record<string, string> = JSON.parse(
        readFileSync(`../locales/${language}.json`, "utf8")
      );
      await page.addInitScript((language) => {
        localStorage.setItem("rw_minishop_demo_language", language);
      }, language);
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(`${root}/users${query}`);
      await openSidebar(page, width);
      const sidebar = page.locator(".admin-sidebar");
      const groups = sidebar.locator("[data-admin-nav-group]");
      await expect(groups.first()).toBeVisible();
      expect(await groups.count()).toBeGreaterThanOrEqual(7);
      for (const group of await groups.all()) {
        await expect(group).toHaveAttribute("aria-expanded", "true");
        const id = await group.getAttribute("aria-controls");
        await expect(sidebar.locator(`nav[id="${id}"]`)).toBeVisible();
      }
      const nodes = sidebar.locator('[data-admin-nav-group="nodes"]');
      const customers = sidebar.locator('[data-admin-nav-group="customers"]');
      const nodePage = sidebar.getByRole("button", {
        name: copy.admin_console_nodes,
        exact: true,
      });
      await expect(nodePage).toHaveCount(1);
      await expect(nodes).toHaveAccessibleName(
        copy.admin_nav_group_collapse.replace("{group}", copy.admin_console_nodes)
      );
      await nodePage.click();
      await expect(page).toHaveURL(/\/admin\/nodes\?/);
      await expect(page.locator(".console-nodes")).toBeVisible();
      await openSidebar(page, width);
      await expect(nodePage).toHaveAttribute("aria-current", "page");
      await nodes.focus();
      await nodes.press("Enter");
      await expect(nodes).toHaveAttribute("aria-expanded", "false");
      await expect(nodes).toBeFocused();
      await expect(nodePage).toBeHidden();
      await expect(nodes).toHaveAccessibleName(
        copy.admin_nav_group_expand.replace("{group}", copy.admin_console_nodes)
      );
      await page.keyboard.press("Tab");
      await expect(sidebar.locator('[data-admin-nav-group="operations"]')).toBeFocused();
      await expect(nodes).toHaveAttribute("aria-expanded", "false");
      await customers.click();
      await expect(customers).toHaveAttribute("aria-expanded", "false");
      await expect(page.locator(".console-nodes")).toHaveAttribute("aria-busy", "false");
      await page.screenshot({
        path: testInfo.outputPath(`navigation-collapsed-${width}-${language}.png`),
        fullPage: true,
        animations: "disabled",
      });
      await page.goBack();
      await expect(page).toHaveURL(/\/admin\/users\?/);
      await openSidebar(page, width);
      await expect(customers).toHaveAttribute("aria-expanded", "true");
      await expect(sidebar.locator('[data-admin-section="users"]')).toHaveAttribute(
        "aria-current",
        "page"
      );
      await expect(nodes).toHaveAttribute("aria-expanded", "false");
      await customers.focus();
      await customers.press("Space");
      await expect(customers).toHaveAttribute("aria-expanded", "false");
      await customers.press("Space");
      await expect(customers).toHaveAttribute("aria-expanded", "true");
      await page.goForward();
      await expect(page).toHaveURL(/\/admin\/nodes\?/);
      await openSidebar(page, width);
      await expect(nodes).toHaveAttribute("aria-expanded", "true");
      await expect(nodePage).toBeVisible();
      await sidebar.locator('[data-admin-section="dedicated-exits"]').click();
      await expect(page).toHaveURL(/\/admin\/dedicated-exits\?/);
      await openSidebar(page, width);
      await nodes.click();
      await expect(nodes).toHaveAttribute("aria-expanded", "false");
      await page.goBack();
      await expect(page).toHaveURL(/\/admin\/nodes\?/);
      await openSidebar(page, width);
      await expect(nodes).toHaveAttribute("aria-expanded", "true");
      await expect(nodePage).toHaveAttribute("aria-current", "page");
      if (width < 1024) {
        await nodes.focus();
        await page.keyboard.press("Escape");
        await expect(page.locator(".admin-mobile-toggle")).toHaveAttribute(
          "aria-expanded",
          "false"
        );
        await expect(page.locator(".admin-mobile-toggle")).toBeFocused();
        await expect(page.locator(".admin-sidebar-backdrop")).toHaveCount(0);
      }
      await page.reload();
      await openSidebar(page, width);
      await expect(nodePage).toHaveAttribute("aria-current", "page");
      for (const group of await groups.all())
        await expect(group).toHaveAttribute("aria-expanded", "true");
      await expect(page.locator(".console-nodes")).toHaveAttribute("aria-busy", "false");
      await page.screenshot({
        path: testInfo.outputPath(`navigation-expanded-${width}-${language}.png`),
        fullPage: true,
        animations: "disabled",
      });
      expect(
        await page.evaluate(() => document.body.scrollWidth - window.innerWidth)
      ).toBeLessThanOrEqual(2);
      expect(errors).toEqual([]);
    });
  }

  test(`runtime plugin navigation remains collapsible and reachable at ${width}px`, async ({
    page,
  }, testInfo) => {
    const digest = "a".repeat(64);
    await page.route("**/api/admin/plugins/assets/**", (route) =>
      route.fulfill({
        contentType: "text/javascript",
        body: `export function mountView(view, target) {
          target.textContent = view;
          target.dataset.testid = 'sample-navigation-page';
          return { target };
        }
        export function unmountView(instance) { instance.target.textContent = ''; }`,
      })
    );
    await page.addInitScript((digest) => {
      type Bundle = { registerRuntimeExtensions: (plugins: unknown[]) => void };
      let bundle: Bundle | undefined;
      Object.defineProperty(window, "SubscriptionWebAppAdmin", {
        configurable: true,
        get: () => bundle,
        set(value: Bundle) {
          value.registerRuntimeExtensions([
            {
              id: "sample",
              digest,
              entry: `/api/admin/plugins/assets/sample/${digest}/index.js`,
              section_groups: [{ id: "sample-tools", order: 80, label: "Sample tools" }],
              sections: [
                {
                  id: "sample-report",
                  view: "report-view",
                  group: "sample-tools",
                  label: "Sample report",
                },
              ],
            },
          ]);
          bundle = value;
        },
      });
    }, digest);
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(`${root}/users${query}`);
    await openSidebar(page, width);
    const group = page.locator('[data-admin-nav-group="sample-tools"]');
    const item = page.locator('[data-admin-section="sample-report"]');
    await expect(group).toHaveAttribute("aria-expanded", "true");
    await group.click();
    await expect(item).toBeHidden();
    await group.press("Space");
    await expect(item).toBeVisible();
    await item.click();
    await expect(page).toHaveURL(/\/admin\/sample-report\?/);
    await expect(page.getByTestId("sample-navigation-page")).toHaveText("report-view");
    await openSidebar(page, width);
    await group.click();
    await expect(group).toHaveAttribute("aria-expanded", "false");
    await page.goBack();
    await expect(page).toHaveURL(/\/admin\/users\?/);
    await page.goForward();
    await expect(page).toHaveURL(/\/admin\/sample-report\?/);
    await openSidebar(page, width);
    await expect(group).toHaveAttribute("aria-expanded", "true");
    await expect(item).toHaveAttribute("aria-current", "page");
    await page.reload();
    await expect(page.getByTestId("sample-navigation-page")).toHaveText("report-view");
    await openSidebar(page, width);
    await expect(group).toHaveAttribute("aria-expanded", "true");
    await expect(item).toBeVisible();
    await item.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: testInfo.outputPath(`navigation-plugin-${width}.png`),
      fullPage: true,
      animations: "disabled",
    });
  });
}
