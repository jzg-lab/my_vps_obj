import { expect, test } from "@playwright/test";

const url = (scenario = "") =>
  `/demo/runtime/admin/service-history?theme_preview=dark&mock=${scenario}`;

for (const width of [1440, 390]) {
  test(`archived services retain their own activation price and paginate at ${width}px`, async ({
    page,
  }, testInfo) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(url());
    const history = page.getByRole("region", { name: "История услуг", exact: true });
    await expect(history.locator("tbody tr")).toHaveCount(25);
    await expect(history.locator("tbody tr").first()).toContainText(
      "Расход не удалось проверить. Показано последнее подтверждённое значение."
    );
    await history
      .locator("tbody tr")
      .first()
      .screenshot({
        path: testInfo.outputPath(`usage-unconfirmed-${width}.png`),
      });
    await expect(
      history.getByRole("button", { name: "Подключить услугу", exact: true })
    ).toHaveCount(0);
    await history.getByRole("button", { name: "Далее", exact: true }).click();
    await expect(history.locator("tbody tr")).toHaveCount(1);
    await expect(history).toContainText("Archived plan 26");
    await history.getByRole("button", { name: "История", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.locator("tbody tr")).toHaveCount(1);
    await expect(dialog).toContainText("19.90 CNY");
    await expect(dialog).not.toContainText("29.90 CNY");
    await expect(dialog).toContainText("Archived plan 26");
    await expect(dialog).not.toContainText("Archived plan 1");
    await expect(dialog).toContainText("100 GiB");
    await expect(dialog).toContainText("2026-10-22 12:00");
    await expect(dialog).toContainText("2027-01-20 12:00");
    await dialog.screenshot({ path: testInfo.outputPath(`activation-history-${width}.png`) });
    expect(
      await dialog.evaluate((node) => node.scrollWidth - node.clientWidth)
    ).toBeLessThanOrEqual(2);
    expect(
      await dialog
        .locator(".admin-table-wrap")
        .evaluate((node) => node.scrollWidth - node.clientWidth)
    ).toBeLessThanOrEqual(2);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(history).toContainText("Archived plan 26");
    await history.getByRole("button", { name: "Назад", exact: true }).click();
    await expect(history.locator("tbody tr")).toHaveCount(25);
    expect(errors).toEqual([]);
  });

  test(`history handles empty results and retry without showing invented snapshots at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(url("history-empty"));
    const history = page.getByRole("region", { name: "История услуг", exact: true });
    await expect(history).toContainText("Сохранённых услуг пока нет.");
    await page.goto(url("history-retry"));
    await expect(history.getByRole("alert")).toBeVisible();
    await expect(history.locator("tbody tr")).toHaveCount(0);
    await history.getByRole("button", { name: "Обновить", exact: true }).click();
    await expect(history.locator("tbody tr")).toHaveCount(25);
    await page.goto(url("history-orders-retry"));
    await history.getByRole("button", { name: "История", exact: true }).first().click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("alert")).toBeVisible();
    await expect(dialog).not.toContainText("19.90 CNY");
    await dialog.getByRole("button", { name: "Обновить", exact: true }).click();
    await expect(dialog).toContainText("19.90 CNY");
    await expect(dialog.getByRole("alert")).toHaveCount(0);
  });
}
