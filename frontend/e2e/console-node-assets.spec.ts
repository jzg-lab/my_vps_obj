import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test, type Page } from "@playwright/test";
import {
  consoleNodeAssetsDemoResponse,
  createConsoleNodeAssetsDemoState,
} from "../src/lib/webapp/mockApi/consoleNodeAssets";

const url = "/demo/runtime/admin/nodes?mock=services&theme_preview=dark&nodes_view=unmanaged";
type TestWindow = typeof window & {
  nodeAssetRequests: Array<{ path: string; method: string }>;
  nodeAssetsReply: (path: string, options: { method?: string; body?: string }) => Promise<unknown>;
};

async function install(page: Page, language = "en", count = 0) {
  const state = createConsoleNodeAssetsDemoState();
  for (let index = 0; index < count; index++)
    state.records.push({
      id: index.toString(16).padStart(32, "0"),
      name: `Pending ${index}`,
      address: "192.0.2.1",
      notes: "",
      management_state: "unmanaged",
      created_at: "2026-10-24T00:00:00Z",
      updated_at: "2026-10-24T00:00:00Z",
    });
  const controls = {
    failRead: false,
    failWrite: false,
    holdRead: false,
    release: null as (() => void) | null,
  };
  await page.exposeFunction("nodeAssetsReply", async (path: string, options: RequestInit) => {
    if ((options.method ?? "GET") === "GET") {
      if (controls.failRead) return { ok: false, error: "node_assets_unavailable" };
      if (controls.holdRead) {
        controls.holdRead = false;
        await new Promise<void>((resolve) => {
          controls.release = resolve;
        });
      }
    } else if (controls.failWrite) return { ok: false, error: "node_assets_unavailable" };
    return consoleNodeAssetsDemoResponse(path, options, state);
  });
  await page.addInitScript((language) => {
    localStorage.setItem("rw_minishop_demo_language", language);
    const harness = window as TestWindow;
    harness.nodeAssetRequests = [];
    type Props = { api: (path: string, options?: RequestInit) => Promise<unknown> };
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
              harness.nodeAssetRequests.push({ path, method: options?.method ?? "GET" });
              if (
                new URL(path, "https://fixture.test").pathname.startsWith(
                  "/admin/console/node-assets"
                )
              )
                return harness.nodeAssetsReply(path, {
                  method: options?.method,
                  body: typeof options?.body === "string" ? options.body : undefined,
                });
              return props.api(path, options);
            },
          });
        bundle = value;
      },
    });
  }, language);
  return { state, controls };
}

function labels(language: string) {
  const locale: Record<string, string> = JSON.parse(
    readFileSync(resolve(__dirname, `../../locales/${language}.json`), "utf8")
  );
  return (key: string) => locale[`admin_${key}`];
}

for (const language of ["en", "ru", "zh-hans"])
  for (const width of [1440, 390]) {
    test(`pending node local CRUD and confirmation at ${width}px in ${language}`, async ({
      page,
    }, testInfo) => {
      const label = labels(language);
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      const { state } = await install(page, language);
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(url);
      const section = page.getByRole("region", {
        name: label("console_node_assets_pending"),
        exact: true,
      });
      await expect(section).toContainText(label("console_node_assets_empty"));
      await expect(section.locator(".admin-list-toolbar-summary strong")).toHaveText("0");
      expect(
        await page.evaluate(() =>
          (window as TestWindow).nodeAssetRequests.some(({ path }) =>
            /\/console\/nodes(?:\?|$)/.test(path)
          )
        )
      ).toBe(false);
      const add = section.getByRole("button", {
        name: label("console_node_assets_add"),
        exact: true,
      });
      await add.click();
      let dialog = page.getByRole("dialog", {
        name: label("console_node_assets_add"),
        exact: true,
      });
      await expect(
        dialog.getByRole("button", { name: label("console_node_assets_save"), exact: true })
      ).toBeDisabled();
      await dialog
        .getByRole("textbox", { name: label("console_node_assets_name"), exact: true })
        .fill("Inventory <node>");
      await dialog
        .getByRole("textbox", { name: label("console_node_assets_address"), exact: true })
        .fill("192.0.2.20");
      await dialog
        .getByRole("textbox", { name: label("console_node_assets_notes"), exact: true })
        .fill("Notes without credentials\n" + "long-name-".repeat(20));
      await page.screenshot({
        path: testInfo.outputPath(`assets-form-${language}-${width}.png`),
        fullPage: true,
        animations: "disabled",
      });
      await dialog
        .getByRole("button", { name: label("console_node_assets_save"), exact: true })
        .click();
      await expect(dialog).toBeHidden();
      await expect(section.locator("tbody tr")).toHaveCount(1);
      await expect(section.locator("tbody tr")).toContainText("Inventory <node>");
      expect(state.records).toHaveLength(1);
      const requestsBeforeReload = await page.evaluate(
        () => (window as TestWindow).nodeAssetRequests
      );
      await page.reload();
      await expect(section.locator("tbody tr")).toHaveCount(1);
      const edit = section.getByRole("button", {
        name: `${label("console_node_assets_edit")}: Inventory <node>`,
        exact: true,
      });
      await edit.click();
      dialog = page.getByRole("dialog", { name: label("console_node_assets_edit"), exact: true });
      await expect(
        dialog.getByRole("textbox", { name: label("console_node_assets_address"), exact: true })
      ).toHaveValue("192.0.2.20");
      await dialog
        .getByRole("textbox", { name: label("console_node_assets_notes"), exact: true })
        .fill("");
      await dialog
        .getByRole("button", { name: label("console_node_assets_save"), exact: true })
        .click();
      await expect(dialog).toBeHidden();
      await expect(section).toContainText(label("console_node_assets_no_notes"));
      const remove = section.getByRole("button", {
        name: `${label("console_node_assets_delete")}: Inventory <node>`,
        exact: true,
      });
      await remove.click();
      dialog = page.getByRole("dialog", {
        name: label("console_node_assets_delete_title"),
        exact: true,
      });
      await expect(dialog).toContainText(label("console_node_assets_delete_hint"));
      expect(state.records).toHaveLength(1);
      await page.keyboard.press("Escape");
      await expect(dialog).toBeHidden();
      await expect(remove).toBeFocused();
      expect(state.records).toHaveLength(1);
      await remove.click();
      await page.screenshot({
        path: testInfo.outputPath(`assets-confirm-${language}-${width}.png`),
        fullPage: true,
        animations: "disabled",
      });
      await dialog
        .getByRole("button", { name: label("console_node_assets_delete"), exact: true })
        .click();
      await expect(dialog).toBeHidden();
      await expect(section).toContainText(label("console_node_assets_empty"));
      expect(state.records).toHaveLength(0);
      expect(await page.evaluate(() => document.body.scrollWidth - innerWidth)).toBeLessThanOrEqual(
        2
      );
      const requestsAfterReload = await page.evaluate(
        () => (window as TestWindow).nodeAssetRequests
      );
      const writes = [...requestsBeforeReload, ...requestsAfterReload].filter(
        ({ method }) => method !== "GET"
      );
      expect(writes.map(({ method }) => method)).toEqual(["POST", "PUT", "DELETE"]);
      expect(writes.every(({ path }) => path.startsWith("/admin/console/node-assets"))).toBe(true);
      expect(errors).toEqual([]);
    });
  }

test("pending pagination and managed filters survive view switches and browser history", async ({
  page,
}) => {
  const label = labels("en");
  await install(page, "en", 21);
  await page.goto(`${url}&node_assets_page=1&nodes_q=HK&nodes_traffic_window=7d`);
  const section = page.getByRole("region", {
    name: label("console_node_assets_pending"),
    exact: true,
  });
  await expect(section.locator("tbody tr")).toHaveCount(1);
  await expect(section.locator(".admin-list-toolbar-summary strong")).toHaveText("21");
  await expect(
    page.getByRole("button", { name: label("console_nodes_window_label"), exact: true })
  ).toHaveCount(0);
  await page.getByRole("tab", { name: label("console_node_assets_managed"), exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: label("console_nodes_search"), exact: true })
  ).toHaveValue("HK");
  await expect(
    page.getByRole("button", { name: label("console_nodes_window_label"), exact: true })
  ).toHaveText(label("console_nodes_window_7d"));
  await page.goBack();
  await expect(section.locator("tbody tr")).toHaveCount(1);
  await section
    .getByRole("button", { name: new RegExp(`^${label("console_node_assets_delete")}:`) })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: label("console_node_assets_delete"), exact: true })
    .click();
  await expect(section.locator("tbody tr")).toHaveCount(20);
  await expect(section.locator(".admin-list-toolbar-summary strong")).toHaveText("20");
  await expect(page).not.toHaveURL(/node_assets_page=1/);
});

test("read/write failures keep count unknown and never silently retry a create", async ({
  page,
}) => {
  const label = labels("en");
  const { controls, state } = await install(page);
  controls.failRead = true;
  await page.goto(url);
  const section = page.getByRole("region", {
    name: label("console_node_assets_pending"),
    exact: true,
  });
  await expect(section.getByRole("alert")).toHaveText(label("console_node_assets_load_failed"));
  await expect(section.locator(".admin-list-toolbar-summary")).toHaveCount(0);
  await expect(section).not.toContainText(label("console_node_assets_empty"));
  controls.failRead = false;
  await section.getByRole("button", { name: label("retry"), exact: true }).click();
  await expect(section).toContainText(label("console_node_assets_empty"));
  controls.failWrite = true;
  await section
    .getByRole("button", { name: label("console_node_assets_add"), exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByRole("textbox", { name: label("console_node_assets_name"), exact: true })
    .fill("Unconfirmed");
  await dialog
    .getByRole("textbox", { name: label("console_node_assets_address"), exact: true })
    .fill("::1");
  await dialog
    .getByRole("button", { name: label("console_node_assets_save"), exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toHaveText(label("console_node_assets_write_failed"));
  expect(state.records).toHaveLength(0);
  expect(
    await page.evaluate(
      () =>
        (window as TestWindow).nodeAssetRequests.filter(({ method }) => method === "POST").length
    )
  ).toBe(1);
});

test("late pending reads cannot repaint the managed view", async ({ page }) => {
  const label = labels("en");
  const { controls } = await install(page, "en", 1);
  controls.holdRead = true;
  await page.goto(url);
  await expect.poll(() => controls.release !== null).toBe(true);
  await page.getByRole("tab", { name: label("console_node_assets_managed"), exact: true }).click();
  controls.release?.();
  await expect(
    page.getByRole("region", { name: label("console_node_assets_pending"), exact: true })
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: label("console_nodes_window_label"), exact: true })
  ).toBeVisible();
  await expect(page.locator(".console-nodes")).not.toContainText("Pending 0");
});
