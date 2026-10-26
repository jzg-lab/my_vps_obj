<script lang="ts">
  import { AdminBadge, AdminEntityLink } from "$components/patterns/admin";
  import type { CatalogResource, ResourceCatalog, ResourceKind } from "$lib/admin/consoleResources";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import { resourceRelations } from "$lib/admin/resourceRelations";
  let {
    rows,
    catalog,
    kind,
    at,
    onOpen,
  }: {
    rows: CatalogResource[];
    catalog: ResourceCatalog;
    kind: ResourceKind;
    at: ConsoleNodesTranslate;
    onOpen: (id: string) => void;
  } = $props();
</script>

<div class="resource-cards" aria-label={at("console_catalog_view_cards")}>
  {#each rows as row (row.id)}
    {@const relations = resourceRelations(catalog, row)}
    <article class="resource-card" data-resource-card={row.id}>
      <header>
        <div data-resource-id={row.id}>
          <AdminEntityLink
            kind="code"
            label={row.name}
            idText={`…${row.id.slice(-8)}`}
            title={`${at("console_catalog_detail")} · ${row.id}`}
            onclick={() => onOpen(row.id)}
          />
        </div>
        <AdminBadge wrap
          >{at(kind === "group" ? "console_rel_group" : "console_rel_host")}</AdminBadge
        >
      </header>
      {#if kind === "host"}
        <p class="endpoint">
          {row.address ?? at("console_unknown")} · {row.port ?? at("console_unknown")}
        </p>
        <div class="flags">
          <AdminBadge wrap variant={row.is_disabled === true ? "warning" : "muted"}
            >{at(
              row.is_disabled === null
                ? "console_rel_state_unknown"
                : row.is_disabled
                  ? "console_rel_disabled"
                  : "console_rel_enabled"
            )}</AdminBadge
          >
          <AdminBadge wrap
            >{at(
              row.is_hidden === null
                ? "console_rel_visibility_unknown"
                : row.is_hidden
                  ? "console_rel_hidden"
                  : "console_rel_visible"
            )}</AdminBadge
          >
        </div>
      {/if}
      <div class="inbound-tags">
        {#each relations.branches.slice(0, 3) as branch (branch.id)}<span title={branch.id}
            >{branch.inbound?.tag ?? at("console_unknown")}</span
          >{/each}
        {#if relations.branches.length > 3}<span>+{relations.branches.length - 3}</span>{/if}
      </div>
      <dl>
        <div>
          <dt>{at("console_rel_inbounds")}</dt>
          <dd>{relations.branches.length}</dd>
        </div>
        <div>
          <dt>{at("console_rel_known_nodes")}</dt>
          <dd>{relations.nodes.length}</dd>
        </div>
        <div>
          <dt>{at(kind === "group" ? "console_rel_known_hosts" : "console_rel_known_groups")}</dt>
          <dd>{relations.peers.length}</dd>
        </div>
      </dl>
      <p class="node-names">
        {relations.nodes
          .slice(0, 3)
          .map((node) => node.name)
          .join(" · ") ||
          at(
            relations.complete ? "console_rel_no_nodes" : "console_rel_unknown_nodes"
          )}{#if relations.nodes.length > 3}
          · +{relations.nodes.length - 3}{/if}
      </p>
      {#if !relations.complete}<p class="partial">{at("console_rel_partial")}</p>{/if}
    </article>
  {/each}
</div>

<style>
  .resource-cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 330px), 1fr));
    gap: 16px;
    min-width: 0;
  }
  .resource-card {
    display: grid;
    align-content: start;
    gap: 16px;
    min-width: 0;
    padding: 20px;
    border: 1px solid var(--admin-border);
    border-radius: 14px;
    background: var(--admin-card-bg);
    box-shadow: var(--admin-card-shadow);
  }
  header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
  }
  header > div {
    min-width: 0;
  }
  header :global(.admin-entity-link-label) {
    font-size: 16px;
    white-space: normal;
    overflow-wrap: anywhere;
  }
  .inbound-tags,
  .flags {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    min-width: 0;
  }
  .inbound-tags span {
    padding: 5px 8px;
    border-radius: 6px;
    background: var(--admin-surface-2);
    font-size: 12px;
    overflow-wrap: anywhere;
  }
  dl {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    padding-block: 16px;
    border-block: 1px solid var(--admin-border);
  }
  dl,
  dd,
  p {
    margin: 0;
  }
  dt {
    color: var(--admin-muted);
    font-size: 12px;
    overflow-wrap: anywhere;
  }
  dd {
    margin-top: 6px;
    font-size: 26px;
    font-weight: 650;
    font-variant-numeric: tabular-nums;
  }
  .endpoint {
    font-size: 14px;
    overflow-wrap: anywhere;
  }
  .node-names,
  .partial {
    font-size: 13px;
    line-height: 1.5;
    color: var(--admin-muted);
    overflow-wrap: anywhere;
  }
  .partial {
    color: var(--warning);
  }
  @media (max-width: 520px) {
    .resource-card {
      padding: 16px;
    }
    header {
      flex-wrap: wrap;
    }
  }
</style>
