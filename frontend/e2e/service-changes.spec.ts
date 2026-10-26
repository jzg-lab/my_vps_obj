import { expect, test, type Page } from "@playwright/test";

async function choose(page: Page, label: string, value: string) {
  await page.getByRole("button", { name: label, exact: true }).click();
  await page.getByRole("option", { name: value, exact: true }).click();
  await expect(page.locator(".admin-select-content")).toHaveCount(0);
}

for (const width of [1440, 390]) {
  test(`single-service changes and separate operation history at ${width}px`, async ({
    page,
  }, testInfo) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/demo/runtime/admin/users?theme_preview=dark");
    await page.locator("tr[data-user-id]").first().click();
    await page.setViewportSize({ width, height: 1000 });
    const region = page.getByRole("region", { name: "Независимые услуги" });
    await expect(region).toContainText("Независимых услуг пока нет.");
    for (let count = 1; count <= 2; count++) {
      await region.getByRole("button", { name: "Подключить услугу", exact: true }).click();
      const activation = page.getByRole("dialog");
      const submit = activation.getByRole("button", { name: "Подключить услугу", exact: true });
      await expect(submit).toBeDisabled();
      await choose(page, "Выберите тариф", "Demo total");
      const preflight = activation.getByRole("region", { name: "Проверка перед активацией" });
      await expect(preflight).toContainText("Можно создать запись услуги, ожидающей выдачи.");
      await expect(preflight).toContainText("Готовность ресурсов: Неизвестно");
      await expect(preflight).toContainText("Готовность к выдаче не подтверждена");
      await expect(submit).toBeEnabled();
      await submit.click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(region.locator("tbody tr")).toHaveCount(count);
    }
    await region.locator(":scope > details > summary").click();
    const first = region.locator("tbody tr").first();
    const other = region.locator("tbody tr").nth(1);
    const originalOther = await other.innerText();
    await first.getByRole("button", { name: "Управление", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByLabel("Добавить дней", { exact: true })).toHaveValue("");
    await dialog.getByRole("button", { name: "Операция", exact: true }).click();
    await expect(page.getByRole("option", { name: "Приостановить", exact: true })).toBeVisible();
    await expect(page.locator(".admin-select-content")).toHaveCSS("opacity", "1");
    await page.screenshot({ path: testInfo.outputPath(`change-menu-${width}.png`) });
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(1);
    await expect(page.locator(".admin-select-content")).toHaveCount(0);
    await dialog.getByLabel("Добавить дней", { exact: true }).fill("31");
    await dialog.getByLabel("Добавить дней", { exact: true }).fill("");
    await choose(page, "Операция", "Приостановить");
    await choose(page, "Операция", "Продлить");
    await expect(dialog.getByLabel("Добавить дней", { exact: true })).toHaveValue("");
    await dialog.getByLabel("Добавить дней", { exact: true }).fill("31");
    await dialog.getByLabel("Цена в записи", { exact: true }).fill("7.90");
    await dialog.screenshot({ path: testInfo.outputPath(`renewal-${width}.png`) });
    expect(
      await dialog.evaluate((node) => node.scrollWidth - node.clientWidth)
    ).toBeLessThanOrEqual(2);
    await dialog.getByRole("button", { name: "Сохранить", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(first).toContainText("Изменение сохранено; ожидается подтверждение панели.");
    await expect(first).toContainText("Неизвестно / 100 GiB");
    await expect(first).toContainText("Ещё не синхронизировано");
    await expect(first).not.toContainText("0 B / 100 GiB");
    expect(await other.innerText()).toBe(originalOther);
    for (const action of ["Приостановить", "Возобновить"]) {
      await first.getByRole("button", { name: "Управление", exact: true }).click();
      await choose(page, "Операция", action);
      await dialog.getByRole("button", { name: "Сохранить", exact: true }).click();
      await expect(dialog).toHaveCount(0);
      await expect(first).toContainText(
        action === "Приостановить" ? "Приостановлена" : "Ожидает настройки подключения"
      );
      expect(await other.innerText()).toBe(originalOther);
    }
    await first.getByRole("button", { name: "История", exact: true }).click();
    await expect(dialog.locator("tbody tr")).toHaveCount(4);
    await expect(dialog).toContainText("7.90 CNY");
    await expect(dialog).toContainText("29.90 CNY");
    await expect(dialog.locator("tbody tr").filter({ hasText: "Продлить" })).toContainText(
      "7.90 CNY"
    );
    await dialog.screenshot({ path: testInfo.outputPath(`changes-history-${width}.png`) });
    expect(
      await dialog.evaluate((node) => node.scrollWidth - node.clientWidth)
    ).toBeLessThanOrEqual(2);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await region.screenshot({ path: testInfo.outputPath(`changes-list-${width}.png`) });
    expect(
      await region.evaluate((node) => node.scrollWidth - node.clientWidth)
    ).toBeLessThanOrEqual(2);
    expect(errors).toEqual([]);
  });
}
