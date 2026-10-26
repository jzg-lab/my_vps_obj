<script lang="ts">
  import { AdminBadge, AdminButton } from "$components/patterns/admin/index.js";
  import AdminMetricChart from "$components/patterns/admin/AdminMetricChart.svelte";
  import type { ConsoleNodesPage, ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import { nodeWindowTrafficQuality, nodeTrafficDate } from "$lib/admin/consoleNodesTraffic";
  import { serviceBytes } from "$lib/admin/servicePlans";
  let {
    nodes,
    stale = false,
    comparison = false,
    at,
    onNode,
  }: {
    nodes: ConsoleNodesPage | null;
    stale?: boolean;
    comparison?: boolean;
    at: ConsoleNodesTranslate;
    onNode: (id: string) => void;
  } = $props();
  const dates = $derived(
    [
      ...new Set(
        nodes?.nodes.flatMap((node) => node.daily_traffic?.map((day) => day.date) ?? []) ?? []
      ),
    ].sort()
  );
  const series = $derived(
    nodes?.nodes.map((node) => ({
      label: node.name,
      values: dates.map(
        (date) => node.daily_traffic?.find((day) => day.date === date)?.bytes ?? null
      ),
    })) ?? []
  );
  const maximum = $derived(
    Math.max(
      0,
      ...(nodes?.nodes.map((node) =>
        nodeWindowTrafficQuality(node, nodes.traffic) === "reported"
          ? (node.window_traffic_bytes ?? 0)
          : 0
      ) ?? [])
    )
  );
</script>

<section
  class="node-traffic-panel"
  data-node-traffic-comparison={comparison || undefined}
  data-overview-chart={!comparison ? "traffic" : undefined}
>
  <header>
    <h3>{at(comparison ? "console_ops_traffic_title" : "console_visual_daily")}</h3>
    {#if stale}<AdminBadge variant="warning">{at("console_stale")}</AdminBadge>{/if}
  </header>
  <p>{at("console_node_daily_scope")}</p>
  <AdminMetricChart
    title={at(comparison ? "console_node_daily_traffic" : "console_visual_daily")}
    labels={dates.map((date) => date.slice(5))}
    {series}
    variant="bar"
    height={comparison ? 280 : 240}
    format={serviceBytes}
    missingLabel={at("console_visual_history_missing")}
    tableLabel={at("console_visual_table")}
    timeLabel={at("console_visual_day")}
  />
  {#if comparison}<ul class="metric-bars" aria-label={at("console_ops_traffic_title")}>
      {#each nodes?.nodes ?? [] as node (node.id)}
        {@const value =
          nodeWindowTrafficQuality(node, nodes?.traffic) === "reported"
            ? node.window_traffic_bytes
            : null}
        <li>
          <div>
            <AdminButton size="sm" onclick={() => onNode(node.id)}>{node.name}</AdminButton><strong
              >{value === null ? at("console_nodes_window_missing") : serviceBytes(value)}</strong
            >
          </div>
          <div class="track" class:unknown={value === null} aria-hidden="true">
            <span style={`width:${value !== null && maximum ? (value / maximum) * 100 : 0}%`}
            ></span>
          </div>
        </li>
      {/each}
    </ul>{/if}
  {#if nodes?.traffic}<p data-overview-window>
      {nodeTrafficDate(nodes.traffic.start_at, at)} — {nodeTrafficDate(nodes.traffic.end_at, at)}
    </p>
    <p>
      {at("console_nodes_window_coverage", {
        matched: nodes.traffic.matched_nodes,
        total: nodes.traffic.inventory_nodes ?? at("console_unknown"),
      })}
    </p>{/if}
  <p>{at("console_node_sample", { count: nodes?.nodes.length ?? 0 })}</p>
</section>

<style>
  .node-traffic-panel {
    min-width: 0;
    display: grid;
    gap: 12px;
    padding: 20px;
    border: 1px solid var(--admin-border);
    border-radius: 14px;
    background: var(--admin-surface);
  }
  header,
  li > div:first-child {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }
  h3,
  p {
    margin: 0;
  }
  h3 {
    font-size: 16px;
  }
  p {
    color: var(--admin-muted);
    font-size: 12px;
    line-height: 1.6;
    overflow-wrap: anywhere;
  }
  ul {
    display: grid;
    gap: 16px;
    list-style: none;
    padding: 0;
    margin: 0;
  }
  strong {
    font-size: 13px;
  }
  .track {
    height: 8px;
    margin-top: 8px;
    border-radius: 4px;
    background: color-mix(in srgb, var(--admin-muted) 15%, transparent);
    overflow: hidden;
  }
  .track span {
    display: block;
    height: 100%;
    background: var(--accent);
  }
  .unknown {
    background: repeating-linear-gradient(
      135deg,
      transparent 0 6px,
      color-mix(in srgb, var(--admin-muted) 25%, transparent) 6px 12px
    );
  }
</style>
