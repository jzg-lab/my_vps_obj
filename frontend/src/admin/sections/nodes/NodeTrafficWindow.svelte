<script lang="ts">
  import { AdminBadge, AdminField, AdminSelect } from "$components/patterns/admin/index.js";
  import { nodeTrafficWindows } from "$lib/admin/consoleNodesNavigation";
  import { nodeTrafficDate } from "$lib/admin/consoleNodesTraffic";
  import type {
    ConsoleNodeTraffic,
    ConsoleNodeTrafficPreset,
    ConsoleNodesTranslate,
  } from "$lib/admin/consoleNodesTypes";

  let {
    value,
    traffic,
    at,
    loading = false,
    onChange,
  }: {
    value: ConsoleNodeTrafficPreset;
    traffic: ConsoleNodeTraffic | null;
    at: ConsoleNodesTranslate;
    loading?: boolean;
    onChange: (value: ConsoleNodeTrafficPreset) => void;
  } = $props();

  const items = $derived(
    nodeTrafficWindows.map((value) => ({ value, label: at(`console_nodes_window_${value}`) }))
  );
</script>

<section class="node-traffic-window" aria-label={at("console_nodes_window_label")}>
  <div class="window-selector">
    <AdminField label={at("console_nodes_window_label")}>
      <AdminSelect
        {value}
        {items}
        wrapLabels
        ariaLabel={at("console_nodes_window_label")}
        onValueChange={(next) => {
          const window = nodeTrafficWindows.find((item) => item === next);
          if (window && window !== value) onChange(window);
        }}
      />
    </AdminField>
  </div>
  {#if !loading}
    <div class="window-evidence" role="status">
      {#if traffic}
        <AdminBadge variant={traffic.availability === "available" ? "muted" : "warning"}>
          {at(`console_nodes_availability_${traffic.availability}`)}
        </AdminBadge>
        <p data-traffic-boundaries>
          {at("console_nodes_window_boundaries", {
            start: nodeTrafficDate(traffic.start_at, at),
            end: nodeTrafficDate(traffic.end_at, at),
          })}
        </p>
        <p data-traffic-coverage>
          {at("console_nodes_window_coverage", {
            matched: traffic.matched_nodes,
            total: traffic.inventory_nodes ?? at("console_unknown"),
          })}
        </p>
        <p data-traffic-read-time>
          {at("console_nodes_last_success")}: {nodeTrafficDate(traffic.last_success_at, at)}
          · {at("console_nodes_attempted")}: {nodeTrafficDate(traffic.attempted_at, at)}
        </p>
        {#if traffic.error}<p>{at(`console_nodes_window_${traffic.error}`)}</p>{/if}
      {:else}
        <p>{at("console_nodes_window_missing")}</p>
      {/if}
      <p>{at("console_nodes_window_source")}</p>
      <p>{at("console_nodes_window_history")}</p>
    </div>
  {/if}
</section>

<style>
  .node-traffic-window,
  .window-evidence {
    display: grid;
    gap: 8px;
    min-width: 0;
  }
  .window-selector {
    width: 100%;
    max-width: 32rem;
    min-width: 0;
  }
  .window-evidence {
    justify-items: start;
    color: var(--admin-muted);
    overflow-wrap: anywhere;
    font-size: 12px;
  }
  p {
    margin: 0;
  }
</style>
