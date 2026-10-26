import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

for (const width of [1440, 390]) {
  for (const language of ["en", "ru", "zh-hans"]) {
    const copy = JSON.parse(readFileSync("../locales/" + language + ".json", "utf8"));
    test(
      "service guidance and support draft at " + width + "px in " + language,
      async ({ page }, info) => {
        const errors: string[] = [];
        page.on("pageerror", (error) => errors.push(error.message));
        await page.setViewportSize({ width, height: 950 });
        await page.addInitScript(
          (language) => localStorage.setItem("rw_minishop_demo_language", language),
          language
        );
        await page.goto("/demo/runtime/services?mock=services&delivery=1&theme_preview=dark");
        const cards = page.locator("[data-service-id]");
        await expect(cards).toHaveCount(10);
        await expect(cards.first().locator("progress")).toHaveClass(/exhausted/);
        await expect(cards.first().locator("[data-slot=badge]")).toHaveClass(/destructive/);
        const pending = cards.nth(1);
        await expect(pending).toContainText(copy.wa_services_next_pending);
        await expect(pending).toContainText(copy.wa_services_remaining_confirmed);
        await expect(pending.locator("[data-service-remaining]")).toContainText("2026-10-22 12:00");
        await expect(pending.locator("progress")).toHaveClass(/unconfirmed/);
        await expect(pending).not.toContainText(copy.wa_services_subscription_update);
        await pending.getByRole("button", { name: copy.wa_services_details, exact: true }).click();
        const dialog = page.getByRole("dialog");
        await expect(dialog).toContainText(copy.wa_services_next_pending);
        await expect(dialog.locator(".service-subscription")).toHaveCount(0);
        await dialog
          .locator(".service-explanation summary")
          .filter({ hasText: copy.wa_services_explanation })
          .click();
        await expect(
          dialog.getByText(copy.wa_services_help_evidence, { exact: true })
        ).toBeVisible();
        expect(copy.wa_services_help_evidence).not.toMatch(/refresh|обновите|刷新/);
        await dialog.screenshot({ path: info.outputPath("pending-detail.png") });
        expect(
          await dialog.evaluate((node) => node.scrollWidth - node.clientWidth)
        ).toBeLessThanOrEqual(2);
        await page.keyboard.press("Escape");
        const active = cards.nth(2);
        await expect(active).toContainText(copy.wa_services_next_import);
        await active.getByRole("button", { name: copy.wa_services_details, exact: true }).click();
        await expect(dialog).toContainText(copy.wa_services_next_import_detail);
        await expect(
          dialog.getByRole("button", { name: copy.wa_services_subscription, exact: true })
        ).toBeVisible();
        await page.keyboard.press("Escape");
        await pending.getByRole("button", { name: copy.wa_services_contact, exact: true }).click();
        await expect(page).toHaveURL(/\/support/);
        const serviceId = "00000000000000000000000000000011";
        await expect(page.locator("input").filter({ visible: true }).first()).toHaveValue(
          copy.wa_services_id + ": " + serviceId
        );
        await expect(page.locator("[contenteditable=true]").first()).toContainText(serviceId);
        await expect(page.locator("[contenteditable=true]").first()).not.toContainText("<p>");
        await page.locator("[contenteditable=true]").first().fill("Keep my unsent message");
        await page.getByRole("heading", { name: copy.wa_nav_support, exact: true }).click();
        await page.getByRole("button", { name: copy.wa_services_nav, exact: true }).click();
        await expect(cards).toHaveCount(10);
        await cards
          .nth(2)
          .getByRole("button", { name: copy.wa_services_contact, exact: true })
          .click();
        await expect(page.locator("[contenteditable=true]").first()).toContainText(
          "Keep my unsent message"
        );
        await expect(page.locator("[contenteditable=true]").first()).toContainText(
          "00000000000000000000000000000012"
        );
        await expect(page.locator("input").filter({ visible: true }).first()).toHaveValue(
          copy.wa_services_id + ": " + serviceId
        );
        await expect(page.locator("[contenteditable=true]").first()).not.toContainText("<p>");
        await expect
          .poll(() =>
            page
              .locator("[contenteditable=true]")
              .first()
              .evaluate((node) => {
                let opacity = 1;
                for (let element: Element | null = node; element; element = element.parentElement) {
                  opacity *= Number(getComputedStyle(element).opacity);
                }
                return opacity;
              })
          )
          .toBe(1);
        await page.screenshot({ path: info.outputPath("support-draft.png"), fullPage: true });
        expect(
          await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)
        ).toBeLessThanOrEqual(2);
        expect(errors).toEqual([]);
      }
    );
  }
}
