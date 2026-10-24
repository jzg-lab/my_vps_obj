<script lang="ts">
  import { onDestroy, onMount, tick, untrack } from "svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import { Checkbox, Input } from "$components/ui/index.js";
  import { AdminButton, AdminField, AdminSelect } from "$components/patterns/admin/index.js";
  import type { ApiClient } from "$lib/webapp/publicApi";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import { nodeRelatedUrl } from "$lib/admin/consoleNodesNavigation";
  import ConsoleServiceDetail from "../services/ConsoleServiceDetail.svelte";
  import ConsoleResourcePreviewResult from "./ConsoleResourcePreviewResult.svelte";
  import { canReviewPreview } from "./resourcePreview";
  import ConsoleResourceCatalogStatus from "./ConsoleResourceCatalogStatus.svelte";
  import ResourceOperationSubmit from "./ResourceOperationSubmit.svelte";
  import {
    catalogAvailable,
    createResourceDraftPreview,
    validDraft,
    type DraftTarget,
  } from "./resourceDraftPreview";

  let {
    api,
    target,
    at,
    currentUrl,
    routePrefix = "",
    onOpenUserCard,
    onclose,
  }: {
    api: ApiClient["api"];
    target: DraftTarget;
    at: ConsoleNodesTranslate;
    currentUrl: string;
    routePrefix?: string;
    onOpenUserCard: (id: unknown) => void;
    onclose: () => void;
  } = $props();
  const draft = untrack(() => createResourceDraftPreview(api, target));
  let serviceId = $state("");
  let content: HTMLDivElement | undefined;
  const catalog = $derived($draft.catalog);
  const change = $derived($draft.change);
  const host = $derived(change?.operation === "host_update" ? change.patch : null);
  const editable = $derived(catalogAvailable(catalog) && Boolean(change));
  const reviewable = $derived(
    editable &&
      !$draft.busy &&
      validDraft(catalog, change) &&
      $draft.validation !== "incomplete" &&
      $draft.validation !== "failed" &&
      canReviewPreview($draft.preview)
  );
  const resource = $derived(
    (target.kind === "group" ? catalog?.groups : catalog?.hosts)?.find(
      (item) => item.id === target.id
    )
  );
  const inbounds = $derived(
    catalog?.profiles.find((profile) => profile.id === host?.profile_id)?.inbounds ?? []
  );
  function toggle(ids: string[], id: string, checked: boolean) {
    return checked ? [...new Set([...ids, id])].sort() : ids.filter((value) => value !== id);
  }
  function hostPatch(patch: Partial<NonNullable<typeof host>>) {
    if (change?.operation === "host_update")
      draft.setChange({ ...change, patch: { ...change.patch, ...patch } });
  }
  function serviceHref(id: string) {
    return nodeRelatedUrl(currentUrl, { serviceId: id }, routePrefix).href;
  }
  async function closeService() {
    const id = serviceId;
    serviceId = "";
    await tick();
    content
      ?.querySelector<HTMLAnchorElement>(`[data-resource-service-id="${CSS.escape(id)}"]`)
      ?.focus();
  }
  onMount(() => {
    void draft.loadCatalog();
  });
  onDestroy(() => draft.destroy());
</script>

<Dialog
  open={!serviceId}
  portal
  size="wide"
  class="admin-dialog resource-draft-dialog"
  title={at("console_draft_title")}
  description={at("resource_ops_review_scope")}
  closeLabel={at("close")}
  {onclose}
>
  <div bind:this={content} class="resource-draft" aria-busy={Boolean($draft.busy)}>
    <p>{resource?.name ?? at("console_unknown")} · {target.id}</p>
    <div>
      <AdminButton disabled={Boolean($draft.busy)} onclick={() => draft.loadCatalog()}
        >{at("console_draft_reload")}</AdminButton
      >
    </div>
    {#if $draft.busy}<p role="status">{at("loading")}</p>{/if}
    {#if $draft.failed}<p role="alert">
        {at(
          $draft.validation === "failed"
            ? "console_resource_revalidate_failed"
            : "services_request_failed"
        )}
      </p>{/if}
    {#if catalog}
      <ConsoleResourceCatalogStatus {catalog} {at} />
      {#if !editable}<p role="alert">{at("console_draft_unavailable")}</p>{/if}
    {/if}
    {#if editable && catalog && change}
      {#if change.operation === "group_inbounds"}
        <fieldset>
          <legend>{at("console_nodes_inbounds")}</legend>
          {#each catalog.profiles as profile (profile.id)}
            <p>{profile.name} · {profile.id}</p>
            {#each profile.inbounds as inbound (inbound.id)}
              <label
                ><Checkbox
                  checked={change.inbound_ids.includes(inbound.id)}
                  ariaLabel={`${profile.name} · ${inbound.tag} · ${inbound.id}`}
                  onCheckedChange={(checked) => {
                    if (change.operation === "group_inbounds")
                      draft.setChange({
                        ...change,
                        inbound_ids: toggle(change.inbound_ids, inbound.id, checked),
                      });
                  }}
                />
                <span>{inbound.tag} · {inbound.id}</span></label
              >
            {/each}
          {/each}
          {#if !change.inbound_ids.length}<p role="status">
              {at("console_draft_empty_inbounds")}
            </p>{/if}
        </fieldset>
      {:else if host}
        <AdminField label={at("console_catalog_endpoint")}
          ><Input
            value={host.address ?? resource?.address ?? ""}
            maxlength={253}
            aria-label={at("console_catalog_endpoint")}
            oninput={(event) => hostPatch({ address: event.currentTarget.value })}
          /></AdminField
        >
        <AdminField label={at("console_catalog_port")}
          ><Input
            value={String(host.port ?? resource?.port ?? "")}
            inputmode="numeric"
            maxlength={5}
            aria-label={at("console_catalog_port")}
            oninput={(event) =>
              hostPatch({
                port: /^\d+$/.test(event.currentTarget.value)
                  ? Number(event.currentTarget.value)
                  : NaN,
              })}
          /></AdminField
        >
        <AdminField label={at("console_nodes_profile")}
          ><AdminSelect
            wrapLabels
            value={host.profile_id}
            ariaLabel={at("console_nodes_profile")}
            items={catalog.profiles.map((profile) => ({
              value: profile.id,
              label: `${profile.name} · ${profile.id}`,
            }))}
            onValueChange={(profile_id) => hostPatch({ profile_id, inbound_id: "" })}
          /></AdminField
        >
        <AdminField label={at("console_nodes_inbounds")}
          ><AdminSelect
            wrapLabels
            value={host.inbound_id}
            ariaLabel={at("console_nodes_inbounds")}
            placeholder={at("console_draft_choose_inbound")}
            items={inbounds.map((inbound) => ({
              value: inbound.id,
              label: `${inbound.tag} · ${inbound.id}`,
            }))}
            onValueChange={(inbound_id) => hostPatch({ inbound_id })}
          /></AdminField
        >
        <fieldset>
          <legend>{at("console_nodes_node")}</legend>
          {#each catalog.nodes as node (node.id)}<label
              ><Checkbox
                checked={node.id !== null && host.node_ids.includes(node.id)}
                disabled={!node.id}
                ariaLabel={`${node.name} · ${node.id}`}
                onCheckedChange={(checked) => {
                  if (host && node.id)
                    hostPatch({ node_ids: toggle(host.node_ids, node.id, checked) });
                }}
              />
              <span>{node.name} · {node.id}</span></label
            >{/each}
        </fieldset>
        <AdminField label={at("console_draft_group_mode")}
          ><AdminSelect
            wrapLabels
            value={host.group_mode}
            ariaLabel={at("console_draft_group_mode")}
            items={[
              { value: "EXCLUDE", label: at("console_draft_exclude") },
              { value: "ALLOW_ONLY", label: at("console_draft_allow_only") },
            ]}
            onValueChange={(value) => {
              if (value === "EXCLUDE" || value === "ALLOW_ONLY") hostPatch({ group_mode: value });
            }}
          /></AdminField
        >
        <fieldset>
          <legend>{at("console_nodes_groups")}</legend>
          {#each catalog.groups as group (group.id)}<label
              ><Checkbox
                checked={group.id !== null && host.group_ids.includes(group.id)}
                disabled={!group.id}
                ariaLabel={`${group.name} · ${group.id}`}
                onCheckedChange={(checked) => {
                  if (host && group.id)
                    hostPatch({ group_ids: toggle(host.group_ids, group.id, checked) });
                }}
              />
              <span>{group.name} · {group.id}</span></label
            >{/each}
        </fieldset>
        <label
          ><Checkbox
            checked={host.is_disabled}
            ariaLabel={at("console_resource_disabled")}
            onCheckedChange={(is_disabled) => hostPatch({ is_disabled })}
          /><span>{at("console_resource_disabled")}</span></label
        >
        <label
          ><Checkbox
            checked={host.is_hidden}
            ariaLabel={at("console_draft_hidden")}
            onCheckedChange={(is_hidden) => hostPatch({ is_hidden })}
          /><span>{at("console_draft_hidden")}</span></label
        >
      {/if}
      {#if !validDraft(catalog, change)}<p role="alert">{at("console_draft_invalid")}</p>{/if}
      <div>
        <AdminButton
          disabled={Boolean($draft.busy) || !validDraft(catalog, change)}
          onclick={() => draft.load()}>{at("console_resource_preview")}</AdminButton
        >
      </div>
    {/if}
    {#if $draft.validation && $draft.validation !== "failed"}<p role="status">
        {at(`console_resource_revalidate_${$draft.validation}`)}
      </p>{/if}
    {#if $draft.preview}
      <ConsoleResourcePreviewResult
        preview={$draft.preview}
        {at}
        {currentUrl}
        {routePrefix}
        {serviceHref}
        onOpenService={(id) => {
          serviceId = id;
        }}
        {onOpenUserCard}
      />
      <label
        ><Checkbox
          checked={$draft.confirmed}
          disabled={!reviewable}
          onCheckedChange={(value) => draft.confirm(value)}
          ariaLabel={at("console_resource_confirm")}
        />
        <span>{at("console_resource_confirm")}</span></label
      >
      <div>
        <AdminButton disabled={!reviewable} onclick={() => draft.revalidate()}
          >{at("console_resource_revalidate")}</AdminButton
        >
      </div>
      <ResourceOperationSubmit
        {api}
        {at}
        {routePrefix}
        preview={$draft.preview}
        confirmed={$draft.confirmed && reviewable}
      />
    {/if}
  </div>
</Dialog>
{#if serviceId}<ConsoleServiceDetail
    {api}
    {at}
    {serviceId}
    {routePrefix}
    {onOpenUserCard}
    onclose={closeService}
  />{/if}

<style>
  .resource-draft,
  fieldset {
    display: grid;
    gap: 12px;
    min-width: 0;
  }
  fieldset {
    margin: 0;
    padding: 12px;
    border: 1px solid var(--admin-border);
  }
  legend,
  p,
  span {
    overflow-wrap: anywhere;
  }
  p {
    margin: 0;
  }
  label {
    display: flex;
    align-items: start;
    gap: 10px;
    min-width: 0;
  }
  :global(.resource-draft-dialog > .dialog-body-scroll) {
    padding-inline-end: 12px;
  }
  :global(
    .resource-draft-dialog
      > .dialog-body-scroll
      > .scroll-area__scrollbar[data-orientation="vertical"]
  ) {
    transform: none;
  }
</style>
