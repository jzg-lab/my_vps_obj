<script lang="ts">
  import { onDestroy } from "svelte";
  import { AdminButton } from "$components/patterns/admin/index.js";
  import AdminMetricChart from "$components/patterns/admin/AdminMetricChart.svelte";
  import ServiceUsageSummary from "./ServiceUsageSummary.svelte";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi";
  import type { components } from "$lib/api/openapi.generated";
  import { serviceBytes, type UserService, type ServiceTranslate } from "$lib/admin/servicePlans";
  import { serviceTrafficMessage } from "$lib/admin/serviceTraffic";
  let {
    services,
    api,
    at,
  }: { services: UserService[]; api: ApiClient["api"]; at: ServiceTranslate } = $props();
  let histories = $state<Record<string, components["schemas"]["ConsoleServiceTrafficOut"] | null>>(
    {}
  );
  let loading = $state(false);
  let request = 0;
  let controller: AbortController | undefined;
  async function load(rows: UserService[]) {
    const token = ++request;
    controller?.abort();
    controller = new AbortController();
    const signal = controller.signal;
    histories = {};
    loading = true;
    const results = await Promise.all(
      rows.map(async (service) => {
        try {
          return [
            service.id,
            unwrap(
              await api(
                builtApiPath<"/api/admin/console/services/{service_id}/traffic">(
                  `/admin/console/services/${encodeURIComponent(service.id)}/traffic`
                ),
                { signal }
              )
            ),
          ] as const;
        } catch {
          return [service.id, null] as const;
        }
      })
    );
    if (token === request) {
      histories = Object.fromEntries(results);
      loading = false;
    }
  }
  $effect(() => {
    void load(services);
  });
  onDestroy(() => {
    request++;
    controller?.abort();
  });
  const dates = $derived(
    [
      ...new Set(
        Object.values(histories).flatMap((history) => history?.days?.map((day) => day.date) ?? [])
      ),
    ].sort()
  );
  const series = $derived(
    services.map((service) => ({
      label: service.name,
      values: dates.map(
        (date) => histories[service.id]?.days?.find((day) => day.date === date)?.bytes ?? null
      ),
    }))
  );
  const hasSamples = $derived(series.some((row) => row.values.some((value) => value !== null)));
</script>

<section class="customer-usage" aria-label={at("console_customer_usage")} aria-busy={loading}>
  <header>
    <h3>{at("console_customer_usage")}</h3>
    <AdminButton size="sm" disabled={loading} onclick={() => load(services)}
      >{at("refresh")}</AdminButton
    >
  </header>
  {#if loading}<p role="status">{at("loading")}</p>
  {:else if hasSamples}
    <p>{at("console_visual_history_scope")}</p>
    <AdminMetricChart
      title={at("console_customer_usage")}
      labels={dates.map((date) => date.slice(5))}
      {series}
      height={280}
      format={serviceBytes}
      missingLabel={at(loading ? "loading" : "console_visual_history_missing")}
      tableLabel={at("console_visual_table")}
      timeLabel={at("console_visual_day")}
    />
  {/if}
  {#if !loading}{#each services as service (service.id)}
      {@const message = serviceTrafficMessage(histories[service.id])}
      {#if message}<p role="status">{service.name} · {at(message)}</p>{/if}
    {/each}{/if}
</section>
<div class="customer-service-summaries">
  {#each services as service (service.id)}<ServiceUsageSummary {service} {at} />{/each}
</div>

<style>
  .customer-usage {
    display: grid;
    gap: 12px;
    min-width: 0;
    padding: 20px;
    border: 1px solid var(--admin-border);
    border-radius: 14px;
    background: var(--admin-surface);
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }
  h3,
  p {
    margin: 0;
  }
  p {
    font-size: 12px;
    color: var(--admin-muted);
    line-height: 1.6;
    overflow-wrap: anywhere;
  }
  .customer-service-summaries {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr));
    gap: 16px;
    min-width: 0;
  }
</style>
