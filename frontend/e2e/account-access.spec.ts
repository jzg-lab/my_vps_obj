import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";

const locale: Record<string, string> = JSON.parse(readFileSync("../locales/ru.json", "utf8"));

for (const width of [1440, 390]) {
  test(`account access shows saved intent and panel confirmation at ${width}px`, async ({
    page,
  }, testInfo) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/demo/runtime/admin/users?theme_preview=dark");
    await page.locator("tr[data-user-id]").first().click();
    await page.setViewportSize({ width, height: 1000 });
    await page.getByRole("tab", { name: "Действия", exact: true }).click();
    const status = page.getByRole("region", { name: locale.admin_account_access_title });
    await expect(status).toContainText(locale.admin_account_access_scope);
    await expect(status).toContainText("Изменение подключений аккаунта не запрошено");
    const toggle = page.locator('[data-admin-action="request-user-ban-toggle"]');
    await toggle.click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("Все подключения услуг будут отключены");
    await dialog.getByRole("button", { name: "Заблокировать", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(status).toContainText("Ожидает синхронизации");
    await expect(toggle).toContainText("Разбанить пользователя");
    await status.screenshot({ path: testInfo.outputPath(`access-pending-${width}.png`) });
    expect(
      await status.evaluate((node) => node.scrollWidth - node.clientWidth)
    ).toBeLessThanOrEqual(2);
    await status.getByRole("button", { name: "Повторить синхронизацию" }).click();
    await expect(status).toContainText("Состояние панели подтверждено");
    await expect(
      status.getByRole("button", { name: "Повторить синхронизацию" })
    ).toHaveCount(0);
    await toggle.click();
    await expect(status).toContainText("Ожидает синхронизации");
    await expect(toggle).toContainText("Заблокировать");
    await status.getByRole("button", { name: "Повторить синхронизацию" }).click();
    await expect(status).toContainText("Состояние панели подтверждено");
    expect(errors).toEqual([]);
  });
}
