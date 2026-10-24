import { expect, type Locator, type Page, type TestInfo } from "@playwright/test";
import type { components } from "../src/lib/api/openapi.generated";

export async function checkReplacementBounds(dialog: Locator) {
  expect(
    await dialog.evaluate((root) => {
      const viewport = root
        .querySelector(".dialog-body-scroll .scroll-area__viewport")!
        .getBoundingClientRect();
      return Array.from(
        root.querySelectorAll<HTMLElement>(
          ".dialog-body-scroll .scroll-area__viewport, .exit-replacement form, .exit-replacement .admin-select-trigger, .replacement-impact, .replacement-impact .admin-table-wrap"
        )
      )
        .filter(
          (node) =>
            node.scrollWidth - node.clientWidth > 2 ||
            node.getBoundingClientRect().left < viewport.left - 2 ||
            node.getBoundingClientRect().right > viewport.right + 2
        )
        .map((node) => ({
          className: node.className,
          width: node.clientWidth,
          contentWidth: node.scrollWidth,
        }));
    })
  ).toEqual([]);
}

export async function checkReplacementImpacts(
  page: Page,
  dialog: Locator,
  info: TestInfo,
  stage: "draft" | "confirm",
  impacts: components["schemas"]["ReplacementImpactOut"][],
  label: (key: string) => string
) {
  const table = dialog.getByRole("table", { name: label("replacement_impact_entities") });
  const rows = table.locator("tbody tr");
  await expect(rows).toHaveCount(impacts.length);
  await checkReplacementBounds(dialog);
  await expect(dialog).toContainText(label("console_resource_scope"));
  for (const [index, impact] of impacts.entries()) {
    const row = rows.nth(index);
    const service = row.locator("td").nth(0);
    const customer = row.locator("td").nth(1);
    await expect(service).toContainText(
      impact.service_name ??
        label(impact.service_id ? "replacement_service_unnamed" : "replacement_service_external")
    );
    if (impact.service_id) {
      await expect(service).toContainText(impact.service_id);
      const url = new URL((await service.getByRole("link").getAttribute("href"))!);
      expect(url.pathname).toBe("/demo/runtime/admin/services");
      expect(url.searchParams.get("service_id")).toBe(impact.service_id);
    } else await expect(service.getByRole("link")).toHaveCount(0);
    if (impact.customer_id !== null) {
      await expect(customer.locator(".admin-entity-link-label")).toHaveText(
        String(impact.customer_id)
      );
      const url = new URL((await customer.getByRole("link").getAttribute("href"))!);
      expect(url.pathname).toBe(`/demo/runtime/admin/users/${impact.customer_id}`);
    } else {
      await expect(customer).toHaveText(label("replacement_customer_unknown"));
      await expect(customer.getByRole("link")).toHaveCount(0);
    }
    for (const entity of await row.locator(".admin-entity-link-text").all()) {
      expect(
        await entity.evaluate((node) => node.scrollWidth - node.clientWidth)
      ).toBeLessThanOrEqual(2);
      for (const text of await entity.locator("span").all())
        expect(
          await text.evaluate((node) => node.scrollHeight - node.clientHeight)
        ).toBeLessThanOrEqual(2);
    }
    await row.scrollIntoViewIfNeeded();
    await expect(row).toBeInViewport();
    await dialog.screenshot({
      path: info.outputPath(`${stage}-impact-${index}.png`),
      animations: "disabled",
    });
  }
  const reference = rows.first().locator("td").first().getByRole("link");
  await expect(reference).toHaveAttribute("target", "_blank");
  await reference.focus();
  await expect(reference).toBeFocused();
  if (stage === "draft") {
    for (const index of [0, 1]) {
      const link = rows.first().locator("td").nth(index).getByRole("link");
      const popupPromise = page.waitForEvent("popup");
      await link.press("Enter");
      const popup = await popupPromise;
      await expect(popup).toHaveURL((url) =>
        index === 0
          ? url.pathname === "/demo/runtime/admin/services" &&
            url.searchParams.get("service_id") === impacts[0].service_id
          : url.pathname === `/demo/runtime/admin/users/${impacts[0].customer_id}`
      );
      const target =
        index === 0
          ? popup.getByRole("dialog", { name: label("console_service_detail"), exact: true })
          : popup.locator(".user-services tbody tr").filter({ hasText: impacts[0].service_id! });
      await expect(target).toContainText(impacts[0].service_name!);
      await popup.close();
      await page.bringToFront();
      await expect(dialog).toBeVisible();
    }
  }
}
