import { readFileSync } from "node:fs";
import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";
import type { components } from "../src/lib/api/openapi.generated";
import { resolveLocaleKey } from "../src/lib/webapp/constants";

type Consumer = "detail" | "customer";
type Mode = "normal" | "banned" | "lost-reply" | "archived";
type Call = { path: string; method: string; body: unknown };
type Harness = { calls: Call[]; applied: number; releaseWrite: (() => void) | null };
declare global {
  interface Window {
    __consoleServiceActions: Harness;
  }
}

const serviceId = "c".repeat(32);
const otherId = "d".repeat(32);
const createdId = "e".repeat(32);
const userId = 910001;
const customerKey = "ms_100000000000400080000000000de2b1";
const query = "?mock=services&theme_preview=dark";
const detailUrl = `/demo/runtime/admin/services${query}&q=Fixture&service_id=${serviceId}`;
const customerUrl = `/demo/runtime/admin/users/${userId}${query}`;
const languages = ["en", "ru", "zh-hans"] as const;
type Language = (typeof languages)[number];
function labels(language: Language) {
  const locale: Record<string, string> = JSON.parse(
    readFileSync(`../locales/${language}.json`, "utf8")
  );
  return (key: string) => {
    const value = locale[resolveLocaleKey(`admin_${key}`)];
    if (!value) throw new Error(`Missing ${language} translation: ${key}`);
    return value;
  };
}

async function installFixture(page: Page, language: Language, mode: Mode = "normal") {
  const errors: string[] = [];
  const unexpectedHttp: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/*", (route) => {
    const request = new URL(route.request().url());
    if (request.pathname.startsWith("/api/")) {
      unexpectedHttp.push(request.pathname);
      return route.abort();
    }
    return ["127.0.0.1", "localhost"].includes(request.hostname) ? route.continue() : route.abort();
  });
  await page.addInitScript(
    ({ language, mode, serviceId, otherId, createdId, userId, customerKey }) => {
      localStorage.setItem("rw_minishop_demo_language", language);
      const trace: Harness = { calls: [], applied: 0, releaseWrite: null };
      window.__consoleServiceActions = trace;
      type Props = { api: (path: string, options?: RequestInit) => Promise<unknown> };
      type Bundle = { mount: (target: HTMLElement, props: Props) => unknown };
      const time = "2026-10-24T01:00:00Z";
      const customer: components["schemas"]["ConsoleCustomerOut"] = {
        user_id: mode === "archived" ? null : userId,
        minishop_id: mode === "archived" ? null : customerKey,
        username: mode === "archived" ? null : "fixture_customer",
        first_name: mode === "archived" ? null : "Fixture",
        last_name: mode === "archived" ? null : "Customer",
        email: null,
        is_banned: mode === "archived" ? null : mode === "banned",
      };
      const terms: components["schemas"]["ServicePlanTerms"] = {
        name: "Fixture original terms",
        description: "Fixture retained terms",
        resource_type: "shared",
        traffic_rule: "total",
        quota_bytes: 1073741824,
        validity_days: 30,
        price: "19.90",
        currency: "CNY",
        squad_uuids: ["22222222-2222-4222-8222-222222222222"],
        resource_pool: null,
      };
      let current: components["schemas"]["UserServiceOut"] = {
        id: serviceId,
        user_id: customer.user_id,
        plan_id: "fixture-plan",
        plan_revision: 1,
        revision: 1,
        name: "Fixture service",
        description: "",
        resource_type: "shared",
        traffic_rule: "total",
        quota_bytes: 1073741824,
        used_bytes: 40,
        usage_total_bytes: 40,
        usage_error: null,
        starts_at: time,
        expires_at: "2026-11-24T01:00:00Z",
        cycle_started_at: null,
        cycle_ends_at: null,
        cycle_pending: false,
        last_usage_sync_at: time,
        status: mode === "banned" ? "account_banned" : "pending",
        desired_status: mode === "banned" ? "paused" : "active",
        connection_state: "pending",
        sync_pending: false,
        sync_error: null,
        sync_confirmed_at: time,
        exit_ip: null,
        exit_verified: false,
        replacement_order_id: null,
      };
      const other = { ...current, id: otherId, name: "Fixture untouched service" };
      let created: typeof current | null = null;
      const plan: components["schemas"]["ServicePlanOut"] = {
        id: current.plan_id,
        revision: 1,
        enabled: true,
        updated_at: time,
        terms,
      };
      const order: components["schemas"]["ServiceOrderOut"] = {
        id: "fixture-activation-order",
        service_id: serviceId,
        user_id: customer.user_id,
        actor_id: userId,
        kind: "activate",
        created_at: time,
        snapshot: {
          terms,
          plan_revision: 1,
          starts_at: time,
          expires_at: current.expires_at,
        },
      };
      const applied = new Set<string>();
      let held = false;
      let lost = false;
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
                const request = new URL(path, "https://fixture.test");
                const pathname = request.pathname;
                const method = options?.method || "GET";
                const body: unknown =
                  typeof options?.body === "string" ? JSON.parse(options.body) : null;
                trace.calls.push({ path, method, body });
                const services =
                  mode === "archived" ? [current] : [current, other, ...(created ? [created] : [])];
                if (method === "GET" && pathname === "/admin/services") {
                  const visible =
                    mode !== "archived" || request.searchParams.get("deleted") === "true"
                      ? services
                      : [];
                  return { ok: true, services: visible, total: visible.length };
                }
                if (pathname === "/admin/console/services")
                  return {
                    ok: true,
                    services:
                      mode === "archived" ? [] : services.map((service) => ({ service, customer })),
                    total: mode === "archived" ? 0 : services.length,
                    page: 0,
                    page_size: 25,
                    observed_at: time,
                    expiring_within_days: 7,
                  };
                if (pathname === `/admin/console/services/${serviceId}`) {
                  const detail: components["schemas"]["ConsoleServiceDetailOut"] = {
                    service: current,
                    customer,
                    terms,
                    connection: null,
                  };
                  return { ok: true, ...detail };
                }
                if (pathname === `/admin/console/services/${serviceId}/resources`)
                  return {
                    ok: true,
                    service_id: serviceId,
                    status: current.status,
                    connection_state: current.connection_state,
                    currently_eligible: false,
                    configured_group_ids: terms.squad_uuids ?? [],
                    groups: [],
                    nodes: [],
                    hosts: [],
                    association_basis: "persisted_service_scope_not_live_connections",
                    remote_authorization_verified: false,
                    coverage: "complete",
                    sources: [],
                    local_observed_at: time,
                  } satisfies components["schemas"]["ConsoleServiceResourcesOut"] & { ok: true };
                if (pathname === "/admin/service-orders")
                  return { ok: true, orders: [order], total: 1 };
                if (pathname === "/admin/service-plans")
                  return { ok: true, plans: [plan], total: 1 };
                if (pathname === "/admin/dedicated-exits") return { ok: true, exits: [], total: 0 };
                if (pathname === "/admin/console/service-preflight" && method === "POST")
                  return {
                    ok: true,
                    user_id: userId,
                    plan_id: plan.id,
                    plan_revision: plan.revision,
                    exit_id: null,
                    exit_revision: null,
                    terms,
                    allow_pending_creation: !customer.is_banned,
                    resource_readiness: "unknown",
                    ready_for_delivery: false,
                    checks: [],
                    configured_group_ids: terms.squad_uuids ?? [],
                    nodes: [],
                    hosts: [],
                    sources: [],
                    local_observed_at: time,
                  } satisfies components["schemas"]["ConsoleServicePreflightOut"] & { ok: true };
                if (method === "POST") {
                  if (mode === "archived")
                    throw new Error("Archived service must remain read only");
                  if (
                    !body ||
                    typeof body !== "object" ||
                    !("user_id" in body) ||
                    body.user_id !== userId ||
                    !("idempotency_key" in body) ||
                    typeof body.idempotency_key !== "string"
                  )
                    throw new Error("Unexpected fixture write owner or missing idempotency key");
                  const previous = structuredClone(current);
                  if (pathname === "/admin/services") {
                    if (customer.is_banned) return { ok: false, error: "account_banned" };
                    created ??= { ...other, id: createdId, name: "Fixture newly created service" };
                    return { ok: true, service: created, duplicate: false };
                  }
                  const kind = pathname.split("/").at(-1);
                  if (
                    pathname !== `/admin/services/${serviceId}/${kind}` ||
                    !["changes", "deliver", "revoke"].includes(kind || "")
                  )
                    throw new Error(`Unexpected fixture write: ${pathname}`);
                  const change = "change" in body ? body.change : null;
                  const action =
                    change && typeof change === "object" && "action" in change
                      ? change.action
                      : kind;
                  if (customer.is_banned && action === "resume")
                    return { ok: false, error: "account_banned" };
                  if (!applied.has(body.idempotency_key)) {
                    applied.add(body.idempotency_key);
                    trace.applied++;
                    current = {
                      ...current,
                      revision: current.revision + 1,
                      used_bytes: 73,
                      usage_total_bytes: 73,
                      status:
                        action === "revoke"
                          ? "cancelled"
                          : action === "pause"
                            ? "paused"
                            : "active",
                      desired_status:
                        action === "revoke"
                          ? "cancelled"
                          : action === "pause"
                            ? "paused"
                            : "active",
                      connection_state: "ready",
                      sync_pending: true,
                    };
                    if (action === "renew") current.expires_at = "2026-12-24T01:00:00Z";
                  }
                  if (kind === "changes" && mode === "lost-reply" && !lost) {
                    lost = true;
                    throw new Error("Fixture response lost after persisting the change");
                  }
                  if (kind === "changes" && mode === "normal" && !held) {
                    held = true;
                    await new Promise<void>((resolve) => {
                      trace.releaseWrite = resolve;
                    });
                    trace.releaseWrite = null;
                  }
                  // The GET contains the authoritative result; the POST snapshot is deliberately stale.
                  return { ok: true, service: previous, duplicate: false };
                }
                const result = await props.api(path, options);
                if (
                  pathname.startsWith("/admin/users/") &&
                  result &&
                  typeof result === "object" &&
                  "user" in result &&
                  result.user &&
                  typeof result.user === "object"
                )
                  return { ...result, user: { ...result.user, is_banned: customer.is_banned } };
                return result;
              },
            });
          bundle = value;
        },
      });
    },
    { language, mode, serviceId, otherId, createdId, userId, customerKey }
  );
  return { errors, unexpectedHttp };
}

async function openConsumer(page: Page, consumer: Consumer, label: (key: string) => string) {
  await page.goto(consumer === "detail" ? detailUrl : customerUrl);
  const host =
    consumer === "detail"
      ? page.getByRole("dialog", { name: label("console_service_detail"), exact: true })
      : page.locator(".user-services");
  const actions =
    consumer === "detail" ? host : host.locator("tbody tr").filter({ hasText: serviceId });
  await expect(actions).toContainText("Fixture service");
  if (consumer === "customer")
    await expect(page).toHaveURL(
      (url) => url.pathname === `/demo/runtime/admin/users/${customerKey}`
    );
  return { host, actions };
}

async function assertPortal(page: Page, dialog: Locator, info: TestInfo, name: string) {
  await expect(dialog).toBeVisible();
  expect(
    await dialog.evaluate((node) => node.parentElement?.closest(".dialog, .admin-table-wrap"))
  ).toBeNull();
  await expect
    .poll(() => dialog.evaluate((node) => node.contains(document.activeElement)))
    .toBe(true);
  expect(
    await dialog.locator(".dialog-card").evaluate((node) => node.scrollWidth - node.clientWidth)
  ).toBeLessThanOrEqual(2);
  const box = await dialog.locator(".dialog-card").boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(page.viewportSize()!.width + 1);
  await dialog.screenshot({ path: info.outputPath(`${name}.png`), animations: "disabled" });
}

async function choose(page: Page, dialog: Locator, label: string, value: string) {
  await dialog.getByRole("button", { name: label, exact: true }).click();
  const option = page.getByRole("option", { name: value, exact: true });
  await expect(option).toBeVisible();
  await expect
    .poll(() =>
      option.evaluate((node) => {
        const box = node.getBoundingClientRect();
        return node.contains(
          document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2)
        );
      })
    )
    .toBe(true);
  await option.click();
  await expect(page.locator(".admin-select-content")).toHaveCount(0);
}

async function calls(page: Page) {
  return page.evaluate(() => window.__consoleServiceActions.calls);
}

for (const width of [1440, 390]) {
  for (const consumer of ["detail", "customer"] as const) {
    for (const language of languages) {
      test(`${consumer} retains nullable archived identity and history at ${width}px in ${language}`, async ({
        page,
      }, info) => {
        const label = labels(language);
        await page.setViewportSize({ width, height: 1000 });
        const evidence = await installFixture(page, language, "archived");
        await page.goto(
          consumer === "detail" ? detailUrl : `/demo/runtime/admin/service-history${query}`
        );
        const host =
          consumer === "detail"
            ? page.getByRole("dialog", { name: label("console_service_detail"), exact: true })
            : page.getByRole("region", { name: label("services_history_title"), exact: true });
        await expect(host).toContainText("Fixture service");
        await expect(host).toContainText(label("services_history_hint"));
        if (consumer === "detail") {
          await expect(host).toContainText(label("user_deleted"));
          await expect(host).toContainText(label("services_history_title"));
          await expect(host.locator("button.admin-entity-link.is-person")).toHaveCount(0);
          await expect(
            host.getByRole("region", { name: label("console_terms_snapshot") })
          ).toContainText("19.90 CNY");
        }
        for (const key of [
          "services_activate",
          "services_manage",
          "services_revoke",
          "services_deliver",
          "console_manage_customer",
        ])
          await expect(host.getByRole("button", { name: label(key), exact: true })).toHaveCount(0);
        await expect(host).not.toContainText("Fixture Customer");
        const beforeUrl = page.url();
        await host
          .getByRole("button", { name: label("services_view_history"), exact: true })
          .click();
        const history = page.getByRole("dialog", {
          name: label("services_order_history"),
          exact: true,
        });
        await expect(history).toContainText("19.90 CNY");
        await assertPortal(page, history, info, "archived-history");
        await page.keyboard.press("Escape");
        await expect(history).toHaveCount(0);
        await expect(host).toBeVisible();
        await expect(page).toHaveURL(beforeUrl);
        await host
          .getByRole("button", { name: label("refresh"), exact: true })
          .first()
          .click();
        await expect(host).toContainText("Fixture service");
        const requests = await calls(page);
        expect(requests.filter((call) => call.method !== "GET")).toEqual([]);
        expect(
          requests.some((call) => /(?:user_id=0(?:&|$)|\/users\/0(?:\?|$))/.test(call.path))
        ).toBe(false);
        if (consumer === "customer")
          expect(
            requests.some((call) => call.path.startsWith("/admin/services?deleted=true"))
          ).toBe(true);
        expect(
          await page.evaluate(() => document.body.scrollWidth - innerWidth)
        ).toBeLessThanOrEqual(2);
        await host.screenshot({
          path: info.outputPath("archived-service.png"),
          animations: "disabled",
        });
        expect(evidence).toEqual({ errors: [], unexpectedHttp: [] });
      });

      test(`${consumer} shared lifecycle and authoritative refresh at ${width}px in ${language}`, async ({
        page,
      }, info) => {
        const label = labels(language);
        await page.setViewportSize({ width, height: 1000 });
        const evidence = await installFixture(page, language);
        const { host, actions } = await openConsumer(page, consumer, label);
        const beforeUrl = page.url();
        const other = page.locator(".user-services tbody tr").filter({ hasText: otherId });
        const otherBefore = consumer === "customer" ? await other.innerText() : "";
        if (consumer === "detail") {
          const terms = host.getByRole("region", { name: label("console_terms_snapshot") });
          await expect(terms).toContainText("Fixture original terms");
          await expect(terms).toContainText("19.90 CNY");
        }
        await actions
          .getByRole("button", { name: label("services_view_history"), exact: true })
          .click();
        const history = page.getByRole("dialog", {
          name: label("services_order_history"),
          exact: true,
        });
        await expect(history).toContainText("19.90 CNY");
        await assertPortal(page, history, info, "history");
        await page.keyboard.press("Escape");
        await expect(history).toHaveCount(0);
        await expect(host).toBeVisible();
        await expect(page).toHaveURL(beforeUrl);

        await actions.getByRole("button", { name: label("services_deliver"), exact: true }).click();
        const delivery = page.getByRole("dialog", { name: label("services_deliver"), exact: true });
        const deliver = delivery.getByRole("button", {
          name: label("services_deliver"),
          exact: true,
        });
        await expect(deliver).toBeDisabled();
        await delivery.getByRole("checkbox").check();
        await assertPortal(page, delivery, info, "delivery");
        await deliver.click();
        await expect(delivery).toHaveCount(0);
        await expect(actions).toContainText("73 B / 1 GiB");
        await expect(actions).toContainText(label("services_sync_pending"));

        await actions.getByRole("button", { name: label("services_manage"), exact: true }).click();
        const change = page.getByRole("dialog", { name: label("services_manage"), exact: true });
        const trigger = change.getByRole("button", { name: label("services_action"), exact: true });
        await trigger.focus();
        await trigger.press("Enter");
        await expect(
          page.getByRole("option", { name: label("services_pause"), exact: true })
        ).toBeVisible();
        await page.screenshot({ path: info.outputPath("change-menu.png"), animations: "disabled" });
        await page.keyboard.press("Escape");
        await expect(page.locator(".admin-select-content")).toHaveCount(0);
        await expect(trigger).toBeFocused();
        await expect(change).toBeVisible();
        await expect(host).toBeVisible();
        await choose(page, change, label("services_action"), label("services_pause"));
        await assertPortal(page, change, info, "change");
        await change.getByRole("button", { name: label("save"), exact: true }).click();
        await expect
          .poll(() => page.evaluate(() => Boolean(window.__consoleServiceActions.releaseWrite)))
          .toBe(true);
        await expect(
          change.getByRole("button", { name: label("save"), exact: true })
        ).toBeDisabled();
        await change
          .locator("form")
          .evaluate((form) =>
            form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }))
          );
        await page.keyboard.press("Escape");
        await expect(change).toBeVisible();
        expect(
          (await calls(page)).filter(
            (call) => call.method === "POST" && call.path.endsWith("/changes")
          )
        ).toHaveLength(1);
        await page.evaluate(() => window.__consoleServiceActions.releaseWrite?.());
        await expect(change).toHaveCount(0);
        await expect(actions).toContainText(label("services_status_paused"));
        const requests = await calls(page);
        const writeIndex = requests.findIndex(
          (call) => call.method === "POST" && call.path.endsWith("/changes")
        );
        expect(
          requests
            .slice(writeIndex + 1)
            .some(
              (call) =>
                call.method === "GET" &&
                (consumer === "detail"
                  ? call.path === `/admin/console/services/${serviceId}`
                  : call.path.startsWith("/admin/services?"))
            )
        ).toBe(true);

        for (const action of ["resume", "renew"] as const) {
          await actions
            .getByRole("button", { name: label("services_manage"), exact: true })
            .click();
          await choose(page, change, label("services_action"), label(`services_${action}`));
          if (action === "renew") {
            await change.getByLabel(label("services_renew_days"), { exact: true }).fill("30");
            await change.getByLabel(label("services_recorded_price"), { exact: true }).fill("9.90");
          }
          await change.getByRole("button", { name: label("save"), exact: true }).click();
          await expect(change).toHaveCount(0);
          await expect(actions).toContainText("73 B / 1 GiB");
        }
        await expect(actions).toContainText("2026-12-24 09:00");
        if (consumer === "customer") expect(await other.innerText()).toBe(otherBefore);
        else
          await expect(
            host.getByRole("region", { name: label("console_terms_snapshot") })
          ).toContainText("19.90 CNY");

        await actions.getByRole("button", { name: label("services_revoke"), exact: true }).click();
        const revoke = page.getByRole("dialog", { name: label("services_revoke"), exact: true });
        await expect(
          revoke.getByRole("button", { name: label("services_revoke"), exact: true })
        ).toBeDisabled();
        await revoke
          .getByLabel(label("services_revoke_reason"), { exact: true })
          .fill("Fixture cancellation evidence");
        await revoke.getByRole("checkbox").check();
        await assertPortal(page, revoke, info, "revoke");
        await revoke.getByRole("button", { name: label("services_revoke"), exact: true }).click();
        await expect(revoke).toHaveCount(0);
        await expect(actions).toContainText(label("services_status_cancelled"));
        await expect(actions).toContainText(label("services_sync_pending"));
        await expect(
          actions.getByRole("button", { name: label("services_revoke"), exact: true })
        ).toHaveCount(0);
        await expect(page).toHaveURL(beforeUrl);

        await host.getByRole("button", { name: label("services_activate"), exact: true }).click();
        const activation = page.getByRole("dialog", {
          name: label("services_activate"),
          exact: true,
        });
        const plan = activation.getByRole("button", {
          name: label("services_choose_plan"),
          exact: true,
        });
        await expect(plan).toBeEnabled();
        await plan.click();
        await expect(
          page.getByRole("option", { name: "Fixture original terms", exact: true })
        ).toBeVisible();
        await page.keyboard.press("Escape");
        await expect(plan).toBeFocused();
        await expect(activation).toBeVisible();
        await choose(page, activation, label("services_choose_plan"), "Fixture original terms");
        await assertPortal(page, activation, info, "activation");
        await activation
          .getByRole("button", { name: label("services_activate"), exact: true })
          .click();
        await expect(activation).toHaveCount(0);
        await expect(
          page.locator(".user-services tbody tr").filter({ hasText: createdId })
        ).toBeVisible();
        await expect(
          page.locator(".user-services tbody tr").filter({ hasText: serviceId })
        ).toContainText(label("services_status_cancelled"));
        if (consumer === "detail") {
          await page.getByRole("button", { name: label("user_back"), exact: true }).click();
          await expect(page).toHaveURL(beforeUrl);
          await expect(host).toContainText(label("services_status_cancelled"));
          await page.keyboard.press("Escape");
          await expect(host).toHaveCount(0);
          await expect(
            page
              .locator(".console-services")
              .getByRole("textbox", { name: label("console_search") })
          ).toHaveValue("Fixture");
        }
        expect(
          await page.evaluate(() => document.body.scrollWidth - innerWidth)
        ).toBeLessThanOrEqual(2);
        expect(
          await page.evaluate(() =>
            JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage)])
          )
        ).not.toContain("subscription.example");
        expect(evidence).toEqual({ errors: [], unexpectedHttp: [] });
      });
    }

    test(`${consumer} preserves a lost-response intent at ${width}px`, async ({ page }) => {
      const label = labels("zh-hans");
      await page.setViewportSize({ width, height: 1000 });
      const evidence = await installFixture(page, "zh-hans", "lost-reply");
      const { actions } = await openConsumer(page, consumer, label);
      await actions.getByRole("button", { name: label("services_manage"), exact: true }).click();
      const dialog = page.getByRole("dialog", { name: label("services_manage"), exact: true });
      await choose(page, dialog, label("services_action"), label("services_pause"));
      await dialog.getByRole("button", { name: label("save"), exact: true }).click();
      await expect(dialog.getByRole("alert")).toHaveText(label("services_request_failed"));
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      await expect(actions).toContainText(label("services_status_paused"));
      await actions.getByRole("button", { name: label("services_manage"), exact: true }).click();
      await expect(dialog).toContainText(label("services_change_pending_request"));
      await expect(
        dialog.getByRole("button", { name: label("services_action"), exact: true })
      ).toBeDisabled();
      await dialog.getByRole("button", { name: label("save"), exact: true }).click();
      await expect(dialog).toHaveCount(0);
      const writes = (await calls(page)).filter((call) => call.method === "POST");
      expect(writes).toHaveLength(2);
      expect(writes[0]).toEqual(writes[1]);
      expect(await page.evaluate(() => window.__consoleServiceActions.applied)).toBe(1);
      await expect(actions).toContainText("73 B / 1 GiB");
      expect(evidence).toEqual({ errors: [], unexpectedHttp: [] });
    });

    test(`${consumer} respects account ban and rejected resume at ${width}px`, async ({ page }) => {
      const label = labels("zh-hans");
      await page.setViewportSize({ width, height: 1000 });
      const evidence = await installFixture(page, "zh-hans", "banned");
      const { host, actions } = await openConsumer(page, consumer, label);
      await expect(
        host.getByRole("button", { name: label("services_activate"), exact: true })
      ).toBeDisabled();
      await expect(
        actions.getByRole("button", { name: label("services_deliver"), exact: true })
      ).toHaveCount(0);
      await expect(
        actions.getByRole("button", { name: label("services_view_history"), exact: true })
      ).toBeEnabled();
      await expect(
        actions.getByRole("button", { name: label("services_revoke"), exact: true })
      ).toBeEnabled();
      await actions.getByRole("button", { name: label("services_manage"), exact: true }).click();
      const dialog = page.getByRole("dialog", { name: label("services_manage"), exact: true });
      await choose(page, dialog, label("services_action"), label("services_resume"));
      await dialog.getByRole("button", { name: label("save"), exact: true }).click();
      await expect(dialog.getByRole("alert")).toHaveText(label("services_account_banned"));
      await expect(dialog.getByRole("button", { name: label("save"), exact: true })).toBeDisabled();
      await expect
        .poll(() => dialog.evaluate((node) => node.contains(document.activeElement)))
        .toBe(true);
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      await expect(actions).toContainText(label("services_status_account_banned"));
      expect(await page.evaluate(() => window.__consoleServiceActions.applied)).toBe(0);
      expect(evidence).toEqual({ errors: [], unexpectedHttp: [] });
    });
  }
}
