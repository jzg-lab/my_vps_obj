import { expect, test } from "@playwright/test";

for (const width of [1440, 390]) {
  test(`Chinese guide uses only the selected service at ${width}px`, async ({ page }, info) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 1000 });
    await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.goto("/demo/runtime/settings?mock=services&delivery=1&theme_preview=dark");
    await page.locator(".language-select-trigger:not(.theme-select-trigger)").click();
    await page.getByRole("option", { name: /简体中文/ }).click();
    await expect(page.locator("html")).toHaveAttribute("lang", "zh-hans");
    await page.goto("/demo/runtime/app/?mock=services&delivery=1&theme_preview=dark");

    const cards = page.locator("[data-service-id]");
    const links: string[] = [];
    for (const index of [2, 3]) {
      await cards.nth(index).getByRole("button", { name: "服务详情" }).click();
      const dialog = page.getByRole("dialog");
      const subscription = dialog.getByRole("region", { name: "导入订阅" });
      await subscription.getByRole("button", { name: "导入订阅", exact: true }).click();
      const field = subscription.getByRole("textbox", { name: "导入订阅" });
      await expect(field).toHaveValue(/https:\/\/subscription.example.test\/demo-only\//);
      links.push(await field.inputValue());
      const guide = subscription.locator(".service-guide");
      await guide.locator("summary").click();
      await guide.locator(".install-platform-trigger").click();
      await page.getByRole("option", { name: "Windows", exact: true }).click();
      await expect(page.getByRole("option", { name: "Windows", exact: true })).not.toBeVisible();
      await expect(guide.locator(".install-platform-trigger")).toContainText("Windows");
      await expect(guide.getByRole("button", { name: "复制本服务订阅链接" })).toBeVisible();
      await guide.getByRole("button", { name: "复制本服务订阅链接" }).click();
      expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(links.at(-1));
      await expect(guide).toContainText("导入这份服务");
      expect(await guide.innerText()).not.toMatch(/[А-Яа-яЁё]/);
      expect(
        await dialog.evaluate((node) => node.scrollWidth - node.clientWidth)
      ).toBeLessThanOrEqual(2);
      await guide.screenshot({
        path: info.outputPath(`guide-${width}-${index}.png`),
        animations: "disabled",
      });
      await page.keyboard.press("Escape");
      await expect(page.locator(".service-guide")).toHaveCount(0);
    }
    expect(links[0]).not.toBe(links[1]);

    await cards.nth(3).getByRole("button", { name: "服务详情" }).click();
    const subscription = page.getByRole("region", { name: "导入订阅" });
    await subscription.getByRole("button", { name: "导入订阅", exact: true }).click();
    await expect(subscription.getByRole("textbox", { name: "导入订阅" })).toHaveValue(links[1]);
    await page.evaluate(() => {
      const url = new URL(location.href);
      url.searchParams.set("delivery_fail", "1");
      history.replaceState(null, "", url);
    });
    await subscription.getByRole("button", { name: "刷新订阅链接" }).click();
    await expect(subscription.getByRole("textbox", { name: "导入订阅" })).toHaveCount(0);
    await expect(subscription.locator(".service-guide")).toHaveCount(0);
    await expect(subscription).toContainText("无法确认连接交付");
    expect(errors).toEqual([]);
  });

  test(`service guide config failure can be retried at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/demo/runtime/settings?mock=services&delivery=1&theme_preview=dark");
    await page.locator(".language-select-trigger:not(.theme-select-trigger)").click();
    await page.getByRole("option", { name: /简体中文/ }).click();
    await expect(page.locator("html")).toHaveAttribute("lang", "zh-hans");
    await page.goto("/demo/runtime/app/?mock=services&delivery=1&guide_fail=1");
    await page
      .locator("[data-service-id]")
      .nth(2)
      .getByRole("button", { name: "服务详情" })
      .click();
    const subscription = page.getByRole("region", { name: "导入订阅" });
    await subscription.getByRole("button", { name: "导入订阅", exact: true }).click();
    const field = subscription.getByRole("textbox", { name: "导入订阅" });
    await expect(field).toHaveValue(/https:\/\/subscription.example.test\/demo-only\//);
    const guide = subscription.locator(".service-guide");
    await guide.locator("summary").click();
    await expect(guide.getByRole("alert")).toContainText("教程暂不可用");
    await expect(guide.getByRole("button", { name: "复制本服务订阅链接" })).toHaveCount(0);
    await page.evaluate(() => {
      const url = new URL(location.href);
      url.searchParams.delete("guide_fail");
      history.replaceState(null, "", url);
    });
    await guide.getByRole("button", { name: "重试" }).click();
    await expect(guide.getByRole("button", { name: "复制本服务订阅链接" })).toBeVisible();
    await expect(field).toHaveValue(/https:\/\/subscription.example.test\/demo-only\//);
  });
}
