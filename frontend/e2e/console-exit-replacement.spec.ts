import { readFileSync } from "node:fs";
import { isIP } from "node:net";
import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";
import { replacementFixture } from "../src/lib/admin/exitReplacementFixtures";
import {
  createExitReplacementDemo,
  type ReplacementDemoState,
} from "../src/lib/webapp/mockApi/exitReplacement";
import { resolveLocaleKey } from "../src/lib/webapp/constants";
import type { components } from "../src/lib/api/openapi.generated";
import { checkReplacementBounds, checkReplacementImpacts } from "./exit-replacement-impact";

type Consumer = "detail" | "customer";
type Mode = "draft" | "active" | "unknown" | "failed" | "archived" | "partial" | "conflict";
type Call = { path: string; method: string; body: Record<string, unknown> };
type Failure = "before" | "after" | "503" | null;
for (const language of ["en", "zh-hans"] as const) {
  const locale: Record<string, string> = JSON.parse(
    readFileSync(`../locales/${language}.json`, "utf8")
  );
  const label = (key: string) => locale[resolveLocaleKey(`admin_${key}`)];
  const query = "?mock=services&theme_preview=dark";
  const endpoint = "/__uc2_replacement_fixture/";

  async function install(page: Page, mode: Mode = "draft", localeName: string = language) {
    const fixture = replacementFixture();
    const { detail, affected, old, candidate, held, draft } = fixture;
    const service = detail.service;
    affected.service.name =
      language === "zh-hans"
        ? "跨地区研发与远程协作团队长期独立服务完整名称及连续标识ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        : "International research and remote collaboration service with a deliberately long continuous identifier ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    draft.impacts![0].service_name = affected.service.name;
    const base = `/admin/console/services/${service.id}`;
    const affectedBase = `/admin/console/services/${affected.service.id}`;
    const controller = createExitReplacementDemo();
    const otherPool = {
      ...candidate,
      id: "9".repeat(32),
      label: "Wrong pool fixture",
      resource_pool: "other-pool",
    };
    const model: ReplacementDemoState = {
      services: [service, affected.service],
      archived: [],
      exits: [old, candidate, held, otherPool],
      audits: [],
      topology: draft,
    };
    if (mode === "partial") {
      draft.coverage = "partial";
      draft.block_reasons = ["exit_replacement_sources_incomplete"];
    }
    if (mode === "conflict") {
      draft.impacts![0].kind = "direct_authorization";
      draft.impacts![0].group_ids = [old.squad_uuid];
      draft.block_reasons = ["exit_replacement_authorization_conflict"];
      draft.allowed_to_start = false;
    }
    if (["active", "unknown", "failed", "archived"].includes(mode)) {
      const replacement = fixture.state.replacement!;
      service.replacement_order_id = replacement.operation.order_id;
      Object.assign(candidate, replacement.candidate_exit, { hold_service_id: service.id });
      controller.replacements.set(replacement.operation.id, replacement);
      controller.operations.push(replacement.operation);
      if (mode === "unknown") {
        replacement.progress.pending_action = "stop_old";
        replacement.operation.status = "unknown";
      }
      if (mode === "failed") {
        service.desired_status = "paused";
        replacement.operation.status = "failed";
      }
      if (mode === "archived") {
        service.user_id = null;
        detail.customer = {
          user_id: null,
          minishop_id: null,
          username: null,
          email: null,
          first_name: null,
          last_name: null,
          is_banned: null,
        };
        model.services = [];
        model.archived = [service];
      }
    }
    const trace = {
      calls: [] as Call[],
      errors: [] as string[],
      unexpectedHttp: [] as string[],
      hold: false,
      release: null as (() => void) | null,
      fail: null as Failure,
      drift: null as "version" | "fingerprint" | null,
    };
    const row = () => {
      const current = [...controller.replacements.values()].at(-1);
      if (!current) throw new Error("Expected fixture replacement");
      return current;
    };
    page.on("pageerror", (error) => trace.errors.push(error.message));
    await page.context().route("**/*", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.pathname !== endpoint) {
        if (url.pathname.startsWith("/api/")) {
          trace.unexpectedHttp.push(url.pathname);
          return route.abort();
        }
        return ["127.0.0.1", "localhost"].includes(url.hostname) ? route.continue() : route.abort();
      }
      const path = url.searchParams.get("path")!;
      const method = request.method();
      const body: Record<string, unknown> = JSON.parse(request.postData() || "{}");
      trace.calls.push({ path, method, body });
      const pathname = path.split("?")[0];
      const reply = (response: unknown, status = 200) =>
        route.fulfill({ status, contentType: "application/json", body: JSON.stringify(response) });
      if (method === "GET") {
        if ([`${base}/traffic`, `${affectedBase}/traffic`].includes(pathname))
          return reply({
            ok: true,
            service_id: pathname.split("/").at(-2)!,
            start_date: "2026-10-18",
            end_date: "2026-10-24",
            timezone: "UTC",
            availability: "unavailable",
            days: [],
            nodes: [],
            source: "panel_service_identity_raw_traffic_not_billing",
            history_completeness: "unknown",
          } satisfies components["schemas"]["ConsoleServiceTrafficOut"] & { ok: true });
        if (pathname === "/admin/services") {
          const owner = new URL(path, url.origin).searchParams.get("user_id");
          const services = model.services.filter((item) => String(item.user_id) === owner);
          return reply({ ok: true, services, total: services.length });
        }
        if (pathname === "/admin/console/services")
          return reply({
            ok: true,
            services: [detail, affected].map(({ service, customer }) => ({ service, customer })),
            total: 2,
            page: 0,
            page_size: 25,
            observed_at: draft.observed_at,
            expiring_within_days: 7,
          });
        if (pathname === base) return reply({ ok: true, ...detail });
        if (pathname === affectedBase) return reply({ ok: true, ...affected });
        if ([`${base}/resources`, `${affectedBase}/resources`].includes(pathname))
          return reply({
            ok: true,
            service_id: pathname === `${base}/resources` ? service.id : affected.service.id,
            status: service.status,
            connection_state: service.connection_state,
            currently_eligible: false,
            configured_group_ids: detail.terms.squad_uuids ?? [],
            groups: [],
            nodes: [],
            hosts: [],
            association_basis: "persisted_service_scope_not_live_connections",
            remote_authorization_verified: false,
            coverage: "complete",
            sources: [],
            local_observed_at: draft.observed_at,
          } satisfies components["schemas"]["ConsoleServiceResourcesOut"] & { ok: true });
        if (pathname === "/admin/dedicated-exits")
          return reply({ ok: true, exits: model.exits, total: model.exits.length });
        if (pathname === "/admin/service-orders") return reply({ ok: true, orders: [], total: 0 });
        if (pathname === "/admin/service-plans") return reply({ ok: true, plans: [], total: 0 });
        if (trace.drift && pathname === `${base}/exit-replacement`) {
          if (trace.drift === "version") row().progress.version++;
          else draft.resource_fingerprint = "9".repeat(64);
          trace.drift = null;
        }
      }
      if (method === "POST") {
        if (trace.hold) {
          trace.hold = false;
          await new Promise<void>((resolve) => {
            trace.release = resolve;
          });
          trace.release = null;
        }
        const failure = trace.fail;
        trace.fail = null;
        if (failure === "before") return route.abort("failed");
        if (failure === "503")
          return reply({ ok: false, error: "exit_replacement_sources_incomplete" }, 503);
        if (
          pathname.endsWith("/verify") &&
          (typeof body.observed_ip !== "string" || !isIP(body.observed_ip))
        )
          return reply({ ok: false, error: "invalid_exit_evidence" }, 400);
        const response = controller.respond(path, { method, body: JSON.stringify(body) }, model);
        if (response?.ok && pathname === `${base}/exit-replacement`) {
          // This historical fixture predates the explicitly entered observation records.
          row().operation.created_at = draft.observed_at;
          if ("replacement" in response && response.replacement)
            response.replacement.operation.created_at = draft.observed_at;
        }
        if (failure === "after") return route.abort("failed");
        if (!response) throw new Error(`Unexpected fixture write: ${path}`);
        return reply(response, response.ok ? 200 : 409);
      }
      const response = controller.respond(path, { method }, model);
      if (!response) throw new Error(`Unexpected fixture read: ${path}`);
      return reply(response, response.ok ? 200 : 409);
    });
    await page.context().addInitScript(
      ({ endpoint, base, affectedBase, localeName }) => {
        localStorage.setItem("rw_minishop_demo_language", localeName);
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
                  const pathname = path.split("?")[0];
                  if (
                    ![
                      "/admin/services",
                      "/admin/console/services",
                      "/admin/dedicated-exits",
                      "/admin/service-orders",
                      "/admin/service-plans",
                    ].includes(pathname) &&
                    !pathname.startsWith(base) &&
                    !pathname.startsWith(affectedBase) &&
                    !pathname.startsWith("/admin/dedicated-exits/")
                  )
                    return props.api(path, options);
                  const response = await fetch(
                    `${endpoint}?path=${encodeURIComponent(path)}`,
                    options
                  );
                  const payload: unknown = await response.json();
                  if (response.status >= 500)
                    throw Object.assign(new Error("service_unavailable"), {
                      status: response.status,
                      payload,
                    });
                  return payload;
                },
              });
            bundle = value;
          },
        });
      },
      { endpoint, base, affectedBase, localeName }
    );
    const writes = () => trace.calls.filter((call) => call.method === "POST");
    const finish = () => {
      expect(trace.errors).toEqual([]);
      expect(trace.unexpectedHttp).toEqual([]);
    };
    return { ...fixture, trace, model, row, writes, finish, base };
  }

  type Harness = Awaited<ReturnType<typeof install>>;
  async function open(page: Page, fixture: Harness, consumer: Consumer = "detail") {
    await page.goto(
      consumer === "detail"
        ? `/demo/runtime/admin/services${query}&q=Replacement&service_id=${fixture.detail.service.id}`
        : `/demo/runtime/admin/users/910002${query}`
    );
    if (consumer === "customer") await page.locator(".user-services > details > summary").click();
    const host =
      consumer === "detail"
        ? page.getByRole("dialog", { name: label("console_service_detail"), exact: true })
        : page.locator(".user-services tbody tr").filter({ hasText: fixture.detail.service.id });
    await expect(host).toContainText("Replacement fixture");
    const trigger = host.getByRole("button", { name: label("replacement_title"), exact: true });
    await trigger.focus();
    await trigger.press("Enter");
    const dialog = page.getByRole("dialog", { name: label("replacement_title"), exact: true });
    await ready(dialog);
    return { dialog, trigger, host };
  }
  async function ready(dialog: Locator) {
    await expect(dialog).toBeVisible();
    await expect(dialog.locator(".exit-replacement")).toHaveAttribute("aria-busy", "false");
  }
  async function screenshot(page: Page, dialog: Locator, info: TestInfo, name: string) {
    await ready(dialog);
    await checkReplacementBounds(dialog);
    for (const key of ["Tab", "Shift+Tab"]) {
      await page.keyboard.press(key);
      await expect
        .poll(() => dialog.evaluate((node) => node.contains(document.activeElement)))
        .toBe(true);
    }
    await expect
      .poll(() => dialog.evaluate((node) => node.contains(document.activeElement)))
      .toBe(true);
    expect(
      await dialog.evaluate((node) => node.parentElement?.closest(".dialog, .admin-table-wrap"))
    ).toBeNull();
    const card = dialog.locator(".dialog-card");
    expect(await card.evaluate((node) => node.scrollWidth - node.clientWidth)).toBeLessThanOrEqual(
      2
    );
    const box = await card.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(page.viewportSize()!.width + 1);
    await dialog.screenshot({ path: info.outputPath(`${name}.png`), animations: "disabled" });
  }
  async function choose(
    page: Page,
    dialog: Locator,
    name: string,
    option: string,
    info?: TestInfo,
    keyboard = false
  ) {
    const trigger = dialog.getByRole("button", { name, exact: true });
    await trigger.focus();
    await trigger.press(keyboard ? "ArrowDown" : "Enter");
    const item = page.getByRole("option", { name: option, exact: true });
    await expect(item).toBeVisible();
    const openMenu = page.locator('.admin-select-content[data-state="open"]');
    await expect(openMenu).toHaveCount(1);
    const menu = page.locator(`[id="${await openMenu.getAttribute("id")}"]`);
    await expect(trigger).toBeFocused();
    await expect(trigger).toHaveAttribute("aria-expanded", "true");
    await expect
      .poll(() =>
        menu.evaluate((node) => {
          const id = document.activeElement?.getAttribute("aria-activedescendant");
          const active = id ? document.getElementById(id) : null;
          return (
            active !== null &&
            node.contains(active) &&
            active.matches('[role="option"][data-highlighted]:not([data-disabled])')
          );
        })
      )
      .toBe(true);
    expect(
      await menu.evaluate((node) => {
        const box = node.getBoundingClientRect();
        return (
          box.left >= 0 &&
          box.right <= document.documentElement.clientWidth + 1 &&
          node.scrollWidth - node.clientWidth <= 2
        );
      })
    ).toBe(true);
    if (info)
      await page.screenshot({ path: info.outputPath("open-menu.png"), animations: "disabled" });
    if (keyboard) {
      await expect(trigger).toHaveAttribute(
        "aria-activedescendant",
        (await item.getAttribute("id"))!
      );
      await trigger.press("Enter");
    } else await item.click();
    await expect(menu).toHaveCount(0);
    await ready(dialog);
  }
  const action = (page: Page, dialog: Locator, value: string, info?: TestInfo) =>
    choose(page, dialog, label("services_exit_action"), label(`replacement_action_${value}`), info);
  async function date(dialog: Locator, name: string, minute = "00") {
    const field = dialog
      .locator(".date-input")
      .filter({ has: dialog.page().getByRole("button", { name, exact: true }) });
    for (const [part, value] of [
      ["year", "2026"],
      ["month", "10"],
      ["day", "23"],
      ["hour", "01"],
      ["minute", minute],
    ]) {
      const segment = field.locator(`[data-segment="${part}"]`);
      await segment.focus();
      await expect(segment).toBeFocused();
      await segment.pressSequentially(value);
      await expect.poll(async () => Number(await segment.textContent())).toBe(Number(value));
    }
  }
  async function evidence(dialog: Locator, metering = false, minute = "00") {
    await date(dialog, label("services_exit_checked_at"), minute);
    const digest = dialog.getByLabel(label("replacement_digest"), { exact: true });
    await expect(digest).toHaveAttribute("pattern", "[0-9a-f]{64}");
    await digest.fill("6".repeat(64));
    if (metering) {
      await date(dialog, label("replacement_usage_at"), "01");
      for (const [key, value] of [
        ["total", "73"],
        ["raw", "23"],
        ["offset", "50"],
      ])
        await dialog.getByLabel(label(`replacement_usage_${key}`), { exact: true }).fill(value);
      const usageDigest = dialog.getByLabel(label("replacement_usage_digest"), { exact: true });
      await expect(usageDigest).toHaveAttribute("pattern", "[0-9a-f]{64}");
      await usageDigest.fill("7".repeat(64));
    }
    for (const checkbox of await dialog
      .locator("form.replacement-evidence")
      .getByRole("checkbox")
      .all())
      await checkbox.check();
  }
  async function submit(dialog: Locator, name: string, fixture: Harness) {
    const before = fixture.writes().length;
    await dialog
      .locator("form.replacement-evidence")
      .getByRole("button", { name: label(`replacement_action_${name}`), exact: true })
      .click();
    await expect.poll(() => fixture.writes().length).toBe(before + 1);
    await ready(dialog);
  }
  async function draft(page: Page, dialog: Locator, fixture: Harness, info?: TestInfo) {
    await choose(
      page,
      dialog,
      label("replacement_candidate"),
      `${fixture.candidate.label} · ${fixture.candidate.ip_address} · ${fixture.candidate.resource_pool}`,
      info,
      true
    );
    await expect(dialog).toContainText(label("console_resource_reload"));
    await dialog
      .getByLabel(label("replacement_reason"), { exact: true })
      .fill("Recorded exit fault");
  }
  async function start(dialog: Locator, fixture: Harness) {
    await dialog
      .getByRole("checkbox", { name: label("replacement_impact_confirm"), exact: true })
      .check();
    const before = fixture.writes().length;
    await dialog.getByRole("button", { name: label("replacement_start"), exact: true }).click();
    await expect.poll(() => fixture.writes().length).toBe(before + 1);
    await ready(dialog);
  }

  for (const width of [1440, 390]) {
    test.describe(`${language} ${width}px`, () => {
      test.use({ viewport: { width, height: 1000 }, timezoneId: "UTC" });
      for (const consumer of ["detail", "customer"] as const) {
        test(`${consumer}: reserve, stop, verify, confirm and explicitly reclaim old hold`, async ({
          page,
        }, info) => {
          const f = await install(page);
          const { dialog, trigger, host } = await open(page, f, consumer);
          await draft(page, dialog, f, info);
          await checkReplacementImpacts(page, dialog, info, "draft", f.draft.impacts!, label);
          expect(f.writes()).toHaveLength(0);
          await start(dialog, f);
          expect(f.writes()[0].body).toMatchObject({
            user_id: 910002,
            expected_revision: 4,
            old_exit_id: f.old.id,
            new_exit_id: f.candidate.id,
            expected_resource_fingerprint: f.draft.resource_fingerprint,
          });
          const operation = f.row().operation.id;
          await action(page, dialog, "stop_evidence");
          await evidence(dialog, true);
          await submit(dialog, "stop_evidence", f);
          expect(f.writes().at(-1)?.body).toMatchObject({
            operation_id: operation,
            purpose: "stop",
            usage_total_bytes: 73,
            usage_raw_bytes: 23,
            usage_lifetime_offset: 50,
            checked_at: "2026-10-23T01:00:00.000Z",
            usage_observed_at: "2026-10-23T01:01:00.000Z",
          });
          await action(page, dialog, "verify");
          await dialog
            .getByLabel(label("services_exit_observed_ip"), { exact: true })
            .fill(f.candidate.ip_address);
          await evidence(dialog);
          await submit(dialog, "verify", f);
          expect(f.writes().at(-1)?.path).toBe(`/admin/dedicated-exits/${f.candidate.id}/verify`);
          expect(f.writes().at(-1)?.body).toMatchObject({
            replacement_operation_id: operation,
            observed_ip: f.candidate.ip_address,
            evidence_digest: "6".repeat(64),
            fixed: true,
            exclusive: true,
          });
          expect(f.writes().at(-1)?.body).not.toHaveProperty("provenance");
          await action(page, dialog, "confirm");
          await checkReplacementImpacts(page, dialog, info, "confirm", f.row().impacts!, label);
          expect(f.writes()).toHaveLength(3);
          await dialog
            .getByRole("checkbox", { name: label("replacement_confirm_terms"), exact: true })
            .check();
          await screenshot(page, dialog, info, "confirm-original-entitlement");
          f.trace.hold = true;
          const form = dialog.locator("form.replacement-evidence");
          await form
            .getByRole("button", { name: label("replacement_action_confirm"), exact: true })
            .click();
          await expect.poll(() => f.trace.release !== null).toBe(true);
          const count = f.writes().length;
          await form.evaluate((node) =>
            node.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }))
          );
          await page.keyboard.press("Escape");
          await expect(dialog).toBeVisible();
          expect(f.writes()).toHaveLength(count);
          f.trace.release!();
          await ready(dialog);
          expect(f.writes().at(-1)?.body).toMatchObject({
            operation_id: operation,
            confirm_replace_and_request_restore: true,
            old_stop_audit_id: f.row().old_stop!.audit_id,
            candidate_verify_audit_id: f.row().candidate_verification!.audit_id,
          });
          await expect(dialog).toContainText(label("console_ops_accepted"));
          await expect(dialog).not.toContainText(label("replacement_switch_confirmed"));
          const terms = structuredClone(f.detail.terms);
          // Only this explicit runner fixture supplies binding/restoration outcomes.
          const completedAt = "2026-10-23T01:02:00.000Z";
          f.old.service_id = null;
          f.old.hold_order_id = f.row().operation.order_id;
          f.old.hold_service_id = f.detail.service.id;
          f.candidate.service_id = f.detail.service.id;
          f.candidate.hold_order_id = null;
          f.candidate.hold_service_id = null;
          Object.assign(f.detail.service, {
            desired_status: "paused",
            status: "paused",
            replacement_order_id: null,
            sync_pending: false,
            sync_error: null,
            sync_confirmed_at: completedAt,
            exit_ip: f.candidate.ip_address,
            exit_verified: true,
          });
          Object.assign(f.row().operation, {
            status: "succeeded",
            completed_at: completedAt,
            error_code: null,
          });
          f.row().gate_active = false;
          Object.assign(f.row().progress, {
            stage: "completed",
            pending_action: null,
            version: f.row().progress.version + 1,
            binding_audit_id: "8".repeat(32),
            restore_result: "restricted",
            restore_block_reasons: ["service_paused"],
          });
          await dialog.getByRole("button", { name: label("refresh"), exact: true }).click();
          await ready(dialog);
          const results = dialog.getByRole("region", { name: label("replacement_results") });
          const status = results
            .locator("dl > div")
            .filter({ has: page.getByText(label("status"), { exact: true }) })
            .locator("dd");
          await expect(status).toHaveText(
            `${label("console_ops_status_succeeded")} · ${label("replacement_stage_completed")}`
          );
          await expect(results).not.toContainText(label("console_ops_status_pending"));
          expect(f.row().gate_active).toBe(false);
          expect(f.row().operation).toMatchObject({
            status: "succeeded",
            completed_at: completedAt,
            error_code: null,
          });
          expect(f.detail.service).toMatchObject({
            desired_status: "paused",
            status: "paused",
            replacement_order_id: null,
            sync_pending: false,
          });
          for (const key of [
            "replacement_switch_confirmed",
            "replacement_restore_restricted",
            "replacement_old_held",
          ])
            await expect(dialog).toContainText(label(key));
          await expect(results).toContainText(label("services_status_paused"));
          await status.scrollIntoViewIfNeeded();
          await expect(status).toBeInViewport();
          await dialog.screenshot({
            path: info.outputPath("completed-restricted-restore.png"),
            animations: "disabled",
          });
          await action(page, dialog, "reclaim");
          await choose(
            page,
            dialog,
            label("replacement_reclaim_target"),
            `${f.old.label} · ${f.old.ip_address}`
          );
          await evidence(dialog, false, "03");
          await screenshot(page, dialog, info, "explicit-old-hold-reclaim");
          await submit(dialog, "reclaim", f);
          expect(f.writes().at(-1)?.body).toMatchObject({
            reclaim_purpose: "retained_old",
            replacement_operation_id: operation,
            checked_at: "2026-10-23T01:03:00.000Z",
          });
          expect(f.old.hold_order_id).toBeNull();
          expect(f.detail.terms).toEqual(terms);
          await expect(dialog).toContainText(label("replacement_old_released"));
          await page.keyboard.press("Escape");
          await expect(dialog).toHaveCount(0);
          await expect(trigger).toBeFocused();
          await expect(
            (consumer === "detail" ? host.locator(".service-visual") : host).getByText(
              label("services_status_paused"),
              { exact: true }
            )
          ).toBeVisible();
          await expect(
            host.getByRole("button", { name: label("services_manage"), exact: true })
          ).toBeEnabled();
          f.finish();
        });
      }

      test("400 evidence rejection preserves fields and permits corrected new request", async ({
        page,
      }, info) => {
        const f = await install(page, "active");
        const { dialog } = await open(page, f);
        await action(page, dialog, "verify", info);
        const ip = dialog.getByLabel(label("services_exit_observed_ip"), { exact: true });
        await ip.fill("invalid-ip");
        await evidence(dialog);
        const rejection = page.waitForResponse(
          (response) => new URL(response.url()).pathname === endpoint && response.status() === 400
        );
        await submit(dialog, "verify", f);
        await rejection;
        await expect(dialog).toContainText(label("replacement_invalid_evidence"));
        await expect(
          dialog.getByRole("button", { name: label("replacement_replay"), exact: true })
        ).toHaveCount(0);
        await expect(ip).toBeEditable();
        await expect(ip).toHaveValue("invalid-ip");
        await expect(dialog.getByLabel(label("replacement_digest"), { exact: true })).toHaveValue(
          "6".repeat(64)
        );
        await expect(
          dialog.getByRole("checkbox", { name: label("replacement_fixed"), exact: true })
        ).toBeChecked();
        const alert = dialog.getByRole("alert");
        await alert.scrollIntoViewIfNeeded();
        await expect(alert).toBeInViewport();
        await dialog.screenshot({
          path: info.outputPath("rejected-evidence.png"),
          animations: "disabled",
        });
        const first = f.writes()[0].body;
        await ip.fill(f.candidate.ip_address);
        await screenshot(page, dialog, info, "corrected-evidence");
        await submit(dialog, "verify", f);
        expect(f.writes()).toHaveLength(2);
        const second = f.writes()[1].body;
        expect(second.idempotency_key).not.toBe(first.idempotency_key);
        expect(second).toEqual({
          ...first,
          observed_ip: f.candidate.ip_address,
          idempotency_key: second.idempotency_key,
        });
        f.finish();
      });

      if (language === "zh-hans") return;

      test("direct authorization conflict remains visible and blocks start", async ({
        page,
      }, info) => {
        const f = await install(page, "conflict");
        const { dialog } = await open(page, f);
        await draft(page, dialog, f);
        await expect(dialog).toContainText(label("replacement_scope_conflict"));
        await expect(dialog).toContainText(label("console_resource_direct"));
        await expect(dialog).toContainText(f.affected.service.name);
        await expect(
          dialog.getByRole("button", { name: label("replacement_start"), exact: true })
        ).toBeDisabled();
        await dialog
          .locator("form.replacement-start")
          .evaluate((node) =>
            node.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }))
          );
        expect(f.writes()).toHaveLength(0);
        await screenshot(page, dialog, info, "authorization-conflict");
        f.finish();
      });

      test("unknown remote write requires reconciliation before same-operation retry", async ({
        page,
      }, info) => {
        const f = await install(page, "unknown");
        const { dialog } = await open(page, f);
        await dialog
          .getByRole("button", { name: label("services_exit_action"), exact: true })
          .click();
        await expect(page.getByRole("option")).toHaveCount(1);
        await expect(
          page.getByRole("option", { name: label("replacement_action_retry"), exact: true })
        ).toHaveCount(0);
        await page
          .getByRole("option", { name: label("replacement_action_resolve_write"), exact: true })
          .click();
        await evidence(dialog);
        await choose(
          page,
          dialog,
          label("replacement_write_result"),
          label("replacement_not_applied")
        );
        await screenshot(page, dialog, info, "unknown-manual-reconciliation");
        await submit(dialog, "resolve_write", f);
        const operation = f.row().operation.id;
        expect(f.writes()[0].body).toMatchObject({
          operation_id: operation,
          purpose: "resolve_write",
          action: "stop_old",
          attempt: 1,
          result: "not_applied",
          usage_total_bytes: null,
        });
        await action(page, dialog, "retry");
        await submit(dialog, "retry", f);
        expect(f.writes()[1].path).toBe(`${f.base}/operations/${operation}/retry`);
        expect(f.writes()).toHaveLength(2);
        f.finish();
      });

      test("failed candidate cleanup and closing proof retain hold until explicit reclaim", async ({
        page,
      }, info) => {
        const f = await install(page, "failed");
        const { dialog } = await open(page, f);
        await action(page, dialog, "candidate_cleanup");
        await evidence(dialog);
        await submit(dialog, "candidate_cleanup", f);
        expect(f.candidate.hold_order_id).toBe(f.row().operation.order_id);
        expect(f.model.audits[0].action).toBe("replace_cleanup");
        await action(page, dialog, "close_evidence");
        await evidence(dialog, true);
        await submit(dialog, "close_evidence", f);
        expect(f.model.audits[0].action).toBe("replace_close_stop");
        expect(f.candidate.hold_order_id).toBe(f.row().operation.order_id);
        await action(page, dialog, "reclaim");
        await choose(
          page,
          dialog,
          label("replacement_reclaim_target"),
          `${f.candidate.label} · ${f.candidate.ip_address}`
        );
        await evidence(dialog);
        await screenshot(page, dialog, info, "candidate-hold-before-release");
        await submit(dialog, "reclaim", f);
        expect(f.candidate.hold_order_id).toBeNull();
        expect(f.model.audits[0].action).toBe("replace_reclaim");
        expect(f.old.service_id).toBe(f.detail.service.id);
        expect(f.writes()).toHaveLength(3);
        f.finish();
      });

      for (const drift of ["version", "fingerprint"] as const) {
        test(`${drift} drift prevents writes and requires fresh evidence`, async ({ page }) => {
          const f = await install(page, "active");
          const { dialog } = await open(page, f);
          await action(page, dialog, "stop_evidence");
          await evidence(dialog, true);
          f.trace.drift = drift;
          await dialog
            .locator("form.replacement-evidence")
            .getByRole("button", { name: label("replacement_action_stop_evidence"), exact: true })
            .click();
          await expect(dialog).toContainText(label("replacement_changed"));
          await ready(dialog);
          expect(f.writes()).toHaveLength(0);
          await expect(dialog.getByLabel(label("replacement_digest"), { exact: true })).toHaveValue(
            ""
          );
          await dialog
            .locator("form.replacement-evidence")
            .evaluate((node) =>
              node.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }))
            );
          expect(f.writes()).toHaveLength(0);
          f.finish();
        });
      }

      for (const failure of ["before", "after", "503"] as const) {
        test(`${failure} reply uncertainty refreshes state without automatic re-post`, async ({
          page,
        }, info) => {
          const f = await install(page, "active");
          const { dialog } = await open(page, f);
          await action(page, dialog, "verify");
          await dialog
            .getByLabel(label("services_exit_observed_ip"), { exact: true })
            .fill(f.candidate.ip_address);
          await evidence(dialog);
          f.trace.fail = failure;
          await submit(dialog, "verify", f);
          await expect(dialog).toContainText(label("replacement_pending_request"));
          const first = f.writes()[0];
          const afterPost = f.trace.calls.slice(f.trace.calls.indexOf(first) + 1);
          expect(
            afterPost.some(
              (call) => call.method === "GET" && call.path.includes("exit-replacement")
            )
          ).toBe(true);
          expect(f.writes()).toHaveLength(1);
          await expect(
            dialog.getByLabel(label("services_exit_observed_ip"), { exact: true })
          ).toBeDisabled();
          await screenshot(page, dialog, info, `${failure}-reply`);
          if (failure === "after") {
            await expect(
              dialog.getByRole("button", { name: label("replacement_replay"), exact: true })
            ).toHaveCount(0);
            await dialog
              .getByRole("button", { name: label("replacement_use_latest"), exact: true })
              .click();
            await ready(dialog);
            expect(f.writes()).toHaveLength(1);
            await expect(dialog).toContainText(label("replacement_administrator_evidence"));
          } else {
            await dialog
              .getByRole("button", { name: label("replacement_replay"), exact: true })
              .click();
            await expect.poll(() => f.writes().length).toBe(2);
            await ready(dialog);
            expect(f.writes()[1]).toEqual(first);
          }
          f.finish();
        });
      }

      test("candidate menu filters held and wrong-pool exits; partial coverage blocks start", async ({
        page,
      }, info) => {
        const f = await install(page, "partial");
        const { dialog } = await open(page, f);
        const trigger = dialog.getByRole("button", {
          name: label("replacement_candidate"),
          exact: true,
        });
        await trigger.press("Enter");
        await expect(page.getByRole("option")).toHaveCount(1);
        await expect(page.getByRole("option", { name: /Held fixture|Wrong pool/ })).toHaveCount(0);
        await page.keyboard.press("Escape");
        await expect(dialog).toBeVisible();
        await expect(trigger).toBeFocused();
        await draft(page, dialog, f);
        await expect(dialog).toContainText(label("replacement_sources_incomplete"));
        await expect(
          dialog.getByRole("button", { name: label("replacement_start"), exact: true })
        ).toBeDisabled();
        await dialog
          .locator("form.replacement-start")
          .evaluate((node) =>
            node.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }))
          );
        expect(f.writes()).toHaveLength(0);
        await screenshot(page, dialog, info, "incomplete-coverage");
        f.finish();
      });

      test("archived replacement remains inspectable and read only", async ({ page }, info) => {
        const f = await install(page, "archived");
        const { dialog } = await open(page, f);
        await expect(dialog).toContainText(label("services_history_hint"));
        await expect(dialog.locator("form")).toHaveCount(0);
        await expect(
          dialog.getByRole("button", { name: label("services_exit_action"), exact: true })
        ).toHaveCount(0);
        await screenshot(page, dialog, info, "archived-replacement");
        expect(f.writes()).toHaveLength(0);
        expect(
          f.trace.calls.filter((call) => call.path.startsWith("/admin/dedicated-exits"))
        ).toHaveLength(0);
        f.finish();
      });
    });
  }
}
