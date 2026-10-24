import { expect, test } from "@playwright/test";
import { installAdminShellFixture } from "./fixtures/admin-shell";

const usersUrl = "/demo/runtime/admin/users?mock=services&theme_preview=dark";

for (const width of [1440, 390]) {
  test(`revoked administrator exits the real customer shell after a new query at ${width}`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 1000 });
    const fixture = await installAdminShellFixture(page);
    await page.goto(usersUrl);
    const customer = page.locator(
      width === 390 ? '[data-mobile-user-id="42"]' : '[data-user-id="42"]'
    );
    await expect(customer.first()).toBeVisible();
    fixture.state.admin = false;
    if (width === 1440) await page.locator(".admin-users-table th button").first().click();
    else {
      const search = page.locator(".admin-users-toolbar input");
      await search.fill("shell-private");
      await search.press("Enter");
    }
    await expect.poll(() => fixture.state.roleChecks).toBeGreaterThan(0);
    await expect(page.locator(".admin-sidebar")).toHaveCount(0);
    await expect(page.locator('[data-user-id="42"], [data-mobile-user-id="42"]')).toHaveCount(0);
    await expect(page).toHaveURL(/\/settings(?:\?|$)/);
    expect(fixture.state.logoutCalls).toBe(0);
    await page.reload();
    await expect(page.locator(".admin-sidebar")).toHaveCount(0);
    await expect(page).toHaveURL(/\/settings(?:\?|$)/);
    expect(fixture.state.logoutCalls).toBe(0);
  });
}

test("business 403 preserves the customer shell and administrator session", async ({ page }) => {
  const fixture = await installAdminShellFixture(page);
  await page.goto(usersUrl);
  await expect(page.locator('[data-user-id="42"]').first()).toBeVisible();
  fixture.state.denied = true;
  await page.locator(".admin-users-table th button").first().click();
  await expect.poll(() => fixture.state.roleChecks).toBe(1);
  await expect(page.locator(".admin-sidebar")).toBeVisible();
  await expect(page.locator('[data-user-id="42"]').first()).toBeVisible();
  expect(fixture.state.logoutCalls).toBe(0);
});

test("late customer responses cannot remount or refill a revoked shell", async ({ page }) => {
  const fixture = await installAdminShellFixture(page);
  await page.goto(usersUrl);
  await expect(page.locator('[data-user-id="42"]').first()).toBeVisible();
  fixture.holdNextList();
  const reads = fixture.state.listReads;
  await page.locator(".admin-users-table th button").first().click();
  await expect.poll(() => fixture.state.listReads).toBeGreaterThan(reads);
  fixture.state.admin = false;
  const search = page.locator(".admin-users-toolbar input");
  await search.fill("revoked-query");
  await search.press("Enter");
  await expect(page.locator(".admin-sidebar")).toHaveCount(0);
  fixture.releaseList();
  await expect(page.locator('[data-user-id="42"]')).toHaveCount(0);
  await expect(page).toHaveURL(/\/settings(?:\?|$)/);
  expect(fixture.state.logoutCalls).toBe(0);
});

for (const language of ["en", "ru", "zh-hans"]) {
  for (const width of [1440, 390]) {
    test(`maintenance stays visible but unconfigured for administrators ${language} ${width}`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 1000 });
      const fixture = await installAdminShellFixture(page, language);
      await page.goto("/demo/runtime/admin/advanced-maintenance?mock=services&theme_preview=dark");
      await expect(
        page.getByRole("region", { name: fixture.label("maintenance_title") })
      ).toBeVisible();
      await expect(
        page.getByText(fixture.label("maintenance_unconfigured"), { exact: true })
      ).toBeVisible();
      await expect(page.locator(".maintenance a")).toHaveCount(0);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
      ).toBe(true);
    });
  }
}

test("ordinary customers cannot mount maintenance by its direct URL", async ({ page }) => {
  const fixture = await installAdminShellFixture(page);
  fixture.state.admin = false;
  await page.goto("/demo/runtime/admin/advanced-maintenance?mock=services");
  await expect(page).toHaveURL(/\/settings(?:\?|$)/);
  await expect(page.locator(".maintenance, .admin-sidebar")).toHaveCount(0);
  expect(fixture.state.logoutCalls).toBe(0);
});
