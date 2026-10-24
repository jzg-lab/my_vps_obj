import { expect, test } from "@playwright/test";
import { installAdminShellFixture } from "./fixtures/admin-shell";

const maintenanceUrl = "/demo/runtime/admin/advanced-maintenance?mock=services&theme_preview=dark";
const destination = "https://panel.example.com/maintenance";

for (const language of ["en", "ru", "zh-hans"]) {
  for (const width of [1440, 390]) {
    test(`maintenance uses the backend destination ${language} ${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1000 });
      const fixture = await installAdminShellFixture(page, language);
      fixture.maintenance.destination = destination;
      await page.goto(maintenanceUrl);
      const section = page.getByRole("region", { name: fixture.label("maintenance_title") });
      const link = section.getByRole("link", { name: fixture.label("maintenance_open") });
      await expect(link).toBeVisible();
      await expect(link).toHaveAttribute("href", destination);
      await expect(link).toHaveAttribute("target", "_blank");
      await expect(link).toHaveAttribute("rel", "noopener noreferrer");
      await expect(link).toHaveAttribute("referrerpolicy", "no-referrer");
      await expect(section.getByText(destination, { exact: true })).toBeVisible();
      await expect(section.getByText(fixture.label("maintenance_auth"))).toBeVisible();
      await expect(section.getByRole("alert")).toHaveCount(0);
      await expect(section.getByText(fixture.label("maintenance_unconfigured"))).toHaveCount(0);
      await expect(section).toHaveAttribute("aria-busy", "false");
      expect(fixture.maintenance.reads).toBe(1);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
      ).toBe(true);
    });
  }
}

test("maintenance shows loading, a retryable error, then the configured destination", async ({
  page,
}) => {
  const fixture = await installAdminShellFixture(page);
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  let reads = 0;
  await page.route("**/api/admin/console/maintenance", async (route) => {
    reads += 1;
    if (reads === 1) {
      await held;
      return route.fulfill({ status: 503, json: { ok: false, error: "service_unavailable" } });
    }
    return route.fulfill({ json: { ok: true, destination } });
  });
  await page.goto(maintenanceUrl);
  const section = page.getByRole("region", { name: fixture.label("maintenance_title") });
  try {
    await expect(section).toHaveAttribute("aria-busy", "true");
    await expect(section.getByRole("status")).toHaveText(fixture.label("loading"));
    await expect(section.getByText(fixture.label("maintenance_unconfigured"))).toHaveCount(0);
    await expect(section.getByRole("link")).toHaveCount(0);
  } finally {
    release();
  }
  await expect(section.getByRole("alert")).toHaveText(fixture.label("maintenance_load_failed"));
  await expect(section.getByText(fixture.label("maintenance_unconfigured"))).toHaveCount(0);
  await expect(section.getByRole("link")).toHaveCount(0);
  await section.getByRole("button", { name: fixture.label("retry"), exact: true }).click();
  await expect(section.getByRole("link")).toHaveAttribute("href", destination);
  await expect(section.getByRole("alert")).toHaveCount(0);
  expect(reads).toBe(2);
});
