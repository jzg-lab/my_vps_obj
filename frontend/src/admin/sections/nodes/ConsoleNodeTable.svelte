<script lang="ts">
  import { AdminBadge, AdminEntityLink, AdminTable } from "$components/patterns/admin/index.js";
  import { serviceBytes } from "$lib/admin/servicePlans";
  import { serviceDate } from "$lib/webapp/independentServices";
  import type {
    ConsoleNode,
    ConsoleNodeTraffic,
    ConsoleNodesTranslate,
    ConsoleNodeSource,
  } from "$lib/admin/consoleNodesTypes";
  import { nodeWindowTrafficQuality } from "$lib/admin/consoleNodesTraffic";
  import { nodeControlStatus } from "./nodeSystemMetrics";
  let {
    nodes,
    at,
    onOpenNode,
    traffic,
    source,
    stale = false,
  }: {
    nodes: ConsoleNode[];
    at: ConsoleNodesTranslate;
    onOpenNode?: (id: string) => void;
    traffic?: ConsoleNodeTraffic | null;
    source?: ConsoleNodeSource;
    stale?: boolean;
  } = $props();
</script>

<AdminTable layout="fixed" minWidth={traffic !== undefined ? "1200px" : "1080px"}>
  <thead
    ><tr
      >{#each ["console_nodes_node", "console_node_metrics_control_status", "console_nodes_address", "console_nodes_groups", "console_nodes_online", ...(traffic !== undefined ? ["console_nodes_window_traffic"] : []), "console_nodes_traffic", "console_observed_at"] as key}<th
          >{at(key)}</th
        >{/each}</tr
    ></thead
  >
  <tbody
    >{#each nodes as node (node.id)}
      {@const controlStatus = stale ? "unknown" : nodeControlStatus(node, source)}
      {@const oldValue = stale || source?.availability === "stale"}
      <tr data-node-id={node.id}>
        <td class="node-identity" data-label={at("console_nodes_node")}
          ><AdminEntityLink
            kind="code"
            label={node.name}
            idText={node.id}
            onclick={onOpenNode ? () => onOpenNode?.(node.id) : undefined}
          /></td
        >
        <td data-label={at("console_node_metrics_control_status")}
          ><AdminBadge
            variant={controlStatus === "online"
              ? "success"
              : controlStatus === "offline"
                ? "danger"
                : "muted"}>{at(`console_nodes_status_${controlStatus}`)}</AdminBadge
          >
          {#if oldValue}<small
              >{at("console_nodes_previous_control", {
                status: at(`console_nodes_status_${node.status}`),
              })}</small
            >{/if}
          {#if node.is_disabled}<small>{at("console_nodes_disabled")}</small>{/if}
          {#if node.is_connecting}<small>{at("console_nodes_connecting")}</small>{/if}
        </td>
        <td data-label={at("console_nodes_address")}
          >{node.address ?? at("console_unknown")}<small
            >{node.country_code ?? at("console_unknown")}</small
          ></td
        >
        <td data-label={at("console_nodes_groups")}
          >{#each node.groups as group (group.id)}<small>{group.name ?? group.id}</small>{:else}{at(
              "console_nodes_no_known_groups"
            )}{/each}</td
        >
        <td data-label={at("console_nodes_online")}
          >{node.users_online_quality === "reported" &&
          node.users_online !== null &&
          node.users_online > 0
            ? (node.users_online ?? at("console_unknown"))
            : at("console_unknown")}
          {#if oldValue}<small>{at("console_stale")}</small>{/if}
        </td>
        {#if traffic !== undefined}
          {@const quality = nodeWindowTrafficQuality(node, traffic)}
          <td data-label={at("console_nodes_window_traffic")} data-window-quality={quality}>
            {#if quality === "reported" && node.window_traffic_bytes !== null}
              {serviceBytes(node.window_traffic_bytes)}
              {#if traffic?.availability === "stale"}<small
                  >{at("console_nodes_availability_stale")}</small
                >{/if}
            {:else}
              {at(
                quality === "invalid"
                  ? "console_nodes_window_invalid"
                  : "console_nodes_window_missing"
              )}
            {/if}
          </td>
        {/if}
        <td data-label={at("console_nodes_traffic")}
          >{node.traffic_used_bytes === null
            ? at("console_unknown")
            : serviceBytes(node.traffic_used_bytes)}
          {#if oldValue}<small>{at("console_stale")}</small>{/if}
        </td>
        <td data-label={at("console_observed_at")}
          >{node.observed_at ? serviceDate(node.observed_at) : at("console_unknown")}</td
        >
      </tr>{/each}</tbody
  >
</AdminTable>
<p class="admin-muted">{at("console_nodes_metric_scope")}</p>

<style>
  .node-identity :global(.admin-entity-link-label),
  .node-identity :global(.admin-entity-link-id) {
    white-space: normal;
    overflow: visible;
    overflow-wrap: anywhere;
  }
  small {
    display: block;
    color: var(--admin-muted);
    overflow-wrap: anywhere;
  }
</style>
