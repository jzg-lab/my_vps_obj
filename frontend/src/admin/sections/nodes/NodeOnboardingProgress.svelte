<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { AdminButton } from "$components/patterns/admin";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi";
  import type { ConsoleNodeDetail, ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import type { ResourceOperation } from "$lib/admin/resourceOperations";
  import { nodesRouteUrl, readNodesRoute } from "$lib/admin/consoleNodesNavigation";
  import { resourcesRouteUrl, readResourcesRoute } from "$lib/admin/consoleResources";
  import { nodeControlStatus } from "./nodeSystemMetrics";
  let {
    api,
    at,
    operation,
    routePrefix = "",
  }: {
    api: ApiClient["api"];
    at: ConsoleNodesTranslate;
    operation: ResourceOperation;
    routePrefix?: string;
  } = $props();
  let detail = $state<ConsoleNodeDetail | null>(null);
  let busy = $state(false);
  let failed = $state(false);
  let active = true;
  let controller: AbortController | null = null;
  const currentUrl = typeof window === "undefined" ? "https://console.test/" : window.location.href;
  const target = $derived(operation.target_id);
  async function refresh() {
    if (!target || busy) return;
    busy = true;
    failed = false;
    detail = null;
    controller = new AbortController();
    try {
      const value = unwrap(
        await api(
          builtApiPath<"/api/admin/console/nodes/{node_id}">(
            `/admin/console/nodes/${encodeURIComponent(target)}`
          ),
          { signal: controller.signal }
        )
      );
      if (active) detail = value;
    } catch {
      if (active) failed = true;
    } finally {
      if (active) busy = false;
    }
  }
  onMount(() => {
    void refresh();
  });
  onDestroy(() => {
    active = false;
    controller?.abort();
  });
</script>

<section class="onboarding-progress" aria-label={at("resource_ops_onboarding_title")}>
  <h4>{at("resource_ops_onboarding_title")}</h4>
  <p>{at("resource_ops_onboarding_registration")}</p>
  <p>
    {at("resource_ops_onboarding_management")}: {detail
      ? at(
          `console_nodes_status_${nodeControlStatus(
            detail.node,
            detail.sources.find((source) => source.source === "nodes")
          )}`
        )
      : at("console_unknown")}
  </p>
  {#if failed}<p role="alert">{at("console_nodes_load_failed")}</p>{/if}
  {#if target}<div>
      <AdminButton disabled={busy} onclick={refresh}>{at("refresh")}</AdminButton>
    </div>
    <a href={nodesRouteUrl(currentUrl, { ...readNodesRoute(""), nodeId: target }, routePrefix).href}
      >{at("console_nodes_detail")}</a
    >{/if}
  <p>{at("resource_ops_onboarding_subscription")}</p>
  <a
    href={resourcesRouteUrl(currentUrl, { ...readResourcesRoute(""), kind: "host" }, routePrefix)
      .href}>{at("console_catalog_title")}</a
  >
</section>

<style>
  .onboarding-progress {
    display: grid;
    gap: 12px;
    min-width: 0;
  }
  h4,
  p {
    margin: 0;
    overflow-wrap: anywhere;
  }
  a {
    color: var(--accent);
  }
</style>
