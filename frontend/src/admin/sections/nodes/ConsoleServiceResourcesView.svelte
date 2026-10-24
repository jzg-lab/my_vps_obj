<script lang="ts">
  import { AdminEntityLink } from "$components/patterns/admin/index.js";
  import { nodesRouteUrl, readNodesRoute } from "$lib/admin/consoleNodesNavigation";
  import type {
    ConsoleServiceResources,
    ConsoleNodesTranslate,
  } from "$lib/admin/consoleNodesTypes";
  import ConsoleNodeSources from "./ConsoleNodeSources.svelte";
  let {
    resources,
    at,
    currentUrl,
    routePrefix = "",
  }: {
    resources: ConsoleServiceResources;
    at: ConsoleNodesTranslate;
    currentUrl: string;
    routePrefix?: string;
  } = $props();
  const route = $derived({
    ...readNodesRoute(new URL(currentUrl).search),
    serviceId: resources.service_id,
    relatedPage: 0,
  });
</script>

<div class="service-resources">
  <h4>{at("console_nodes_resources")}</h4>
  <p>{at("console_nodes_resource_scope")}</p>
  <p>{at(resources.currently_eligible ? "console_nodes_eligible" : "console_nodes_ineligible")}</p>
  <h5>{at("console_nodes_groups")}</h5>
  {#each resources.groups as group (group.id)}<p class="resource-id">
      {group.name ?? at("console_unknown")} · {group.id}
    </p>{:else}<p>{at("console_nodes_no_known_groups")}</p>{/each}
  <h5>{at("console_nodes_node")}</h5>
  {#each resources.nodes as node (node.id)}
    <a href={nodesRouteUrl(currentUrl, { ...route, nodeId: node.id }, routePrefix).href}
      ><AdminEntityLink kind="code" label={node.name} idText={node.id} /></a
    >
  {:else}<p>
      {at(
        resources.coverage === "complete"
          ? "console_nodes_no_resource_nodes"
          : "console_nodes_no_known_resource_nodes"
      )}
    </p>{/each}
  <h5>{at("console_nodes_hosts")}</h5>
  {#each resources.hosts as host (host.id)}<p class="resource-id">
      {host.name ?? at("console_unknown")} · {host.id}
    </p>{:else}<p>{at("console_nodes_no_known_hosts")}</p>{/each}
  <ConsoleNodeSources coverage={resources.coverage} sources={resources.sources} {at} />
</div>

<style>
  .service-resources {
    display: grid;
    gap: 12px;
    min-width: 0;
  }
  h4,
  h5,
  p {
    margin: 0;
  }
  a {
    color: var(--accent);
    text-decoration: none;
  }
  a:hover {
    text-decoration: underline;
  }
  .resource-id {
    overflow-wrap: anywhere;
  }
</style>
