<script lang="ts">
  import { onDestroy, untrack } from "svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminDashboardGrid,
    AdminEmptyState,
  } from "$components/patterns/admin/index.js";
  import { unwrap, builtApiPath, type ApiClient } from "$lib/webapp/publicApi";
  import type { components } from "$lib/api/openapi.generated";
  import { serviceBytes, type ServiceTranslate } from "$lib/admin/servicePlans";
  import { serviceDate } from "$lib/webapp/independentServices";
  import {
    consoleAccessDenied,
    readServicesRoute,
    servicesRouteUrl,
    type ConsoleSummary,
  } from "$lib/admin/consoleServices";
  import { consoleServiceErrorKey, consoleServiceLabel } from "$lib/admin/consoleServiceOperations";
  import {
    nodesRouteUrl,
    readNodesRoute,
    type NodesRoute,
  } from "$lib/admin/consoleNodesNavigation";
  import ConsoleNodeSources from "./nodes/ConsoleNodeSources.svelte";
  import { withRoutePrefix } from "$lib/webapp/routes";
  import { operationsRouteUrl, readOperationsRoute } from "$lib/admin/consoleGlobalOperations";
  import ConsoleNodeInventory from "./nodes/ConsoleNodeInventory.svelte";
  import ConsoleOverviewSignals from "./overview/ConsoleOverviewSignals.svelte";
  import ConsoleOverviewFeedback from "./overview/ConsoleOverviewFeedback.svelte";
  import ConsoleOverviewCharts from "./overview/ConsoleOverviewCharts.svelte";
  import { buildAdminSupportTicketsPath } from "$lib/webapp/publicApi";
  import type { ConsoleNodeTrafficPreset } from "$lib/admin/consoleNodesTypes";

  let {
    api,
    at,
    routePrefix = "",
  }: { api: ApiClient["api"]; at: ServiceTranslate; routePrefix?: string } = $props();
  let summary = $state<ConsoleSummary | null>(null);
  let nodes = $state<components["schemas"]["ConsoleNodesListOut"] | null>(null);
  let localFailed = $state(false);
  let nodesFailed = $state(false);
  let loading = $state(true);
  let controller: AbortController | null = null;
  let request = 0;
  let supportStats = $state<components["schemas"]["AdminSupportStatsOut"] | null>(null);
  let feedbackFailed = $state(false);
  let feedbackReadAt = $state<string | null>(null);
  let tickets = $state<components["schemas"]["AdminSupportTicketOut"][] | null>(null);
  let ticketsFailed = $state(false);
  let trafficWindow = $state<ConsoleNodeTrafficPreset>("7d");
  let todos = $state<components["schemas"]["ConsoleGlobalOperationsOut"] | null>(null);
  const healthFields = [
    "delivery_pending",
    "delivery_failed",
    "sync_pending",
    "sync_failed",
    "usage_failed",
    "usage_unobserved",
    "cycle_pending",
    "account_sync_pending",
    "account_sync_failed",
  ] as const;
  const exitFields = [
    "available",
    "occupied",
    "pending_verification",
    "pending_reclaim",
    "disabled",
    "unverified_total",
  ] as const;

  function openSection(section: string, status = "") {
    let url: URL;
    if (section === "console-operations")
      url = operationsRouteUrl(
        window.location.href,
        { ...readOperationsRoute(""), needsAttention: true },
        routePrefix
      );
    else if (section === "services")
      url = servicesRouteUrl(
        window.location.href,
        { ...readServicesRoute(""), status: status || "all" },
        routePrefix
      );
    else {
      url = new URL(window.location.href);
      url.pathname = withRoutePrefix(`/admin/${section}`, routePrefix);
      for (const key of ["service_id", "node_id", "q", "status", "sort", "page", "user_id"])
        url.searchParams.delete(key);
      url.searchParams.set("section", section);
      if (section === "nodes") url.searchParams.delete("nodes_view");
    }
    window.history.pushState(null, "", url);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }
  function openNodes(status: NodesRoute["status"] = "all") {
    const url = nodesRouteUrl(
      window.location.href,
      { ...readNodesRoute(""), status, trafficWindow },
      routePrefix
    );
    url.searchParams.delete("nodes_view");
    window.history.pushState(null, "", url);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }
  function openTodo(serviceId: string) {
    const url = operationsRouteUrl(
      window.location.href,
      { ...readOperationsRoute(""), needsAttention: true, serviceId, detailServiceId: serviceId },
      routePrefix
    );
    window.history.pushState(null, "", url);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }
  function openNode(id: string) {
    const url = new URL(window.location.href);
    url.pathname = withRoutePrefix("/admin/nodes", routePrefix);
    url.searchParams.set("section", "nodes");
    url.searchParams.set("node_id", id);
    url.searchParams.delete("nodes_view");
    url.searchParams.set("nodes_traffic_window", trafficWindow);
    window.history.pushState(null, "", url);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }
  async function load(window: ConsoleNodeTrafficPreset = trafficWindow) {
    const token = ++request;
    controller?.abort();
    controller = new AbortController();
    loading = true;
    const signal = controller.signal;
    const [local, remote, feedback, ticketList, operations] = await Promise.allSettled([
      api("/admin/console/summary", { signal }).then(unwrap),
      api(
        builtApiPath<"/api/admin/console/nodes">(
          `/admin/console/nodes?page_size=5&page=0&traffic_window=${window}`
        ),
        {
          signal,
        }
      ).then(unwrap),
      api("/admin/support/stats", { signal }).then(unwrap),
      api(
        buildAdminSupportTicketsPath(
          new URLSearchParams({
            limit: "3",
            offset: "0",
            status: "awaiting_admin",
            sort: "importance_desc",
          })
        ),
        { signal }
      ).then(unwrap),
      api(
        builtApiPath<"/api/admin/console/operations">(
          "/admin/console/operations?needs_attention=true&limit=4"
        ),
        { signal }
      ).then(unwrap),
    ]);
    if (token !== request) return;
    const accessDenied = [local, remote].some(
      (result) => result.status === "rejected" && consoleAccessDenied(result.reason)
    );
    if (accessDenied) {
      todos = null;
      summary = null;
      nodes = null;
      supportStats = null;
      tickets = null;
      feedbackReadAt = null;
      localFailed = true;
      nodesFailed = true;
      loading = false;
      return;
    }
    localFailed = local.status === "rejected";
    nodesFailed = remote.status === "rejected";
    if (local.status === "fulfilled") summary = local.value;
    if (remote.status === "fulfilled") {
      nodes = remote.value;
      trafficWindow = window;
    }
    feedbackFailed = feedback.status === "rejected";
    supportStats = feedback.status === "fulfilled" ? feedback.value.stats : null;
    feedbackReadAt = feedback.status === "fulfilled" ? new Date().toISOString() : null;
    ticketsFailed = ticketList.status === "rejected";
    tickets = ticketList.status === "fulfilled" ? ticketList.value.tickets : null;
    todos = operations.status === "fulfilled" ? operations.value : null;
    loading = false;
  }
  $effect(() => {
    untrack(() => {
      void load("7d");
    });
  });
  onDestroy(() => {
    request++;
    controller?.abort();
  });
</script>

<section class="console-overview" aria-label={at("console_overview")} aria-busy={loading}>
  <header class="overview-intro">
    <div>
      <h2>{at("console_ops_intro_title")}</h2>
      <p class="admin-muted">{at("console_ops_subtitle")}</p>
    </div>
    <AdminButton disabled={loading} onclick={() => load()}>{at("refresh")}</AdminButton>
  </header>
  <ConsoleOverviewSignals
    {nodes}
    stale={nodesFailed}
    stats={supportStats}
    {at}
    onNodes={openNodes}
    onFeedback={() => openSection("support")}
  />
  <details class="overview-provenance">
    <summary>{at("console_ops_chart_evidence")}</summary>
    <p class="admin-muted">{at("console_local_scope")}</p>
  </details>
  {#if loading}<p role="status">{at("loading")}</p>{/if}
  {#if localFailed}<p role="alert">
      {at(summary ? "console_refresh_failed" : "console_local_failed")}
    </p>{/if}
  <section class="metric-section" data-overview-todos aria-label={at("console_visual_todos")}>
    <div class="todo-heading">
      <h3>{at("console_visual_todos")} · {todos?.total ?? at("console_unknown")}</h3>
      <AdminButton size="sm" onclick={() => openSection("console-operations")}
        >{at("console_global_attention_entry")}</AdminButton
      >
    </div>
    {#if !todos && !loading}<p role="status">{at("console_todos_unavailable")}</p>{/if}
    {#if todos?.total === 0}<p class="admin-muted">{at("console_todos_empty")}</p>{/if}
    {#each todos?.operations ?? [] as operation (operation.record_type + ":" + operation.id)}
      <article class="overview-todo">
        <div>
          <strong>{operation.service_name}</strong> · {at(
            consoleServiceLabel("phase", operation.phase)
          )}
          <AdminBadge variant={operation.status === "failed" ? "danger" : "warning"}
            >{at(consoleServiceLabel("operation", operation.status))}</AdminBadge
          >
          <p>
            {operation.error_code
              ? at(consoleServiceErrorKey(operation.error_code))
              : at("console_ops_next_inspect_operation_results")}
          </p>
          <small
            >{at(
              operation.first_failed_at ? "console_ops_first_failed_at" : "services_recorded_at"
            )}: {operation.first_failed_at || operation.created_at
              ? serviceDate(operation.first_failed_at || operation.created_at)
              : at("console_unknown")}</small
          >
        </div>
        <AdminButton size="sm" onclick={() => openTodo(operation.service_id)}
          >{at("console_global_open_service")}</AdminButton
        >
      </article>
    {/each}
  </section>
  <div class="operations-priority">
    <section class="metric-section" data-console-metric="nodes">
      <h3>{at("console_nodes")}</h3>
      {#if nodesFailed}<p role="alert">
          {at(nodes ? "console_refresh_failed" : "console_nodes_failed")}
        </p>{/if}
      {#if nodes}
        <details>
          <summary>{at("console_ops_chart_evidence")}</summary>
          <p>
            {at("console_inventory_total")}: {nodes.total === null
              ? at("console_unknown")
              : nodes.total}
          </p>
          <AdminBadge variant={!nodesFailed && nodes.coverage === "complete" ? "muted" : "warning"}
            >{at(`console_nodes_coverage_${nodesFailed ? "stale" : nodes.coverage}`)}</AdminBadge
          >
          <details class="node-provenance">
            <summary>{at("console_node_metrics_source")}</summary>
            <p class="admin-muted">{at("console_node_scope")}</p>
            <p>{at("console_node_visuals_rate_scope")}</p>
            <ConsoleNodeSources
              showCoverage={false}
              coverage={nodesFailed ? "stale" : nodes.coverage}
              sources={nodes.sources}
              stale={nodesFailed}
              {at}
            />
          </details>
          <p class="admin-muted">{at("console_node_sample", { count: nodes.nodes.length })}</p>
        </details>
        {#if nodes.nodes.length}<ConsoleNodeInventory
            compact
            nodes={nodes.nodes}
            traffic={nodes.traffic}
            source={nodes.sources.find((source) => source.source === "nodes")}
            stale={nodesFailed}
            {at}
            onOpenNode={openNode}
          />
        {:else if !nodesFailed && nodes.coverage === "complete"}<AdminEmptyState
            >{at("console_nodes_empty")}</AdminEmptyState
          >{/if}
      {/if}
      <AdminButton onclick={() => openSection("nodes")}>{at("console_open_nodes")}</AdminButton>
    </section>
    <section class="metric-section" data-console-metric="feedback">
      <ConsoleOverviewFeedback
        stats={supportStats}
        {tickets}
        failed={feedbackFailed}
        listFailed={ticketsFailed}
        readAt={feedbackReadAt}
        {loading}
        {at}
        {routePrefix}
        onOpen={() => openSection("support")}
      />
    </section>
  </div>
  <ConsoleOverviewCharts
    {nodes}
    {tickets}
    stale={nodesFailed}
    listFailed={ticketsFailed}
    {loading}
    {at}
    onNode={openNode}
  />
  <details class="overview-details">
    <summary>{at("console_visual_details")}</summary>
    {#if summary}
      <p data-summary-observed-at>
        {at("console_observed_at")}: {serviceDate(summary.observed_at)}
        <AdminBadge variant={localFailed ? "warning" : "muted"}
          >{at(localFailed ? "console_stale" : "console_local_records")}</AdminBadge
        >
      </p>
      <AdminDashboardGrid columns={3}>
        <section class="metric-section" data-console-metric="customers">
          <h3>{at("console_customers")}</h3>
          <p class="admin-muted">{at("console_customer_source")}</p>
          <AdminButton onclick={() => openSection("users")}>{summary.customers.total}</AdminButton>
          <p>{at("console_with_services")}: {summary.customers.with_services}</p>
          <p>{at("console_banned")}: {summary.customers.banned}</p>
        </section>
        <section class="metric-section" data-console-metric="services">
          <h3>{at("console_services")}</h3>
          <p class="admin-muted">{at("console_service_source")}</p>
          <AdminButton onclick={() => openSection("services")}>{summary.services.total}</AdminButton
          >
          <p>{at("console_entitlement_valid")}: {summary.services.entitlement_valid}</p>
          <p>{at("console_delivery_ready")}: {summary.services.delivery_ready}</p>
          <div class="metric-links">
            {#each Object.entries(summary.services.by_status) as [status, count]}<AdminButton
                size="sm"
                onclick={() => openSection("services", status)}
                >{at(`services_status_${status}`)}: {count}</AdminButton
              >{/each}
          </div>
          <p>{at("console_archived")}: {summary.services.archived}</p>
        </section>
        <section class="metric-section" data-console-metric="usage">
          <h3>{at("console_usage_aggregate")}</h3>
          <p class="admin-muted">{at("console_usage_aggregate_scope")}</p>
          <strong
            >{summary.usage.confirmed_used_bytes === null
              ? at("console_unknown")
              : serviceBytes(summary.usage.confirmed_used_bytes)}</strong
          >
          <p>
            <AdminBadge variant={summary.usage.availability === "available" ? "muted" : "warning"}
              >{at(`console_availability_${summary.usage.availability}`)}</AdminBadge
            >
          </p>
          <p>
            {at("console_samples", {
              sampled: summary.usage.services_sampled,
              total: summary.usage.services_total,
            })}
          </p>
          <p>
            {at("console_sample_oldest")}: {summary.usage.oldest_sample_at
              ? serviceDate(summary.usage.oldest_sample_at)
              : at("console_unknown")}
          </p>
          <p>
            {at("console_sample_latest")}: {summary.usage.latest_sample_at
              ? serviceDate(summary.usage.latest_sample_at)
              : at("console_unknown")}
          </p>
          <p>{at("console_usage_errors")}: {summary.usage.services_with_errors}</p>
          <AdminButton size="sm" onclick={() => openSection("services", "usage_unconfirmed")}
            >{at("console_filter_usage_unconfirmed")}</AdminButton
          >
        </section>
      </AdminDashboardGrid>
      <AdminDashboardGrid columns={3}>
        <section class="metric-section" data-console-metric="health">
          <h3>{at("console_health")}</h3>
          <p class="admin-muted">{at("console_health_source")}</p>
          <p class="admin-muted">{at("console_health_links_scope")}</p>
          <dl>
            {#each healthFields as field}<div>
                <dt>{at(`console_health_${field}`)}</dt>
                <dd>{summary.health[field]}</dd>
              </div>{/each}
          </dl>
          <p>
            {at("console_latest_any_success")}: {summary.health.latest_success_at
              ? serviceDate(summary.health.latest_success_at)
              : at("console_unknown")}
          </p>
          <p>
            {at("console_latest_attempt")}: {summary.health.latest_attempt_at
              ? serviceDate(summary.health.latest_attempt_at)
              : at("console_unknown")}
          </p>
          <p>
            {at("console_oldest_pending")}: {summary.health.oldest_pending_since
              ? serviceDate(summary.health.oldest_pending_since)
              : at("console_pending_time_unknown")}
          </p>
          <div class="metric-links">
            <AdminButton size="sm" onclick={() => openSection("console-operations")}
              >{at("console_global_attention_entry")}</AdminButton
            >
            <AdminButton size="sm" onclick={() => openSection("services", "sync_error")}
              >{at("console_filter_sync_error")}</AdminButton
            ><AdminButton size="sm" onclick={() => openSection("services", "sync_pending")}
              >{at("console_filter_sync_pending")}</AdminButton
            >
            <AdminButton size="sm" onclick={() => openSection("service-history")}
              >{at("services_history_title")}</AdminButton
            >
          </div>
        </section>
        <section class="metric-section" data-console-metric="exits">
          <h3>{at("services_exits_title")}</h3>
          <p class="admin-muted">{at("console_exit_source")}</p>
          <AdminButton onclick={() => openSection("dedicated-exits")}
            >{summary.exits.total}</AdminButton
          >
          <dl>
            {#each exitFields as field}<div>
                <dt>{at(`console_exit_${field}`)}</dt>
                <dd>{summary.exits[field]}</dd>
              </div>{/each}
          </dl>
        </section>
      </AdminDashboardGrid>
    {/if}
  </details>
</section>

<style>
  .todo-heading,
  .overview-todo {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: center;
    flex-wrap: wrap;
  }
  .overview-todo {
    padding: 12px 0;
    border-top: 1px solid var(--admin-border);
  }
  .overview-todo > div {
    min-width: 0;
    flex: 1 1 260px;
    overflow-wrap: anywhere;
  }
  .overview-todo p {
    margin: 6px 0;
  }
  .overview-todo small {
    color: var(--admin-muted);
  }

  .overview-details > summary {
    cursor: pointer;
    padding: 12px 0;
    color: var(--admin-muted);
  }
  .overview-intro h2 {
    margin: 0;
    font-size: 24px;
  }
  .console-overview {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  .overview-intro {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
    text-align: left;
  }
  .overview-intro h2 {
    font-size: 20px;
    margin: 0;
  }
  .operations-priority {
    display: grid;
    gap: 16px;
    min-width: 0;
    align-items: start;
  }
  .overview-provenance,
  .node-provenance {
    margin-block: 8px;
    font-size: 12px;
    color: var(--admin-muted);
  }
  .node-provenance summary {
    cursor: pointer;
    padding-block: 6px;
  }
  @media (min-width: 1200px) {
    .operations-priority {
      grid-template-columns: minmax(0, 1.8fr) minmax(280px, 1fr);
    }
  }
  p {
    margin: 8px 0;
    overflow-wrap: anywhere;
  }
  .metric-section {
    min-width: 0;
    padding: 16px;
    border: 1px solid var(--admin-border);
    border-radius: 14px;
    background: var(--admin-surface);
  }
  h3 {
    margin: 0;
    font-size: 16px;
  }
  dl {
    margin: 12px 0;
  }
  dl > div {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    margin: 6px 0;
  }
  dt {
    color: var(--admin-muted);
  }
  dd {
    margin: 0;
  }
  .metric-links {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 12px;
  }
</style>
