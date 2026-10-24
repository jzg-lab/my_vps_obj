<script lang="ts">
  import { onDestroy } from "svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminDashboardGrid,
    AdminListToolbar,
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
  import ConsoleNodeSources from "./nodes/ConsoleNodeSources.svelte";
  import ConsoleNodeTable from "./nodes/ConsoleNodeTable.svelte";
  import { withRoutePrefix } from "$lib/webapp/routes";
  import { operationsRouteUrl, readOperationsRoute } from "$lib/admin/consoleGlobalOperations";

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
    }
    window.history.pushState(null, "", url);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }
  function openNode(id: string) {
    const url = new URL(window.location.href);
    url.pathname = withRoutePrefix("/admin/nodes", routePrefix);
    url.searchParams.set("section", "nodes");
    url.searchParams.set("node_id", id);
    window.history.pushState(null, "", url);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }
  async function load() {
    const token = ++request;
    controller?.abort();
    controller = new AbortController();
    loading = true;
    const signal = controller.signal;
    const [local, remote] = await Promise.allSettled([
      api("/admin/console/summary", { signal }).then(unwrap),
      api(builtApiPath<"/api/admin/console/nodes">("/admin/console/nodes?page_size=5&page=0"), {
        signal,
      }).then(unwrap),
    ]);
    if (token !== request) return;
    const accessDenied = [local, remote].some(
      (result) => result.status === "rejected" && consoleAccessDenied(result.reason)
    );
    if (accessDenied) {
      summary = null;
      nodes = null;
      localFailed = true;
      nodesFailed = true;
      loading = false;
      return;
    }
    localFailed = local.status === "rejected";
    nodesFailed = remote.status === "rejected";
    if (local.status === "fulfilled") summary = local.value;
    if (remote.status === "fulfilled") nodes = remote.value;
    loading = false;
  }
  $effect(() => {
    void load();
  });
  onDestroy(() => {
    request++;
    controller?.abort();
  });
</script>

<section class="console-overview" aria-label={at("console_overview")} aria-busy={loading}>
  <AdminListToolbar
    >{#snippet actions()}<AdminButton disabled={loading} onclick={load}>{at("refresh")}</AdminButton
      >{/snippet}</AdminListToolbar
  >
  <p class="admin-muted">{at("console_local_scope")}</p>
  {#if loading}<p role="status">{at("loading")}</p>{/if}
  {#if localFailed}<p role="alert">
      {at(summary ? "console_refresh_failed" : "console_local_failed")}
    </p>{/if}
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
        <AdminButton onclick={() => openSection("services")}>{summary.services.total}</AdminButton>
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
  <section class="metric-section" data-console-metric="nodes">
    <h3>{at("console_nodes")}</h3>
    <p class="admin-muted">{at("console_node_scope")}</p>
    {#if nodesFailed}<p role="alert">
        {at(nodes ? "console_refresh_failed" : "console_nodes_failed")}
      </p>{/if}
    {#if nodes}
      <p>
        {at("console_inventory_total")}: {nodes.total === null
          ? at("console_unknown")
          : nodes.total}
      </p>
      <ConsoleNodeSources
        coverage={nodesFailed ? "stale" : nodes.coverage}
        sources={nodes.sources}
        stale={nodesFailed}
        {at}
      />
      <p class="admin-muted">{at("console_node_sample", { count: nodes.nodes.length })}</p>
      {#if nodes.nodes.length}<ConsoleNodeTable
          nodes={nodes.nodes}
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
</section>

<style>
  .console-overview {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  p {
    margin: 8px 0;
    overflow-wrap: anywhere;
  }
  .metric-section {
    min-width: 0;
    padding-block: 12px;
    border-top: 1px solid var(--admin-border);
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
