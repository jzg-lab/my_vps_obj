<script lang="ts">
  import { onDestroy } from "svelte";
  import { AdminButton } from "$components/patterns/admin/index.js";
  import AdminMetricChart from "$components/patterns/admin/AdminMetricChart.svelte";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi";
  import type { components } from "$lib/api/openapi.generated";
  import { serviceBytes, type UserService, type ServiceTranslate } from "$lib/admin/servicePlans";
  import ServiceUsageSummary from "./ServiceUsageSummary.svelte";
  import ConsoleServiceResources from "../nodes/ConsoleServiceResources.svelte";
  import { serviceTrafficMessage } from "$lib/admin/serviceTraffic";

  let {
    service,
    api,
    at,
    routePrefix = "",
    showResources = true,
  }: {
    service: UserService;
    api: ApiClient["api"];
    at: ServiceTranslate;
    routePrefix?: string;
    showResources?: boolean;
  } = $props();
  let history = $state<components["schemas"]["ConsoleServiceTrafficOut"] | null>(null);
  let loading = $state(false);
  let request = 0;
  let controller: AbortController | undefined;
  async function load(id: string) {
    const token = ++request;
    controller?.abort();
    controller = new AbortController();
    history = null;
    loading = true;
    try {
      const value = unwrap(
        await api(
          builtApiPath<"/api/admin/console/services/{service_id}/traffic">(
            `/admin/console/services/${encodeURIComponent(id)}/traffic`
          ),
          { signal: controller.signal }
        )
      );
      if (token === request) history = value;
    } catch {
      if (token === request) history = null;
    } finally {
      if (token === request) loading = false;
    }
  }
  $effect(() => {
    void load(service.id);
  });
  onDestroy(() => {
    request++;
    controller?.abort();
  });
  const hasSamples = $derived(history?.days?.some((day) => day.bytes !== null) ?? false);
  const message = $derived(serviceTrafficMessage(history));
</script>

<section class="service-visual" aria-label={at("console_visual_service")}>
  <div class="quota-grid">
    <ServiceUsageSummary {service} {at} />
    <div class="history" aria-busy={loading}>
      <header>
        <h4>{at("console_visual_history")}</h4>
        <AdminButton size="sm" disabled={loading} onclick={() => load(service.id)}
          >{at("refresh")}</AdminButton
        >
      </header>
      {#if loading}<p role="status">{at("loading")}</p>
      {:else if hasSamples}<AdminMetricChart
          title={at("console_visual_history")}
          labels={(history?.days ?? []).map((day) => day.date.slice(5))}
          series={[{ label: service.name, values: (history?.days ?? []).map((day) => day.bytes) }]}
          format={serviceBytes}
          missingLabel={at(loading ? "loading" : "console_visual_history_missing")}
          tableLabel={at("console_visual_table")}
          timeLabel={at("console_visual_day")}
        />{/if}
      {#if !loading && message}<p role="status">{at(message)}</p>{/if}
      {#if hasSamples}<p>{at("console_visual_history_scope")}</p>{/if}
    </div>
  </div>
  {#if showResources}<ConsoleServiceResources
      {api}
      {at}
      serviceId={service.id}
      {routePrefix}
    />{/if}
  {#if history && ["available", "partial"].includes(history.availability)}<details>
      <summary>{at("console_visual_used_nodes")}</summary>
      {#each history.nodes ?? [] as node (node.node_id)}<p>
          {node.node_id} · {serviceBytes(node.bytes)}
        </p>{:else}<p>{at("console_visual_no_used_nodes")}</p>{/each}
    </details>{/if}
</section>

<style>
  .service-visual {
    display: grid;
    gap: 18px;
    min-width: 0;
  }
  .quota-grid {
    display: grid;
    grid-template-columns: minmax(220px, 1fr) minmax(0, 2fr);
    gap: 16px;
  }
  .history {
    min-width: 0;
    padding: 16px;
    border: 1px solid var(--admin-border);
    border-radius: 14px;
    background: var(--admin-surface);
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }
  h4 {
    margin: 0 0 12px;
  }
  p,
  summary {
    font-size: 12px;
    color: var(--admin-muted);
    overflow-wrap: anywhere;
    line-height: 1.6;
  }
  summary {
    cursor: pointer;
  }
  @media (max-width: 800px) {
    .quota-grid {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
