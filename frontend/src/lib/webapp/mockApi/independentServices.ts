import type { components } from "$lib/api/openapi.generated.js";
import { jsonBody } from "../demoMockRuntime.js";
import type { ServicePlan, DedicatedExit, UserService } from "$lib/admin/servicePlans.js";
import type { ServiceOrder } from "$lib/admin/serviceHistory";

const stamp = "2026-10-22T04:00:00Z";
const uuid = "11111111-1111-4111-8111-111111111111";
const plans: ServicePlan[] = [
  {
    id: "1".repeat(32),
    revision: 1,
    enabled: true,
    updated_at: stamp,
    terms: {
      name: "Demo total",
      description: "",
      resource_type: "shared",
      traffic_rule: "total",
      quota_bytes: 100 * 2 ** 30,
      validity_days: 90,
      price: "29.90",
      currency: "CNY",
      squad_uuids: [uuid],
      resource_pool: null,
    },
  },
  {
    id: "2".repeat(32),
    revision: 1,
    enabled: true,
    updated_at: stamp,
    terms: {
      name: "Demo dedicated",
      description: "",
      resource_type: "dedicated",
      traffic_rule: "monthly",
      quota_bytes: 50 * 2 ** 30,
      validity_days: 365,
      price: "99.00",
      currency: "CNY",
      squad_uuids: [],
      resource_pool: "demo",
    },
  },
];
const exits: DedicatedExit[] = [
  {
    id: "3".repeat(32),
    label: "Demo exit",
    ip_address: "192.0.2.10",
    resource_pool: "demo",
    squad_uuid: uuid,
    service_id: null,
    verified_at: null,
    enabled: true,
  },
];
const services: UserService[] = [];
const orders: ServiceOrder[] = [];
const archived: UserService[] = Array.from({ length: 26 }, (_, index) => ({
  id: (200 + index).toString(16).padStart(32, "0"),
  user_id: null,
  plan_id: plans[0].id,
  plan_revision: 1,
  name: `Archived plan ${index + 1}`,
  description: "",
  resource_type: "shared",
  traffic_rule: "total",
  quota_bytes: 100 * 2 ** 30,
  used_bytes: 10 * 2 ** 30,
  starts_at: stamp,
  expires_at: "2027-01-20T04:00:00Z",
  cycle_started_at: null,
  cycle_ends_at: null,
  last_usage_sync_at: stamp,
  cycle_pending: false,
  usage_total_bytes: null,
  usage_error: index === 0 ? "panel_usage_unavailable" : null,
  status: "cancelled",
  connection_state: "revoked",
  revision: 1,
  desired_status: "cancelled",
  sync_pending: false,
  sync_error: null,
  sync_confirmed_at: null,
  exit_ip: null,
  exit_verified: false,
}));
for (const service of archived)
  orders.push({
    id: `f${service.id.slice(1)}`,
    user_id: null,
    service_id: service.id,
    actor_id: 42,
    kind: "activate",
    created_at: stamp,
    snapshot: {
      terms: { ...plans[0].terms, name: service.name, price: "19.90" },
      plan_id: service.plan_id,
      plan_revision: 1,
      starts_at: stamp,
      expires_at: service.expires_at,
      exit_id: null,
      fulfillment: "manual",
    },
  });
let historyFailureShown = false;
let orderFailureShown = false;
let demoOwner = 0;
const requests = new Map<string, UserService>();
const id = () => crypto.randomUUID().replaceAll("-", "");

export function seedIndependentServicesDemo(owner: number, empty = false) {
  demoOwner = owner;
  services.length = 0;
  if (empty) return;
  for (let index = 0; index < 12; index++) {
    const monthly = index === 1;
    services.push({
      id: String(index + 10).padStart(32, "0"),
      user_id: owner,
      plan_id: plans[monthly ? 1 : 0].id,
      plan_revision: 1,
      name: monthly ? "Demo dedicated" : "Demo total",
      description: "",
      resource_type: monthly ? "dedicated" : "shared",
      traffic_rule: monthly ? "monthly" : "total",
      quota_bytes: 100 * 2 ** 30,
      used_bytes: (index === 0 ? 117 : index === 1 ? 23 : 0) * 2 ** 30,
      starts_at: stamp,
      expires_at: "2027-01-20T04:00:00Z",
      cycle_started_at: monthly ? stamp : null,
      cycle_ends_at: monthly ? "2026-11-22T04:00:00Z" : null,
      last_usage_sync_at: index < 2 ? stamp : null,
      cycle_pending: monthly && new URLSearchParams(window.location.search).has("cycle_pending"),
      usage_total_bytes: null,
      usage_error: monthly ? "panel_usage_unavailable" : null,
      status: index === 0 ? "exhausted" : "pending",
      connection_state: "pending",
      revision: 1,
      desired_status: "active",
      sync_pending: false,
      sync_error: null,
      sync_confirmed_at: null,
      exit_ip: monthly ? "192.0.2.10" : null,
      exit_verified: false,
    });
  }
}

export function independentServicesDemoResponse(path: string, options: RequestInit): unknown {
  const url = new URL(path, "https://example.test");
  const route = url.pathname;
  const method = options.method || "GET";
  const offset = Number(url.searchParams.get("offset") || 0);
  const limit = Number(url.searchParams.get("limit") || 100);
  if (route === "/service-catalog" && method === "GET") {
    const rows = plans
      .filter((plan) => plan.enabled)
      .map((plan) => {
        const { squad_uuids: _squads, resource_pool: _pool, ...terms } = plan.terms;
        return { id: plan.id, ...terms };
      });
    return { ok: true, plans: rows.slice(offset, offset + limit), total: rows.length };
  }
  if (route.startsWith("/services/") && method === "GET") {
    const service = services.find(
      (item) => item.id === route.split("/").pop() && item.user_id === demoOwner
    );
    return service ? { ok: true, service } : { ok: false, error: "service_not_found" };
  }
  if (route === "/admin/service-plans" && method === "GET")
    return { ok: true, plans: plans.slice(offset, offset + limit), total: plans.length };
  if (route === "/admin/service-plans" && method === "POST") {
    const body = jsonBody(options) as components["schemas"]["ServicePlanBody"];
    const plan: ServicePlan = { ...body, id: id(), revision: 1, updated_at: stamp };
    plans.unshift(plan);
    return { ok: true, plan };
  }
  if (route.startsWith("/admin/service-plans/") && method === "PUT") {
    const body = jsonBody(options) as components["schemas"]["ServicePlanUpdateBody"];
    const plan = plans.find((item) => item.id === route.split("/").pop());
    if (!plan) return { ok: false, error: "plan_not_found" };
    if (body.expected_revision !== plan.revision)
      return { ok: false, error: "plan_revision_changed" };
    if (plan.terms.quota_bytes !== body.terms.quota_bytes && !body.quota_change_reason?.trim())
      return { ok: false, error: "quota_change_reason_required" };
    plan.terms = body.terms;
    plan.enabled = body.enabled;
    plan.revision++;
    return { ok: true, plan };
  }
  if (route === "/admin/dedicated-exits" && method === "GET")
    return { ok: true, exits: exits.slice(offset, offset + limit), total: exits.length };
  if (route === "/admin/dedicated-exits" && method === "POST") {
    const body = jsonBody(options) as components["schemas"]["DedicatedExitBody"];
    if (
      exits.some(
        (item) => item.ip_address === body.ip_address || item.squad_uuid === body.squad_uuid
      )
    )
      return { ok: false, error: "exit_already_exists" };
    const resource: DedicatedExit = {
      ...body,
      id: id(),
      enabled: true,
      service_id: null,
      verified_at: null,
    };
    exits.unshift(resource);
    return { ok: true, exit: resource };
  }
  if (route === "/admin/services" && method === "POST") {
    const body = jsonBody(options) as components["schemas"]["ServiceActivationBody"];
    const key = `${body.user_id}:${body.idempotency_key}`;
    const previous = requests.get(key);
    if (previous)
      return {
        ok: true,
        service: previous,
        duplicate: true,
        order: orders.find((item) => item.service_id === previous.id),
      };
    const plan = plans.find((item) => item.id === body.plan_id);
    if (!plan?.enabled) return { ok: false, error: "plan_disabled" };
    if (plan.revision !== body.expected_revision)
      return { ok: false, error: "plan_revision_changed" };
    const resource = exits.find((item) => item.id === body.exit_id);
    if (
      plan.terms.resource_type === "dedicated" &&
      (!resource || resource.service_id || resource.resource_pool !== plan.terms.resource_pool)
    )
      return { ok: false, error: "exit_unavailable" };
    const service: UserService = {
      id: id(),
      user_id: body.user_id,
      plan_id: plan.id,
      plan_revision: plan.revision,
      name: plan.terms.name,
      description: plan.terms.description,
      resource_type: plan.terms.resource_type,
      traffic_rule: plan.terms.traffic_rule,
      quota_bytes: plan.terms.quota_bytes,
      used_bytes: 0,
      starts_at: stamp,
      expires_at: new Date(Date.parse(stamp) + plan.terms.validity_days * 86400000).toISOString(),
      cycle_started_at: plan.terms.traffic_rule === "monthly" ? stamp : null,
      cycle_ends_at: plan.terms.traffic_rule === "monthly" ? "2026-11-22T04:00:00Z" : null,
      last_usage_sync_at: null,
      cycle_pending: false,
      usage_total_bytes: null,
      usage_error: null,
      status: "pending",
      connection_state: "pending",
      revision: 1,
      desired_status: "active",
      sync_pending: false,
      sync_error: null,
      sync_confirmed_at: null,
      exit_ip: resource?.ip_address || null,
      exit_verified: false,
    };
    if (resource) resource.service_id = service.id;
    if (new URLSearchParams(window.location.search).get("mock") === "usage-reconciliation") {
      service.usage_error = "panel_usage_reset";
      service.used_bytes = 500;
      service.usage_total_bytes = 500;
      service.desired_status = "paused";
      service.status = "paused";
    }
    services.unshift(service);
    requests.set(key, service);
    const order: ServiceOrder = {
      id: id(),
      user_id: body.user_id,
      service_id: service.id,
      actor_id: 42,
      kind: "activate",
      created_at: stamp,
      snapshot: {
        terms: structuredClone(plan.terms),
        plan_id: plan.id,
        plan_revision: plan.revision,
        starts_at: service.starts_at,
        expires_at: service.expires_at,
        exit_id: resource?.id || null,
        fulfillment: "manual",
      },
    };
    orders.unshift(order);
    return { ok: true, service, duplicate: false, order };
  }
  const scenario = new URLSearchParams(window.location.search).get("mock");
  if (/^\/admin\/services\/[^/]+\/changes$/.test(route) && method === "POST") {
    const body = jsonBody(options) as components["schemas"]["ServiceChangeBody"];
    const service = services.find(
      (item) => item.id === route.split("/")[3] && item.user_id === body.user_id
    );
    if (!service) return { ok: false, error: "service_not_found" };
    const key = `${body.user_id}:${body.idempotency_key}`;
    if (requests.has(key)) return { ok: true, service, duplicate: true };
    if (service.revision !== body.expected_revision)
      return { ok: false, error: "service_revision_changed" };
    const before = {
      desired_status: service.desired_status,
      expires_at: service.expires_at,
      revision: service.revision,
      used_bytes: service.used_bytes,
    };
    if (body.change.action === "reconcile_usage") {
      if (service.desired_status !== "paused")
        return { ok: false, error: "usage_reconciliation_pause_required" };
      if (
        body.change.expected_raw_bytes !== 100 ||
        (body.change.verified_total_bytes ?? 0) < service.used_bytes
      )
        return { ok: false, error: "usage_reconciliation_changed" };
      service.used_bytes = body.change.verified_total_bytes!;
      service.usage_total_bytes = service.used_bytes;
      service.usage_error = null;
    } else if (body.change.action === "renew")
      service.expires_at = new Date(
        Math.max(Date.now(), Date.parse(service.expires_at)) + Number(body.change.days) * 86400000
      ).toISOString();
    else {
      service.desired_status = body.change.action === "pause" ? "paused" : "active";
      service.status = service.desired_status === "paused" ? "paused" : "pending";
    }
    service.revision++;
    service.sync_pending = true;
    const plan = plans.find((item) => item.id === service.plan_id)!;
    const order: ServiceOrder = {
      id: id(),
      user_id: service.user_id,
      service_id: service.id,
      actor_id: 42,
      kind: body.change.action,
      created_at: new Date().toISOString(),
      snapshot: {
        terms: { ...plan.terms, name: service.name },
        plan_id: service.plan_id,
        plan_revision: service.plan_revision,
        starts_at: service.starts_at,
        expires_at: service.expires_at,
        quota_bytes: service.quota_bytes,
        used_bytes: service.used_bytes,
        desired_status: service.desired_status,
        before,
        change: body.change,
        revision: service.revision,
        fulfillment: "manual",
      },
    };
    orders.unshift(order);
    requests.set(key, service);
    return { ok: true, service, order, duplicate: false };
  }
  if (route === "/admin/service-orders") {
    if (scenario === "history-orders-retry" && !orderFailureShown) {
      orderFailureShown = true;
      return { ok: false, error: "unavailable" };
    }
    const owner =
      url.searchParams.get("deleted") === "true" ? null : Number(url.searchParams.get("user_id"));
    const selected = url.searchParams.get("service_id");
    const rows = orders.filter(
      (order) => order.user_id === owner && (!selected || order.service_id === selected)
    );
    return { ok: true, orders: rows.slice(offset, offset + limit), total: rows.length };
  }
  if (route === "/admin/services" || route === "/services") {
    if (route === "/admin/services" && url.searchParams.get("deleted") === "true") {
      if (scenario === "history-retry" && !historyFailureShown) {
        historyFailureShown = true;
        return { ok: false, error: "unavailable" };
      }
      const rows = scenario === "history-empty" ? [] : archived;
      return { ok: true, services: rows.slice(offset, offset + limit), total: rows.length };
    }
    const owner = Number(url.searchParams.get("user_id") || 0);
    const rows = services.filter(
      (item) => item.user_id === (route === "/services" ? demoOwner : owner)
    );
    return { ok: true, services: rows.slice(offset, offset + limit), total: rows.length };
  }
  return undefined;
}
