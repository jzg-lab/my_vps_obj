<script lang="ts">
  import { AdminEntityLink, AdminTable } from "$components/patterns/admin";
  import type { CatalogResource, ResourceKind } from "$lib/admin/consoleResources";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  let {
    rows,
    kind,
    at,
    onOpen,
  }: {
    rows: CatalogResource[];
    kind: ResourceKind;
    at: ConsoleNodesTranslate;
    onOpen: (id: string) => void;
  } = $props();
</script>

<div class="catalog-table">
  <AdminTable layout="fixed" aria-label={at("console_catalog_title")}>
    <thead
      ><tr>
        <th>{at("console_resource_name")}</th><th>{at("console_nodes_inbounds")}</th>
        {#if kind === "host"}<th>{at("console_catalog_endpoint")}</th><th
            >{at("console_catalog_host_flags")}</th
          >{/if}
      </tr></thead
    >
    <tbody
      >{#each rows as row (row.id)}<tr>
          <td data-label={at("console_resource_name")} data-resource-id={row.id}>
            <AdminEntityLink
              kind="code"
              label={row.name}
              idText={row.id}
              title={at("console_catalog_detail")}
              onclick={() => onOpen(row.id)}
            />
          </td>
          <td data-label={at("console_nodes_inbounds")}
            >{row.inbound_ids.join(", ") || at("console_resource_none")}</td
          >
          {#if kind === "host"}
            <td data-label={at("console_catalog_endpoint")}
              >{row.address ?? at("console_unknown")}<br />{at("console_catalog_port")}: {row.port ??
                at("console_unknown")}</td
            >
            <td data-label={at("console_catalog_host_flags")}
              >{at("console_resource_disabled")}: {at(
                row.is_disabled === null ? "console_unknown" : row.is_disabled ? "yes" : "no"
              )}<br />{at("console_draft_hidden")}: {at(
                row.is_hidden === null ? "console_unknown" : row.is_hidden ? "yes" : "no"
              )}</td
            >
          {/if}
        </tr>{/each}</tbody
    >
  </AdminTable>
</div>

<style>
  .catalog-table {
    min-width: 0;
  }
  td {
    overflow-wrap: anywhere;
  }
  .catalog-table :global(.admin-entity-link-label),
  .catalog-table :global(.admin-entity-link-id) {
    white-space: normal;
    overflow: visible;
    overflow-wrap: anywhere;
  }
</style>
