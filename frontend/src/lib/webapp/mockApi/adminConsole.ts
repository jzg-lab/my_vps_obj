import type { components } from "$lib/api/openapi.generated";
import type { DedicatedExit, ServicePlan, UserService } from "$lib/admin/servicePlans";

type Schema = components["schemas"];
type State = {
  services: UserService[];
  archived: UserService[];
  plans: ServicePlan[];
  exits: DedicatedExit[];
  owner: number;
};

export function withCustomerServiceSummaries(
  response: unknown,
  services: readonly UserService[]
): unknown {
  if (
    !response ||
    typeof response !== "object" ||
    !("ok" in response) ||
    response.ok !== true ||
    !("users" in response) ||
    !Array.isArray(response.users)
  )
    return response;
  const users: unknown[] = response.users;
  const userIdOf = (user: unknown): number | undefined => {
    if (!user || typeof user !== "object" || !("user_id" in user)) return undefined;
    const id = user.user_id;
    if (typeof id !== "number" && (typeof id !== "string" || !id.trim())) return undefined;
    return Number.isSafeInteger(Number(id)) ? Number(id) : undefined;
  };
  const now = new Date().toISOString();
  const summaries = new Map<number, Schema["ConsoleCustomerServicesOut"]>();
  const banned = new Set<number>();
  for (const user of users) {
    const userId = userIdOf(user);
    if (userId === undefined) continue;
    if (user && typeof user === "object" && "is_banned" in user && user.is_banned === true)
      banned.add(userId);
    summaries.set(userId, {
      total: 0,
      by_status: {
        active: 0,
        pending: 0,
        paused: 0,
        cancelled: 0,
        expired: 0,
        exhausted: 0,
        account_banned: 0,
      },
      sync_error: 0,
      sync_pending: 0,
      cycle_pending: 0,
      sync_unobserved: 0,
      usage_unobserved: 0,
      oldest_sync_confirmed_at: null,
      latest_sync_confirmed_at: null,
      oldest_usage_sync_at: null,
      latest_usage_sync_at: null,
      observed_at: now,
      source: "local_independent_service_records",
      scope: "current_owner_excludes_archived",
      activity: "not_collected",
    });
  }
  for (const service of services) {
    if (service.user_id === null) continue;
    const summary = summaries.get(service.user_id);
    if (!summary) continue;
    summary.total++;
    const status = banned.has(service.user_id) ? "account_banned" : service.status;
    summary.by_status[status] = (summary.by_status[status] ?? 0) + 1;
    if (service.connection_state === "error" || service.sync_error || service.usage_error)
      summary.sync_error++;
    if (service.sync_pending) summary.sync_pending++;
    if (service.cycle_pending) summary.cycle_pending++;
    if (!service.sync_confirmed_at) summary.sync_unobserved++;
    if (!service.last_usage_sync_at) summary.usage_unobserved++;
    for (const [value, oldest, latest] of [
      [service.sync_confirmed_at, "oldest_sync_confirmed_at", "latest_sync_confirmed_at"],
      [service.last_usage_sync_at, "oldest_usage_sync_at", "latest_usage_sync_at"],
    ] as const) {
      if (!value) continue;
      if (!summary[oldest] || Date.parse(value) < Date.parse(summary[oldest]))
        summary[oldest] = value;
      if (!summary[latest] || Date.parse(value) > Date.parse(summary[latest]))
        summary[latest] = value;
    }
  }
  return {
    ...response,
    users: users.map((user) => {
      const userId = userIdOf(user);
      const summary = userId === undefined ? undefined : summaries.get(userId);
      return summary && user && typeof user === "object"
        ? { ...user, independent_services: summary }
        : user;
    }),
  };
}

export function adminConsoleDemoResponse(url: URL, state: State): unknown {
  const route = url.pathname;
  if (
    !/^\/admin\/console\/(?:summary|nodes(?:\/[^/]+)?|services(?:\/[^/]+(?:\/resources)?)?)$/.test(
      route
    )
  )
    return undefined;
  const now = new Date().toISOString();
  const { services, archived, plans, exits, owner } = state;
  const page = Math.max(0, Number(url.searchParams.get("page")) || 0);
  const pageSize = Math.max(1, Math.min(100, Number(url.searchParams.get("page_size")) || 25));
  const sources: Schema["ConsoleNodeSourceOut"][] = (
    ["nodes", "hosts", "internal_squads"] as const
  ).map((source) => ({
    source,
    availability: "unconfigured",
    attempted_at: now,
    last_success_at: null,
    error: "not_configured",
  }));
  const customer: Schema["ConsoleCustomerOut"] = {
    user_id: owner,
    minishop_id: `MS-${owner}`,
    username: null,
    email: null,
    first_name: null,
    last_name: null,
    is_banned: false,
  };
  const sampled = services.filter((service) => service.last_usage_sync_at);
  const times = sampled.map((service) => service.last_usage_sync_at!).sort();
  const count = (predicate: (service: UserService) => boolean) => services.filter(predicate).length;
  if (route === "/admin/console/summary") {
    const health = [...services, ...archived];
    const summary: Schema["ConsoleSummaryOut"] = {
      observed_at: now,
      timezone: "Asia/Shanghai",
      refresh_mode: "read_only_local_records",
      customers: {
        total: 1,
        with_services: services.length ? 1 : 0,
        banned: 0,
        source: "business_accounts",
      },
      services: {
        source: "nonarchived_services",
        total: services.length,
        archived: archived.length,
        by_status: Object.fromEntries(
          [...new Set(services.map((s) => s.status))].map((status) => [
            status,
            count((s) => s.status === status),
          ])
        ),
        entitlement_valid: count((s) => s.status === "active"),
        delivery_ready: count(
          (s) =>
            s.status === "active" &&
            s.connection_state === "ready" &&
            !s.sync_pending &&
            !s.sync_error &&
            !!s.last_usage_sync_at
        ),
      },
      usage: {
        source: "persisted_service_usage",
        scope: "current_period_upload_plus_download_business_payload",
        unit: "bytes",
        freshness: "last_confirmed_observation",
        confirmed_used_bytes: sampled.length
          ? sampled.reduce((sum, s) => sum + s.used_bytes, 0)
          : services.length
            ? null
            : 0,
        services_total: services.length,
        services_sampled: sampled.length,
        services_with_errors: count((s) => !!s.usage_error),
        oldest_sample_at: times[0] || null,
        latest_sample_at: times.at(-1) || null,
        availability:
          services.length && !sampled.length
            ? "unknown"
            : sampled.length === services.length && !count((s) => !!s.usage_error)
              ? "available"
              : "partial",
      },
      health: {
        source: "local_service_and_account_sync_records",
        scope: "including_archived_services",
        pending_time_unavailable_reason: "enqueue_time_not_recorded",
        delivery_pending: health.filter((s) => s.connection_state === "pending").length,
        delivery_failed: health.filter((s) => s.connection_state === "error").length,
        sync_pending: health.filter((s) => s.sync_pending).length,
        sync_failed: health.filter((s) => s.sync_error).length,
        usage_failed: health.filter((s) => s.usage_error).length,
        usage_unobserved: health.filter((s) => !s.last_usage_sync_at).length,
        cycle_pending: health.filter((s) => s.cycle_pending).length,
        account_sync_pending: 0,
        account_sync_failed: 0,
        latest_success_at:
          health
            .map((s) => s.sync_confirmed_at)
            .filter((v): v is string => !!v)
            .sort()
            .at(-1) || null,
        latest_attempt_at: null,
        oldest_pending_since: null,
      },
      exits: {
        source: "dedicated_exit_inventory",
        overlap: "pending_reclaim_subset_of_occupied_disabled_may_overlap",
        total: exits.length,
        available: exits.filter((e) => e.enabled && !e.service_id && e.verified_at).length,
        occupied: exits.filter((e) => e.service_id).length,
        pending_verification: exits.filter((e) => e.enabled && !e.service_id && !e.verified_at)
          .length,
        pending_reclaim: exits.filter(
          (e) =>
            e.service_id &&
            services.some(
              (s) => s.id === e.service_id && ["expired", "cancelled"].includes(s.status)
            )
        ).length,
        disabled: exits.filter((e) => !e.enabled).length,
        unverified_total: exits.filter((e) => !e.verified_at).length,
      },
    };
    return { ok: true, ...summary };
  }
  if (route === "/admin/console/nodes") {
    const result: Schema["ConsoleNodesListOut"] = {
      nodes: [],
      traffic: null,
      total: null,
      page,
      page_size: pageSize,
      coverage: "unavailable",
      sources,
      cache_ttl_seconds: 30,
    };
    return { ok: true, ...result };
  }
  if (route.startsWith("/admin/console/nodes/")) return { ok: false, error: "node_not_found" };
  if (route === "/admin/console/services") {
    const q = (url.searchParams.get("q") || "").toLowerCase();
    const status = url.searchParams.get("status") || "all";
    const userId = url.searchParams.get("user_id");
    const rows = services.filter((s) => {
      if (userId && String(s.user_id) !== userId) return false;
      if (![s.name, s.id, customer.minishop_id].some((value) => value?.toLowerCase().includes(q)))
        return false;
      if (status === "sync_error") return !!s.sync_error;
      if (status === "sync_pending") return s.sync_pending;
      if (status === "usage_unconfirmed")
        return !s.last_usage_sync_at || !!s.usage_error || s.cycle_pending;
      if (status === "expiring")
        return (
          Date.parse(s.expires_at) > Date.now() &&
          Date.parse(s.expires_at) <= Date.now() + 7 * 86400000
        );
      return status === "all" || s.status === status;
    });
    const sort = url.searchParams.get("sort") || "created_desc";
    rows.sort((a, b) =>
      sort === "usage_desc"
        ? b.used_bytes - a.used_bytes
        : sort.startsWith("expires")
          ? (Date.parse(a.expires_at) - Date.parse(b.expires_at)) * (sort.endsWith("desc") ? -1 : 1)
          : a.id.localeCompare(b.id) * (sort.endsWith("desc") ? -1 : 1)
    );
    const result: Schema["ConsoleServiceListOut"] = {
      services: rows
        .slice(page * pageSize, (page + 1) * pageSize)
        .map((service) => ({ service, customer })),
      total: rows.length,
      page,
      page_size: pageSize,
      observed_at: now,
      expiring_within_days: 7,
    };
    return { ok: true, ...result };
  }
  const service = services.find((s) => s.id === route.split("/")[4]);
  if (!service) return { ok: false, error: "service_not_found" };
  const terms = plans.find((p) => p.id === service.plan_id)?.terms;
  if (!terms) return { ok: false, error: "service_not_found" };
  if (route.endsWith("/resources")) {
    const result: Schema["ConsoleServiceResourcesOut"] = {
      service_id: service.id,
      status: service.status,
      connection_state: service.connection_state,
      currently_eligible: service.status === "active",
      configured_group_ids: terms.squad_uuids || [],
      groups: [],
      nodes: [],
      hosts: [],
      coverage: "unavailable",
      sources,
      local_observed_at: now,
      remote_authorization_verified: false,
      association_basis: "persisted_service_scope_not_live_connections",
    };
    return { ok: true, ...result };
  }
  const detail: Schema["ConsoleServiceDetailOut"] = { service, customer, terms, connection: null };
  return { ok: true, ...detail };
}
