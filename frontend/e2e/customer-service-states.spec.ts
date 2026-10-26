import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

for (const language of ["en", "ru", "zh-hans"]) {
  const locale: Record<string, string> = JSON.parse(
    readFileSync("../locales/" + language + ".json", "utf8")
  );
  const label = (key: string) => locale["admin_" + key];
  for (const width of [1440, 390]) {
    test(
      "pending customer service explains missing data at " + width + " in " + language,
      async ({ page }, testInfo) => {
        const errors: string[] = [];
        page.on("pageerror", (error) => errors.push(error.message));
        await page.setViewportSize({ width, height: 1000 });
        await page.addInitScript(
          ({ language }) => {
            localStorage.setItem("rw_minishop_demo_language", language);
            type Reply = Record<string, unknown>;
            type Props = { api: (path: string, options?: RequestInit) => Promise<Reply> };
            type Bundle = { mount: (target: HTMLElement, props: Props) => unknown };
            const state = { history: "default", usageFailed: false };
            Object.defineProperty(window, "customerStateHarness", { value: state });
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
                      const url = new URL(path, "https://fixture.test");
                      if (url.pathname.endsWith("/traffic") && state.history !== "default") {
                        if (state.history === "failure") throw new Error("private-history-error");
                        return {
                          ok: true,
                          service_id: url.pathname.split("/")[4],
                          availability: "available",
                          start_date: "2026-10-21",
                          end_date: "2026-10-27",
                          days: state.history === "zero" ? [{ date: "2026-10-27", bytes: 0 }] : [],
                          nodes: [],
                        };
                      }
                      const result = await props.api(path, options);
                      if (
                        url.pathname === "/admin/services" &&
                        (!options?.method || options.method === "GET") &&
                        state.usageFailed &&
                        Array.isArray(result.services)
                      )
                        return {
                          ...result,
                          services: result.services.map((service: Record<string, unknown>) => ({
                            ...service,
                            usage_error: "panel_usage_unavailable",
                          })),
                        };
                      return result;
                    },
                  });
                bundle = value;
              },
            });
          },
          { language }
        );
        await page.goto(
          "/demo/runtime/admin/users/ms_100000000000400080000000000de422?mock=services&theme_preview=dark"
        );
        const services = page.getByRole("region", { name: label("services_title"), exact: true });
        await expect(services).toContainText(label("services_no_services"));
        await services
          .getByRole("button", { name: label("services_activate"), exact: true })
          .click();
        const activation = page.getByRole("dialog", {
          name: label("services_activate"),
          exact: true,
        });
        await activation
          .getByRole("button", { name: label("services_choose_plan"), exact: true })
          .click();
        await page.getByRole("option").first().click();
        await expect(
          activation.getByRole("button", { name: label("services_activate"), exact: true })
        ).toBeEnabled();
        await activation
          .getByRole("button", { name: label("services_activate"), exact: true })
          .click();
        await expect(activation).toHaveCount(0);
        const relations = services.locator("[data-customer-relations]");
        const usage = services.locator(".customer-usage");
        const quota = services.locator(".quota");
        await expect(relations).toContainText(label("console_nodes_pending_configuration"));
        await expect(
          relations
            .getByText(label("console_nodes_resources_unconfigured"), { exact: true })
            .first()
        ).toBeVisible();
        await expect(
          relations.getByText(label("console_nodes_coverage_unavailable"), { exact: true })
        ).not.toBeVisible();
        await expect(usage).toContainText(label("console_visual_history_unconfigured"));
        await expect(usage.locator(".metric-chart, table")).toHaveCount(0);
        await expect(quota).toContainText(label("services_usage_missing"));
        await expect(quota).not.toContainText(label("services_usage_unconfirmed"));
        await expect(quota).not.toContainText(label("services_next_reset"));
        await expect(
          page.getByRole("region", { name: label("account_access_title"), exact: true })
        ).toContainText(label("account_access_scope"));
        await services.screenshot({ path: testInfo.outputPath("pending-customer.png") });
        await relations.locator("details > summary").click();
        await expect(
          relations
            .getByText(label("console_nodes_availability_unconfigured"), { exact: false })
            .first()
        ).toBeVisible();
        await relations.locator("details > summary").click();

        for (const [mode, key] of [
          ["failure", "console_visual_history_failed"],
          ["empty", "console_visual_history_no_samples"],
        ]) {
          await page.evaluate((mode) => {
            (
              window as typeof window & { customerStateHarness: { history: string } }
            ).customerStateHarness.history = mode;
          }, mode);
          await usage.getByRole("button", { name: label("refresh"), exact: true }).click();
          await expect(usage).toContainText(label(key));
          await expect(usage.locator("table")).toHaveCount(0);
        }
        await page.evaluate(() => {
          (
            window as typeof window & { customerStateHarness: { history: string } }
          ).customerStateHarness.history = "zero";
        });
        await usage.getByRole("button", { name: label("refresh"), exact: true }).click();
        await expect(usage.locator(".plot canvas").first()).toBeVisible();
        await usage.getByText(label("console_visual_table"), { exact: true }).click();
        await expect(usage.locator("tbody td").last()).toBeVisible();
        await expect(usage.locator("tbody td").last()).toHaveText("0 B");

        await page.evaluate(() => {
          (
            window as typeof window & { customerStateHarness: { usageFailed: boolean } }
          ).customerStateHarness.usageFailed = true;
        });
        await services
          .getByRole("button", { name: label("refresh"), exact: true })
          .first()
          .click();
        await expect(quota).toContainText(label("services_usage_unconfirmed"));
        await expect(quota).not.toContainText(label("services_usage_stale"));
        await expect(services).not.toContainText("private-history-error");
        expect(
          await services.evaluate((element) => element.scrollWidth - element.clientWidth)
        ).toBeLessThanOrEqual(2);
        const serviceId = await relations
          .locator("[data-service-relation]")
          .getAttribute("data-service-relation");
        expect(serviceId).toBeTruthy();
        await page.evaluate(() => {
          const state = (
            window as typeof window & {
              customerStateHarness: { history: string; usageFailed: boolean };
            }
          ).customerStateHarness;
          state.history = "default";
          state.usageFailed = false;
        });
        await relations.locator(".relation-service").click();
        await expect(page).toHaveURL((url) => url.searchParams.get("service_id") === serviceId);
        const detail = page.getByRole("dialog", {
          name: label("console_service_detail"),
          exact: true,
        });
        await expect(detail).toContainText("@new_wave_login");
        await expect(detail).toContainText("ms_100000000000400080000000000de422");
        await expect(detail.locator(".history")).toContainText(
          label("console_visual_history_unconfigured")
        );
        await expect(detail.locator(".history .metric-chart")).toHaveCount(0);
        await expect(detail.locator(".quota")).toContainText(label("services_usage_missing"));
        await page.goBack();
        await expect(detail).toHaveCount(0);
        await expect(relations.locator("[data-service-relation]")).toHaveAttribute(
          "data-service-relation",
          serviceId!
        );
        expect(errors).toEqual([]);
      }
    );
  }
}
