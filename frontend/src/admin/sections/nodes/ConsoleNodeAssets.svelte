<script lang="ts">
  import { onDestroy, tick } from "svelte";
  import {
    AdminButton,
    AdminEmptyState,
    AdminListToolbar,
    AdminPagination,
  } from "$components/patterns/admin/index.js";
  import { Plus, RefreshCw } from "$components/ui/icons.js";
  import type { ApiClient } from "$lib/webapp/publicApi";
  import {
    loadNodeAssets,
    type NodeAssetAction,
    type NodeAssetsPage,
  } from "$lib/admin/consoleNodeAssets";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import ConsoleNodeAssetTable from "./ConsoleNodeAssetTable.svelte";
  import ConsoleNodeAssetDialog from "./ConsoleNodeAssetDialog.svelte";

  let {
    api,
    at,
    page,
    onPageChange,
  }: {
    api: ApiClient["api"];
    at: ConsoleNodesTranslate;
    page: number;
    onPageChange: (page: number) => void;
  } = $props();
  let data = $state<NodeAssetsPage | null>(null);
  let loading = $state(true);
  let failed = $state(false);
  let action = $state<NodeAssetAction | null>(null);
  let message = $state("");
  let root: HTMLElement;
  let trigger: HTMLElement | null = null;
  let controller: AbortController | null = null;
  let request = 0;
  async function load(currentPage: number) {
    const token = ++request;
    controller?.abort();
    controller = new AbortController();
    loading = true;
    failed = false;
    data = null;
    try {
      const result = await loadNodeAssets(api, currentPage, controller.signal);
      if (request !== token) return;
      data = result;
      if (currentPage > 0 && currentPage * result.page_size >= result.total)
        onPageChange(Math.max(0, Math.ceil(result.total / result.page_size) - 1));
    } catch {
      if (request === token) failed = true;
    } finally {
      if (request === token) loading = false;
    }
  }
  $effect(() => {
    void load(page);
  });
  onDestroy(() => {
    request++;
    controller?.abort();
  });
  function open(next: NodeAssetAction, target: HTMLElement) {
    action = next;
    trigger = target;
    message = "";
  }
  async function restoreFocus() {
    await tick();
    if (action !== null) return;
    if (trigger?.isConnected) trigger.focus();
    else root?.querySelector<HTMLButtonElement>("button")?.focus();
  }
  async function close() {
    action = null;
    await restoreFocus();
  }
  async function saved(kind: NodeAssetAction["kind"]) {
    action = null;
    message = kind === "delete" ? "console_node_assets_deleted" : "console_node_assets_saved";
    if (kind === "create" && page !== 0) onPageChange(0);
    else await load(page);
    await restoreFocus();
  }
</script>

<section
  bind:this={root}
  class="node-assets"
  aria-label={at("console_node_assets_pending")}
  aria-busy={loading}
>
  <p class="admin-muted">{at("console_node_assets_scope")}</p>
  <AdminListToolbar total={data?.total} totalLabel={at("console_node_assets_count")}>
    {#snippet actions()}
      <AdminButton
        variant="primary"
        onclick={(event) => {
          if (event.currentTarget instanceof HTMLElement)
            open({ kind: "create" }, event.currentTarget);
        }}><Plus size={16} />{at("console_node_assets_add")}</AdminButton
      >
      <AdminButton
        disabled={loading}
        title={at("refresh")}
        aria-label={at("refresh")}
        size="icon"
        onclick={() => load(page)}><RefreshCw size={16} /></AdminButton
      >
    {/snippet}
  </AdminListToolbar>
  {#if message}<p role="status">{at(message)}</p>{/if}
  {#if loading}<p role="status">{at("loading")}</p>
  {:else if failed}<AdminEmptyState tone="card"
      ><p role="alert">{at("console_node_assets_load_failed")}</p>
      <AdminButton onclick={() => load(page)}>{at("retry")}</AdminButton></AdminEmptyState
    >
  {:else if data}
    {#if data.items.length}<ConsoleNodeAssetTable assets={data.items} {at} onAction={open} />
    {:else}<AdminEmptyState tone="card">{at("console_node_assets_empty")}</AdminEmptyState>{/if}
    <AdminPagination
      {page}
      total={data.total}
      pageCount={Math.ceil(data.total / data.page_size)}
      {onPageChange}
      prevLabel={at("services_previous")}
      nextLabel={at("services_next")}
      pageLabel={at("services_page")}
      ofLabel={at("services_of")}
      totalLabel={at("console_node_assets_count")}
      jumpLabel={at("services_page")}
      jumpAriaLabel={at("services_go_page")}
      goLabel={at("services_go_page")}
    />
  {/if}
</section>

{#if action}<ConsoleNodeAssetDialog {api} {at} {action} onclose={close} onsaved={saved} />{/if}

<style>
  .node-assets {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  p {
    margin: 0;
    overflow-wrap: anywhere;
  }
</style>
