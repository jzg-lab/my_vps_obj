import { readFileSync } from "node:fs";
import { expect, type Locator, type Page, type TestInfo } from "@playwright/test";
import { createApiClient, unwrap } from "../../src/lib/webapp/publicApi";
import { resolveLocaleKey } from "../../src/lib/webapp/constants";
import {
  consoleNodeDetailFixture,
  consoleNodeServiceFixture,
} from "../../src/lib/admin/consoleNodesFixtures";
import {
  readResourceOperation,
  type ResourceOperation,
} from "../../src/lib/admin/resourceOperations";
import {
  consoleResourceOperationsDemoResponse,
  resetResourceOperationsDemo,
  seedResourceOperationDemo,
} from "../../src/lib/webapp/mockApi/consoleResourceOperations";
import { consoleResourceCatalogFixture } from "../../src/lib/webapp/mockApi/consoleResourcePreview";

export type Language = "en" | "ru" | "zh-hans";
export const query = "?mock=services&theme_preview=dark";
const endpoint = "/__uc3_resources_fixture/";
export const labels = (language: Language) => {
  const locale: Record<string, string> = JSON.parse(
    readFileSync(`../locales/${language}.json`, "utf8")
  );
  return (key: string) => {
    const value = locale[resolveLocaleKey(`admin_${key}`)];
    if (!value) throw new Error(`Missing ${language}: ${key}`);
    return value;
  };
};
export async function installResources(page: Page, language: Language) {
  resetResourceOperationsDemo();
  const client = createApiClient({ mockApi: consoleResourceOperationsDemoResponse });
  const catalog = consoleResourceCatalogFixture();
  const longName =
    language === "zh-hans"
      ? "跨地区研发与远程协作组完整名称ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
      : language === "ru"
        ? "Межрегиональная исследовательская группа ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        : "International research and collaboration group ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
  catalog.groups.forEach((group) => {
    group.name = longName;
  });
  catalog.profiles[0].name = longName;
  catalog.profiles[0].inbounds[0].tag = `${longName} vless-main`;
  const trace = {
    calls: [] as { path: string; method: string; body: Record<string, unknown> }[],
    errors: [] as string[],
    unexpected: [] as string[],
    fail: "" as "" | "reject" | "after" | "evidence" | "retry",
    drift: false,
    available: true,
  };
  const row = async () => {
    const list = unwrap(await client.api("/admin/console/resources/operations"));
    if (!list.items[0]) throw new Error("No operation in the fixture");
    return list.items[0];
  };
  page.on("pageerror", (error) => trace.errors.push(error.message));
  await page.context().route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname !== endpoint) {
      if (url.pathname.startsWith("/api/")) {
        trace.unexpected.push(url.pathname);
        return route.abort();
      }
      return ["127.0.0.1", "localhost"].includes(url.hostname) ? route.continue() : route.abort();
    }
    const path = url.searchParams.get("path")!;
    const method = request.method();
    const body: Record<string, unknown> = JSON.parse(request.postData() || "{}");
    trace.calls.push({ path, method, body });
    const reply = (value: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(value) });
    if (path === "/admin/console/resources/catalog")
      return reply({ ok: true, ...catalog, execution_available: trace.available });
    if (
      path === "/admin/console/resources/operations" &&
      method === "POST" &&
      trace.fail === "reject"
    ) {
      trace.fail = "";
      return reply({ ok: false, error: "invalid_resource_operation_request", status: 400 }, 400);
    }
    if (path.endsWith("/evidence") && trace.fail === "evidence") {
      trace.fail = "";
      return reply({ ok: false, error: "resource_evidence_invalid", status: 409 }, 409);
    }
    if (path.endsWith("/retry") && trace.fail === "retry")
      return reply({ ok: false, error: "private_upstream_credential" }, 503);
    const response = consoleResourceOperationsDemoResponse(path, {
      method,
      body: request.postData() ?? undefined,
    });
    if (
      path === "/admin/console/resources/operations" &&
      method === "POST" &&
      trace.fail === "after"
    ) {
      trace.fail = "";
      return reply({ ok: false, error: "private_response_lost" }, 503);
    }
    if (response && typeof response === "object" && "ok" in response && response.ok) {
      if ("execution_available" in response) response.execution_available = trace.available;
      if ("preview" in response && response.preview && typeof response.preview === "object") {
        Object.assign(response.preview, { execution_available: trace.available });
        if (trace.drift) {
          Object.assign(response, { valid: false, reason: "changed" });
          Object.assign(response.preview, { fingerprint: "e".repeat(64) });
        }
      }
    }
    return reply(response ?? { ok: false, error: "fixture_unmatched" });
  });
  await page.addInitScript(
    ({ language, endpoint, nodeDetail, service }) => {
      localStorage.setItem("rw_minishop_demo_language", language);
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
              api: async (path, options = {}) => {
                const pathname = path.split("?")[0];
                if (pathname === "/admin/me")
                  return { ok: true, user_id: 910001, admin_ids: [910001] };
                if (pathname === `/admin/console/services/${service.service.id}`)
                  return { ok: true, ...service };
                if (
                  pathname.startsWith("/admin/console/nodes/") &&
                  pathname !== "/admin/console/nodes/onboarding/deployment"
                )
                  return {
                    ok: true,
                    ...nodeDetail,
                    node: {
                      ...nodeDetail.node,
                      id: pathname.split("/").at(-1),
                      status: "online",
                      is_disabled: false,
                    },
                  };
                if (
                  !pathname.startsWith("/admin/console/resources/") &&
                  pathname !== "/admin/console/nodes/onboarding/deployment"
                )
                  return props.api(path, options);
                const response = await fetch(
                  `${endpoint}?path=${encodeURIComponent(path)}`,
                  options
                );
                const payload: unknown = await response.json();
                if (response.status >= 500)
                  throw Object.assign(new Error("resource_request_uncertain"), {
                    status: response.status,
                  });
                return payload;
              },
            });
          bundle = value;
        },
      });
    },
    { language, endpoint, nodeDetail: consoleNodeDetailFixture, service: consoleNodeServiceFixture }
  );
  return {
    catalog,
    longName,
    trace,
    row,
    writes: () =>
      trace.calls.filter(
        (call) => call.method === "POST" && !/\/(preview|revalidate)$/.test(call.path)
      ),
    seed: seedResourceOperationDemo,
    read: (id: string) => readResourceOperation(client.api, id),
    finish: () => {
      expect(trace.errors).toEqual([]);
      expect(trace.unexpected).toEqual([]);
    },
  };
}
export type ResourceHarness = Awaited<ReturnType<typeof installResources>>;

export async function choose(
  page: Page,
  host: Locator,
  name: string,
  option: string,
  info?: TestInfo,
  keyboard = false
) {
  const trigger = host.getByRole("button", { name, exact: true });
  await trigger.focus();
  await trigger.press("ArrowDown");
  const menu = page.locator('.admin-select-content[data-state="open"]');
  const item = page.getByRole("option", { name: option, exact: true });
  await expect(item).toBeVisible();
  await expect(trigger).toBeFocused();
  await expect
    .poll(() =>
      menu.evaluate((node) => {
        const id = document.activeElement?.getAttribute("aria-activedescendant");
        const active = id ? document.getElementById(id) : null;
        return (
          active !== null &&
          node.contains(active) &&
          active.matches('[role="option"][data-highlighted]')
        );
      })
    )
    .toBe(true);
  expect(
    await menu.evaluate((node) => {
      const box = node.getBoundingClientRect();
      return (
        box.left >= 0 && box.right <= innerWidth + 1 && node.scrollWidth <= node.clientWidth + 2
      );
    })
  ).toBe(true);
  if (info)
    await page.screenshot({ path: info.outputPath("open-menu.png"), animations: "disabled" });
  if (keyboard) {
    const target = await item.getAttribute("id");
    for (
      let index = 0;
      index < 12 && (await trigger.getAttribute("aria-activedescendant")) !== target;
      index++
    )
      await trigger.press("ArrowDown");
    await expect(trigger).toHaveAttribute("aria-activedescendant", target!);
    await trigger.press("Enter");
  } else await item.click();
  await expect(menu).toHaveCount(0);
}

export async function capture(page: Page, host: Locator, info: TestInfo, name: string) {
  await expect(host).toBeVisible();
  const overflow = await host.evaluate((root) =>
    [
      root,
      ...root.querySelectorAll<HTMLElement>(
        ".dialog-card, .dialog-body-scroll > .scroll-area__viewport, form, .admin-field, .admin-select-trigger"
      ),
    ]
      .filter((node) => node.getBoundingClientRect().width > 0)
      .filter((node) => node.scrollWidth > node.clientWidth + 2)
      .map((node) => ({
        tag: node.tagName,
        class: node.className,
        width: node.clientWidth,
        scroll: node.scrollWidth,
      }))
  );
  // Dialog scrollbars intentionally occupy the 12px gutter outside their root; inspect the viewport instead.
  expect(overflow).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)).toBe(
    true
  );
  if ((await host.getAttribute("role")) === "dialog") {
    await page.keyboard.press("Tab");
    await expect
      .poll(() => host.evaluate((node) => node.contains(document.activeElement)))
      .toBe(true);
  }
  await host.screenshot({ path: info.outputPath(`${name}.png`), animations: "disabled" });
}

export function observed(
  operation: ResourceOperation,
  status: "unknown" | "succeeded" | "failed",
  result: "before" | "after" = "after"
): ResourceOperation {
  const target = operation.target_id ?? "60000000-0000-0000-0000-000000000001";
  return {
    ...operation,
    status,
    version: operation.version + 1,
    gate_active: status === "unknown",
    completed_at: status === "unknown" ? null : new Date().toISOString(),
    error_code:
      status === "failed"
        ? "resource_write_rejected"
        : status === "unknown"
          ? "resource_write_unknown"
          : null,
    can_retry: status === "failed",
    requires_manual_reconciliation: status === "unknown",
    target_id:
      operation.change.operation.endsWith("_create") && status === "unknown" ? null : target,
    attempts: [
      {
        number: 1,
        receipt: status === "unknown" ? "unknown" : status === "failed" ? "rejected" : "accepted",
        started_at: "2026-10-23T00:00:00Z",
      },
    ],
    observation: {
      observed_at: "2026-10-23T01:00:00Z",
      configuration: result === "after" ? "matched" : "different",
      values:
        result === "after"
          ? { ...operation.preview.proposed!, id: target }
          : operation.preview.current,
      runtime: "unverified",
      restart: "not_requested",
      correlation: operation.change.operation.endsWith("_create")
        ? "creation_marker"
        : "known_uuid",
    },
  };
}

export async function evidenceTime(dialog: Locator) {
  for (const [part, value] of [
    ["year", "2026"],
    ["month", "10"],
    ["day", "23"],
    ["hour", "01"],
    ["minute", "00"],
  ]) {
    const segment = dialog.locator(`.resource-evidence [data-segment="${part}"]`);
    await segment.focus();
    await segment.pressSequentially(value);
    await expect.poll(async () => Number(await segment.textContent())).toBe(Number(value));
  }
}
