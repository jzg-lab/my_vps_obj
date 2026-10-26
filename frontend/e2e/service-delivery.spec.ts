import { expect, test } from "@playwright/test";

for (const width of [1440, 390]) {
  test(`service-specific import and update at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/demo/runtime/services?mock=services&delivery=1&theme_preview=dark");
    const cards = page.locator("[data-service-id]");
    await cards.first().getByRole("button", { name: "Подробнее об услуге" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("button", { name: "Импорт подписки", exact: true })).toHaveCount(
      0
    );
    await page.keyboard.press("Escape");
    const links: string[] = [];
    for (const index of [2, 3]) {
      await cards.nth(index).getByRole("button", { name: "Подробнее об услуге" }).click();
      const section = dialog.getByRole("region", { name: "Импорт подписки" });
      await section.getByRole("button", { name: "Импорт подписки", exact: true }).click();
      const field = section.getByRole("textbox", { name: "Импорт подписки" });
      await expect(field).toHaveValue(/https:\/\/subscription.example.test\/demo-only\//);
      links.push(await field.inputValue());
      await section.getByRole("button", { name: "Обновить ссылку подписки" }).click();
      await expect(field).toHaveValue(links.at(-1)!);
      await field.click();
      await expect(field).toBeFocused();
      await dialog.screenshot({ path: testInfo.outputPath(`import-${width}-${index}.png`) });
      expect(
        await dialog.evaluate((node) => node.scrollWidth - node.clientWidth)
      ).toBeLessThanOrEqual(2);
      await page.keyboard.press("Escape");
      await expect(page.locator(".service-subscription")).toHaveCount(0);
    }
    expect(links[0]).not.toEqual(links[1]);
    const storage = await page.evaluate(() =>
      JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage)])
    );
    expect(storage).not.toContain("subscription.example.test");
  });

  test(`resource evidence and audit at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/demo/runtime/admin/dedicated-exits?theme_preview=dark");
    const row = page.locator("tbody tr").filter({ hasText: "192.0.2.10" });
    await row.getByRole("button", { name: "Проверка и возврат" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("Проверка или возврат ещё не зафиксированы.");
    await dialog.getByRole("button", { name: "Действие с ресурсом", exact: true }).click();
    await expect(page.getByRole("option", { name: "Подтвердить проверку выхода" })).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath(`exit-menu-${width}.png`),
      animations: "disabled",
    });
    await page.keyboard.press("Escape");
    await expect(
      page.getByRole("option", { name: "Подтвердить проверку выхода" })
    ).not.toBeVisible();
    await expect(dialog).toBeVisible();
    await dialog.getByLabel("Наблюдаемый IP выхода", { exact: true }).fill("192.0.2.10");
    await dialog
      .getByLabel("Результаты и ссылка на проверку", { exact: true })
      .fill("UI fixture only: no real Node is used by this test.");
    await dialog.getByRole("checkbox").check();
    await dialog.screenshot({
      path: testInfo.outputPath(`exit-evidence-${width}.png`),
      animations: "disabled",
    });
    expect(
      await dialog.evaluate((node) => node.scrollWidth - node.clientWidth)
    ).toBeLessThanOrEqual(2);
    await dialog.getByRole("button", { name: "Сохранить", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(row).toContainText("Проверен");
    await row.getByRole("button", { name: "Проверка и возврат" }).click();
    await expect(dialog).toContainText("UI fixture only: no real Node is used by this test.");
    await dialog.screenshot({ path: testInfo.outputPath(`exit-audit-${width}.png`) });
    await page.keyboard.press("Escape");
  });

  test(`service revocation preserves the other service at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(
      "/demo/runtime/admin/users?delivery=1&theme_preview=dark&mock=cancelled-reconciliation"
    );
    await page.locator("tr[data-user-id]").first().click();
    await page.setViewportSize({ width, height: 1000 });
    const region = page.getByRole("region", { name: "Независимые услуги" });
    for (let index = 0; index < 2; index++) {
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
    }
    await region.locator(":scope > details > summary").click();
    const first = region.locator("tbody tr").first();
    const other = region.locator("tbody tr").nth(1);
    const previous = await other.innerText();
    await first.getByRole("button", { name: "Выдать подключение", exact: true }).click();
    const delivery = page.getByRole("dialog");
    await delivery.getByRole("checkbox").check();
    await delivery.screenshot({ path: testInfo.outputPath(`deliver-${width}.png`) });
    expect(
      await delivery.evaluate((node) => node.scrollWidth - node.clientWidth)
    ).toBeLessThanOrEqual(2);
    await delivery.getByRole("button", { name: "Выдать подключение", exact: true }).click();
    await expect(delivery).toHaveCount(0);
    await expect(first).toContainText("Активна");
    expect(await other.innerText()).toBe(previous);
    await first.getByRole("button", { name: "Отозвать услугу", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Причина отзыва", { exact: true }).fill("UI cancellation fixture");
    await dialog.getByRole("checkbox").check();
    await dialog.screenshot({ path: testInfo.outputPath(`revoke-${width}.png`) });
    expect(
      await dialog.evaluate((node) => node.scrollWidth - node.clientWidth)
    ).toBeLessThanOrEqual(2);
    await dialog.getByRole("button", { name: "Отозвать услугу", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(first).toContainText("Отменена");
    expect(await other.innerText()).toBe(previous);
    await first.getByRole("button", { name: "Управление", exact: true }).click();
    await dialog.getByRole("button", { name: "Операция", exact: true }).click();
    await expect(page.getByRole("option")).toHaveCount(1);
    await expect(page.getByRole("option", { name: "Сверить трафик", exact: true })).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath(`cancelled-actions-${width}.png`),
      animations: "disabled",
    });
    await page.keyboard.press("Escape");
    await expect(dialog).toBeVisible();
    await dialog.getByLabel("Проверенный общий расход (байты)", { exact: true }).fill("600");
    await dialog.getByLabel("Проверенный счётчик панели (байты)", { exact: true }).fill("100");
    await dialog
      .getByLabel("Точные записи и обоснование сверки", { exact: true })
      .fill("Exact cancelled-service ledger");
    await dialog.screenshot({
      path: testInfo.outputPath(`cancelled-reconciliation-${width}.png`),
      animations: "disabled",
    });
    await dialog.getByRole("button", { name: "Сохранить", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(first).toContainText("Отменена");
    await expect(first).toContainText("600 B");
    await expect(first.getByRole("button", { name: "Управление", exact: true })).toHaveCount(0);
    expect(await other.innerText()).toBe(previous);
    await first.getByRole("button", { name: "История", exact: true }).click();
    await expect(dialog).toContainText("UI cancellation fixture");
    await expect(dialog).toContainText("Exact cancelled-service ledger");
    await page.keyboard.press("Escape");
  });
}
