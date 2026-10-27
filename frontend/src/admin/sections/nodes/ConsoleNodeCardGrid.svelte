<script lang="ts">
  import {
    AdminBadge,
    AdminButton,
    AdminEntityLink,
    AdminCopyableValue,
  } from "$components/patterns/admin/index.js";
  import { copyTextToClipboard } from "$lib/webapp/clipboard";
  import { serviceDate } from "$lib/webapp/independentServices";
  import { serviceBytes } from "$lib/admin/servicePlans";
  import { nodeWindowTrafficQuality } from "$lib/admin/consoleNodesTraffic";
  import type {
    ConsoleNode,
    ConsoleNodeSource,
    ConsoleNodeTraffic,
    ConsoleNodesTranslate,
  } from "$lib/admin/consoleNodesTypes";
  import { nodeControlStatus, nodeMetricQuality } from "./nodeSystemMetrics";
  import { consoleNodeCountryLabel } from "$lib/admin/consoleNodeMetadata";

  let {
    nodes,
    at,
    source,
    traffic,
    stale = false,
    compact = false,
    onOpenNode,
  }: {
    nodes: ConsoleNode[];
    at: ConsoleNodesTranslate;
    source?: ConsoleNodeSource;
    traffic?: ConsoleNodeTraffic | null;
    stale?: boolean;
    compact?: boolean;
    onOpenNode?: (id: string) => void;
  } = $props();

  let copyMessage = $state("");
  async function copyId(id: string) {
    copyMessage = at((await copyTextToClipboard(id)) ? "value_copied" : "console_copy_failed");
  }
  function metricValue(
    node: ConsoleNode,
    field:
      "memory_used_bytes" | "memory_total_bytes" | "rx_bytes_per_second" | "tx_bytes_per_second"
  ) {
    const value = node.system?.[field];
    return nodeMetricQuality(node.system, field) === "reported" && typeof value === "number"
      ? value
      : null;
  }

  function memoryPercent(node: ConsoleNode) {
    const used = metricValue(node, "memory_used_bytes");
    const total = metricValue(node, "memory_total_bytes");
    return used !== null && total !== null && total > 0
      ? Math.min(100, Math.max(0, (used / total) * 100))
      : null;
  }
</script>

<div class="node-card-grid" class:compact aria-label={at("console_node_visuals_title")}>
  {#each nodes as node (node.id)}
    {@const controlStatus = stale ? "unknown" : nodeControlStatus(node, source)}
    {@const oldValue = stale || source?.availability === "stale"}
    {@const memory = memoryPercent(node)}
    {@const trafficQuality = nodeWindowTrafficQuality(node, traffic)}
    <article class="node-card" data-node-card-id={node.id}>
      <header class="node-card-head">
        <div class="node-card-title">
          <AdminEntityLink
            kind="code"
            label={node.display_name ?? node.name}
            title={`${node.name} · ${node.id}`}
            onclick={onOpenNode ? () => onOpenNode?.(node.id) : undefined}
          />
          <small>{node.address ?? at("console_unknown")}</small>
          <small
            >{at("console_nodes_country")}: {consoleNodeCountryLabel(node.country_code) ??
              at("console_unknown")}</small
          >
          {#if node.region}<small>{at("console_nodes_region")}: {node.region}</small>{/if}
          {#if node.provider}<small>{at("console_nodes_provider")}: {node.provider}</small>{/if}
          {#if node.display_name}<small>{at("console_nodes_panel_name")}: {node.name}</small>{/if}
        </div>
        <AdminBadge
          variant={controlStatus === "online"
            ? "success"
            : controlStatus === "offline"
              ? "danger"
              : "muted"}>{at(`console_node_control_${controlStatus}`)}</AdminBadge
        >
      </header>
      {#if !compact}<p class="card-note">
          {at("console_observed_at")}: {node.observed_at
            ? serviceDate(node.observed_at)
            : at("console_unknown")}
        </p>
      {/if}
      {#if oldValue}<p class="card-note">{at("console_stale")}</p>{/if}
      {#if node.is_disabled}<p class="card-note">{at("console_nodes_disabled")}</p>{/if}
      {#if node.is_connecting}<p class="card-note">{at("console_nodes_connecting")}</p>{/if}
      <div class="node-card-metrics">
        <div class="node-card-metric">
          <span>{at("console_nodes_window_traffic")}</span>
          <strong
            >{trafficQuality === "reported" && node.window_traffic_bytes !== null
              ? serviceBytes(node.window_traffic_bytes)
              : at(
                  trafficQuality === "invalid"
                    ? "console_nodes_window_invalid"
                    : "console_nodes_window_missing"
                )}</strong
          >
        </div>
      </div>
      <div class="node-card-bars">
        <div class="bar-metric">
          <div>
            <span>{at("console_node_metrics_memory_used_bytes")}</span><strong
              >{memory === null ? at("console_unknown") : `${memory.toFixed(0)}%`}</strong
            >
          </div>
          <div class="bar-track" aria-hidden="true">
            <span style={`width:${memory ?? 0}%`} class:bar-unknown={memory === null}></span>
          </div>
        </div>
      </div>
      {#if compact}<small class="card-note"
          >{node.groups.map((group) => group.name).join(" / ") || at("console_unknown")}</small
        >{/if}
      {#if !compact}<details class="card-note node-auxiliary">
          <summary>{at("console_node_auxiliary")}</summary>
          <AdminCopyableValue
            value={node.id}
            wrap
            copyLabel={at("copy_value", { value: node.id })}
            oncopy={copyId}
          />
          <p>
            {at("console_nodes_online")}: {node.users_online_quality === "reported" &&
            node.users_online !== null &&
            node.users_online > 0
              ? node.users_online
              : at("console_unknown")}
          </p>
        </details>{/if}
      {#if onOpenNode}<AdminButton size="sm" onclick={() => onOpenNode?.(node.id)}
          >{at("console_nodes_detail")}</AdminButton
        >{/if}
    </article>
  {/each}
</div>
{#if copyMessage}<p role="status" class="card-note">{copyMessage}</p>{/if}

<style>
  .node-auxiliary summary {
    cursor: pointer;
    margin-bottom: 8px;
  }
  .node-auxiliary p {
    margin: 8px 0 0;
  }
  .node-card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr));
    gap: 12px;
    min-width: 0;
  }
  .node-card-grid.compact {
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 175px), 1fr));
  }
  .compact .node-card-metrics {
    grid-template-columns: 1fr;
  }
  .compact .node-card {
    padding: 12px;
    gap: 8px;
  }
  .compact .node-card-head {
    flex-direction: column;
  }
  .node-card {
    display: grid;
    align-content: start;
    gap: 12px;
    min-width: 0;
    overflow-wrap: anywhere;
    padding: 16px;
    border: 1px solid var(--admin-border);
    border-radius: 14px;
    background: var(--admin-card-bg);
    box-shadow: var(--admin-card-shadow);
  }
  .node-card-head,
  .bar-metric > div {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    align-items: flex-start;
  }
  .node-card-title,
  .node-card-metrics,
  .node-card-bars,
  .bar-metric {
    display: grid;
    gap: 8px;
    min-width: 0;
  }

  .node-card-title :global(.admin-entity-link-label),
  .node-card-title :global(.admin-entity-link-id) {
    white-space: normal;
    overflow-wrap: anywhere;
  }
  .node-card-title small,
  .node-card-metric span,
  .bar-metric span,
  .card-note {
    color: var(--admin-muted);
    overflow-wrap: anywhere;
  }
  .card-note {
    margin: 0;
    font-size: 12px;
    line-height: 1.5;
  }
  .node-card-metric {
    display: grid;
    gap: 4px;
    font-size: 12px;
  }
  .node-card-metric strong {
    font-size: 16px;
  }
  .bar-metric {
    font-size: 12px;
  }
  .node-card-metrics {
    grid-template-columns: 1fr;
  }
  .node-card-metric {
    padding: 10px;
    border-radius: 10px;
    background: color-mix(in srgb, var(--accent) 6%, var(--admin-surface));
  }
  .bar-track {
    height: 7px;
    overflow: hidden;
    border-radius: 999px;
    background: color-mix(in srgb, var(--admin-muted) 18%, transparent);
  }
  .bar-track span {
    display: block;
    height: 100%;
    border-radius: inherit;
    background: var(--accent);
  }
  .bar-track .bar-unknown {
    width: 100% !important;
    background: repeating-linear-gradient(
      135deg,
      transparent 0 6px,
      color-mix(in srgb, var(--admin-muted) 30%, transparent) 6px 12px
    );
  }
  @media (max-width: 520px) {
    .node-card-metrics {
      grid-template-columns: 1fr;
    }
  }
</style>
