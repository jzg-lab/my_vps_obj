import type { components } from "$lib/api/openapi.generated.js";
import { jsonBody } from "../demoMockRuntime.js";
import type { ServicePlan, DedicatedExit, UserService } from "$lib/admin/servicePlans.js";

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
const requests = new Map<string, UserService>();
const id = () => crypto.randomUUID().replaceAll("-", "");

export function independentServicesDemoResponse(path: string, options: RequestInit): unknown {
  const url = new URL(path, "https://example.test");
  const route = url.pathname;
  const method = options.method || "GET";
  const offset = Number(url.searchParams.get("offset") || 0);
  const limit = Number(url.searchParams.get("limit") || 100);
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
    if (previous) return { ok: true, service: previous, duplicate: true, order: {} };
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
      status: "pending",
      connection_state: "pending",
      exit_ip: resource?.ip_address || null,
      exit_verified: false,
    };
    if (resource) resource.service_id = service.id;
    services.unshift(service);
    requests.set(key, service);
    return { ok: true, service, duplicate: false, order: {} };
  }
  if (route === "/admin/services" || route === "/services") {
    const owner = Number(url.searchParams.get("user_id") || 0);
    const rows = services.filter((item) => route === "/services" || item.user_id === owner);
    return { ok: true, services: rows.slice(offset, offset + limit), total: rows.length };
  }
  return undefined;
}
