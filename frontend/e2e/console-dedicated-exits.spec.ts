import { readFileSync } from "node:fs";
import { expect, test, type BrowserContext, type Locator, type Page } from "@playwright/test";
import type { components, paths } from "../src/lib/api/openapi.generated";
import {
  consoleNodeServiceFixture,
  consoleServiceResourcesFixture,
} from "../src/lib/admin/consoleNodesFixtures";
import { resolveLocaleKey } from "../src/lib/webapp/constants";

const locale: Record<string, string> = JSON.parse(readFileSync("../locales/zh-hans.json", "utf8"));
const label = (key: string) => {
  const resolvedKey = resolveLocaleKey(`admin_${key}`);
  const value = locale[resolvedKey];
  if (typeof value !== "string" || value.length === 0)
    throw new Error(`Missing zh-hans translation: ${key} (${resolvedKey})`);
  return value;
};
const baseUrl =
  "/demo/runtime/admin/dedicated-exits?section=dedicated-exits&mock=services&theme_preview=dark&nodes_q=HK&users_q=910002";
const customerId = consoleNodeServiceFixture.customer?.minishop_id;
if (!customerId) throw new Error("The shared customer fixture requires a minishop ID.");
const currentService: components["schemas"]["ConsoleServiceDetailOut"] = {
  ...consoleNodeServiceFixture,
  service: {
    ...consoleNodeServiceFixture.service,
    name: "Current dedicated service",
    resource_type: "dedicated",
    exit_ip: "192.0.2.90",
    exit_verified: true,
  },
  terms: {
    ...consoleNodeServiceFixture.terms,
    name: "Current dedicated service",
    resource_type: "dedicated",
    resource_pool: "dedicated-e2e",
  },
};
const archivedService: components["schemas"]["ConsoleServiceDetailOut"] = {
  ...currentService,
  customer: {
    user_id: null,
    minishop_id: null,
    username: null,
    email: null,
    first_name: null,
    last_name: null,
    is_banned: null,
  },
  terms: { ...currentService.terms, name: "Archived dedicated service" },
  service: {
    ...currentService.service,
    id: "b".repeat(32),
    user_id: null,
    name: "Archived dedicated service",
    status: "cancelled",
    desired_status: "cancelled",
    connection_state: "revoked",
    exit_ip: null,
    exit_verified: false,
  },
};
const boundExit: components["schemas"]["DedicatedExitOut"] = {
  id: "e".repeat(32),
  label: "Bound exit on page two",
  ip_address: "192.0.2.90",
  resource_pool: "dedicated-e2e",
  revision: 5,
  squad_uuid: "40000000-0000-0000-0000-000000000001",
  service_id: currentService.service.id,
  hold_order_id: null,
  hold_service_id: null,
  enabled: true,
  verified_at: "2026-10-24T08:00:00Z",
};
const exits: components["schemas"]["DedicatedExitOut"][] = [
  ...Array.from({ length: 25 }, (_, index) => ({
    ...boundExit,
    id: (600 + index).toString(16).padStart(32, "0"),
    label: `Unbound exit ${index + 1}`,
    ip_address: `192.0.2.${index + 10}`,
    service_id: null,
    verified_at: null,
  })),
  boundExit,
];
const audit: components["schemas"]["ExitAuditOut"][] = Array.from({ length: 11 }, (_, index) => ({
  id: (700 + index).toString(16).padStart(32, "0"),
  exit_id: boundExit.id,
  service_id: index === 10 ? archivedService.service.id : currentService.service.id,
  actor_id: 42,
  action: index === 10 ? "reclaim" : "verify",
  created_at: index === 10 ? "2026-10-22T08:00:00Z" : "2026-10-24T08:00:00Z",
  evidence: {
    evidence:
      index === 10 ? "Archived allocation evidence" : `Current allocation evidence ${index}`,
    ...(index === 10
      ? { connections_stopped: true, old_config_rejected: true }
      : { observed_ip: boundExit.ip_address, fixed: true, exclusive: true }),
  },
}));
const resources: components["schemas"]["ConsoleServiceResourcesOut"] = {
  ...consoleServiceResourcesFixture,
  nodes: [],
  hosts: [],
  groups: [],
  configured_group_ids: [],
  coverage: "complete",
  sources: [],
};

declare global {
  interface Window {
    __dedicatedExitHarness: {
      allocation: "bound" | "held" | "held_unknown";
      serviceState: "ready" | "replacing" | "failed" | "missing";
      rejectEvidence: boolean;
      holdNextAudit: boolean;
      failNextAudit: boolean;
      settled: number;
      calls: Array<{ path: string; method: string; aborted: boolean }>;
      releaseAudit: (fail?: boolean) => void;
    };
  }
}

async function installExitsApi(context: BrowserContext) {
  // Context scope is intentional: copied links, reloads and new tabs need the same records.
  await context.addInitScript(
    ({ exits, audit, currentService, archivedService, resources }) => {
      localStorage.setItem("rw_minishop_demo_language", "zh-hans");
      type Props = { api: (path: string, options?: RequestInit) => Promise<unknown> };
      type Bundle = { mount: (target: HTMLElement, props: Props) => unknown };
      let bundle: Bundle | undefined;
      let release: ((fail?: boolean) => void) | undefined;
      const harness: Window["__dedicatedExitHarness"] = {
        allocation: "bound",
        serviceState: "ready",
        rejectEvidence: false,
        holdNextAudit: false,
        failNextAudit: false,
        settled: 0,
        calls: [],
        releaseAudit: (fail) => release?.(fail),
      };
      window.__dedicatedExitHarness = harness;
      Object.defineProperty(window, "SubscriptionWebAppAdmin", {
        configurable: true,
        get: () => bundle,
        set(value: Bundle) {
          const mount = value.mount;
          value.mount = (target, props) =>
            mount(target, {
              ...props,
              api: async (path, options) => {
                const request = new URL(path, "https://fixture.test");
                const call = { path, method: options?.method ?? "GET", aborted: false };
                harness.calls.push(call);
                options?.signal?.addEventListener("abort", () => (call.aborted = true));
                if (call.method !== "GET") {
                  if (
                    harness.rejectEvidence &&
                    call.method === "POST" &&
                    /^\/admin\/dedicated-exits\/[^/]+\/(verify|reclaim)$/.test(request.pathname)
                  )
                    return { ok: false, error: "exit_replacement_in_progress" };
                  throw new Error("ownership_fixture_is_read_only");
                }
                const offset = Number(request.searchParams.get("offset") ?? 0);
                const limit = Number(request.searchParams.get("limit") ?? 25);
                if (request.pathname === "/admin/dedicated-exits") {
                  const inventory = exits.map((exit) =>
                    exit.id === exits.at(-1)!.id && harness.allocation !== "bound"
                      ? {
                          ...exit,
                          service_id: null,
                          hold_order_id: "d".repeat(32),
                          hold_service_id:
                            harness.allocation === "held" ? currentService.service.id : null,
                        }
                      : exit
                  );
                  return {
                    ok: true,
                    exits: inventory.slice(offset, offset + limit),
                    total: exits.length,
                  } satisfies paths["/api/admin/dedicated-exits"]["get"]["responses"][200]["content"]["application/json"];
                }
                if (request.pathname === `/admin/dedicated-exits/${exits.at(-1)!.id}/audit`) {
                  if (harness.failNextAudit) {
                    harness.failNextAudit = false;
                    throw new Error("fixture_audit_failed");
                  }
                  if (harness.holdNextAudit) {
                    harness.holdNextAudit = false;
                    // Ignore AbortSignal deliberately to exercise the request-sequence guard too.
                    await new Promise<void>((resolve, reject) => {
                      release = (fail) => {
                        release = undefined;
                        harness.settled++;
                        if (fail) reject(new Error("fixture_late_audit_failure"));
                        else resolve();
                      };
                    });
                  }
                  return {
                    ok: true,
                    audit: audit.slice(offset, offset + limit),
                    total: audit.length,
                  } satisfies paths["/api/admin/dedicated-exits/{exit_id}/audit"]["get"]["responses"][200]["content"]["application/json"];
                }
                if (request.pathname === "/admin/service-plans")
                  return {
                    ok: true,
                    plans: [
                      {
                        id: "f".repeat(32),
                        enabled: true,
                        revision: 1,
                        updated_at: "2026-10-24T08:00:00Z",
                        terms: currentService.terms,
                      },
                    ],
                    total: 1,
                  } satisfies paths["/api/admin/service-plans"]["get"]["responses"][200]["content"]["application/json"];
                for (const detail of [currentService, archivedService]) {
                  if (request.pathname === `/admin/console/services/${detail.service.id}`) {
                    if (harness.serviceState === "failed") throw new Error("fixture_read_failed");
                    const service = {
                      ...detail.service,
                      replacement_order_id:
                        harness.serviceState === "replacing" ? "d".repeat(32) : null,
                    };
                    if (harness.serviceState === "missing")
                      Reflect.deleteProperty(service, "replacement_order_id");
                    return { ok: true, ...detail, service };
                  }
                  if (request.pathname === `/admin/console/services/${detail.service.id}/resources`)
                    return {
                      ok: true,
                      ...resources,
                      service_id: detail.service.id,
                      status: detail.service.status,
                      connection_state: detail.service.connection_state,
                      currently_eligible: detail.service.user_id !== null,
                    };
                }
                if (
                  request.pathname === "/admin/services" &&
                  request.searchParams.get("user_id") === String(currentService.service.user_id)
                )
                  return { ok: true, services: [currentService.service], total: 1 };
                if (request.pathname === "/admin/service-orders")
                  return { ok: true, orders: [], total: 0 };
                return props.api(path, options);
              },
            });
          bundle = value;
        },
      });
    },
    { exits, audit, currentService, archivedService, resources }
  );
}

function evidenceDialog(page: Page) {
  return page.getByRole("dialog", { name: label("services_exit_evidence"), exact: true });
}
function serviceDialog(page: Page) {
  return page.getByRole("dialog", { name: label("console_service_detail"), exact: true });
}
async function expectFocusInside(dialog: Locator) {
  await expect
    .poll(() => dialog.evaluate((element) => element.contains(document.activeElement)))
    .toBe(true);
}
async function expectNoOverflow(page: Page, dialog?: Locator) {
  expect(await page.evaluate(() => document.body.scrollWidth - innerWidth)).toBeLessThanOrEqual(2);
  if (dialog)
    expect(
      await dialog
        .locator(".dialog-card")
        .evaluate((element) => element.scrollWidth - element.clientWidth)
    ).toBeLessThanOrEqual(2);
}
async function expectReadOnly(page: Page) {
  expect(
    await page.evaluate(() =>
      window.__dedicatedExitHarness.calls.filter((call) => call.method !== "GET")
    )
  ).toEqual([]);
}
const evidenceUrl = `${baseUrl}&exits_page=1&exit_id=${boundExit.id}`;

async function fillEvidence(page: Page, action: "verify" | "reclaim" = "verify") {
  const dialog = evidenceDialog(page);
  const note = dialog.getByLabel(label("services_exit_evidence_note"), { exact: true });
  await expect(note).toBeEnabled();
  if (action === "reclaim") {
    await dialog.getByRole("button", { name: label("services_exit_action"), exact: true }).click();
    await page.getByRole("option", { name: label("services_exit_reclaim"), exact: true }).click();
  } else
    await dialog
      .getByLabel(label("services_exit_observed_ip"), { exact: true })
      .fill(boundExit.ip_address);
  await note.fill("Evidence must not bypass a replacement hold.");
  await dialog.getByRole("checkbox").check();
  await expect(dialog.getByRole("button", { name: label("save"), exact: true })).toBeEnabled();
}

for (const width of [1440, 390]) {
  test.describe(`dedicated exit ownership at ${width}px`, () => {
    test.beforeEach(async ({ context, page }) => {
      await page.setViewportSize({ width, height: 1000 });
      await installExitsApi(context);
    });

    for (const knownOwner of [true, false]) {
      test(`held inventory stays protected with ${knownOwner ? "known" : "unknown"} ownership`, async ({
        page,
      }, info) => {
        await page.goto(`${baseUrl}&exits_page=1`);
        const inventory = page.locator(".exits");
        await expect(inventory.locator("tbody tr")).toHaveCount(1);
        await page.evaluate((known) => {
          window.__dedicatedExitHarness.allocation = known ? "held" : "held_unknown";
        }, knownOwner);
        await inventory.getByRole("button", { name: label("refresh"), exact: true }).click();
        const row = inventory.locator(`[data-exit-id="${boundExit.id}"]`);
        await expect(row).toContainText(label("services_exit_held"));
        await expect(row).not.toContainText(label("services_available"));
        await expect(row).toContainText(label("services_exit_hold_service"));
        if (knownOwner)
          await expect(
            row.getByRole("link", { name: currentService.service.id, exact: true })
          ).toBeVisible();
        else {
          await expect(row.locator("a")).toHaveCount(0);
          await expect(row).toContainText(label("console_unknown"));
        }
        await page.screenshot({
          path: info.outputPath("held-inventory.png"),
          fullPage: true,
          animations: "disabled",
        });
        await row
          .getByRole("button", { name: label("services_exit_evidence"), exact: true })
          .click();
        const evidence = evidenceDialog(page);
        await expect(evidence).toContainText(label("services_exit_held"));
        await expect(evidence).not.toContainText(label("console_exit_replacement_in_progress"));
        await expect(
          evidence.getByRole("button", { name: label("save"), exact: true })
        ).toBeDisabled();
        await expect(
          evidence.getByRole("button", { name: label("services_exit_action"), exact: true })
        ).toBeDisabled();
        await expect(evidence.getByRole("checkbox")).toBeDisabled();
        await evidence
          .locator("form.exit-evidence")
          .evaluate((form) =>
            form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }))
          );
        await expect(evidence.locator("ol li")).toHaveCount(10);
        await expectNoOverflow(page, evidence);
        await evidence.screenshot({
          path: info.outputPath("held-evidence.png"),
          animations: "disabled",
        });
        if (knownOwner) {
          await evidence
            .getByRole("link", { name: currentService.service.id, exact: true })
            .first()
            .click();
          const detail = serviceDialog(page);
          await expect(
            detail.getByRole("heading", {
              name: currentService.service.name,
              level: 3,
              exact: true,
            })
          ).toBeVisible();
          await detail
            .getByRole("button", { name: label("services_activate"), exact: true })
            .click();
          const activation = page.getByRole("dialog", {
            name: label("services_activate"),
            exact: true,
          });
          await activation
            .getByRole("button", { name: label("services_choose_plan"), exact: true })
            .click();
          await page.getByRole("option", { name: currentService.terms.name, exact: true }).click();
          await activation
            .getByRole("button", { name: label("services_choose_exit"), exact: true })
            .click();
          await expect(
            page.getByRole("option", {
              name: `${boundExit.label} · ${boundExit.ip_address}`,
              exact: true,
            })
          ).toHaveCount(0);
          await expect(
            page.getByRole("option", {
              name: `${exits[0].label} · ${exits[0].ip_address}`,
              exact: true,
            })
          ).toBeVisible();
          await expect(
            activation.getByRole("button", { name: label("services_activate"), exact: true })
          ).toBeDisabled();
          await expectNoOverflow(page, activation);
          await page.screenshot({
            path: info.outputPath("held-activation.png"),
            fullPage: true,
            animations: "disabled",
          });
        }
        await expectReadOnly(page);
      });
    }

    for (const action of ["verify", "reclaim"] as const) {
      test(`rechecks the binding before ${action} and blocks an active replacement`, async ({
        page,
      }) => {
        await page.goto(evidenceUrl);
        await fillEvidence(page, action);
        await page.evaluate(() => {
          window.__dedicatedExitHarness.serviceState = "replacing";
        });
        const evidence = evidenceDialog(page);
        await evidence.getByRole("button", { name: label("save"), exact: true }).click();
        await expect(evidence).toContainText(label("console_exit_replacement_in_progress"));
        await expect(
          evidence.getByRole("button", { name: label("save"), exact: true })
        ).toBeDisabled();
        await expect(evidence.getByRole("checkbox")).toBeDisabled();
        await expectReadOnly(page);
      });
    }

    for (const state of ["failed", "missing"] as const) {
      test(`${state} binding information blocks evidence writes until a successful reread`, async ({
        page,
      }) => {
        await page.goto(evidenceUrl);
        await fillEvidence(page);
        await page.evaluate((value) => {
          window.__dedicatedExitHarness.serviceState = value;
        }, state);
        const evidence = evidenceDialog(page);
        await evidence.getByRole("button", { name: label("save"), exact: true }).click();
        await expect(evidence.getByRole("alert")).toHaveText(label("console_detail_failed"));
        await expect(
          evidence.getByRole("button", { name: label("save"), exact: true })
        ).toBeDisabled();
        await page.evaluate(() => {
          window.__dedicatedExitHarness.serviceState = "ready";
        });
        await evidence.getByRole("button", { name: label("refresh"), exact: true }).click();
        await expect(evidence.getByRole("alert")).toHaveCount(0);
        await expect(
          evidence.getByRole("button", { name: label("save"), exact: true })
        ).toBeEnabled();
        await expectReadOnly(page);
      });
    }

    test("a server replacement rejection stays blocked without replaying the ordinary write", async ({
      page,
    }) => {
      await page.goto(evidenceUrl);
      await fillEvidence(page);
      await page.evaluate(() => {
        window.__dedicatedExitHarness.rejectEvidence = true;
      });
      const evidence = evidenceDialog(page);
      await evidence.getByRole("button", { name: label("save"), exact: true }).click();
      await expect(evidence.getByRole("alert")).toHaveText(
        label("console_exit_replacement_in_progress")
      );
      await expect(
        evidence.getByRole("button", { name: label("save"), exact: true })
      ).toBeDisabled();
      await evidence
        .locator("form.exit-evidence")
        .evaluate((form) =>
          form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }))
        );
      expect(
        await page.evaluate(() =>
          window.__dedicatedExitHarness.calls
            .filter((call) => call.method !== "GET")
            .map((call) => call.path)
        )
      ).toEqual([`/admin/dedicated-exits/${boundExit.id}/verify`]);
      await expect(evidence.locator("ol li")).toHaveCount(10);
    });

    test("inventory links preserve pages through new tab, reload, customer and browser history", async ({
      page,
      context,
    }, info) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.goto(baseUrl);
      const inventory = page.locator(".exits");
      await expect(inventory.locator("tbody tr")).toHaveCount(25);
      await expect(inventory.locator("tbody a")).toHaveCount(0);
      await expect(inventory.locator(".admin-list-toolbar-summary strong")).toHaveText("26");
      await inventory.getByRole("button", { name: label("services_next"), exact: true }).click();
      await expect(inventory.locator("tbody tr")).toHaveCount(1);
      const listUrl = page.url();
      const link = inventory.getByRole("link", { name: currentService.service.id, exact: true });
      const target = new URL((await link.getAttribute("href"))!);
      expect(target.pathname).toBe("/demo/runtime/admin/dedicated-exits");
      expect(target.searchParams.get("exit_service_id")).toBe(currentService.service.id);
      expect(target.searchParams.get("exits_page")).toBe("1");
      expect(target.searchParams.get("nodes_q")).toBe("HK");
      expect(target.searchParams.get("users_q")).toBe("910002");
      const popup = context.waitForEvent("page");
      await link.click({ modifiers: ["ControlOrMeta"] });
      const tab = await popup;
      const tabErrors: string[] = [];
      tab.on("pageerror", (error) => tabErrors.push(error.message));
      await tab.setViewportSize({ width, height: 1000 });
      await expect(tab).toHaveURL(target.href);
      await expect(
        serviceDialog(tab).getByRole("heading", {
          name: currentService.service.name,
          level: 3,
          exact: true,
        })
      ).toBeVisible();
      await tab.reload();
      await expect(serviceDialog(tab)).toBeVisible();
      await expectReadOnly(tab);
      expect(tabErrors).toEqual([]);
      await tab.close();
      await expect(page).toHaveURL(listUrl);

      await link.focus();
      await page.keyboard.press("Enter");
      const serviceUrl = page.url();
      const service = serviceDialog(page);
      await expect(
        service.getByRole("heading", { name: currentService.service.name, level: 3, exact: true })
      ).toBeVisible();
      await page.reload();
      await expect(service).toBeVisible();
      await service
        .getByRole("button", { name: label("console_manage_customer"), exact: true })
        .click();
      await expect(page.locator(".admin-user-hero")).toContainText(customerId);
      await expect(page.locator(".user-services")).toContainText(currentService.service.id);
      await expect(page.locator(".user-services")).not.toContainText(archivedService.service.id);
      const customerUrl = page.url();
      await page.reload();
      await expect(page.locator(".admin-user-hero")).toContainText(customerId);
      await page.goBack();
      await expect(page).toHaveURL(serviceUrl);
      await expect(service).toBeVisible();
      await page.goForward();
      await expect(page).toHaveURL(customerUrl);
      await page.getByRole("button", { name: label("user_back"), exact: true }).click();
      await expect(page).toHaveURL(serviceUrl);
      await expectFocusInside(service);
      await page.keyboard.press("Escape");
      await expect(page).toHaveURL(listUrl);
      await expect(link).toBeFocused();
      await expect(inventory.locator("tbody tr")).toHaveCount(1);
      // Outgoing customer stages can still cover an already mounted, focused exit row.
      const stage = page.locator(".admin-section-stage");
      await expect(stage).toHaveCount(1);
      await expect(stage).toHaveAttribute("data-admin-active-section", "dedicated-exits");
      await expect(stage).toHaveCSS("opacity", "1");
      await expect(page.locator(".admin-main .admin-skeleton:visible")).toHaveCount(0);
      await expect(page.locator(".admin-main .admin-section-loading:visible")).toHaveCount(0);
      await expect(inventory).toHaveAttribute("aria-busy", "false");
      const restoredExit = inventory.locator(`tbody tr[data-exit-id="${boundExit.id}"]`);
      await expect(restoredExit).toBeVisible();
      await expect(restoredExit.locator("td").nth(0)).toHaveText(boundExit.label);
      await expect(restoredExit.locator("td").nth(1)).toHaveText(boundExit.ip_address);
      await expect(restoredExit.locator("td").nth(2)).toHaveText(boundExit.resource_pool);
      await expect(
        restoredExit.getByRole("link", { name: currentService.service.id, exact: true })
      ).toBeVisible();
      await expect(inventory.locator(".admin-list-toolbar-summary strong")).toHaveText("26");
      await expect(
        inventory.locator(".admin-pagination-summary .admin-pagination-count")
      ).toHaveText([
        `${label("services_page")} 2 ${label("services_of")} 2`,
        `${label("services_exits_count")} 26`,
      ]);
      await expect(inventory.locator('.admin-pagination-pages [aria-current="page"]')).toHaveText(
        "2"
      );
      await expect(
        inventory.getByRole("button", { name: label("services_previous"), exact: true })
      ).toBeEnabled();
      await expect(
        inventory.getByRole("button", { name: label("services_next"), exact: true })
      ).toBeDisabled();
      await expect(page.locator('.admin-nav-item[aria-current="page"]')).toHaveCount(1);
      await expect(page.locator('.admin-nav-item[aria-current="page"]')).toHaveAttribute(
        "data-admin-section",
        "dedicated-exits"
      );
      await expect(service).toHaveCount(0);
      await expect(page.locator(".admin-user-hero")).toHaveCount(0);
      await expect(page).toHaveURL(listUrl);
      const restoredUrl = new URL(page.url());
      expect(restoredUrl.searchParams.get("exits_page")).toBe("1");
      expect(restoredUrl.searchParams.get("nodes_q")).toBe("HK");
      expect(restoredUrl.searchParams.get("users_q")).toBe("910002");
      await expect(link).toBeFocused();
      await page.screenshot({ path: info.outputPath("inventory-return.png"), fullPage: true });
      await expectNoOverflow(page);
      await expectReadOnly(page);
      expect(errors).toEqual([]);
    });

    test("evidence context, unsaved fields, nested focus and Escape survive service and customer visits", async ({
      page,
    }, info) => {
      await page.goto(`${evidenceUrl}&exit_audit_page=1`);
      const evidence = evidenceDialog(page);
      const service = serviceDialog(page);
      await expect(evidence.locator("ol li")).toHaveCount(1);
      await expect(evidence).toContainText("Archived allocation evidence");
      const sourceUrl = page.url();
      const action = evidence.getByRole("button", {
        name: label("services_exit_action"),
        exact: true,
      });
      await action.click();
      await expect(
        page.getByRole("option", { name: label("services_exit_reclaim"), exact: true })
      ).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(evidence).toBeVisible();
      await expect(action).toBeFocused();
      const note = evidence.getByLabel(label("services_exit_evidence_note"), { exact: true });
      await note.fill("Unsaved audit evidence must survive the service visit.");
      await evidence
        .getByLabel(label("services_exit_observed_ip"), { exact: true })
        .fill(boundExit.ip_address);
      await evidence.getByRole("checkbox").check();
      await evidence.getByRole("link", { name: currentService.service.id, exact: true }).click();
      await expect(service).toBeVisible();
      await expect(evidence).not.toBeVisible();
      await expectFocusInside(service);
      await service
        .getByRole("button", { name: label("services_view_history"), exact: true })
        .click();
      const orders = page.getByRole("dialog", {
        name: label("services_order_history"),
        exact: true,
      });
      await expect(orders.getByText(label("services_no_orders"), { exact: true })).toBeVisible();
      await expectFocusInside(orders);
      await page.keyboard.press("Shift+Tab");
      await expectFocusInside(orders);
      await page.keyboard.press("Tab");
      await expectFocusInside(orders);
      await page.keyboard.press("Escape");
      await expect(orders).not.toBeVisible();
      await expect(service).toBeVisible();
      await expectFocusInside(service);
      await page.keyboard.press("Escape");
      await expect(page).toHaveURL(sourceUrl);
      await expect(note).toHaveValue("Unsaved audit evidence must survive the service visit.");
      await expect(evidence.getByRole("checkbox")).toBeChecked();
      await expectFocusInside(evidence);
      await expect(evidence.locator("ol li")).toHaveCount(1);
      await expectNoOverflow(page, evidence);
      await evidence.screenshot({ path: info.outputPath("evidence-return.png") });

      await evidence.getByRole("link", { name: currentService.service.id, exact: true }).click();
      const serviceUrl = page.url();
      await service
        .getByRole("button", { name: label("console_manage_customer"), exact: true })
        .click();
      await expect(page.locator(".admin-user-hero")).toContainText(customerId);
      await page.reload();
      await page.getByRole("button", { name: label("user_back"), exact: true }).click();
      await expect(page).toHaveURL(serviceUrl);
      await expectFocusInside(service);
      await page.keyboard.press("Escape");
      await expect(page).toHaveURL(sourceUrl);
      await expect(evidence.locator("ol li")).toHaveCount(1);
      await page.reload();
      await expect(evidence).toContainText("Archived allocation evidence");
      await expectFocusInside(evidence);
      await page.keyboard.press("Escape");
      await expect(evidence).not.toBeVisible();
      await expect(page).toHaveURL(
        (url) => url.searchParams.get("exits_page") === "1" && !url.searchParams.has("exit_id")
      );
      await expect(
        page
          .locator(`[data-exit-id="${boundExit.id}"]`)
          .getByRole("button", { name: label("services_exit_evidence"), exact: true })
      ).toBeFocused();
      await expectReadOnly(page);
    });

    test("historical allocation opens an archived service with no fabricated customer", async ({
      page,
      context,
    }, info) => {
      await page.goto(`${evidenceUrl}&exit_audit_page=1`);
      const evidence = evidenceDialog(page);
      const sourceUrl = page.url();
      const historical = evidence
        .locator("ol")
        .getByRole("link", { name: archivedService.service.id, exact: true });
      const href = (await historical.getAttribute("href"))!;
      const popup = context.waitForEvent("page");
      await historical.click({ modifiers: ["ControlOrMeta"] });
      const tab = await popup;
      await tab.setViewportSize({ width, height: 1000 });
      await expect(tab).toHaveURL(href);
      await expect(
        serviceDialog(tab).getByRole("heading", {
          name: archivedService.service.name,
          level: 3,
          exact: true,
        })
      ).toBeVisible();
      await expect(
        serviceDialog(tab).getByRole("button", {
          name: label("console_manage_customer"),
          exact: true,
        })
      ).toHaveCount(0);
      await tab.reload();
      await expect(
        serviceDialog(tab).getByRole("heading", {
          name: archivedService.service.name,
          level: 3,
          exact: true,
        })
      ).toBeVisible();
      await expectFocusInside(serviceDialog(tab));
      await tab.keyboard.press("Escape");
      await expect(tab).toHaveURL(sourceUrl);
      await expect(evidenceDialog(tab)).toContainText("Archived allocation evidence");
      await expectReadOnly(tab);
      await tab.close();

      await historical.click();
      const service = serviceDialog(page);
      await expect(
        service.getByRole("heading", { name: archivedService.service.name, level: 3, exact: true })
      ).toBeVisible();
      await expect(service.locator(".admin-entity-link.is-person")).toHaveCount(0);
      for (const key of [
        "console_manage_customer",
        "services_manage",
        "services_revoke",
        "services_deliver",
        "services_activate",
      ])
        await expect(service.getByRole("button", { name: label(key), exact: true })).toHaveCount(0);
      await expect(service.getByRole("alert")).toHaveCount(0);
      await service.screenshot({ path: info.outputPath("archived-service.png") });
      await expectNoOverflow(page, service);
      await page.reload();
      await expect(
        service.getByRole("heading", { name: archivedService.service.name, level: 3, exact: true })
      ).toBeVisible();
      await page.goBack();
      await expect(page).toHaveURL(sourceUrl);
      await expect(evidence.locator("ol li")).toHaveCount(1);
      await expect(historical).toBeVisible();
      await expectReadOnly(page);
    });

    for (const lateFailure of [false, true]) {
      test(`late audit ${lateFailure ? "failure" : "success"} cannot overwrite the restored page`, async ({
        page,
      }) => {
        await page.goto(evidenceUrl);
        const evidence = evidenceDialog(page);
        await expect(evidence.locator("ol li")).toHaveCount(10);
        const sourceUrl = page.url();
        await page.evaluate(() => (window.__dedicatedExitHarness.holdNextAudit = true));
        await evidence.getByRole("button", { name: label("services_next"), exact: true }).click();
        await expect(page).toHaveURL(/exit_audit_page=1/);
        await expect(evidence.getByRole("status")).toHaveText(label("loading"));
        await expect(evidence.locator("ol li")).toHaveCount(0);
        await expect(
          evidence.getByText(label("services_exit_no_evidence"), { exact: true })
        ).toHaveCount(0);
        await expect(evidence.locator(".admin-pagination-summary")).toContainText(
          `${label("services_exit_audit")} 11`
        );
        await page.goBack();
        await expect(page).toHaveURL(sourceUrl);
        await expect(evidence.locator("ol li")).toHaveCount(10);
        expect(
          await page.evaluate(() =>
            window.__dedicatedExitHarness.calls.some(
              (call) =>
                call.path.includes("/audit?") && call.path.includes("offset=10") && call.aborted
            )
          )
        ).toBe(true);
        await page.evaluate(async (fail) => {
          window.__dedicatedExitHarness.releaseAudit(fail);
          await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
        }, lateFailure);
        await expect.poll(() => page.evaluate(() => window.__dedicatedExitHarness.settled)).toBe(1);
        await expect(evidence.locator("ol li")).toHaveCount(10);
        await expect(evidence).not.toContainText("Archived allocation evidence");
        await expect(evidence.getByRole("alert")).toHaveCount(0);
        await expect(page).toHaveURL(sourceUrl);
        await expectReadOnly(page);
      });
    }

    test("audit loading and failed reads retain truthful totals and allow retry", async ({
      page,
    }) => {
      await page.goto(`${baseUrl}&exits_page=1`);
      await expect(page.locator(".exits tbody tr")).toHaveCount(1);
      await page.evaluate(() => (window.__dedicatedExitHarness.holdNextAudit = true));
      await page
        .locator(".exits")
        .getByRole("button", { name: label("services_exit_evidence"), exact: true })
        .click();
      const evidence = evidenceDialog(page);
      await expect(evidence.getByRole("status")).toHaveText(label("loading"));
      await expect(evidence.locator(".admin-pagination-summary")).toHaveCount(0);
      await expect(
        evidence.getByText(label("services_exit_no_evidence"), { exact: true })
      ).toHaveCount(0);
      await page.evaluate(() => window.__dedicatedExitHarness.releaseAudit());
      await expect(evidence.locator("ol li")).toHaveCount(10);
      await page.evaluate(() => (window.__dedicatedExitHarness.failNextAudit = true));
      await evidence.getByRole("button", { name: label("services_next"), exact: true }).click();
      await expect(evidence.getByRole("alert")).toHaveText(label("services_request_failed"));
      await expect(evidence.locator("ol li")).toHaveCount(0);
      await expect(evidence.locator(".admin-pagination-summary")).toContainText(
        `${label("services_exit_audit")} 11`
      );
      await expect(
        evidence.getByText(label("services_exit_no_evidence"), { exact: true })
      ).toHaveCount(0);
      await evidence.getByRole("button", { name: label("refresh"), exact: true }).click();
      await expect(evidence.locator("ol li")).toHaveCount(1);
      await expect(evidence).toContainText("Archived allocation evidence");
      await expectReadOnly(page);
    });

    test("out-of-range pages recover without a history loop and missing exits stay explicit", async ({
      page,
    }) => {
      await page.goto(baseUrl);
      await expect(page.locator(".exits tbody tr")).toHaveCount(25);
      const sourceUrl = page.url();
      await page.goto(`${baseUrl}&exits_page=999&exit_id=${boundExit.id}&exit_audit_page=999`);
      const evidence = evidenceDialog(page);
      await expect(evidence.locator("ol li")).toHaveCount(1);
      await expect(page).toHaveURL(
        (url) =>
          url.searchParams.get("exits_page") === "1" &&
          url.searchParams.get("exit_audit_page") === "1"
      );
      await page.goBack();
      await expect(page).toHaveURL(sourceUrl);
      await expect(page.locator(".exits tbody tr")).toHaveCount(25);
      await page.goto(`${baseUrl}&exits_page=1&exit_id=missing-exit`);
      await expect(page.getByRole("alert")).toHaveText(label("services_exit_unavailable"));
      await expect(evidence).toHaveCount(0);
      await expect(page.locator(".exits tbody tr")).toHaveCount(1);
      await page.getByRole("button", { name: label("close"), exact: true }).click();
      await expect(page.getByRole("alert")).toHaveCount(0);
      await expect(page).toHaveURL(
        (url) => url.searchParams.get("exits_page") === "1" && !url.searchParams.has("exit_id")
      );
      await expect(page.locator(".exits")).toBeFocused();
      await expectReadOnly(page);
    });
  });
}
