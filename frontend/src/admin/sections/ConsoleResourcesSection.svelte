<script lang="ts">
  import { onMount, onDestroy, tick } from "svelte";
  import Input from "$components/ui/input.svelte";
  import {
    AdminButton,
    AdminEmptyState,
    AdminField,
    AdminListToolbar,
    AdminSelect,
  } from "$components/patterns/admin";
  import { unwrap, type ApiClient } from "$lib/webapp/publicApi";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import {
    catalogResources,
    filterCatalogResources,
    readResourcesRoute,
    resourcesRouteUrl,
    type ResourceCatalog,
    type ResourcesRoute,
  } from "$lib/admin/consoleResources";
  import ConsoleResourceCatalogStatus from "./nodes/ConsoleResourceCatalogStatus.svelte";
  import ConsoleResourceCatalogTable from "./nodes/ConsoleResourceCatalogTable.svelte";
  import ConsoleResourceDetail from "./nodes/ConsoleResourceDetail.svelte";
  import ResourceCreateDialog from "./nodes/ResourceCreateDialog.svelte";
  import { resourceOperationsUrl } from "$lib/admin/resourceOperations";
  let {
    api,
    at,
    routePrefix = "",
    onOpenUserCard,
  }: {
    api: ApiClient["api"];
    at: ConsoleNodesTranslate;
    routePrefix?: string;
    onOpenUserCard: (id: unknown) => void;
  } = $props();
  const initialRoute = readResourcesRoute(
    typeof window === "undefined" ? "" : window.location.search
  );
  let route = $state(initialRoute);
  let query = $state(initialRoute.query);
  let currentUrl = $state(
    typeof window === "undefined" ? "http://localhost/admin/node-resources" : window.location.href
  );
  let catalog = $state<ResourceCatalog | null>(null);
  let loading = $state(true);
  let failed = $state(false);
  let createKind = $state<"group" | "host" | null>(null);
  let createTrigger: HTMLElement | null = null;
  async function closeCreate() {
    createKind = null;
    await load();
    await tick();
    createTrigger?.focus();
  }
  let content: HTMLElement | undefined;
  let request = 0;
  let controller: AbortController | null = null;
  const rows = $derived(catalog ? filterCatalogResources(catalog, route) : []);
  const resource = $derived(
    catalog
      ? catalogResources(catalog, route.kind).find((item) => item.id === route.resourceId)
      : undefined
  );
  function navigate(patch: Partial<ResourcesRoute>) {
    route = { ...route, ...patch };
    const url = resourcesRouteUrl(window.location.href, route, routePrefix);
    window.history.pushState(null, "", url);
    currentUrl = url.href;
  }
  async function closeDetail() {
    const id = route.resourceId;
    navigate({ resourceId: "" });
    await tick();
    const trigger = content?.querySelector<HTMLButtonElement>(
      `[data-resource-id="${CSS.escape(id)}"] button`
    );
    (trigger ?? content?.querySelector<HTMLInputElement>("input"))?.focus();
  }
  async function load() {
    const token = ++request;
    controller?.abort();
    controller = new AbortController();
    loading = true;
    failed = false;
    catalog = null;
    try {
      const result = unwrap(
        await api("/admin/console/resources/catalog", { signal: controller.signal })
      );
      if (token === request) catalog = result;
    } catch {
      if (token === request) failed = true;
    } finally {
      if (token === request) loading = false;
    }
  }
  onMount(() => {
    void load();
    const restore = () => {
      route = readResourcesRoute(window.location.search);
      query = route.query;
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

<section
  class="console-resources"
  bind:this={content}
  aria-label={at("console_catalog_title")}
  aria-busy={loading}
>
  <AdminListToolbar
    columns={1}
    total={catalog && !failed ? rows.length : undefined}
    totalLabel={at("console_catalog_known_count")}
    onsubmit={() => navigate({ query: query.trim(), resourceId: "" })}
  >
    {#snippet search()}<Input
        bind:value={query}
        maxlength={200}
        aria-label={at("console_catalog_search")}
        placeholder={at("console_catalog_search")}
      />{/snippet}
    {#snippet searchActions()}<AdminButton type="submit">{at("search")}</AdminButton>{/snippet}
    {#snippet filters()}<AdminField label={at("console_catalog_kind")}
        ><AdminSelect
          wrapLabels
          value={route.kind}
          ariaLabel={at("console_catalog_kind")}
          items={[
            { value: "group", label: at("console_nodes_groups") },
            { value: "host", label: at("console_nodes_hosts") },
          ]}
          onValueChange={(kind) =>
            navigate({ kind: kind === "host" ? "host" : "group", resourceId: "" })}
        /></AdminField
      >{/snippet}
    {#snippet actions()}<AdminButton disabled={loading} onclick={load}>{at("refresh")}</AdminButton>
      <AdminButton
        onclick={(event) => {
          createTrigger = event.currentTarget instanceof HTMLElement ? event.currentTarget : null;
          createKind = route.kind;
        }}
        >{at(
          route.kind === "group"
            ? "resource_ops_action_group_create"
            : "resource_ops_action_host_create"
        )}</AdminButton
      >{/snippet}
  </AdminListToolbar>
  <p>{at("console_catalog_scope")}</p>
  <a href={resourceOperationsUrl(currentUrl, routePrefix).href}>{at("resource_ops_title")}</a>
  {#if loading}<p role="status">{at("loading")}</p>
  {:else if failed}<p role="alert">{at("console_catalog_load_failed")}</p>
  {:else if catalog}
    <ConsoleResourceCatalogStatus {catalog} {at} />
    {#if rows.length}<ConsoleResourceCatalogTable
        {rows}
        kind={route.kind}
        {at}
        onOpen={(resourceId) => navigate({ resourceId })}
      />
    {:else}<AdminEmptyState tone="card"
        >{at(
          catalog.coverage === "complete"
            ? "console_catalog_empty"
            : "console_catalog_no_known_matches"
        )}</AdminEmptyState
      >{/if}
    {#if route.resourceId && !resource}<p role="alert">{at("console_catalog_not_found")}</p>
      <div><AdminButton onclick={closeDetail}>{at("console_catalog_back")}</AdminButton></div>{/if}
  {/if}
</section>
{#if resource && catalog && !createKind}{#key `${route.kind}:${resource.id}`}<ConsoleResourceDetail
      {api}
      {catalog}
      {resource}
      kind={route.kind}
      {at}
      {currentUrl}
      {routePrefix}
      {onOpenUserCard}
      onclose={closeDetail}
    />{/key}{/if}

{#if createKind}<ResourceCreateDialog
    {api}
    {at}
    kind={createKind}
    {routePrefix}
    {onOpenUserCard}
    onclose={closeCreate}
  />{/if}

<style>
  .console-resources {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  p {
    margin: 0;
    overflow-wrap: anywhere;
  }
</style>
