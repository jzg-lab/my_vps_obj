<script lang="ts">
  import { navigateConsoleLink } from "$lib/admin/consoleNavigation";
  import { onDestroy, onMount, tick, untrack } from "svelte";
  import Input from "$components/ui/input.svelte";
  import {
    AdminButton,
    AdminBadge,
    AdminEmptyState,
    AdminField,
    AdminListToolbar,
    AdminPagination,
    AdminSelect,
  } from "$components/patterns/admin/index.js";
  import { unwrap, type ApiClient } from "$lib/webapp/publicApi";
  import {
    consoleNodeDetailPath,
    consoleNodesListPath,
    nodeRelatedUrl,
    nodesRouteUrl,
    readNodesRoute,
    type NodesRoute,
  } from "$lib/admin/consoleNodesNavigation";
  import type {
    ConsoleNodeDetail as Detail,
    ConsoleNodesPage,
    ConsoleNodesTranslate,
  } from "$lib/admin/consoleNodesTypes";
  import type { ConsoleNodeMetadata } from "$lib/admin/consoleNodeMetadata";
  import ConsoleNodeDetail from "./nodes/ConsoleNodeDetail.svelte";
  import ConsoleNodeSources from "./nodes/ConsoleNodeSources.svelte";
  import ConsoleNodeInventory from "./nodes/ConsoleNodeInventory.svelte";
  import ConsoleNodeTrafficChart from "./nodes/ConsoleNodeTrafficChart.svelte";
  import NodeTrafficWindow from "./nodes/NodeTrafficWindow.svelte";
  import ResourceCreateDialog from "./nodes/ResourceCreateDialog.svelte";
  import { resourceOperationsUrl } from "$lib/admin/resourceOperations";
  import { Tabs } from "$components/ui/primitives.js";
  import {
    nodeAssetsViewUrl,
    readNodeAssetsRoute,
    type NodeAssetView,
  } from "$lib/admin/consoleNodeAssets";
  import ConsoleNodeAssets from "./nodes/ConsoleNodeAssets.svelte";
  import { consoleAccessDenied } from "$lib/admin/consoleServices";

  let {
    api,
    at,
    routePrefix = "",
    onOpenUserCard,
  }: {
    api: ApiClient["api"];
    at: ConsoleNodesTranslate;
    routePrefix?: string;
    onOpenUserCard: (userId: unknown) => void;
  } = $props();
  const initialRoute = readNodesRoute(typeof window === "undefined" ? "" : window.location.search);
  let route = $state(initialRoute);
  let inputQuery = $state(initialRoute.query);
  let currentUrl = $state(
    typeof window === "undefined" ? "http://localhost/admin/nodes" : window.location.href
  );
  const assetRoute = $derived(readNodeAssetsRoute(new URL(currentUrl).search));
  const activeView = $derived(assetRoute.view);
  const routeScope = $derived(JSON.stringify(route));
  let table = $state(false);
  function navigateAssets(view: NodeAssetView, page?: number) {
    const url = nodeAssetsViewUrl(window.location.href, view, page);
    window.history.pushState(null, "", url);
    route = readNodesRoute(url.search);
    currentUrl = url.href;
  }
  let data = $state<ConsoleNodesPage | null>(null);
  let detail = $state<Detail | null>(null);
  let loading = $state(true);
  let failed = $state(false);
  let onboarding = $state(false);
  let onboardingTrigger: HTMLElement | null = null;
  let nodeActions = $state<HTMLDivElement>();
  async function startPendingOnboarding() {
    navigateAssets("managed");
    await tick();
    onboardingTrigger = nodeActions?.querySelector("button") ?? null;
    onboarding = true;
  }
  async function closeOnboarding() {
    onboarding = false;
    await load(route);
    await tick();
    onboardingTrigger?.focus();
  }
  let request = 0;
  let controller: AbortController | null = null;
  let scope = "";
  let listSnapshot: { scope: string; data: ConsoleNodesPage } | null = null;
  const statuses = ["all", "online", "offline", "unknown"] as const;
  const items = $derived(
    statuses.map((value) => ({
      value,
      label: at(value === "all" ? "console_all" : `console_nodes_status_${value}`),
    }))
  );

  function navigate(patch: Partial<NodesRoute>) {
    route = { ...route, ...patch };
    const url = nodesRouteUrl(window.location.href, route, routePrefix);
    url.searchParams.delete("nodes_view");
    window.history.pushState(null, "", url);
    currentUrl = url.href;
  }
  function changeStatus(value: string) {
    const status = statuses.find((status) => status === value) ?? "all";
    navigate({ status, page: 0 });
  }
  async function load(current: NodesRoute) {
    const token = ++request;
    controller?.abort();
    controller = new AbortController();
    loading = true;
    const nextScope = current.nodeId
      ? consoleNodeDetailPath(current)
      : consoleNodesListPath(current);
    if (scope !== nextScope) {
      scope = nextScope;
      failed = false;
      data = !current.nodeId && listSnapshot?.scope === scope ? listSnapshot.data : null;
      detail = null;
    }
    try {
      if (current.nodeId) {
        const result = unwrap(
          await api(consoleNodeDetailPath(current), { signal: controller.signal })
        );
        if (request !== token) return;
        detail = result;
        failed = false;
        if (
          result.service_total !== null &&
          current.relatedPage > 0 &&
          current.relatedPage * result.page_size >= result.service_total
        )
          navigate({
            relatedPage: Math.max(0, Math.ceil(result.service_total / result.page_size) - 1),
          });
      } else {
        const result = unwrap(
          await api(consoleNodesListPath(current), { signal: controller.signal })
        );
        if (request !== token) return;
        data = result;
        failed = false;
        listSnapshot = { scope: nextScope, data: result };
        if (
          result.total !== null &&
          current.page > 0 &&
          current.page * result.page_size >= result.total
        )
          navigate({ page: Math.max(0, Math.ceil(result.total / result.page_size) - 1) });
      }
    } catch (error) {
      if (request === token) {
        failed = true;
        if (consoleAccessDenied(error)) {
          data = null;
          detail = null;
          listSnapshot = null;
        }
      }
    } finally {
      if (request === token) loading = false;
    }
  }
  async function updateNodeMetadata(metadata: ConsoleNodeMetadata | null) {
    if (!detail) return;
    detail = {
      ...detail,
      node: {
        ...detail.node,
        display_name: metadata?.display_name ?? null,
        region: metadata?.region ?? null,
        provider: metadata?.provider ?? null,
        country_override: metadata?.country_code ?? null,
        country_lookup_ip: metadata?.country_lookup_ip ?? null,
        country_code: metadata?.country_code ?? null,
        country_source: metadata?.country_code ? "manual" : "unknown",
        country_ip: null,
        country_looked_up_at: null,
      },
    };
    await load(route);
  }
  $effect(() => {
    const view = activeView;
    void routeScope;
    untrack(() => {
      if (view === "unmanaged") {
        request++;
        controller?.abort();
        data = null;
        detail = null;
        scope = "";
        loading = false;
        return;
      }
      void load({ ...route });
    });
  });
  onMount(() => {
    const restore = () => {
      route = readNodesRoute(window.location.search);
      inputQuery = route.query;
      currentUrl = window.location.href;
    };
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  });
  onDestroy(() => {
    request++;
    controller?.abort();
  });
</script>

<section class="console-nodes" aria-busy={loading} aria-label={at("console_nodes")}>
  {#if !route.nodeId}<div class="nodes-navigation">
      <Tabs.Root
        class="admin-tabs-root"
        value={assetRoute.view}
        onValueChange={(value) => {
          if (value === "managed" || value === "unmanaged") navigateAssets(value);
        }}
      >
        <Tabs.List class="admin-tabs-list" aria-label={at("console_node_assets_views")}>
          <Tabs.Trigger class="admin-tabs-trigger" value="managed"
            >{at("console_node_assets_managed")}</Tabs.Trigger
          >
          <Tabs.Trigger class="admin-tabs-trigger" value="unmanaged"
            >{at("console_node_assets_pending")}</Tabs.Trigger
          >
        </Tabs.List>
      </Tabs.Root>
      {#if assetRoute.view === "managed"}<div class="node-actions" bind:this={nodeActions}>
          <AdminButton
            size="sm"
            variant="primary"
            onclick={(event) => {
              onboardingTrigger =
                event.currentTarget instanceof HTMLElement ? event.currentTarget : null;
              onboarding = true;
            }}>{at("resource_ops_action_node_create")}</AdminButton
          >
          <a
            href={resourceOperationsUrl(currentUrl, routePrefix).href}
            onclick={navigateConsoleLink}>{at("resource_ops_title")}</a
          >
        </div>{/if}
    </div>{/if}
  {#if assetRoute.view === "unmanaged"}
    <ConsoleNodeAssets
      {api}
      {at}
      page={assetRoute.page}
      onPageChange={(page) => navigateAssets("unmanaged", page)}
      onStartOnboarding={startPendingOnboarding}
    />
  {:else}
    {#if route.serviceId}<p>
        <a
          href={nodeRelatedUrl(currentUrl, { serviceId: route.serviceId }, routePrefix).href}
          onclick={navigateConsoleLink}>{at("console_nodes_return_service")}: {route.serviceId}</a
        >
        · {at("console_nodes_inventory_scope")}
      </p>{/if}
    {#if !route.nodeId}
      <p>{at("console_nodes_purpose")}</p>
      <AdminListToolbar
        compact
        total={data?.total ?? undefined}
        totalLabel={at("console_nodes_count")}
        columns={1}
        onsubmit={() => navigate({ query: inputQuery.trim(), page: 0 })}
      >
        {#snippet search()}<Input
            bind:value={inputQuery}
            maxlength={200}
            aria-label={at("console_nodes_search")}
            placeholder={at("console_nodes_search")}
          />{/snippet}
        {#snippet searchActions()}<AdminButton type="submit">{at("search")}</AdminButton>{/snippet}
        {#snippet filters()}<AdminField label={at("console_node_metrics_control_status")}
            ><AdminSelect
              value={route.status}
              {items}
              ariaLabel={at("console_node_metrics_control_status")}
              onValueChange={changeStatus}
            /></AdminField
          >{/snippet}
        {#snippet actions()}<AdminButton disabled={loading} onclick={() => load(route)}
            >{at("refresh")}</AdminButton
          >{/snippet}
      </AdminListToolbar>
    {/if}
    <div class="node-controls">
      <NodeTrafficWindow
        value={route.trafficWindow}
        traffic={detail?.traffic ?? data?.traffic ?? null}
        {at}
        {loading}
        onChange={(trafficWindow) => navigate({ trafficWindow })}
      />
      {#if detail}<AdminButton size="sm" disabled={loading} onclick={() => load(route)}
          >{at("refresh")}</AdminButton
        >{/if}
    </div>
    {#if loading}<p role="status">{at("loading")}</p>{/if}
    {#if failed}<p role="alert">
        {at(data || detail ? "console_refresh_failed" : "console_nodes_load_failed")}
      </p>{/if}
    {#if failed && !data && !detail}
      {#if route.nodeId}<div>
          <AdminButton onclick={() => load(route)}>{at("refresh")}</AdminButton>
          <AdminButton onclick={() => navigate({ nodeId: "", relatedPage: 0 })}
            >{at("console_nodes_back")}</AdminButton
          >
        </div>{/if}
    {:else if detail}
      <ConsoleNodeDetail
        {api}
        {detail}
        {at}
        {currentUrl}
        {routePrefix}
        {onOpenUserCard}
        page={route.relatedPage}
        {loading}
        stale={failed}
        onPageChange={(relatedPage) => navigate({ relatedPage })}
        onMetadataSaved={updateNodeMetadata}
        onBack={() => navigate({ nodeId: "", relatedPage: 0 })}
      />
    {:else if data}
      {#if data.nodes.length}
        <ConsoleNodeInventory
          bind:table
          nodes={data.nodes}
          traffic={data.traffic}
          source={data.sources.find((source) => source.source === "nodes")}
          {at}
          stale={failed}
          onOpenNode={(nodeId) => navigate({ nodeId, relatedPage: 0 })}
        />
      {:else}<AdminEmptyState tone="card"
          >{at(
            data.coverage === "unavailable"
              ? "console_nodes_inventory_unavailable"
              : data.total === 0
                ? "console_nodes_empty"
                : "console_nodes_no_known_matches"
          )}</AdminEmptyState
        >{/if}
      <ConsoleNodeTrafficChart
        nodes={data}
        comparison
        stale={failed}
        {at}
        onNode={(nodeId) => navigate({ nodeId, relatedPage: 0 })}
      />
      <AdminPagination
        page={route.page}
        total={data.total}
        pageCount={data.total === null ? null : Math.ceil(data.total / data.page_size)}
        onPageChange={data.total === null ? null : (page) => navigate({ page })}
        onPrev={() => navigate({ page: route.page - 1 })}
        onNext={() => navigate({ page: route.page + 1 })}
        prevDisabled={route.page === 0}
        nextDisabled={data.nodes.length < data.page_size}
        prevLabel={at("services_previous")}
        nextLabel={at("services_next")}
        pageLabel={at("services_page")}
        ofLabel={at("services_of")}
        totalLabel={at("console_nodes_count")}
        jumpLabel={at("services_page")}
        jumpAriaLabel={at("services_go_page")}
        goLabel={at("services_go_page")}
      />
      <details class="inventory-evidence">
        <summary
          >{at("console_ops_chart_evidence")} · <AdminBadge
            variant={data.coverage === "complete" ? "muted" : "warning"}
            >{at(`console_nodes_coverage_${data.coverage}`)}</AdminBadge
          ></summary
        >
        <p class="admin-muted">{at("console_nodes_inventory_scope")}</p>
        <ConsoleNodeSources
          coverage={data.coverage}
          sources={data.sources}
          {at}
          showCoverage={false}
        />
      </details>
    {/if}
  {/if}
</section>

{#if onboarding && assetRoute.view === "managed"}<ResourceCreateDialog
    {api}
    {at}
    kind="node"
    {routePrefix}
    {onOpenUserCard}
    onclose={closeOnboarding}
  />{/if}

<style>
  .console-nodes {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 16px;
    min-width: 0;
  }
  .nodes-navigation,
  .node-actions {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }
  .nodes-navigation {
    justify-content: space-between;
  }
  .node-controls {
    display: flex;
    align-items: end;
    gap: 12px;
    flex-wrap: wrap;
  }
  .node-controls :global(.node-traffic-window) {
    flex: 1 1 400px;
  }
  .node-actions {
    font-size: 12px;
  }
  .inventory-evidence summary {
    cursor: pointer;
  }
  .inventory-evidence p {
    margin-block: 12px;
  }
  p {
    margin: 0;
    overflow-wrap: anywhere;
  }
  a {
    color: var(--accent);
  }
</style>
