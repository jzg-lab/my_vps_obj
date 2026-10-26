<script lang="ts">
  import { AdminEntityLink } from "$components/patterns/admin/index.js";
  import { nodesRouteUrl, readNodesRoute, nodeRelatedUrl } from "$lib/admin/consoleNodesNavigation";
  import type { UserService } from "$lib/admin/servicePlans";
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
    service,
    onOpenService,
  }: {
    resources: ConsoleServiceResources;
    at: ConsoleNodesTranslate;
    currentUrl: string;
    routePrefix?: string;
    service?: UserService;
    onOpenService?: (serviceId: string) => void;
  } = $props();
  function openService(event: MouseEvent) {
    if (
      !service ||
      !onOpenService ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    )
      return;
    event.preventDefault();
    onOpenService(service.id);
  }
  const route = $derived({
    ...readNodesRoute(new URL(currentUrl).search),
    serviceId: resources.service_id,
    relatedPage: 0,
  });
  const eligibilityLabel = $derived(
    resources.currently_eligible
      ? "console_nodes_eligible"
      : resources.status === "pending"
        ? "console_nodes_pending_configuration"
        : "console_nodes_ineligible"
  );
  const unconfigured = $derived(
    resources.sources.length > 0 &&
      resources.sources.every((source) => source.availability === "unconfigured")
  );
  const missingNodesLabel = $derived(
    unconfigured
      ? "console_nodes_resources_unconfigured"
      : resources.coverage === "complete"
        ? "console_nodes_no_resource_nodes"
        : "console_nodes_no_known_resource_nodes"
  );
</script>

<div class="service-resources">
  {#if !service}<p>{at("console_nodes_resource_scope")}</p>{/if}
  {#if service}
    <div class="service-node-flow" data-service-relation={service.id}>
      <a
        class="relation-service"
        href={nodeRelatedUrl(currentUrl, { serviceId: service.id }, routePrefix).href}
        onclick={openService}
      >
        <small>{at("services_title")} · {at(`services_status_${service.status}`)}</small>
        <AdminEntityLink kind="code" label={service.name} idText={service.id} />
        <small>{at(eligibilityLabel)}</small>
      </a>
      <span class="relation-connector" aria-hidden="true"></span>
      <div class="relation-nodes">
        {#each resources.nodes as node (node.id)}
          <a href={nodesRouteUrl(currentUrl, { ...route, nodeId: node.id }, routePrefix).href}>
            <small>{at("console_nodes_node")}</small>
            <AdminEntityLink kind="code" label={node.name} idText={node.id} />
          </a>
        {:else}<p>
            {at(missingNodesLabel)}
          </p>{/each}
      </div>
    </div>
    {#if resources.coverage !== "complete" && resources.nodes.length > 0}<p role="status">
        {at(`console_nodes_coverage_${resources.coverage}`)}
      </p>{/if}
  {/if}
  <details open={!service}>
    <summary>{at("console_nodes_resources")}</summary>
    {#if !service}<p>{at(eligibilityLabel)}</p>{/if}
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
        {at(missingNodesLabel)}
      </p>{/each}
    <h5>{at("console_nodes_hosts")}</h5>
    {#each resources.hosts as host (host.id)}<p class="resource-id">
        {host.name ?? at("console_unknown")} · {host.id}
      </p>{:else}<p>{at("console_nodes_no_known_hosts")}</p>{/each}
    <ConsoleNodeSources coverage={resources.coverage} sources={resources.sources} {at} />
  </details>
</div>

<style>
  .service-resources {
    display: grid;
    gap: 12px;
    min-width: 0;
  }
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
  .service-node-flow {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 36px minmax(0, 1fr);
    align-items: center;
    gap: 8px;
  }
  .relation-service,
  .relation-nodes > a {
    display: grid;
    gap: 12px;
    min-width: 0;
    padding: 18px;
    border: 1px solid color-mix(in srgb, var(--accent) 40%, var(--admin-border));
    border-radius: 12px;
    background: var(--admin-surface);
    color: var(--admin-text);
  }
  .relation-nodes {
    display: grid;
    gap: 12px;
    min-width: 0;
  }
  .relation-nodes > a {
    border-color: color-mix(in srgb, var(--info) 45%, var(--admin-border));
  }
  .relation-connector {
    height: 2px;
    background: var(--info);
  }
  small,
  summary {
    color: var(--admin-muted);
    font-size: 12px;
  }
  summary {
    cursor: pointer;
    padding-block: 8px;
  }
  details[open] {
    display: grid;
    gap: 12px;
  }
  .service-node-flow :global(.admin-entity-link-label),
  .service-node-flow :global(.admin-entity-link-id) {
    white-space: normal;
    overflow-wrap: anywhere;
  }
  @media (max-width: 760px) {
    .service-node-flow {
      grid-template-columns: minmax(0, 1fr);
      gap: 0;
    }
    .relation-connector {
      width: 2px;
      height: 20px;
      justify-self: center;
    }
  }
</style>
