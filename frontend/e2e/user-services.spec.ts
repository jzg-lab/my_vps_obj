import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

const copy: Record<string, string> = JSON.parse(readFileSync("../locales/ru.json", "utf8"));

const url = (path = "/", scenario = "services") =>
  `/demo/runtime${path === "/" ? "/app/" : path}?mock=${scenario}&theme_preview=dark`;

for (const width of [1440, 390]) {
  test(`independent user services, catalog and details at ${width}px`, async ({
    page,
  }, testInfo) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(url());
    await expect(page.locator(".services-home")).toBeVisible();
    await expect(page.locator(".services-home")).toContainText("12");
    await expect(page.locator("[data-service-id]")).toHaveCount(0);
    await page.screenshot({
      path: testInfo.outputPath(`simple-home-${width}.png`),
      fullPage: true,
    });
    await page.locator("nav").getByRole("button", { name: "Мои тарифы", exact: true }).click();
    await expect(page).toHaveURL(/\/services\?/);
    await page.reload();
    const screen = page.locator(".services-screen");
    await expect(screen.getByRole("heading", { name: "Мои тарифы", exact: true })).toBeVisible();
    const cards = screen.locator("[data-service-id]");
    await expect(cards).toHaveCount(10);
    await expect(cards.first()).toContainText("117 GiB / 100 GiB");
    await expect(cards.first()).toContainText("17 GiB");
    await expect(cards.first()).toContainText("Лимит исчерпан");
    await expect(cards.nth(1).locator("[data-service-remaining]")).toContainText("77 GiB");
    await expect(cards.nth(1).locator("[data-service-remaining]")).toContainText("2026-10-22 12:00");
    await expect(cards.nth(1)).toContainText(copy.wa_services_usage_stale);
    await expect(cards.nth(1)).toContainText("23 GiB / 100 GiB");
    await expect(cards.nth(1)).toContainText("2026-10-22 12:00");
    await expect(cards.nth(1)).toContainText("2026-11-22 12:00");
    await cards.nth(1).getByRole("button", { name: "Подробнее об услуге" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText(copy.wa_services_usage_stale);
    await expect(dialog).toContainText("23 GiB / 100 GiB");
    await expect(dialog.locator("[data-service-remaining]")).toContainText("77 GiB");
    await expect(dialog.locator("[data-service-remaining]")).toContainText("2026-10-22 12:00");
    await expect(dialog).toContainText("2026-10-22 12:00");
    await expect(dialog).toContainText("192.0.2.10");
    await expect(dialog).toContainText("Ожидает проверки");
    await expect(dialog).toContainText("ссылка подписки пока недоступна");
    await dialog.screenshot({ path: testInfo.outputPath(`service-detail-${width}.png`) });
    expect(
      await dialog.evaluate((node) => node.scrollWidth - node.clientWidth)
    ).toBeLessThanOrEqual(2);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await screen.getByRole("button", { name: "Далее", exact: true }).click();
    await expect(cards).toHaveCount(2);
    await screen.getByRole("button", { name: "Каталог тарифов", exact: true }).click();
    await expect(screen).toContainText("29.90 CNY");
    await expect(screen).toContainText("365 дней");
    await expect(screen).toContainText("Услуги подключает администратор");
    await expect(screen.locator("[data-service-id]")).toHaveCount(0);
    await screen.getByRole("button", { name: "Мои услуги", exact: true }).click();
    await expect(cards).toHaveCount(10);
    await page.screenshot({
      path: testInfo.outputPath(`service-home-${width}.png`),
      fullPage: true,
    });
    expect(
      await screen.evaluate((node) => node.scrollWidth - node.clientWidth)
    ).toBeLessThanOrEqual(2);
    await expect(page.locator('[data-webapp-action="open-payment-history"]')).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test(`empty service account retains settings and security at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(url("/", "services-empty"));
    await expect(page.locator(".services-home")).toContainText("Услуг пока нет");
    await page.getByRole("button", { name: "Открыть мои тарифы", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Услуг пока нет" })).toBeVisible();
    await page.goto(url("/settings", "services-empty"));
    await expect(page.locator(".settings-profile")).toBeVisible();
    await expect(page.locator('[data-webapp-action="open-payment-history"]')).toHaveCount(0);
    await expect(page.locator(".settings-profile-balance")).toHaveCount(0);
    await page.goto(url("/settings/security", "services-empty"));
    await expect(page.locator(".security-screen")).toBeVisible();
    await expect(page.locator('[data-webapp-action="open-subscription-reissue"]')).toHaveCount(0);
    await page.getByRole("button", { name: /(?:Задать|Изменить) пароль/ }).click();
    await expect(page.locator(".webapp-set-password-dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });
}

test("old checkout and bonus deep links do not open competing subscription flows", async ({
  page,
}) => {
  await page.goto(`${url("/checkout")}&promo=GIFT7&topup=regular`);
  await expect(page.locator(".services-home")).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".checkout-entry-screen")).toHaveCount(0);
  await page.goto(url("/invite"));
  await expect(page.locator(".services-home")).toBeVisible();
});
