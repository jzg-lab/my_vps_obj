import { expect, test } from "@playwright/test";

const url = (route: string) => `/demo/runtime/admin/${route}?mock=services&theme_preview=dark`;

for (const width of [1440, 390]) {
  test(`independent admin retires old navigation and preserves account actions at ${width}px`, async ({
    page,
  }, testInfo) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(url("tariffs"));
    await expect(page.getByRole("button", { name: "Новый тариф", exact: true })).toBeVisible();
    for (const section of ["stats", "tariffs", "promos", "gifts", "partners"]) {
      await expect(page.locator(`[data-admin-section="${section}"]`)).toHaveCount(0);
    }
    if (width < 800) await page.getByRole("button", { name: "Меню", exact: true }).click();
    await page.locator('[data-admin-section="users"]').click();
    const account =
      width < 800
        ? page.locator(".admin-user-mobile-card").first()
        : page.locator("tr[data-user-id]").first();
    await expect(account).toBeVisible();
    await account.click();
    const services = page.getByRole("region", { name: "Независимые услуги" });
    await expect(services).toBeVisible();
    await expect(services.getByRole("button", { name: "Обновить", exact: true })).toBeEnabled();
    await expect(page.getByRole("tab", { name: "Подписка", exact: true })).toHaveCount(0);
    await expect(page.locator(".admin-user-stats")).toHaveCount(0);
    for (const action of ["request-user-merge", "request-user-ban-toggle", "request-user-delete"]) {
      await expect(page.locator(`[data-admin-action="${action}"]`)).toBeVisible();
    }
    await expect(
      page.locator('[data-admin-action="request-user-subscription-reissue"]')
    ).toHaveCount(0);
    await page.locator('[data-admin-action="request-user-delete"]').click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath(`account-${width}.png`), fullPage: true });
    expect(errors).toEqual([]);
  });

  test(`independent user list clears subscription filters and keeps account filters at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(
      `${url("users")}&users_filter=trial&users_panel_status=limited&users_premium_traffic=critical`
    );
    await expect(page.locator(".admin-users-table-wrap")).toBeVisible();
    await expect(page).not.toHaveURL(
      /users_filter=trial|users_panel_status=limited|users_premium_traffic=critical/
    );
    await expect(page.locator(".admin-users-filter-chip")).toHaveCount(0);
    if (width < 800) await page.locator(".admin-users-filter-toggle").click();
    const filter = page.getByRole("button", { name: "Фильтр", exact: true });
    await filter.click();
    await expect(
      page.getByRole("option", { name: "С пробной подпиской", exact: true })
    ).toHaveCount(0);
    await expect(page.getByRole("option")).toHaveCount(8);
    await page.getByRole("option", { name: "Забанены", exact: true }).click();
    await expect(page.locator(".admin-select-content")).toHaveCount(0);
    await expect(page).toHaveURL(/users_filter=banned/);
    await page.screenshot({
      path: testInfo.outputPath(`account-filter-${width}.png`),
      fullPage: true,
    });
    if (width < 800) await page.keyboard.press("Escape");
  });

  test(`independent settings omit retired pricing and quota controls at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(url("settings/payments/stripe"));
    await expect(page.locator('[data-settings-anchor="settings-section:general"]')).toBeVisible();
    for (const section of ["payments", "trial", "pricing", "referral", "partner", "devices"]) {
      await expect(
        page.locator(`[data-settings-anchor="settings-section:${section}"]`)
      ).toHaveCount(0);
    }
    for (const section of ["login_methods", "remnawave", "support", "backups"]) {
      await expect(
        page.locator(`[data-settings-anchor="settings-section:${section}"]`)
      ).toBeVisible();
    }
    await page.getByRole("button", { name: "Развернуть всё", exact: true }).click();
    for (const key of [
      "USER_TRAFFIC_STRATEGY",
      "GIFTS_ENABLED",
      "PANEL_WEBHOOK_SECRET",
      "USER_SQUAD_UUIDS",
      "USER_EXTERNAL_SQUAD_UUID",
    ]) {
      await expect(page.locator(`[data-settings-anchor="settings-field:${key}"]`)).toHaveCount(0);
    }
    await page.locator(".admin-settings-search-input").fill("USER_TRAFFIC_STRATEGY");
    await expect(page.locator(".admin-settings-search-result")).toHaveCount(0);
    await page.locator(".admin-settings-search-input").fill("PANEL_API_URL");
    await expect(page.locator(".admin-settings-search-result").first()).toBeVisible();
    await page.keyboard.press("Escape");
    await page.screenshot({ path: testInfo.outputPath(`settings-${width}.png`), fullPage: true });
  });

  test(`historical payments remain readable without entitlement actions at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.addInitScript(() => {
      type Row = Record<string, unknown>;
      type Props = { api: (path: string, options?: RequestInit) => Promise<Row> };
      type Bundle = { mount: (target: HTMLElement, props: Props) => unknown };
      let bundle: Bundle | undefined;
      Object.defineProperty(window, "SubscriptionWebAppAdmin", {
        configurable: true,
        get: () => bundle,
        set(value: Bundle) {
          const mount = value.mount;
          value.mount = (target, props) =>
            mount(target, {
              ...props,
              api: async (path, options) => {
                const response = await props.api(path, options);
                if (/^\/admin\/payments\/\d+$/.test(path) && response.payment) {
                  return {
                    ...response,
                    payment: {
                      ...(response.payment as Row),
                      can_manual_finalize: true,
                      can_reverse: true,
                    },
                  };
                }
                return response;
              },
            });
          bundle = value;
        },
      });
    });
    await page.goto(url("payments"));
    await expect(
      page.getByText("История платежей доступна только для просмотра.", { exact: false })
    ).toBeVisible();
    const rows = page.locator(
      width < 800 ? ".admin-payment-mobile-card" : ".admin-payments-table tbody tr"
    );
    await rows
      .first()
      .getByRole("button", { name: /Открыть.*плат/ })
      .click();
    const dialog = page.locator(".admin-payment-dialog");
    await expect(dialog.locator(".admin-payment-summary")).toBeVisible();
    await expect(dialog.locator(".admin-payment-actions-panel")).toHaveCount(0);
    await dialog.screenshot({ path: testInfo.outputPath(`payment-history-${width}.png`) });
    expect(
      await dialog.evaluate((node) => node.scrollWidth - node.clientWidth)
    ).toBeLessThanOrEqual(2);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });
}
