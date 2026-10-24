<script lang="ts">
  import { onMount, onDestroy, tick } from "svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import { AdminButton } from "$components/patterns/admin";
  import { unwrap, type ApiClient } from "$lib/webapp/publicApi";
  import type { ResourceCatalog } from "$lib/admin/consoleResources";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import {
    resourceActionKey,
    resourceErrorKey,
    resourceOperationsUrl,
    type ResourceOperation,
  } from "$lib/admin/resourceOperations";
  import { catalogAvailable } from "./resourceDraftPreview";
  import type { ResourceChange } from "./resourcePreview";
  import ResourceCreateForm from "./ResourceCreateForm.svelte";
  import ResourceOperationReview from "./ResourceOperationReview.svelte";
  import ResourceOperationStatus from "./ResourceOperationStatus.svelte";
  import ConsoleResourceCatalogStatus from "./ConsoleResourceCatalogStatus.svelte";
  import NodeDeployment from "./NodeDeployment.svelte";
  import ConsoleServiceDetail from "../services/ConsoleServiceDetail.svelte";
  let {
    api,
    at,
    kind,
    routePrefix = "",
    onclose,
    onOpenUserCard,
  }: {
    api: ApiClient["api"];
    at: ConsoleNodesTranslate;
    kind: "node" | "group" | "host";
    routePrefix?: string;
    onclose: () => void;
    onOpenUserCard: (id: unknown) => void;
  } = $props();
  let catalog = $state<ResourceCatalog | null>(null);
  let change = $state<ResourceChange | null>(null);
  let operation = $state<ResourceOperation | null>(null);
  let serviceId = $state("");
  let busy = $state(false);
  let error = $state("");
  let active = true;
  let controller: AbortController | null = null;
  let content: HTMLDivElement | undefined;
  const currentUrl = typeof window === "undefined" ? "https://console.test/" : window.location.href;
  async function load() {
    if (busy) return;
    busy = true;
    error = "";
    controller = new AbortController();
    try {
      const result = unwrap(
        await api("/admin/console/resources/catalog", { signal: controller.signal })
      );
      if (active) catalog = result;
    } catch (failure) {
      if (active) error = resourceErrorKey(failure);
    } finally {
      if (active) busy = false;
    }
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
    void load();
  });
  onDestroy(() => {
    active = false;
    controller?.abort();
  });
</script>

<Dialog
  open={!serviceId}
  portal
  size="wide"
  class="admin-dialog resource-create-dialog"
  title={at(resourceActionKey(`${kind}_create`))}
  focusKey={operation ? "result" : change ? "review" : catalog ? "draft" : "loading"}
  closeLabel={at("close")}
  {onclose}
>
  <div class="resource-create" bind:this={content}>
    {#if kind === "node"}<ol>
        <li>{at("resource_ops_onboarding_registration")}</li>
        <li>{at("resource_ops_onboarding_management")}</li>
        <li>{at("resource_ops_onboarding_subscription")}</li>
      </ol>{/if}
    {#if error}<p role="alert">{at(error)}</p>{/if}
    {#if busy}<p role="status">{at("loading")}</p>{/if}
    {#if operation}<ResourceOperationStatus {operation} {at} /><a
        href={resourceOperationsUrl(currentUrl, routePrefix, operation.id).href}
        >{at("resource_ops_open_record")}</a
      >
    {:else}
      {#if change}<div>
          <AdminButton
            onclick={() => {
              change = null;
            }}>{at("resource_ops_edit_draft")}</AdminButton
          >
        </div>
        <ResourceOperationReview
          {api}
          {at}
          {change}
          {currentUrl}
          {routePrefix}
          {onOpenUserCard}
          onOpenService={(id) => {
            serviceId = id;
          }}
          onAccepted={(value) => {
            operation = value;
          }}
        />{/if}
      <div hidden={Boolean(change)}>
        <div><AdminButton disabled={busy} onclick={load}>{at("refresh")}</AdminButton></div>
        {#if catalog}<ConsoleResourceCatalogStatus {catalog} {at} />
          {#if kind === "node" && !change}<NodeDeployment
              {api}
              {at}
              available={catalog.execution_available && catalogAvailable(catalog)}
            />{/if}
          {#if catalogAvailable(catalog)}<ResourceCreateForm
              {kind}
              {catalog}
              {at}
              onReview={(value) => {
                change = value;
              }}
            />{:else}<p role="alert">{at("console_draft_unavailable")}</p>{/if}
        {/if}
      </div>
    {/if}
  </div>
</Dialog>
{#if serviceId}<ConsoleServiceDetail
    {api}
    {at}
    {routePrefix}
    {onOpenUserCard}
    {serviceId}
    onclose={closeService}
  />{/if}

<style>
  .resource-create {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  p,
  ol {
    margin: 0;
    overflow-wrap: anywhere;
  }
  a {
    color: var(--accent);
  }
  :global(.resource-create-dialog > .dialog-body-scroll) {
    padding-inline-end: 12px;
  }
  :global(
    .resource-create-dialog
      > .dialog-body-scroll
      > .scroll-area__scrollbar[data-orientation="vertical"]
  ) {
    transform: none;
  }
</style>
