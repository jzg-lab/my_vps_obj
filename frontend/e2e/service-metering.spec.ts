import { expect, test } from "@playwright/test";

for (const width of [1440, 390]) {
  test(`quota edit explains existing-service impact and requires a reason at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/demo/runtime/admin/service-plans?theme_preview=dark");
    await page
      .locator("tbody tr")
      .filter({ hasText: "Demo total" })
      .getByRole("button", { name: "Изменить тариф" })
      .click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel(/^Лимит \(ГиБ\)/).fill("75");
    await dialog.getByRole("button", { name: "Сохранить", exact: true }).click();
    await expect(dialog.getByRole("alert")).toContainText("Укажите причину");
    await dialog
      .getByLabel("Причина изменения квоты", { exact: true })
      .fill("Verified allowance change");
    await dialog.screenshot({
      path: testInfo.outputPath(`quota-${width}.png`),
      animations: "disabled",
    });
    expect(
      await dialog.evaluate((node) => node.scrollWidth - node.clientWidth)
    ).toBeLessThanOrEqual(2);
    await dialog.getByRole("button", { name: "Сохранить", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.locator("tbody tr").filter({ hasText: "Demo total" })).toContainText(
      "75 GiB"
    );
  });

  test(`exact usage reconciliation preserves pause and displays its audit at ${width}px`, async ({
    page,
  }, testInfo) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/demo/runtime/admin/users?theme_preview=dark&mock=usage-reconciliation");
    await page.locator("tr[data-user-id]").first().click();
    await page.setViewportSize({ width, height: 1000 });
    const region = page.getByRole("region", { name: "Независимые услуги" });
    await region.getByRole("button", { name: "Подключить услугу", exact: true }).click();
    const activation = page.getByRole("dialog");
    const submit = activation.getByRole("button", { name: "Подключить услугу", exact: true });
    await expect(submit).toBeDisabled();
    await page.getByRole("button", { name: "Выберите тариф", exact: true }).click();
    await page.getByRole("option", { name: "Demo total", exact: true }).click();
    const preflight = activation.getByRole("region", { name: "Проверка перед активацией" });
    await expect(preflight).toContainText("Можно создать запись услуги, ожидающей выдачи.");
    await expect(preflight).toContainText("Готовность ресурсов: Неизвестно");
    await expect(preflight).toContainText("Готовность к выдаче не подтверждена");
    await expect(submit).toBeEnabled();
    await submit.click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await region.locator(":scope > details > summary").click();
    await region.getByRole("button", { name: "Управление", exact: true }).click();
    await page.getByRole("button", { name: "Операция", exact: true }).click();
    await expect(page.getByRole("option", { name: "Сверить трафик", exact: true })).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath(`metering-menu-${width}.png`),
      animations: "disabled",
    });
    await page.getByRole("option", { name: "Сверить трафик", exact: true }).click();
    await expect(page.getByRole("option", { name: "Сверить трафик", exact: true })).toBeHidden();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Проверенный общий расход (байты)", { exact: true }).fill("600");
    await dialog.getByLabel("Проверенный счётчик панели (байты)", { exact: true }).fill("100");
    await dialog
      .getByLabel("Точные записи и обоснование сверки", { exact: true })
      .fill("Exact per-identity ledger, incident 42");
    await dialog.screenshot({
      path: testInfo.outputPath(`reconciliation-${width}.png`),
      animations: "disabled",
    });
    expect(
      await dialog.evaluate((node) => node.scrollWidth - node.clientWidth)
    ).toBeLessThanOrEqual(2);
    await dialog.getByRole("button", { name: "Сохранить", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(region).toContainText("600 B");
    await expect(region).not.toContainText("Неизвестно / 100 GiB");
    await expect(region).not.toContainText("Ещё не синхронизировано");
    await expect(region).toContainText("Приостановлена");
    await region.getByRole("button", { name: "История", exact: true }).click();
    await expect(dialog).toContainText("Exact per-identity ledger, incident 42");
    await expect(dialog).toContainText("500 B → 600 B");
    await dialog.screenshot({
      path: testInfo.outputPath(`metering-history-${width}.png`),
      animations: "disabled",
    });
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    expect(errors).toEqual([]);
  });
}

for (const width of [1440, 390]) {
  test(`monthly confirmation notice retains confirmed usage at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/demo/runtime/services?mock=services&cycle_pending=1&theme_preview=dark");
    const card = page.locator("[data-service-id]").nth(1);
    await expect(card).toContainText("23 GiB / 100 GiB");
    await expect(card).toContainText("Ожидается подтверждение месячной квоты");
    await card.getByRole("button", { name: "Подробнее об услуге" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("23 GiB / 100 GiB");
    await expect(dialog).toContainText("сохранённой отметки переключения");
    await dialog.screenshot({
      path: testInfo.outputPath(`cycle-pending-${width}.png`),
      animations: "disabled",
    });
    expect(
      await dialog.evaluate((node) => node.scrollWidth - node.clientWidth)
    ).toBeLessThanOrEqual(2);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
  });
}
