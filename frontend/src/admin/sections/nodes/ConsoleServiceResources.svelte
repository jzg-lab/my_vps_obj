<script lang="ts">
  import { onDestroy } from "svelte";
  import { AdminButton } from "$components/patterns/admin/index.js";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi";
  import type {
    ConsoleServiceResources,
    ConsoleNodesTranslate,
  } from "$lib/admin/consoleNodesTypes";
  import ConsoleServiceResourcesView from "./ConsoleServiceResourcesView.svelte";
  let {
    api,
    at,
    serviceId,
    routePrefix = "",
  }: {
    api: ApiClient["api"];
    at: ConsoleNodesTranslate;
    serviceId: string;
    routePrefix?: string;
  } = $props();
  let resources = $state<ConsoleServiceResources | null>(null);
  let loading = $state(true);
  let failed = $state(false);
  let request = 0;
  let controller: AbortController | null = null;
  async function load(id: string) {
    const token = ++request;
    controller?.abort();
    controller = new AbortController();
    resources = null;
    loading = true;
    failed = false;
    try {
      const result = unwrap(
        await api(
          builtApiPath<"/api/admin/console/services/{service_id}/resources">(
            `/admin/console/services/${encodeURIComponent(id)}/resources`
          ),
          { signal: controller.signal }
        )
      );
      if (token === request) resources = result;
    } catch {
      if (token === request) failed = true;
    } finally {
      if (token === request) loading = false;
    }
  }
  $effect(() => {
    void load(serviceId);
  });
  onDestroy(() => {
    request++;
    controller?.abort();
  });
</script>

<section aria-label={at("console_nodes_resources")} aria-busy={loading}>
  {#if loading}<p role="status">{at("loading")}</p>
  {:else if failed}<p role="alert">{at("console_nodes_resources_failed")}</p>
    <AdminButton onclick={() => load(serviceId)}>{at("refresh")}</AdminButton>
  {:else if resources}<ConsoleServiceResourcesView
      {resources}
      {at}
      {routePrefix}
      currentUrl={typeof window === "undefined"
        ? "http://localhost/admin/services"
        : window.location.href}
    />{/if}
</section>
