<script lang="ts">
  import { tick } from "svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminTable,
    AdminCopyableValue,
  } from "$components/patterns/admin";
  import { copyTextToClipboard } from "$lib/webapp/clipboard";
  import ConsoleResourceRelations from "./ConsoleResourceRelations.svelte";
  import type { ApiClient } from "$lib/webapp/publicApi";
  import type { CatalogResource, ResourceCatalog, ResourceKind } from "$lib/admin/consoleResources";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import { nodesRouteUrl, readNodesRoute } from "$lib/admin/consoleNodesNavigation";
  import { catalogAvailable } from "./resourceDraftPreview";
  import ConsoleResourceDraftPreview from "./ConsoleResourceDraftPreview.svelte";
  let {
    api,
    catalog,
    resource,
    kind,
    at,
    currentUrl,
    routePrefix = "",
    onclose,
    onOpenUserCard,
  }: {
    api: ApiClient["api"];
    catalog: ResourceCatalog;
    resource: CatalogResource;
    kind: ResourceKind;
    at: ConsoleNodesTranslate;
    currentUrl: string;
    routePrefix?: string;
    onclose: () => void;
    onOpenUserCard: (id: unknown) => void;
  } = $props();
  let preview = $state(false);
  let copyMessage = $state("");
  async function copyId(id: string) {
    copyMessage = at((await copyTextToClipboard(id)) ? "value_copied" : "console_copy_failed");
  }
  let content: HTMLDivElement | undefined;
  const profile = $derived(catalog.profiles.find((item) => item.id === resource.profile_id));
  const inbounds = $derived(catalog.profiles.flatMap((profile) => profile.inbounds));
  function nodeHref(id: string) {
    return nodesRouteUrl(
      currentUrl,
      { ...readNodesRoute(new URL(currentUrl).search), nodeId: id, relatedPage: 0 },
      routePrefix
    ).href;
  }
  async function closePreview() {
    preview = false;
    await tick();
    content?.querySelector<HTMLButtonElement>(".resource-preview-trigger button")?.focus();
  }
</script>

<Dialog
  open={!preview}
  portal
  size="wide"
  class="admin-dialog"
  title={at("console_catalog_detail")}
  description={at("console_catalog_scope")}
  closeLabel={at("close")}
  {onclose}
>
  <div class="resource-detail" bind:this={content}>
    <h3>{resource.name}</h3>
    <AdminCopyableValue
      value={resource.id}
      wrap
      copyLabel={at("copy_value", { value: resource.id })}
      oncopy={copyId}
    />
    {#if copyMessage}<p role="status">{copyMessage}</p>{/if}
    {#if kind === "host"}
      <p>{resource.address ?? at("console_unknown")} · {resource.port ?? at("console_unknown")}</p>
      <div class="resource-flags">
        <AdminBadge wrap variant={resource.is_disabled === true ? "warning" : "muted"}
          >{at(
            resource.is_disabled === null
              ? "console_rel_state_unknown"
              : resource.is_disabled
                ? "console_rel_disabled"
                : "console_rel_enabled"
          )}</AdminBadge
        >
        <AdminBadge wrap
          >{at(
            resource.is_hidden === null
              ? "console_rel_visibility_unknown"
              : resource.is_hidden
                ? "console_rel_hidden"
                : "console_rel_visible"
          )}</AdminBadge
        >
      </div>
    {/if}
    <div class="resource-preview-trigger">
      <AdminButton
        disabled={!catalogAvailable(catalog)}
        onclick={() => {
          preview = true;
        }}
        >{at(
          kind === "group" ? "console_draft_group_open" : "console_draft_host_open"
        )}</AdminButton
      >
    </div>
    {#if !catalogAvailable(catalog)}<p role="status">{at("console_draft_unavailable")}</p>{/if}
    <ConsoleResourceRelations {catalog} {resource} {at} {currentUrl} {routePrefix} />
    <details class="resource-technical">
      <summary>{at("console_rel_technical")}</summary>
      <AdminTable layout="fixed">
        <thead
          ><tr><th>{at("console_resource_field")}</th><th>{at("console_resource_current")}</th></tr
          ></thead
        >
        <tbody>
          <tr
            ><td data-label={at("console_resource_field")}>{at("console_nodes_inbounds")}</td><td
              data-label={at("console_resource_current")}
              >{#each resource.inbound_ids as id}<span
                  >{inbounds.find((item) => item.id === id)?.tag ?? at("console_unknown")} · {id}</span
                >{:else}{at("console_resource_none")}{/each}</td
            ></tr
          >
          {#if kind === "host"}
            <tr
              ><td data-label={at("console_resource_field")}>{at("console_catalog_endpoint")}</td
              ><td data-label={at("console_resource_current")}
                >{resource.address ?? at("console_unknown")}</td
              ></tr
            >
            <tr
              ><td data-label={at("console_resource_field")}>{at("console_catalog_port")}</td><td
                data-label={at("console_resource_current")}
                >{resource.port ?? at("console_unknown")}</td
              ></tr
            >
            <tr
              ><td data-label={at("console_resource_field")}>{at("console_nodes_profile")}</td><td
                data-label={at("console_resource_current")}
                >{profile?.name ?? at("console_unknown")} · {resource.profile_id ??
                  at("console_unknown")}</td
              ></tr
            >
            <tr
              ><td data-label={at("console_resource_field")}>{at("console_nodes_node")}</td><td
                data-label={at("console_resource_current")}
              >
                {#if resource.node_ids === undefined}{at(
                    "console_unknown"
                  )}{:else}{#each resource.node_ids as id}<a href={nodeHref(id)}
                      >{catalog.nodes.find((item) => item.id === id)?.name ?? at("console_unknown")} ·
                      {id}</a
                    >{:else}{at("console_catalog_no_node_selection")}{/each}{/if}
              </td></tr
            >
            <tr
              ><td data-label={at("console_resource_field")}>{at("console_draft_group_mode")}</td
              ><td data-label={at("console_resource_current")}
                >{at(
                  resource.group_mode === "ALLOW_ONLY"
                    ? "console_draft_allow_only"
                    : resource.group_mode === "EXCLUDE"
                      ? "console_draft_exclude"
                      : "console_unknown"
                )}</td
              ></tr
            >
            <tr
              ><td data-label={at("console_resource_field")}>{at("console_nodes_groups")}</td><td
                data-label={at("console_resource_current")}
              >
                {#if resource.group_ids === undefined}{at(
                    "console_unknown"
                  )}{:else}{#each resource.group_ids as id}<span
                      >{catalog.groups.find((item) => item.id === id)?.name ??
                        at("console_unknown")} ·
                      {id}</span
                    >{:else}{at("console_resource_none")}{/each}{/if}
              </td></tr
            >
            {#each [["console_resource_disabled", resource.is_disabled], ["console_draft_hidden", resource.is_hidden]] as [label, value]}<tr
                ><td data-label={at("console_resource_field")}>{at(String(label))}</td><td
                  data-label={at("console_resource_current")}
                  >{at(value === null ? "console_unknown" : value ? "yes" : "no")}</td
                ></tr
              >{/each}
          {/if}
        </tbody>
      </AdminTable>
    </details>
  </div>
</Dialog>
{#if preview}<ConsoleResourceDraftPreview
    {api}
    {at}
    target={{ kind, id: resource.id }}
    {currentUrl}
    {routePrefix}
    {onOpenUserCard}
    onclose={closePreview}
  />{/if}

<style>
  .resource-detail {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 16px;
    min-width: 0;
  }
  .resource-technical summary {
    cursor: pointer;
    color: var(--admin-muted);
    padding-block: 8px;
  }
  .resource-technical {
    min-width: 0;
  }
  .resource-flags {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  h3,
  p {
    margin: 0;
    overflow-wrap: anywhere;
  }
  td {
    overflow-wrap: anywhere;
  }
  td span,
  td a {
    display: block;
  }
  a {
    color: var(--accent);
  }
</style>
