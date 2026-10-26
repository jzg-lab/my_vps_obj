import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test, type Locator, type Page } from "@playwright/test";
import type { components } from "../src/lib/api/openapi.generated";
import {
  consoleNodeDetailFixture,
  consoleNodeFixture,
  consoleNodeServiceFixture,
} from "../src/lib/admin/consoleNodesFixtures";
import { consoleResourcePreviewFixture } from "../src/lib/webapp/mockApi/consoleResourcePreview";
import { resolveLocaleKey } from "../src/lib/webapp/constants";

type Preview = components["schemas"]["ConsoleResourcePreviewOut"];
type Revalidation = components["schemas"]["ConsoleResourceRevalidateOut"];
type Language = "en" | "ru" | "zh-hans";

const locales: Record<Language, Record<string, string>> = {
  en: JSON.parse(readFileSync(resolve(__dirname, "../../locales/en.json"), "utf8")),
  ru: JSON.parse(readFileSync(resolve(__dirname, "../../locales/ru.json"), "utf8")),
  "zh-hans": JSON.parse(readFileSync(resolve(__dirname, "../../locales/zh-hans.json"), "utf8")),
};
const label = (key: string, language: Language = "zh-hans") => {
  const resolvedKey = resolveLocaleKey(`admin_${key}`);
  const value = locales[language][resolvedKey];
  if (!value) throw new Error(`Missing ${language} translation: ${key} (${resolvedKey})`);
  return value;
};
const baseUrl =
  "/demo/runtime/admin/nodes?section=nodes&mock=services&theme_preview=dark&nodes_q=HK&nodes_page=2&nodes_related_page=1&node_id=" +
  consoleNodeFixture.id;
const serviceId = consoleNodeDetailFixture.services[0].id;

declare global {
  interface Window {
    __resourcePreviewHarness: {
      calls: Array<{ path: string; method: string; body?: string }>;
      catalogMode: "complete" | "partial" | "unavailable" | "failed";
      holdNextPreview: boolean;
      settled: number;
      revalidateMode: "unchanged" | "changed" | "incomplete" | "failed";
      releasePreview: () => void;
    };
  }
}

function makePreview(): Preview {
  const preview = consoleResourcePreviewFixture({
    operation: "node_disable",
    target_id: consoleNodeFixture.id,
    force_restart: false,
  });
  const direct = preview.direct.services[0];
  const reloadService = {
    ...direct,
    service_id: "b".repeat(32),
    name: "Reload-only service",
  };
  preview.possible_reload = {
    ...preview.direct,
    services: [reloadService],
    service_total: 1,
    customer_ids: [direct.customer_id],
    customer_total: 1,
  };
  preview.affected_service_ids = [direct.service_id, reloadService.service_id];
  preview.affected_customer_ids = [direct.customer_id];
  return preview;
}

async function installResourcePreviewApi(page: Page, language: Language = "zh-hans") {
  const preview = makePreview();
  await page.addInitScript(
    ({ detail, node, preview, language, service }) => {
      localStorage.setItem("rw_minishop_demo_language", language);
      type Props = { api: (path: string, options?: RequestInit) => Promise<unknown> };
      type Bundle = { mount: (target: HTMLElement, props: Props) => unknown };
      let bundle: Bundle | undefined;
      let release: (() => void) | undefined;
      const harness: Window["__resourcePreviewHarness"] = {
        calls: [],
        catalogMode: "complete",
        holdNextPreview: false,
        settled: 0,
        revalidateMode: "unchanged",
        releasePreview: () => release?.(),
      };
      window.__resourcePreviewHarness = harness;
      Object.defineProperty(window, "SubscriptionWebAppAdmin", {
        configurable: true,
        get: () => bundle,
        set(value: Bundle) {
          const mount = value.mount;
          value.mount = (target, props) =>
            mount(target, {
              ...props,
              api: async (path, options = {}) => {
                const request = new URL(path, "https://fixture.test");
                const method = options.method ?? "GET";
                harness.calls.push({
                  path: request.pathname,
                  method,
                  body: typeof options.body === "string" ? options.body : undefined,
                });
                const requestBody =
                  typeof options.body === "string"
                    ? (JSON.parse(options.body) as { change?: Preview["change"] })
                    : null;
                const requestedChange = requestBody?.change ?? preview.change;
                const responsePreview: Preview =
                  requestedChange.operation === "group_inbounds" ||
                  requestedChange.operation === "host_update"
                    ? ((await props.api("/admin/console/resources/preview", {
                        method: "POST",
                        body: JSON.stringify({ change: requestedChange }),
                      })) as Preview)
                    : {
                        ...preview,
                        change: requestedChange,
                        possible_reload:
                          requestedChange.operation === "node_restart"
                            ? {
                                ...preview.possible_reload,
                                services: [
                                  {
                                    ...preview.possible_reload.services[0],
                                    name: "Late restart result",
                                  },
                                ],
                              }
                            : preview.possible_reload,
                      };
                if (request.pathname === "/admin/console/nodes")
                  return { ok: true, nodes: [node], total: 100, page: 2, page_size: 25 };
                if (request.pathname === `/admin/console/nodes/${node.id}`)
                  return { ok: true, ...detail };
                if (request.pathname === "/admin/console/resources/catalog") {
                  if (harness.catalogMode === "failed") throw new Error("fixture_catalog_failed");
                  const catalog = (await props.api(
                    path,
                    options
                  )) as components["schemas"]["ConsoleResourceCatalogOut"];
                  return {
                    ...catalog,
                    profiles: catalog.profiles.map((profile) => ({
                      ...profile,
                      inbounds: profile.inbounds.map((inbound) => ({
                        ...inbound,
                        tag: profile.inbounds[0].tag,
                      })),
                    })),
                    ...(harness.catalogMode === "partial"
                      ? { coverage: "partial" }
                      : harness.catalogMode === "unavailable"
                        ? { draft_available: false }
                        : {}),
                  };
                }
                if (request.pathname === "/admin/console/resources/preview") {
                  if (harness.holdNextPreview) {
                    harness.holdNextPreview = false;
                    await new Promise<void>((resolve) => {
                      release = () => {
                        release = undefined;
                        harness.settled++;
                        resolve();
                      };
                    });
                  }
                  return { ok: true, ...responsePreview };
                }
                if (request.pathname === "/admin/console/resources/revalidate") {
                  if (harness.revalidateMode === "failed")
                    throw new Error("fixture_revalidate_failed");
                  const reason = harness.revalidateMode;
                  const result: Revalidation = {
                    valid: reason === "unchanged",
                    reason,
                    preview:
                      reason === "changed"
                        ? { ...responsePreview, fingerprint: "f".repeat(64) }
                        : reason === "incomplete"
                          ? {
                              ...responsePreview,
                              coverage: "partial",
                              blockers: ["nodes_unavailable"],
                              fingerprint: null,
                            }
                          : responsePreview,
                  };
                  return { ok: true, ...result };
                }
                if (request.pathname === `/admin/console/services/${service.service.id}`)
                  return { ok: true, ...service };
                if (request.pathname === `/admin/console/services/${"b".repeat(32)}`)
                  return {
                    ok: true,
                    ...service,
                    service: {
                      ...service.service,
                      id: "b".repeat(32),
                      name: "Reload-only service",
                    },
                    terms: { ...service.terms, name: "Reload-only service" },
                  };
                return props.api(path, options);
              },
            });
          bundle = value;
        },
      });
    },
    {
      detail: consoleNodeDetailFixture,
      node: consoleNodeFixture,
      preview,
      language,
      service: consoleNodeServiceFixture,
    }
  );
}

async function expectDraftFits(dialog: Locator) {
  // Check both the ScrollArea root and its actual scrolling viewport.
  const containers = dialog.locator(
    ".dialog-body-scroll, .dialog-body-scroll > .scroll-area__viewport, " +
      ".dialog-body-scroll > .scroll-area__viewport > div, " +
      ".resource-draft, .resource-draft .admin-field, .resource-draft .admin-field-label, " +
      ".resource-draft fieldset, .resource-draft .admin-select-trigger, .resource-draft .admin-select-trigger > span, " +
      ".resource-draft .admin-table-wrap"
  );
  await expect(dialog.locator(".resource-draft")).toBeVisible();
  await expect
    .poll(() =>
      containers.evaluateAll((elements) =>
        elements
          .filter((element) => element.scrollWidth > element.clientWidth + 1)
          .map((element) => ({
            element: element.className || element.tagName,
            scrollWidth: element.scrollWidth,
            clientWidth: element.clientWidth,
          }))
      )
    )
    .toEqual([]);
}

async function expectDraftMenuFits(page: Page, dialog: Locator) {
  const menu = page.locator('.admin-select-content[data-state="open"]');
  await expect(menu).toBeVisible();
  await expect(page.locator('.admin-select-content[data-state="closed"]')).toHaveCount(0);
  await expectDraftFits(dialog);
  await expect
    .poll(() =>
      menu.evaluate((element) => {
        const bounds = element.getBoundingClientRect();
        return {
          withinViewport: bounds.left >= 0 && bounds.right <= window.innerWidth + 1,
          overflow: [
            element,
            ...element.querySelectorAll(
              ".admin-select-viewport, [role='option'], [role='option'] > span"
            ),
          ]
            .filter((item) => item.scrollWidth > item.clientWidth + 1)
            .map((item) => ({
              element: item.className,
              scrollWidth: item.scrollWidth,
              clientWidth: item.clientWidth,
            })),
          truncatedLabels: [...element.querySelectorAll("[role='option'] > span")]
            .filter(
              (item) =>
                item.scrollHeight > item.clientHeight + 1 ||
                getComputedStyle(item).textOverflow === "ellipsis"
            )
            .map((item) => item.textContent),
        };
      })
    )
    .toEqual({ withinViewport: true, overflow: [], truncatedLabels: [] });
}

async function scrollDraftToTop(dialog: Locator) {
  const viewport = dialog.locator(".dialog-body-scroll > .scroll-area__viewport");
  await viewport.evaluate((element) => element.scrollTo({ top: 0, left: 0, behavior: "instant" }));
  await expect.poll(() => viewport.evaluate((element) => element.scrollTop)).toBe(0);
}

for (const width of [1440, 390]) {
  test(`Node resource preview stays truthful at ${width}px in zh-hans`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await installResourcePreviewApi(page);
    await page.goto(baseUrl);

    const detail = page.getByRole("region", { name: label("console_nodes_detail") });
    await expect(
      detail.getByRole("heading", { name: consoleNodeFixture.name, exact: true })
    ).toBeVisible();
    await detail.getByRole("button", { name: label("console_resource_open"), exact: true }).click();
    const previewDialog = page.getByRole("dialog", { name: label("console_resource_title") });
    await expect(previewDialog).toBeVisible();

    const operation = previewDialog.getByRole("button", {
      name: label("console_resource_operation"),
      exact: true,
    });
    await operation.click();
    await expect(
      page.getByRole("option", { name: label("console_resource_node_disable"), exact: true })
    ).toBeVisible();
    await page
      .getByRole("option", { name: label("console_resource_node_disable"), exact: true })
      .click();
    await previewDialog
      .getByRole("button", { name: label("console_resource_preview"), exact: true })
      .click();

    const direct = previewDialog.getByRole("region", { name: label("console_resource_direct") });
    const reload = previewDialog.getByRole("region", { name: label("console_resource_reload") });
    await expect(direct).toContainText("Shared service");
    await expect(reload).toContainText("Reload-only service");
    await expect(previewDialog).toContainText(`${label("console_resource_affected_services")}: 2`);
    await expect(previewDialog).toContainText(`${label("console_resource_affected_customers")}: 1`);
    await expect(previewDialog.getByRole("button", { name: /execute|执行|выполн/i })).toHaveCount(
      0
    );

    const confirmation = previewDialog.getByRole("checkbox", {
      name: label("console_resource_confirm"),
      exact: true,
    });
    await confirmation.check();
    await expect(confirmation).toBeChecked();

    await operation.click();
    await page
      .getByRole("option", { name: label("console_resource_node_restart"), exact: true })
      .click();
    await expect(previewDialog.getByText("Shared service", { exact: true })).toHaveCount(0);
    const forceRestart = previewDialog.getByRole("checkbox", {
      name: label("console_resource_force_restart"),
      exact: true,
    });
    await forceRestart.check();
    await expect(forceRestart).toBeChecked();
    await previewDialog
      .getByRole("button", { name: label("console_resource_preview"), exact: true })
      .click();
    await expect(previewDialog).toContainText("Shared service");
    await expect(confirmation).not.toBeChecked();

    await page.evaluate(() => {
      window.__resourcePreviewHarness.holdNextPreview = true;
    });
    await previewDialog
      .getByRole("button", { name: label("console_resource_preview"), exact: true })
      .click();
    await operation.click();
    await page
      .getByRole("option", { name: label("console_resource_node_disable"), exact: true })
      .click();
    await page.evaluate(() => window.__resourcePreviewHarness.releasePreview());
    await previewDialog
      .getByRole("button", { name: label("console_resource_preview"), exact: true })
      .click();
    await expect(previewDialog).toContainText("Shared service");
    await expect(previewDialog).toContainText("Reload-only service");
    await expect(previewDialog).not.toContainText("Late restart result");
    expect(await page.evaluate(() => window.__resourcePreviewHarness.settled)).toBe(1);

    for (const mode of ["changed", "incomplete", "failed"] as const) {
      await previewDialog
        .getByRole("button", { name: label("console_resource_preview"), exact: true })
        .click();
      await expect(previewDialog).toContainText("Shared service");
      await confirmation.check();
      await page.evaluate((value) => {
        window.__resourcePreviewHarness.revalidateMode = value;
      }, mode);
      await previewDialog
        .getByRole("button", { name: label("console_resource_revalidate"), exact: true })
        .click();
      if (mode === "failed") await expect(confirmation).toHaveCount(0);
      else await expect(confirmation).not.toBeChecked();
      await expect(previewDialog).toContainText(
        label(`console_resource_revalidate_${mode === "failed" ? "failed" : mode}`)
      );
    }

    await previewDialog
      .getByRole("button", { name: label("console_resource_preview"), exact: true })
      .click();
    const serviceLink = previewDialog.locator(`[data-resource-service-id="${serviceId}"]`).first();
    await expect(serviceLink).toBeVisible();
    const serviceUrl = new URL((await serviceLink.getAttribute("href"))!);
    expect(serviceUrl.searchParams.get("nodes_q")).toBe("HK");
    expect(serviceUrl.searchParams.get("nodes_page")).toBe("2");
    expect(serviceUrl.searchParams.get("nodes_related_page")).toBe("1");
    await serviceLink.click();
    const serviceDialog = page.getByRole("dialog", { name: label("console_service_detail") });
    await expect(
      serviceDialog.getByRole("heading", { name: "Shared service", level: 3, exact: true })
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(serviceDialog).toHaveCount(0);
    await expect(serviceLink).toBeFocused();
    const returned = new URL(page.url());
    expect(returned.searchParams.get("nodes_q")).toBe("HK");
    expect(returned.searchParams.get("nodes_page")).toBe("2");
    expect(returned.searchParams.get("nodes_related_page")).toBe("1");
    await page.screenshot({
      path: info.outputPath(`resource-preview-${width}.png`),
      fullPage: true,
    });

    const calls = await page.evaluate(() => window.__resourcePreviewHarness.calls);
    expect(calls.some((call) => call.method !== "GET" && !call.path.includes("/resources/"))).toBe(
      false
    );
    expect(calls.some((call) => call.path.includes("/execute"))).toBe(false);
  });
}

for (const width of [1440, 390]) {
  for (const language of ["en", "ru", "zh-hans"] as const) {
    test(`Group and Host drafts remain read-only at ${width}px in ${language}`, async ({
      page,
    }, info) => {
      const text = (key: string) => label(key, language);
      await page.setViewportSize({ width, height: 1000 });
      await installResourcePreviewApi(page, language);
      await page.goto(baseUrl);
      const detail = page.getByRole("region", { name: text("console_nodes_detail") });
      const groupEntry = detail.getByRole("button", {
        name: text("console_draft_group_open"),
        exact: true,
      });
      await groupEntry.click();
      const dialog = page.getByRole("dialog", { name: text("console_draft_title") });
      const generate = dialog.getByRole("button", {
        name: text("console_resource_preview"),
        exact: true,
      });
      const confirmation = dialog.getByRole("checkbox", {
        name: text("console_resource_confirm"),
        exact: true,
      });
      const firstInbound = dialog.getByRole("checkbox", {
        name: `HK profile · vless-main · ${consoleNodeFixture.inbound_ids[0]}`,
        exact: true,
      });
      await expect(firstInbound).toBeChecked();
      await expectDraftFits(dialog);
      await scrollDraftToTop(dialog);
      await page.screenshot({
        path: info.outputPath(`resource-draft-group-top-${language}-${width}.png`),
        fullPage: true,
        animations: "disabled",
      });
      await firstInbound.uncheck();
      await expect(dialog).toContainText(text("console_draft_empty_inbounds"));
      await generate.click();
      await confirmation.check();
      await expect(confirmation).toBeChecked();
      await firstInbound.check();
      await expect(confirmation).toHaveCount(0);
      await generate.click();
      await expect(confirmation).not.toBeChecked();
      const service = dialog.locator(`[data-resource-service-id="${serviceId}"]`).first();
      await service.click();
      const serviceDialog = page.getByRole("dialog", { name: text("console_service_detail") });
      await expect(
        serviceDialog.getByRole("heading", { name: "Shared service", level: 3, exact: true })
      ).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(service).toBeFocused();
      await expect(firstInbound).toBeChecked();
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      await expect(groupEntry).toBeFocused();

      await detail
        .getByRole("button", { name: text("console_draft_host_open"), exact: true })
        .click();
      const profile = dialog.getByRole("button", {
        name: text("console_nodes_profile"),
        exact: true,
      });
      await expect(profile).toBeVisible();
      await expectDraftFits(dialog);
      await scrollDraftToTop(dialog);
      await page.screenshot({
        path: info.outputPath(`resource-draft-host-top-${language}-${width}.png`),
        fullPage: true,
        animations: "disabled",
      });
      await dialog
        .getByRole("button", { name: text("console_nodes_inbounds"), exact: true })
        .click();
      await expectDraftMenuFits(page, dialog);
      for (const id of [
        "30000000-0000-0000-0000-000000000001",
        "30000000-0000-0000-0000-000000000002",
      ])
        await expect(
          page.getByRole("option", { name: `vless-main · ${id}`, exact: true })
        ).toBeVisible();
      await page.screenshot({
        path: info.outputPath(`resource-draft-same-name-inbounds-${language}-${width}.png`),
        fullPage: true,
        animations: "disabled",
      });
      await page.keyboard.press("Escape");
      await profile.click();
      await expectDraftMenuFits(page, dialog);
      for (const id of [
        "20000000-0000-0000-0000-000000000001",
        "20000000-0000-0000-0000-000000000002",
      ])
        await expect(
          page.getByRole("option", { name: `HK profile · ${id}`, exact: true })
        ).toBeVisible();
      await page.screenshot({
        path: info.outputPath(`resource-draft-profile-menu-${language}-${width}.png`),
        fullPage: true,
        animations: "disabled",
      });
      await page
        .getByRole("option", {
          name: "HK profile · 20000000-0000-0000-0000-000000000002",
          exact: true,
        })
        .click();
      await expect(generate).toBeDisabled();
      await dialog
        .getByRole("button", { name: text("console_nodes_inbounds"), exact: true })
        .click();
      await expectDraftMenuFits(page, dialog);
      await page.screenshot({
        path: info.outputPath(`resource-draft-inbound-menu-${language}-${width}.png`),
        fullPage: true,
        animations: "disabled",
      });
      await page
        .getByRole("option", {
          name: "vless-other · 30000000-0000-0000-0000-000000000003",
          exact: true,
        })
        .click();
      await dialog
        .getByRole("button", { name: text("console_draft_group_mode"), exact: true })
        .click();
      await expectDraftMenuFits(page, dialog);
      await page.screenshot({
        path: info.outputPath(`resource-draft-group-menu-${language}-${width}.png`),
        fullPage: true,
        animations: "disabled",
      });
      await page
        .getByRole("option", { name: text("console_draft_allow_only"), exact: true })
        .click();
      await dialog
        .getByRole("checkbox", {
          name: "Shared HK · 40000000-0000-0000-0000-000000000002",
          exact: true,
        })
        .check();
      await dialog
        .getByRole("checkbox", { name: text("console_draft_hidden"), exact: true })
        .check();
      await generate.click();
      await confirmation.check();
      for (const mode of ["changed", "incomplete", "failed"] as const) {
        await page.evaluate((mode) => {
          window.__resourcePreviewHarness.revalidateMode = mode;
        }, mode);
        await dialog
          .getByRole("button", { name: text("console_resource_revalidate"), exact: true })
          .click();
        await expect(dialog).toContainText(text(`console_resource_revalidate_${mode}`));
        if (mode === "failed") await expect(confirmation).toHaveCount(0);
        else await expect(confirmation).not.toBeChecked();
        await generate.click();
        await confirmation.check();
      }
      await expect(dialog.getByRole("button", { name: /execute|执行|выполн/i })).toHaveCount(0);
      await page.screenshot({
        path: info.outputPath(`resource-draft-${language}-${width}.png`),
        fullPage: true,
        animations: "disabled",
      });
      await expectDraftFits(dialog);
      const calls = await page.evaluate(() => window.__resourcePreviewHarness.calls);
      const writes = calls.filter((call) => call.method !== "GET");
      expect(
        writes.every((call) =>
          ["/admin/console/resources/preview", "/admin/console/resources/revalidate"].includes(
            call.path
          )
        )
      ).toBe(true);
      const hostCall = writes.find((call) => call.body?.includes("host_update"));
      const body = JSON.parse(hostCall!.body!);
      expect(body.change.patch).toMatchObject({
        profile_id: "20000000-0000-0000-0000-000000000002",
        inbound_id: "30000000-0000-0000-0000-000000000003",
        group_mode: "ALLOW_ONLY",
        group_ids: ["40000000-0000-0000-0000-000000000002"],
        is_hidden: true,
      });
      expect(body.change.patch).not.toHaveProperty("address");
      expect(body.change.patch).not.toHaveProperty("port");
      expect(new URL(page.url()).searchParams.get("nodes_related_page")).toBe("1");
    });
  }
}

for (const mode of ["partial", "unavailable", "failed"] as const) {
  test(`Catalog ${mode} invalidates existing draft confirmation and permits retry`, async ({
    page,
  }) => {
    await installResourcePreviewApi(page);
    await page.goto(baseUrl);
    await page
      .getByRole("button", { name: label("console_draft_group_open"), exact: true })
      .click();
    const dialog = page.getByRole("dialog", { name: label("console_draft_title") });
    await dialog
      .getByRole("button", { name: label("console_resource_preview"), exact: true })
      .click();
    const confirmation = dialog.getByRole("checkbox", {
      name: label("console_resource_confirm"),
      exact: true,
    });
    await confirmation.check();
    await page.evaluate((mode) => {
      window.__resourcePreviewHarness.catalogMode = mode;
    }, mode);
    await dialog.getByRole("button", { name: label("console_draft_reload"), exact: true }).click();
    await expect(dialog.getByRole("alert")).toContainText(
      label(mode === "failed" ? "services_request_failed" : "console_draft_unavailable")
    );
    await expect(confirmation).toHaveCount(0);
    await expect(
      dialog.getByRole("button", { name: label("console_resource_preview"), exact: true })
    ).toHaveCount(0);
    await page.evaluate(() => {
      window.__resourcePreviewHarness.catalogMode = "complete";
    });
    await dialog.getByRole("button", { name: label("console_draft_reload"), exact: true }).click();
    await expect(
      dialog.getByRole("button", { name: label("console_resource_preview"), exact: true })
    ).toBeEnabled();
    await expect(confirmation).toHaveCount(0);
  });
}
