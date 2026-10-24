import { readFileSync } from "node:fs";
import type { Page } from "@playwright/test";
import type { components } from "../../src/lib/api/openapi.generated";
import { consoleNodeServiceFixture } from "../../src/lib/admin/consoleNodesFixtures";
import {
  diagnosticsFixture,
  operationFixture,
} from "../../src/lib/admin/consoleServiceOperationsFixtures";
import {
  createConsoleServiceOperationsDemo,
  type ConsoleServiceOperationsDemoState,
} from "../../src/lib/webapp/mockApi/consoleServiceOperations";
import { resolveLocaleKey } from "../../src/lib/webapp/constants";

export type OperationsLanguage = "en" | "ru" | "zh-hans";
export function operationLabels(language: OperationsLanguage) {
  const locale: Record<string, string> = JSON.parse(
    readFileSync(`../locales/${language}.json`, "utf8")
  );
  return (key: string) => {
    const text = locale[resolveLocaleKey(`admin_${key}`)];
    if (!text) throw new Error(`Missing ${language} translation: ${key}`);
    return text;
  };
}
type BridgeReply = { handled: false } | { handled: true; value: unknown };
declare global {
  interface Window {
    __consoleOperationsRequest: (
      path: string,
      method: string,
      body: string | null
    ) => Promise<BridgeReply>;
  }
}
export async function installOperationsFixture(
  page: Page,
  language: OperationsLanguage,
  options: {
    lostReply?: boolean;
    holdFirstPreflight?: boolean;
    archived?: boolean;
    banned?: boolean;
  } = {}
) {
  const service: components["schemas"]["UserServiceOut"] = {
    ...consoleNodeServiceFixture.service,
    user_id: options.archived ? null : 910001,
    plan_id: "1".repeat(32),
    revision: 3,
    name: "Operations fixture",
    status: options.banned ? "account_banned" : "paused",
    desired_status: "paused",
    sync_pending: true,
  };
  const state: ConsoleServiceOperationsDemoState = {
    owner: 910001,
    banned: options.banned,
    services: [service],
    archived: [],
    exits: [
      {
        id: "3".repeat(32),
        label: "Operations exit",
        revision: 1,
        ip_address: "192.0.2.30",
        resource_pool: "operations",
        squad_uuid: "22222222-2222-4222-8222-222222222222",
        service_id: null,
        hold_order_id: null,
        hold_service_id: null,
        verified_at: null,
        enabled: true,
      },
    ],
    plans: [
      {
        id: "1".repeat(32),
        revision: 1,
        enabled: true,
        updated_at: diagnosticsFixture.local_observed_at,
        terms: { ...consoleNodeServiceFixture.terms, name: "Operations plan 1" },
      },
      {
        id: "2".repeat(32),
        revision: 1,
        enabled: true,
        updated_at: diagnosticsFixture.local_observed_at,
        terms: {
          ...consoleNodeServiceFixture.terms,
          name: "Operations plan 2",
          resource_type: "dedicated",
          squad_uuids: [],
          resource_pool: "operations",
        },
      },
    ],
    operations: Array.from({ length: 27 }, (_, index) => ({
      ...operationFixture,
      id: index ? index.toString(16).padStart(32, "0") : operationFixture.id,
      status: index === 0 ? "failed" : index % 2 ? "unknown" : "superseded",
      retryable: index === 0 && !options.archived && !options.banned,
      retry_block_reason: index
        ? "historical_result_unknown"
        : options.banned
          ? "account_banned"
          : options.archived
            ? "service_not_editable"
            : null,
      attempt_count: index ? null : 1,
      attempted_at: index ? null : operationFixture.attempted_at,
      first_failed_at: index ? null : operationFixture.first_failed_at,
    })),
  };
  const customer: components["schemas"]["ConsoleCustomerOut"] = {
    ...consoleNodeServiceFixture.customer,
    user_id: service.user_id,
    minishop_id: service.user_id === null ? null : "ms_100000000000400080000000000de2b1",
    is_banned: options.archived ? null : Boolean(options.banned),
  };
  const adapter = createConsoleServiceOperationsDemo();
  const calls: { path: string; method: string; body: unknown }[] = [];
  const errors: string[] = [];
  const http: string[] = [];
  let release: (() => void) | undefined;
  let held = false;
  let lost = false;
  let unavailable = false;
  let unsafe = false;
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith("/api/")) {
      http.push(url.pathname);
      return route.abort();
    }
    return ["127.0.0.1", "localhost"].includes(url.hostname) ? route.continue() : route.abort();
  });
  await page.exposeFunction(
    "__consoleOperationsRequest",
    async (path: string, method: string, rawBody: string | null): Promise<BridgeReply> => {
      const url = new URL(path, "https://fixture.invalid");
      const body: unknown = rawBody ? JSON.parse(rawBody) : null;
      calls.push({ path, method, body });
      const response = (value: unknown): BridgeReply => ({ handled: true, value });
      if (url.pathname === "/admin/console/services")
        return response({
          ok: true,
          services: [{ service, customer }],
          total: 1,
          page: 0,
          page_size: 25,
          observed_at: diagnosticsFixture.local_observed_at,
          expiring_within_days: 7,
        });
      if (url.pathname === `/admin/console/services/${service.id}`)
        return response({
          ok: true,
          service,
          customer,
          terms: state.plans[0].terms,
          connection: null,
        });
      if (url.pathname === "/admin/services" && method === "GET")
        return response({ ok: true, services: [service], total: 1 });
      if (url.pathname === "/admin/service-plans")
        return response({ ok: true, plans: state.plans, total: state.plans.length });
      if (url.pathname === "/admin/dedicated-exits")
        return response({ ok: true, exits: state.exits, total: state.exits.length });
      if (url.pathname.endsWith("/resources"))
        return response({
          ok: true,
          service_id: service.id,
          status: service.status,
          connection_state: service.connection_state,
          currently_eligible: false,
          configured_group_ids: [],
          groups: [],
          nodes: [],
          hosts: [],
          coverage: "unavailable",
          sources: [],
          local_observed_at: diagnosticsFixture.local_observed_at,
          remote_authorization_verified: false,
          association_basis: "persisted_service_scope_not_live_connections",
        } satisfies components["schemas"]["ConsoleServiceResourcesOut"] & { ok: true });
      if (url.pathname.endsWith("/diagnostics")) {
        if (unavailable) throw new Error("observation unavailable");
        return response({
          ok: true,
          ...diagnosticsFixture,
          user_id: service.user_id,
          service_revision: service.revision,
          status: service.status,
          next_steps: unsafe ? ["private-next-step"] : diagnosticsFixture.next_steps,
          remote: {
            ...diagnosticsFixture.remote,
            error: unsafe ? "private-token" : diagnosticsFixture.remote.error,
          },
        });
      }
      if (
        url.pathname === "/admin/console/service-preflight" &&
        options.holdFirstPreflight &&
        !held
      ) {
        held = true;
        const result = adapter(path, { method, body: rawBody }, state);
        await new Promise<void>((resolve) => {
          release = resolve;
        });
        return response(result);
      }
      const result = adapter(path, { method, body: rawBody }, state);
      if (result !== undefined) {
        if (url.pathname.endsWith("/retry") && options.lostReply && !lost) {
          lost = true;
          service.revision++;
          if (state.operations?.[0]) state.operations[0].retryable = false;
          throw new Error("reply lost after acceptance");
        }
        return response(result);
      }
      return { handled: false };
    }
  );
  await page.addInitScript(
    ({ language }) => {
      localStorage.setItem("rw_minishop_demo_language", language);
      type Props = { api: (path: string, options?: RequestInit) => Promise<unknown> };
      type Bundle = { mount: (target: HTMLElement, props: Props) => unknown };
      let bundle: Bundle | undefined;
      Object.defineProperty(window, "SubscriptionWebAppAdmin", {
        configurable: true,
        get: () => bundle,
        set(value: Bundle) {
          const mount = value.mount.bind(value);
          value.mount = (target, props) =>
            mount(target, {
              ...props,
              api: async (path, options = {}) => {
                const result = await window.__consoleOperationsRequest(
                  path,
                  options.method || "GET",
                  typeof options.body === "string" ? options.body : null
                );
                return result.handled ? result.value : props.api(path, options);
              },
            });
          bundle = value;
        },
      });
    },
    { language }
  );
  return {
    state,
    service,
    calls,
    errors,
    http,
    releasePreflight: () => release?.(),
    failReads: () => {
      unavailable = true;
    },
    unsafeCodes: () => {
      unsafe = true;
    },
  };
}
