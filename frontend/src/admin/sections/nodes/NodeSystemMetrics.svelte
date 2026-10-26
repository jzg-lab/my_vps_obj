<script lang="ts">
  import type { Snippet } from "svelte";
  import {
    AdminBadge,
    AdminChartEmptyState,
    AdminTable,
  } from "$components/patterns/admin/index.js";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import type { ConsoleNodeTraffic } from "$lib/admin/consoleNodesTypes";
  import { serviceBytes } from "$lib/admin/servicePlans";
  import { nodeTrafficDate, nodeWindowTrafficQuality } from "$lib/admin/consoleNodesTraffic";
  import { serviceDate } from "$lib/webapp/independentServices";
  import {
    nodeControlStatus,
    nodeMetricQuality,
    nodeMetricRows,
    nodeMetricText,
    bytesPerSecondToMbps,
    nodeSpeedSummary,
    type MetricsNode,
    type MetricsSource,
  } from "./nodeSystemMetrics";
  import AdminMetricChart from "$components/patterns/admin/AdminMetricChart.svelte";

  let {
    node,
    source,
    traffic,
    related,
    at,
  }: {
    node: MetricsNode;
    source?: MetricsSource;
    traffic?: ConsoleNodeTraffic | null;
    at: ConsoleNodesTranslate;
    related?: Snippet;
  } = $props();
  const nodeSource = $derived(source?.source === "nodes" ? source : undefined);
  const memoryPercent = $derived.by(() => {
    const total =
      nodeMetricQuality(node.system, "memory_total_bytes") === "reported"
        ? node.system?.memory_total_bytes
        : null;
    const used =
      nodeMetricQuality(node.system, "memory_used_bytes") === "reported"
        ? node.system?.memory_used_bytes
        : null;
    return typeof total === "number" && total > 0 && typeof used === "number"
      ? Math.min(100, Math.max(0, (used / total) * 100))
      : null;
  });
  const memoryLabel = $derived(
    memoryPercent === null ? at("console_unknown") : `${memoryPercent.toFixed(0)}%`
  );
  const speedSamples = $derived(node.speed_history ?? []);
  const speedSummary = $derived(nodeSpeedSummary(speedSamples));
  const speedLabels = $derived(
    speedSamples.map((sample) => serviceDate(sample.sampled_at).slice(11))
  );
  const speedSeries = $derived([
    {
      label: at("console_node_metrics_rx_bytes_per_second"),
      values: speedSamples.map((sample) => bytesPerSecondToMbps(sample.rx_bytes_per_second)),
    },
    {
      label: at("console_node_metrics_tx_bytes_per_second"),
      values: speedSamples.map((sample) => bytesPerSecondToMbps(sample.tx_bytes_per_second)),
    },
  ]);
  function speedValue(bytesPerSecond: number | null | undefined) {
    const value = bytesPerSecondToMbps(bytesPerSecond ?? null);
    return value === null
      ? at("console_unknown")
      : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} Mbps`;
  }
</script>

<section class="node-system-metrics" aria-label={at("console_node_metrics_title")}>
  <div class="system-summary">
    <section class="server-summary">
      <h3>{at("console_node_metrics_title")}</h3>
      <p>{at("console_node_metrics_scope")}</p>
      <div class="metric-visual-grid" data-node-metric-visuals>
        <article class="metric-visual-card">
          <span>{at("console_node_metrics_cpu_cores")}</span><strong
            >{nodeMetricText(node.system, nodeMetricRows[0], at)}</strong
          >
        </article>
        <article class="metric-visual-card">
          <span>{at("console_node_metrics_memory_used_bytes")}</span><strong>{memoryLabel}</strong>
          <div class="metric-bar" aria-hidden="true">
            <span
              style={`width:${memoryPercent ?? 0}%`}
              class:metric-bar-unknown={memoryPercent === null}
            ></span>
          </div>
        </article>
        <article class="metric-visual-card">
          <span>{at("console_node_metrics_load_1m")}</span><strong
            >{nodeMetricText(node.system, nodeMetricRows[5], at)}</strong
          >
        </article>
        <article class="metric-visual-card">
          <span>{at("console_node_metrics_uptime_seconds")}</span><strong
            >{nodeMetricText(node.system, nodeMetricRows[8], at)}</strong
          >
        </article>
      </div>
    </section>
    {#if related}<aside class="related-summary">{@render related()}</aside>{/if}
  </div>
  <article class="metric-visual-card metric-history-card">
    <h4>{at("console_visual_speed")}</h4>
    {#if speedSummary.latest}
      <p>{at("console_node_speed_latest")} · {serviceDate(speedSummary.latest.sampled_at)}</p>
      <div class="speed-summary" data-speed-summary>
        <div class="rx">
          <small>{at("console_node_metrics_rx_bytes_per_second")}</small><strong
            >{speedValue(speedSummary.latest.rx_bytes_per_second)}</strong
          >
        </div>
        <div class="tx">
          <small>{at("console_node_metrics_tx_bytes_per_second")}</small><strong
            >{speedValue(speedSummary.latest.tx_bytes_per_second)}</strong
          >
        </div>
        <div class="peak">
          <small>{at("console_node_speed_peak")}</small><strong
            >RX {speedValue(speedSummary.rxPeakBytesPerSecond)} · TX {speedValue(
              speedSummary.txPeakBytesPerSecond
            )}</strong
          >
        </div>
      </div>
      <AdminMetricChart
        height={300}
        title={at("console_visual_speed")}
        labels={speedLabels}
        series={speedSeries}
        format={(value) => `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} Mbps`}
        missingLabel={at("console_visual_speed_missing")}
        tableLabel={at("console_visual_table")}
        timeLabel={at("console_visual_day")}
      />
    {:else}<AdminChartEmptyState label={at("console_visual_speed_missing")} plotHeight={180} />{/if}
  </article>

  <section
    class="node-traffic-chart"
    data-node-daily-traffic
    aria-label={at("console_node_daily_traffic")}
  >
    <header>
      <h3>{at("console_node_daily_traffic")}</h3>
      <strong
        >{at("console_nodes_window_traffic")}: {nodeWindowTrafficQuality(node, traffic) ===
          "reported" && node.window_traffic_bytes !== null
          ? serviceBytes(node.window_traffic_bytes)
          : at("console_unknown")}</strong
      >
    </header>
    {#if traffic}<p>
        {nodeTrafficDate(traffic.start_at, at)} — {nodeTrafficDate(traffic.end_at, at)}
      </p>
      {#if traffic.availability !== "available"}<AdminBadge variant="warning"
          >{at(`console_nodes_availability_${traffic.availability}`)}</AdminBadge
        >{/if}
    {/if}
    <AdminMetricChart
      title={at("console_node_daily_traffic")}
      labels={(node.daily_traffic ?? []).map((day) => day.date.slice(5))}
      series={[{ label: node.name, values: (node.daily_traffic ?? []).map((day) => day.bytes) }]}
      variant="bar"
      height={280}
      format={serviceBytes}
      missingLabel={at("console_visual_history_missing")}
      tableLabel={at("console_visual_table")}
      timeLabel={at("console_visual_day")}
    />
    <p>{at("console_node_daily_scope")}</p>
  </section>

  <div class="metrics-observation" role="status">
    <p>
      {at("console_node_metrics_source")}: <AdminBadge
        wrap
        variant={nodeSource?.availability === "available" ? "muted" : "warning"}
        >{nodeSource
          ? at(`console_nodes_availability_${nodeSource.availability}`)
          : at("console_unknown")}</AdminBadge
      >
    </p>
    {#if nodeSource?.error}<p>{at(`console_node_metrics_error_${nodeSource.error}`)}</p>{/if}
    <p data-metrics-read-time>
      {at("console_nodes_last_success")}: {node.observed_at
        ? serviceDate(node.observed_at)
        : at("console_unknown")}
    </p>
    <p data-metrics-sample-time>
      {at("console_node_metrics_sample_time")}: {at("console_node_metrics_sample_unknown")}
    </p>
    {#if nodeSource}<p>
        {at("console_nodes_attempted")}: {serviceDate(nodeSource.attempted_at)}
      </p>{/if}
    <p>{at("console_node_metrics_freshness")}</p>
    {#if node.users_online_quality === "unverified_zero"}<p>
        {at("console_node_metrics_online_unverified")}
      </p>{/if}
  </div>

  <p>{at("console_node_visuals_rate_scope")}</p>
  <AdminTable layout="fixed" minWidth="0">
    <thead
      ><tr>
        <th>{at("console_node_metrics_metric")}</th>
        <th>{at("console_node_metrics_value")}</th>
        <th>{at("console_node_metrics_quality")}</th>
      </tr></thead
    >
    <tbody>
      {#each nodeMetricRows as row (row.field)}
        {@const quality = nodeMetricQuality(node.system, row.field)}
        <tr data-node-metric={row.field} data-metric-quality={quality}>
          <td data-label={at("console_node_metrics_metric")}
            >{at(`console_node_metrics_${row.field}`)}</td
          >
          <td data-label={at("console_node_metrics_value")}
            >{nodeMetricText(node.system, row, at)}</td
          >
          <td data-label={at("console_node_metrics_quality")}
            ><AdminBadge wrap variant={quality === "invalid" ? "warning" : "muted"}
              >{at(`console_node_metrics_${quality}`)}</AdminBadge
            ></td
          >
        </tr>
      {/each}
    </tbody>
  </AdminTable>
  <p>{at("console_node_metrics_load_scope")}</p>
  <p>{at("console_node_metrics_memory_scope")}</p>
  <p>{at("console_node_metrics_network_scope")}</p>

  <section aria-label={at("console_node_metrics_connectivity")}>
    <h4>{at("console_node_metrics_connectivity")}</h4>
    <p>
      {at("console_node_metrics_control_status")}: <AdminBadge wrap
        >{at(`console_nodes_status_${nodeControlStatus(node, nodeSource)}`)}</AdminBadge
      >
    </p>
    {#if node.is_disabled}<p>{at("console_nodes_disabled")}</p>{/if}
    {#if node.is_connecting}<p>{at("console_nodes_connecting")}</p>{/if}
    <p>{at("console_node_metrics_control_scope")}</p>
    <dl>
      <div>
        <dt>{at("console_node_metrics_latency")}</dt>
        <dd>{at("console_node_metrics_not_collected")}</dd>
      </div>
      <div>
        <dt>{at("console_node_metrics_packet_loss")}</dt>
        <dd>{at("console_node_metrics_not_collected")}</dd>
      </div>
    </dl>
    <p>{at("console_node_metrics_probe_missing")}</p>
  </section>
</section>

<style>
  .system-summary {
    display: grid;
    grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr);
    gap: 16px;
    align-items: stretch;
  }
  .server-summary,
  .related-summary {
    min-width: 0;
    padding: 20px;
    border: 1px solid var(--admin-border);
    border-radius: 14px;
    background: var(--admin-surface);
  }
  .server-summary {
    display: grid;
    align-content: start;
    gap: 16px;
  }
  .server-summary p {
    font-size: 12px;
    line-height: 1.6;
  }
  .metric-visual-card strong {
    font-size: 24px;
  }
  @media (max-width: 1000px) {
    .system-summary {
      grid-template-columns: minmax(0, 1fr);
    }
  }

  .node-traffic-chart {
    display: grid;
    gap: 16px;
    min-width: 0;
    padding: 20px;
    border: 1px solid var(--admin-border);
    border-radius: 14px;
    background: var(--admin-surface);
  }
  .node-traffic-chart header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .node-traffic-chart p {
    color: var(--admin-muted);
    font-size: 12px;
    overflow-wrap: anywhere;
  }
  .node-traffic-chart :global(.admin-badge) {
    justify-self: start;
  }

  .node-system-metrics,
  .metrics-observation,
  section section {
    display: grid;
    gap: 8px;
    min-width: 0;
    overflow-wrap: anywhere;
  }
  h3,
  h4,
  p,
  dl,
  dd {
    margin: 0;
  }
  p,
  dt {
    color: var(--admin-muted);
  }
  td {
    white-space: normal;
    overflow-wrap: anywhere;
  }
  dl {
    display: grid;
    gap: 8px;
  }
  dl > div {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 8px;
  }
  .metric-visual-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }
  @media (min-width: 1200px) {
    .metric-visual-grid {
      grid-template-columns: repeat(4, minmax(0, 1fr));
      align-items: start;
    }
    .metric-visual-grid .metric-visual-card {
      background: none;
      border: 0;
      padding: 8px 0;
    }
    .metric-visual-grid .metric-visual-card > span {
      font-size: 12px;
    }
  }
  .metric-visual-card {
    display: grid;
    gap: 8px;
    min-width: 0;
    padding: 12px;
    border: 1px solid var(--admin-border);
    border-radius: 12px;
    background: color-mix(in srgb, var(--accent) 5%, var(--admin-surface));
  }
  .metric-visual-card > span,
  .metric-visual-card > strong {
    overflow-wrap: anywhere;
  }
  .metric-visual-card > span {
    color: var(--admin-muted);
  }
  .metric-bar {
    height: 8px;
    overflow: hidden;
    border-radius: 999px;
    background: color-mix(in srgb, var(--admin-muted) 18%, transparent);
  }
  .metric-bar span {
    display: block;
    height: 100%;
    border-radius: inherit;
    background: var(--accent);
  }
  .metric-bar .metric-bar-unknown {
    width: 100% !important;
    background: repeating-linear-gradient(
      135deg,
      transparent 0 6px,
      color-mix(in srgb, var(--admin-muted) 30%, transparent) 6px 12px
    );
  }
  .metric-history-card {
    grid-column: 1 / -1;
  }
  .speed-summary {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1.4fr);
    gap: 16px;
  }
  .speed-summary > div {
    display: grid;
    gap: 4px;
  }
  .speed-summary small {
    color: var(--admin-muted);
  }
  .speed-summary strong {
    overflow-wrap: anywhere;
    font-size: 24px;
    font-variant-numeric: tabular-nums;
  }
  .speed-summary .rx strong {
    color: var(--accent);
  }
  .speed-summary .tx strong {
    color: var(--info);
  }
  .speed-summary .peak strong {
    font-size: 16px;
    color: var(--warning);
  }
  .metric-history-card {
    padding: 20px;
    background: var(--admin-surface);
  }
  @media (max-width: 900px) {
    .metric-visual-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
  @media (max-width: 520px) {
    .speed-summary {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .speed-summary .peak {
      grid-column: 1 / -1;
    }
    .metric-visual-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
