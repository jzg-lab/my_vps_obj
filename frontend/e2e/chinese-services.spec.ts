import { expect, test, type Page } from "@playwright/test";
const url = (path: string) => `/demo/runtime/${path}?mock=services&theme_preview=dark`;
async function chooseChinese(page: Page) {
  await page.goto(url("settings"));
  await page.locator(".language-select-trigger:not(.theme-select-trigger)").click();
  await page.getByRole("option", { name: /简体中文/ }).click();
  await expect(page.locator(".language-select-trigger:not(.theme-select-trigger)")).toContainText("语言");
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-hans");
}
for (const width of [1440, 390]) {
  test(`Chinese service preferences, details and calendar at ${width}px`, async ({
    page,
  }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await chooseChinese(page);
    await page.reload();
    await expect(page.locator(".language-select-trigger:not(.theme-select-trigger)")).toContainText("简体中文");
    await expect(page.locator("html")).toHaveAttribute("lang", "zh-hans");
    await page.goto(url("app/"));
    const screen = page.locator(".services-screen");
    await expect(screen.getByRole("heading", { name: "我的服务", exact: true })).toBeVisible();
    const service = screen.locator("[data-service-id]").nth(1);
    await expect(service).toContainText("2026-11-22 12:00");
    await service.getByRole("button", { name: "服务详情", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("等待核验");
    await expect(dialog).toContainText("北京时间");
    await expect(dialog).toContainText("192.0.2.10");
    await expect(dialog).toContainText("暂未提供订阅链接");
    expect(
      await dialog.evaluate((node) => node.scrollWidth - node.clientWidth)
    ).toBeLessThanOrEqual(2);
    await dialog.screenshot({ path: info.outputPath(`chinese-service-${width}.png`) });
    await page.keyboard.press("Escape");
    await screen.getByRole("button", { name: "套餐目录", exact: true }).click();
    await expect(screen).toContainText("365 天");
    await expect(screen).toContainText("29.90 CNY");
    await expect(screen).toContainText("管理员人工开通");
    await page.goto(url("settings/security"));
    await page.getByRole("button", { name: /设置密码|修改密码/ }).click();
    await expect(page.getByRole("dialog")).toContainText("邮箱登录密码");
    await page.keyboard.press("Escape");
    await page.goto(url("settings"));
    await page.locator(".language-select-trigger:not(.theme-select-trigger)").click();
    await page.getByRole("option", { name: /English/ }).click();
    await expect(page.locator(".language-select-trigger:not(.theme-select-trigger)")).toContainText("Language");
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
  });
  test(`Chinese admin plans, resources, accounts and history at ${width}px`, async ({
    page,
  }, info) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 1000 });
    await chooseChinese(page);
    await page.goto(url("admin/service-plans"));
    await page.getByRole("button", { name: "新建套餐", exact: true }).click();
    let dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("已开通服务保留原始条款");
    await dialog.getByRole("button", { name: "资源类型", exact: true }).click();
    await page.getByRole("option", { name: "专用 IP", exact: true }).click();
    await dialog.getByRole("button", { name: "流量规则", exact: true }).click();
    await page.getByRole("option", { name: "月度额度", exact: true }).click();
    await expect(page.locator(".admin-select-content")).toHaveCount(0);
    await dialog.getByLabel("套餐名称", { exact: true }).fill(" ");
    await dialog.getByLabel(/^额度/).fill("25");
    await dialog.getByLabel("有效期（天）", { exact: true }).fill("30");
    await dialog.getByLabel("价格", { exact: true }).fill("5");
    await dialog.getByLabel(/^资源池/).fill("demo");
    await dialog.getByRole("button", { name: "保存", exact: true }).click();
    await expect(dialog).toContainText("请填写名称");
    expect(
      await dialog.evaluate((node) => node.scrollWidth - node.clientWidth)
    ).toBeLessThanOrEqual(2);
    await dialog.screenshot({ path: info.outputPath(`chinese-plan-${width}.png`) });
    await page.keyboard.press("Escape");
    await page.goto(url("admin/dedicated-exits"));
    await page.getByRole("button", { name: "登记出口", exact: true }).click();
    await expect(page.getByRole("dialog")).toContainText("确认连接停用后再手动回收");
    await page.keyboard.press("Escape");
    await page.goto(url("admin/users"));
    await (
      width < 800
        ? page.locator(".admin-user-mobile-card").first()
        : page.locator("tr[data-user-id]").first()
    ).click();
    await expect(page.getByRole("region", { name: "独立服务", exact: true })).toBeVisible();
    await page.locator('[data-admin-action="request-user-delete"]').click();
    await expect(page.getByRole("dialog")).toContainText("独立服务和开通历史将保留");
    await page.keyboard.press("Escape");
    await page.goto(url("admin/service-history"));
    const history = page.getByRole("region", { name: "服务历史", exact: true });
    await history.getByRole("button", { name: "查看历史", exact: true }).first().click();
    dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("记录价格不代表已付款");
    await expect(dialog).toContainText("19.90 CNY");
    expect(
      await dialog.evaluate((node) => node.scrollWidth - node.clientWidth)
    ).toBeLessThanOrEqual(2);
    await dialog.screenshot({ path: info.outputPath(`chinese-history-${width}.png`) });
    await page.keyboard.press("Escape");
    await page.goto(url("admin/settings"));
    await expect(page.getByPlaceholder("按名称或说明搜索设置")).toBeVisible();
    await page.getByPlaceholder("按名称或说明搜索设置").fill("默认语言");
    await expect(page.getByText("默认语言", { exact: true }).first()).toBeVisible();
    expect(errors).toEqual([]);
  });
}
