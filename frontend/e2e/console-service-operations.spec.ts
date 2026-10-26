import { expect, test } from "@playwright/test";
import { installOperationsFixture, operationLabels } from "./fixtures/consoleServiceOperations";
import { operationFixture } from "../src/lib/admin/consoleServiceOperationsFixtures";

const query = "?mock=services&theme_preview=dark";
for (const width of [1440, 390]) {
  for (const consumer of ["detail", "customer"] as const) {
    test(`${consumer} diagnostics, authoritative pagination and lost retry receipt at ${width}px`, async ({
      page,
    }, info) => {
      const at = operationLabels("zh-hans");
      const fixture = await installOperationsFixture(page, "zh-hans", { lostReply: true });
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(
        consumer === "detail"
          ? `/demo/runtime/admin/services${query}&service_id=${fixture.service.id}`
          : `/demo/runtime/admin/users/910001${query}`
      );
      const host =
        consumer === "detail"
          ? page.getByRole("dialog", { name: at("console_service_detail"), exact: true })
          : page.locator(".user-services");
      await expect(host).toContainText(fixture.service.name);
      if (consumer === "customer") await host.locator(":scope > details > summary").click();
      expect(fixture.calls.filter((call) => call.path.endsWith("/diagnostics"))).toHaveLength(0);
      await host.getByRole("button", { name: at("console_ops_title"), exact: true }).click();
      const dialog = page.getByRole("dialog", { name: at("console_ops_title"), exact: true });
      await expect(dialog).toContainText(at("console_ops_remote_unavailable"));
      await expect(dialog).toContainText(at("console_ops_data_plane_unverified"));
      expect(
        await dialog.evaluate((node) => node.parentElement?.closest(".dialog, .admin-table-wrap"))
      ).toBeNull();
      const operations = dialog.getByRole("region", {
        name: at("console_ops_operations"),
        exact: true,
      });
      await expect(operations.locator(".admin-pagination-summary")).toContainText("27");
      await operations.getByRole("button", { name: at("services_next"), exact: true }).click();
      await expect(operations.locator("tbody tr")).toHaveCount(2);
      await expect(operations).toContainText(at("console_ops_history_unknown"));
      await operations.getByRole("button", { name: at("services_previous"), exact: true }).click();
      const row = operations.getByRole("row").filter({ hasText: operationFixture.id });
      await row.getByRole("button", { name: at("console_ops_retry"), exact: true }).click();
      await expect(dialog).toContainText(at("console_ops_unclassified_error"));
      await expect(row).toContainText(at("console_ops_uncertain_receipt"));
      await expect
        .poll(() => dialog.evaluate((node) => node.contains(document.activeElement)))
        .toBe(true);
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      await expect(host).toBeVisible();
      await host.getByRole("button", { name: at("console_ops_title"), exact: true }).click();
      await row
        .getByRole("button", { name: at("console_ops_confirm_receipt"), exact: true })
        .click();
      await expect(dialog).toContainText(at("console_ops_accepted"));
      await expect(row).not.toContainText(at("console_ops_uncertain_receipt"));
      const writes = fixture.calls.filter((call) => call.path.endsWith("/retry"));
      expect(writes).toHaveLength(2);
      expect(writes[0]).toEqual(writes[1]);
      expect(
        fixture.calls
          .slice(fixture.calls.lastIndexOf(writes[1]) + 1)
          .some((call) => call.path.endsWith("/diagnostics"))
      ).toBe(true);
      await expect(row).toContainText(at("console_ops_status_pending"));
      await expect(row).not.toContainText(at("console_ops_status_succeeded"));
      expect(
        await dialog.locator(".dialog-card").evaluate((node) => node.scrollWidth - node.clientWidth)
      ).toBeLessThanOrEqual(2);
      await page.screenshot({
        path: info.outputPath(`${consumer}-operations-${width}.png`),
        animations: "disabled",
      });
      fixture.failReads();
      await dialog.getByRole("button", { name: at("refresh"), exact: true }).click();
      await expect(dialog).toContainText(at("console_ops_load_failed"));
      await expect(dialog.locator(".admin-pagination-summary")).toHaveCount(0);
      expect(fixture.errors).toEqual([]);
      expect(fixture.http).toEqual([]);
    });
  }
  test(`preflight selection clears stale results and preserves unknown readiness at ${width}px`, async ({
    page,
  }, info) => {
    const at = operationLabels("en");
    const fixture = await installOperationsFixture(page, "en", { holdFirstPreflight: true });
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(`/demo/runtime/admin/users/910001${query}`);
    await page.getByRole("button", { name: at("services_activate"), exact: true }).click();
    const dialog = page.getByRole("dialog", { name: at("services_activate"), exact: true });
    const trigger = dialog.getByRole("button", { name: at("services_choose_plan"), exact: true });
    const submit = dialog.getByRole("button", { name: at("services_activate"), exact: true });
    await trigger.click();
    await page.getByRole("option", { name: "Operations plan 1", exact: true }).click();
    await expect
      .poll(() => fixture.calls.some((call) => call.path.endsWith("service-preflight")))
      .toBe(true);
    await expect(submit).toBeDisabled();
    fixture.state.plans[1].enabled = false;
    await trigger.click();
    await page.getByRole("option", { name: "Operations plan 2", exact: true }).click();
    const exit = dialog.getByRole("button", { name: at("services_choose_exit"), exact: true });
    await exit.click();
    await page.getByRole("option", { name: /Operations exit/ }).click();
    await expect(dialog).toContainText(at("console_preflight_creation_blocked"));
    fixture.releasePreflight();
    await expect(dialog).not.toContainText(at("console_preflight_creation_allowed"));
    await expect(submit).toBeDisabled();
    await trigger.click();
    await page.getByRole("option", { name: "Operations plan 1", exact: true }).click();
    await expect(dialog).toContainText(at("console_preflight_creation_allowed"));
    await expect(dialog).toContainText(at("console_preflight_not_deliverable"));
    await expect(submit).toBeEnabled();
    await page.screenshot({
      path: info.outputPath(`preflight-${width}.png`),
      animations: "disabled",
    });
    fixture.state.plans[0].revision++;
    await dialog
      .getByRole("button", { name: at("console_preflight_reload_choices"), exact: true })
      .click();
    await expect(
      dialog.getByRole("region", { name: at("console_preflight_title"), exact: true })
    ).toHaveCount(0);
    await expect(submit).toBeDisabled();
    await trigger.click();
    await page.getByRole("option", { name: "Operations plan 1", exact: true }).click();
    await expect(submit).toBeEnabled();
    expect(
      fixture.calls.filter((call) => call.path.endsWith("service-preflight")).at(-1)?.body
    ).toMatchObject({ expected_revision: 2 });
    expect(
      fixture.calls.filter(
        (call) => call.method === "POST" && !call.path.endsWith("service-preflight")
      )
    ).toEqual([]);
    expect(fixture.errors).toEqual([]);
    expect(fixture.http).toEqual([]);
  });
  for (const mode of ["archived", "banned"] as const) {
    test(`${mode} service cannot retry at ${width}px`, async ({ page }) => {
      const at = operationLabels("ru");
      const fixture = await installOperationsFixture(page, "ru", { [mode]: true });
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(`/demo/runtime/admin/services${query}&service_id=${fixture.service.id}`);
      await page.getByRole("button", { name: at("console_ops_title"), exact: true }).click();
      const dialog = page.getByRole("dialog", { name: at("console_ops_title"), exact: true });
      await expect(dialog).toContainText(at("console_ops_operations"));
      await expect(
        dialog.getByRole("button", { name: at("console_ops_retry"), exact: true })
      ).toHaveCount(0);
      fixture.unsafeCodes();
      await dialog.getByRole("button", { name: at("refresh"), exact: true }).click();
      await expect(dialog).toContainText(at("console_ops_next_unknown"));
      await expect(dialog).not.toContainText("private-token");
      await expect(dialog).not.toContainText("private-next-step");
      expect(fixture.calls.filter((call) => call.method === "POST")).toEqual([]);
      expect(fixture.calls.some((call) => /users\/0\b|user_id=0\b/.test(call.path))).toBe(false);
      expect(fixture.errors).toEqual([]);
      expect(fixture.http).toEqual([]);
    });
  }
  for (const change of ["owner", "revision"] as const) {
    test(`blocks a new retry after ${change} changes at ${width}px`, async ({ page }) => {
      const at = operationLabels("zh-hans");
      const fixture = await installOperationsFixture(page, "zh-hans");
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(`/demo/runtime/admin/services${query}&service_id=${fixture.service.id}`);
      await page.getByRole("button", { name: at("console_ops_title"), exact: true }).click();
      const dialog = page.getByRole("dialog", { name: at("console_ops_title"), exact: true });
      const row = dialog
        .getByRole("region", { name: at("console_ops_operations"), exact: true })
        .getByRole("row")
        .filter({ hasText: operationFixture.id });
      if (change === "owner") fixture.service.user_id = 910002;
      else fixture.service.revision = 4;
      await row.getByRole("button", { name: at("console_ops_retry"), exact: true }).click();
      await expect(dialog).toContainText(
        at(change === "owner" ? "services_idempotency_owner_changed" : "services_change_conflict")
      );
      expect(fixture.calls.filter((call) => call.method === "POST")).toEqual([]);
      expect(fixture.errors).toEqual([]);
      expect(fixture.http).toEqual([]);
    });
  }
}
