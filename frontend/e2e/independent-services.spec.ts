import { expect, test, type Page } from "@playwright/test";

const adminUrl = (route: string) => `/demo/runtime/admin/${route}?theme_preview=dark`;
async function select(page: Page, label: string, value: string) {
  await page.getByRole("button", { name: label, exact: true }).click();
  const option = page.getByRole("option", { name: value, exact: true });
  await option.click();
  await expect(page.locator(".admin-select-content")).toHaveCount(0);
  await expect(page.getByRole("button", { name: label, exact: true })).toContainText(value);
}

for (const width of [1440, 390]) {
  test(`independent plan editing preserves type, price and monthly terms at ${width}px`, async ({
    page,
  }, testInfo) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(adminUrl("service-plans"));
    await expect(page.getByRole("cell", { name: "Demo total", exact: false })).toBeVisible();
    await page.getByRole("button", { name: "Новый тариф", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Название тарифа", { exact: true }).fill("Custom monthly");
    await select(page, "Тип ресурса", "Выделенный IP");
    await select(page, "Правило учёта трафика", "Ежемесячный лимит");
    await dialog.getByLabel(/^Лимит \(ГиБ\)/).fill("25.5");
    await dialog.getByLabel("Срок (дни)", { exact: true }).fill("365");
    await dialog.getByLabel("Цена", { exact: true }).fill("39.90");
    await dialog.getByLabel(/^Пул ресурсов/).fill("demo");
    await dialog.screenshot({ path: testInfo.outputPath(`plan-form-${width}.png`) });
    expect(
      await dialog.evaluate((node) => node.scrollWidth - node.clientWidth)
    ).toBeLessThanOrEqual(2);
    await dialog.getByRole("button", { name: "Сохранить", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    const row = page.locator("tbody tr").filter({ hasText: "Custom monthly" });
    await expect(row).toContainText("25.5 GiB");
    await expect(row).toContainText("39.90 CNY");
    await row.getByRole("button", { name: "Изменить тариф" }).click();
    await expect(dialog.getByLabel(/^Лимит \(ГиБ\)/)).toHaveValue("25.5");
    await expect(dialog.getByRole("button", { name: "Тип ресурса" })).toContainText(
      "Выделенный IP"
    );
    await dialog.getByLabel("Цена", { exact: true }).fill("49.90");
    await dialog.getByRole("button", { name: "Сохранить", exact: true }).click();
    await expect(row).toContainText("Версия 2");
    await expect(row).toContainText("49.90 CNY");
    await page.screenshot({ path: testInfo.outputPath(`plan-list-${width}.png`), fullPage: true });
    expect(errors).toEqual([]);
  });

  test(`one user can receive two copies without replacement at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(adminUrl("users"));
    await page.locator("tr[data-user-id]").first().click();
    await page.setViewportSize({ width, height: 1000 });
    const services = page.getByRole("region", { name: "Независимые услуги" });
    await expect(services).toBeVisible();
    await expect(services).toContainText("Независимых услуг пока нет.");
    for (let count = 1; count <= 2; count++) {
      await services.getByRole("button", { name: "Подключить услугу", exact: true }).click();
      await select(page, "Выберите тариф", "Demo total");
      const dialog = page.getByRole("dialog");
      await dialog.getByRole("button", { name: "Подключить услугу", exact: true }).click();
      await expect(dialog).toHaveCount(0);
      await expect(services.locator("tbody tr")).toHaveCount(count);
    }
    await expect(services.getByText("Ожидает настройки подключения", { exact: true })).toHaveCount(
      2
    );
    await expect(services.getByText("100 GiB", { exact: true })).toHaveCount(2);
    const badges = services.locator(".service-status");
    for (const badge of await badges.all()) {
      const bounds = await badge.evaluate((node) => {
        const box = node.getBoundingClientRect();
        const parent = node.parentElement!.getBoundingClientRect();
        return { width: box.width, available: parent.width };
      });
      expect(bounds.width).toBeLessThanOrEqual(bounds.available + 1);
    }
    await services.screenshot({ path: testInfo.outputPath(`two-services-${width}.png`) });
    expect(
      await services.evaluate((node) => node.scrollWidth - node.clientWidth)
    ).toBeLessThanOrEqual(2);
  });

  test(`exit registration stays explicitly unverified at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(adminUrl("dedicated-exits"));
    await expect(page.getByRole("cell", { name: /192\.0\.2\.10/ })).toBeVisible();
    await expect(page.getByRole("cell", { name: /Не проверен/ })).toBeVisible();
    await page.getByRole("button", { name: "Добавить выход", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Название ресурса", { exact: true }).fill("New exclusive exit");
    await dialog.getByLabel("IP-адрес выхода", { exact: true }).fill("192.0.2.11");
    await dialog.getByLabel("Пул ресурсов", { exact: true }).fill("demo");
    await dialog.getByRole("button", { name: "Группа выделенного выхода", exact: true }).click();
    await page.getByRole("option").first().click();
    await expect(page.locator(".admin-select-content")).toHaveCount(0);
    await dialog.screenshot({ path: testInfo.outputPath(`exit-form-${width}.png`) });
    await dialog.getByRole("button", { name: "Сохранить", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    const row = page.locator("tbody tr").filter({ hasText: "192.0.2.11" });
    await expect(row).toContainText("Не проверен");
    await expect(row).toContainText("Свободен");
  });
}
