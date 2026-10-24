<script lang="ts">
  import { AdminBadge } from "$components/patterns/admin/index.js";
  import { serviceDate } from "$lib/webapp/independentServices";
  import type {
    ConsoleNodeSource,
    ConsoleNodesPage,
    ConsoleNodesTranslate,
  } from "$lib/admin/consoleNodesTypes";
  let {
    coverage,
    sources,
    at,
    stale = false,
  }: {
    coverage: ConsoleNodesPage["coverage"];
    sources: ConsoleNodeSource[];
    at: ConsoleNodesTranslate;
    stale?: boolean;
  } = $props();
</script>

<div class="node-sources" role="status">
  <AdminBadge variant={coverage === "complete" ? "muted" : "warning"}
    >{at(`console_nodes_coverage_${coverage}`)}</AdminBadge
  >
  <p>{at("console_nodes_read_time")}</p>
  <ul>
    {#each sources as source (source.source)}
      <li>
        <strong>{at(`console_nodes_source_${source.source}`)}</strong>: {at(
          `console_nodes_availability_${stale ? "stale" : source.availability}`
        )}
        <span
          >{at("console_nodes_last_success")}: {source.last_success_at
            ? serviceDate(source.last_success_at)
            : at("console_unknown")}</span
        >
        <span>{at("console_nodes_attempted")}: {serviceDate(source.attempted_at)}</span>
      </li>
    {/each}
  </ul>
</div>

<style>
  .node-sources {
    display: grid;
    justify-items: start;
    gap: 8px;
    color: var(--admin-muted);
    overflow-wrap: anywhere;
  }
  p,
  ul {
    margin: 0;
  }
  ul {
    display: grid;
    gap: 8px;
    padding-left: 20px;
  }
  span {
    display: block;
    font-size: 12px;
  }
</style>
