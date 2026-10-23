import { expect, test, type Page } from "@playwright/test";
const url = (path: string) => `/demo/runtime/${path}?mock=services&theme_preview=dark`;
async function chooseChinese(page: Page) {
  await page.goto(url("settings"));
  await page.locator(".language-select-trigger:not(.theme-select-trigger)").click();
  await page.getByRole("option", { name: /简体中文/ }).click();
  await expect(page.locator(".language-select-trigger:not(.theme-select-trigger)")).toContainText(
    "语言"
  );
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-hans");
}
for (const width of [1440, 390]) {
  test(`Chinese service preferences, details and calendar at ${width}px`, async ({
    page,
  }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await chooseChinese(page);
    await page.reload();
    await expect(page.locator(".language-select-trigger:not(.theme-select-trigger)")).toContainText(
      "简体中文"
    );
    await expect(page.locator("html")).toHaveAttribute("lang", "zh-hans");
    await page.goto(url("services"));
    const screen = page.locator(".services-screen");
    await expect(screen.getByRole("heading", { name: "我的套餐", exact: true })).toBeVisible();
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
    await expect(page.locator(".language-select-trigger:not(.theme-select-trigger)")).toContainText(
      "Language"
    );
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
    await expect(dialog).toContainText("额度修改也会应用于已开通服务");
    await expect(dialog).toContainText("其他修改仅影响后续开通");
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
  test(`Chinese document, plugin, theme and backup controls at ${width}px`, async ({
    page,
  }, info) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 1000 });
    await chooseChinese(page);
    await page.goto(url("admin/documents"));
    await page.getByRole("button", { name: "新建文档", exact: true }).click();
    let dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("button", { name: "粗体", exact: true })).toBeVisible();
    await dialog.getByRole("button", { name: "用途", exact: true }).click();
    await page.getByRole("option", { name: "隐私政策", exact: true }).click();
    await expect(page.locator(".admin-select-content")).toHaveCount(0);
    await expect(dialog).toContainText("显示在用户设置");
    await dialog.screenshot({ path: info.outputPath(`chinese-document-${width}.png`) });
    await page.keyboard.press("Escape");

    await page.goto(url("admin/plugins"));
    await page.getByRole("button", { name: "添加插件", exact: true }).first().click();
    dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("将插件 ZIP 拖到此处");
    await dialog.getByRole("button", { name: "Git 仓库", exact: true }).click();
    await expect(dialog.getByPlaceholder("https://github.com/author/repository")).toBeVisible();
    await expect(dialog).toContainText("包含可用软件包索引");
    await dialog.screenshot({ path: info.outputPath(`chinese-plugin-${width}.png`) });
    await page.keyboard.press("Escape");

    await page.goto(url("admin/appearance"));
    await page.locator('[data-theme-key="dark"] .theme-card-actions button').last().click();
    dialog = page.locator(".appearance-settings-dialog");
    await expect(dialog.locator(".appearance-preset-row")).toContainText("翡翠绿");
    await expect(dialog.locator(".appearance-preset-row")).toContainText("海洋蓝");
    await dialog.locator(".appearance-select-grid .admin-select-trigger").first().click();
    await expect(page.getByRole("option", { name: "系统默认", exact: true })).toBeVisible();
    await expect(page.getByRole("option", { name: "系统界面字体", exact: true })).toBeInViewport();
    await page.screenshot({
      path: info.outputPath(`chinese-font-menu-${width}.png`),
      animations: "disabled",
    });
    await page.keyboard.press("Escape");
    await dialog.locator(".dialog-head button").click();
    await page
      .locator(".appearance-library")
      .getByRole("button", { name: "添加主题", exact: true })
      .click();
    dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("将归档拖到此处");
    await expect(dialog).toContainText("最大 20 MB");
    await dialog.screenshot({ path: info.outputPath(`chinese-theme-${width}.png`) });
    await page.keyboard.press("Escape");

    await page.goto(url("admin/backups"));
    const restore = page.locator(".backups-restore-card");
    await expect(restore.getByRole("button", { name: "从备份恢复", exact: true })).toBeDisabled();
    await expect(
      page.getByRole("button", { name: "选择 ZIP 或备份分卷", exact: true })
    ).toBeVisible();
    await expect(restore).toContainText("恢复");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true
    );
    await page.screenshot({ path: info.outputPath(`chinese-backup-${width}.png`), fullPage: true });
    expect(errors).toEqual([]);
  });
  test(`Chinese advertising and message menus at ${width}px`, async ({ page }, info) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 1000 });
    await chooseChinese(page);
    await page.goto(url("admin/ads"));
    await page.locator('[data-admin-action="create-ad"]').click();
    await expect(page.getByRole("dialog")).toContainText("活动标识");
    await page
      .getByRole("dialog")
      .screenshot({ path: info.outputPath(`chinese-ad-create-${width}.png`) });
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "打开活动", exact: true }).first().click();
    const workspace = page.locator(".ad-workspace");
    await workspace.getByRole("tab", { name: "CSV 导入", exact: true }).click();
    await expect(workspace).toContainText("列映射");
    await expect(workspace).toContainText("汇总指标不能识别单个用户");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true
    );
    await page.screenshot({
      path: info.outputPath(`chinese-ad-import-${width}.png`),
      fullPage: true,
    });

    await page.goto(url("admin/broadcast"));
    await expect(page.getByRole("heading", { name: "群发历史", exact: true })).toBeVisible();
    await expect(page.locator(".broadcast-history-message-preview").first()).toContainText(
      "夏季更新已上线"
    );
    await expect(page.getByRole("button", { name: "粗体", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "表情", exact: true }).first().click();
    const picker = page.getByRole("dialog");
    await expect(picker).toContainText("选择表情");
    await expect(picker).toContainText("最近使用");
    await picker.screenshot({ path: info.outputPath(`chinese-emoji-${width}.png`) });
    await page.keyboard.press("Escape");
    await expect(page.getByRole("heading", { name: "群发历史", exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });
}
