<script lang="ts">
  import { AdminBadge, AdminEntityLink, AdminTable } from "$components/patterns/admin/index.js";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import { serviceDate } from "$lib/webapp/independentServices";
  import {
    nodeControlStatus,
    nodeMetricQuality,
    nodeMetricRows,
    nodeMetricText,
    type MetricsNode,
    type MetricsSource,
  } from "./nodeSystemMetrics";

  let {
    node,
    source,
    at,
  }: {
    node: MetricsNode;
    source?: MetricsSource;
    at: ConsoleNodesTranslate;
  } = $props();
  const nodeSource = $derived(source?.source === "nodes" ? source : undefined);
</script>

<section class="node-system-metrics" aria-label={at("console_node_metrics_title")}>
  <h3>{at("console_node_metrics_title")}</h3>
  <AdminEntityLink kind="code" label={node.name} idText={node.id} />
  <p>{at("console_node_metrics_scope")}</p>

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
</style>
