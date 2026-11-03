<script lang="ts">
  import { AdminButton } from "$components/patterns/admin/index.js";
  import type {
    ConsoleNode,
    ConsoleNodeSource,
    ConsoleNodeTraffic,
    ConsoleNodesTranslate,
  } from "$lib/admin/consoleNodesTypes";
  import ConsoleNodeCardGrid from "./ConsoleNodeCardGrid.svelte";
  import ConsoleNodeTable from "./ConsoleNodeTable.svelte";
  let {
    nodes,
    source,
    traffic,
    stale = false,
    compact = false,
    at,
    onOpenNode,
    table = $bindable(false),
  }: {
    nodes: ConsoleNode[];
    source?: ConsoleNodeSource;
    traffic?: ConsoleNodeTraffic | null;
    stale?: boolean;
    compact?: boolean;
    at: ConsoleNodesTranslate;
    onOpenNode?: (id: string) => void;
    table?: boolean;
  } = $props();
</script>

<div class="inventory-view" role="group" aria-label={at("console_nodes_view")}>
  <AdminButton size="sm" aria-pressed={!table} onclick={() => (table = false)}
    >{at("console_nodes_view_cards")}</AdminButton
  >
  <AdminButton size="sm" aria-pressed={table} onclick={() => (table = true)}
    >{at("console_nodes_view_table")}</AdminButton
  >
</div>
<div hidden={table}>
  <ConsoleNodeCardGrid {compact} {nodes} {source} {traffic} {stale} {at} {onOpenNode} />
</div>
<div hidden={!table}><ConsoleNodeTable {nodes} {source} {traffic} {stale} {at} {onOpenNode} /></div>

<style>
  .inventory-view {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .inventory-view ~ div {
    min-width: 0;
  }
</style>
