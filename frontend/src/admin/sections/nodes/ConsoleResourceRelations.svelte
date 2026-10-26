<script lang="ts">
  import { AdminBadge, AdminEntityLink } from "$components/patterns/admin";
  import { Server, Share2, Radio } from "$components/ui/icons";
  import {
    resourcesRouteUrl,
    type CatalogResource,
    type ResourceCatalog,
  } from "$lib/admin/consoleResources";
  import { nodesRouteUrl, readNodesRoute } from "$lib/admin/consoleNodesNavigation";
  import { resourceRelations } from "$lib/admin/resourceRelations";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  let {
    catalog,
    resource,
    at,
    currentUrl,
    routePrefix = "",
  }: {
    catalog: ResourceCatalog;
    resource: CatalogResource;
    at: ConsoleNodesTranslate;
    currentUrl: string;
    routePrefix?: string;
  } = $props();
  const relations = $derived(resourceRelations(catalog, resource));
  function nodeHref(id: string) {
    return nodesRouteUrl(
      currentUrl,
      { ...readNodesRoute(new URL(currentUrl).search), nodeId: id, relatedPage: 0 },
      routePrefix
    ).href;
  }
  function peerHref(id: string) {
    return resourcesRouteUrl(
      currentUrl,
      { kind: resource.kind === "group" ? "host" : "group", query: "", resourceId: id },
      routePrefix
    ).href;
  }
</script>

<section class="resource-relations" aria-label={at("console_rel_title")}>
  <div class="relation-heading">
    <h4>{at("console_rel_title")}</h4>
    <span>{at("console_rel_inbounds")} · {relations.branches.length}</span>
  </div>
  <p class="scope">{at("console_rel_scope")}</p>
  {#if !relations.complete}<p role="status" class="partial">{at("console_rel_partial")}</p>{/if}
  {#each relations.branches as branch (branch.id)}
    <article class="relation-branch" data-resource-inbound={branch.id}>
      <div class="relation-origin">
        <div class="column-label">
          <Share2 size={16} aria-hidden="true" /><span>{at("console_rel_inbounds")}</span>
        </div>
        <strong>{branch.inbound?.tag ?? at("console_unknown")}</strong>
        <span>{branch.profile?.name ?? at("console_unknown")}</span>
        <small title={branch.id}>…{branch.id.slice(-8)}</small>
      </div>
      <div class="relation-targets nodes">
        <div class="column-label">
          <Server size={16} aria-hidden="true" /><span
            >{at("console_rel_known_nodes")} · {branch.nodes.length}</span
          >
        </div>
        {#each branch.nodes as node (node.id)}
          <div class="target-row">
            <a href={nodeHref(node.id)}
              ><AdminEntityLink kind="code" label={node.name} idText={`…${node.id.slice(-8)}`} /></a
            >
            <AdminBadge wrap variant={node.is_disabled === true ? "warning" : "muted"}
              >{at(
                node.is_disabled === null
                  ? "console_rel_state_unknown"
                  : node.is_disabled
                    ? "console_rel_disabled"
                    : "console_rel_enabled"
              )}</AdminBadge
            >
          </div>
        {:else}<p>
            {at(relations.complete ? "console_rel_no_nodes" : "console_rel_unknown_nodes")}
          </p>{/each}
      </div>
      <div class="relation-targets peers">
        <div class="column-label">
          <Radio size={16} aria-hidden="true" /><span
            >{at(
              resource.kind === "group" ? "console_rel_known_hosts" : "console_rel_known_groups"
            )} · {branch.peers.length}</span
          >
        </div>
        {#each branch.peers as peer (peer.id)}
          <div class="target-row">
            <a href={peerHref(peer.id)}
              ><AdminEntityLink kind="code" label={peer.name} idText={`…${peer.id.slice(-8)}`} /></a
            >
            {#if resource.kind === "group"}<p>
                {peer.address ?? at("console_unknown")} · {peer.port ?? at("console_unknown")}
              </p>
              <div class="peer-flags">
                <AdminBadge wrap variant={peer.is_disabled === true ? "warning" : "muted"}
                  >{at(
                    peer.is_disabled === null
                      ? "console_rel_state_unknown"
                      : peer.is_disabled
                        ? "console_rel_disabled"
                        : "console_rel_enabled"
                  )}</AdminBadge
                >
                <AdminBadge wrap
                  >{at(
                    peer.is_hidden === null
                      ? "console_rel_visibility_unknown"
                      : peer.is_hidden
                        ? "console_rel_hidden"
                        : "console_rel_visible"
                  )}</AdminBadge
                >
              </div>
            {/if}
          </div>
        {:else}<p>
            {at(relations.complete ? "console_rel_no_peers" : "console_rel_unknown_peers")}
          </p>{/each}
      </div>
    </article>
  {:else}<p>{at("console_rel_no_inbounds")}</p>{/each}
</section>

<style>
  .resource-relations {
    display: grid;
    gap: 12px;
    min-width: 0;
  }
  .relation-heading {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }
  h4,
  p {
    margin: 0;
  }
  .scope,
  .relation-heading > span {
    color: var(--admin-muted);
    font-size: 13px;
    line-height: 1.5;
  }
  .partial {
    color: var(--warning);
    font-size: 13px;
  }
  .relation-branch {
    display: grid;
    grid-template-columns: minmax(0, 0.9fr) minmax(0, 1fr) minmax(0, 1.15fr);
    border: 1px solid var(--admin-border);
    border-radius: 12px;
    overflow: hidden;
  }
  .relation-origin,
  .relation-targets {
    display: grid;
    align-content: start;
    gap: 12px;
    min-width: 0;
    padding: 18px;
    overflow-wrap: anywhere;
  }
  .relation-origin {
    background: color-mix(in srgb, var(--accent) 6%, var(--admin-surface));
    border-left: 3px solid var(--accent);
  }
  .relation-origin > strong {
    font-size: 16px;
  }
  .relation-origin > span,
  .relation-origin > small {
    color: var(--admin-muted);
    font-size: 12px;
  }
  .relation-targets {
    border-left: 1px solid var(--admin-border);
  }
  .column-label {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: var(--admin-muted);
  }
  .column-label :global(svg) {
    flex-shrink: 0;
  }
  .nodes .column-label {
    color: var(--info);
  }
  .peers .column-label {
    color: var(--accent);
  }
  .target-row {
    display: grid;
    gap: 8px;
    min-width: 0;
    padding-block: 6px;
  }
  .target-row + .target-row {
    border-top: 1px solid var(--admin-border);
    padding-top: 14px;
  }
  .target-row :global(.admin-badge) {
    justify-self: start;
  }
  .peer-flags {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .target-row a {
    text-decoration: none;
    color: var(--admin-text);
    min-width: 0;
  }
  .target-row a:hover {
    text-decoration: underline;
  }
  .target-row :global(.admin-entity-link-label) {
    white-space: normal;
    overflow-wrap: anywhere;
  }
  .target-row p,
  .relation-targets > p {
    color: var(--admin-muted);
    font-size: 13px;
    line-height: 1.5;
  }
  @media (max-width: 760px) {
    .relation-branch {
      grid-template-columns: 1fr;
    }
    .relation-targets {
      border-left: 0;
      border-top: 1px solid var(--admin-border);
    }
  }
</style>
