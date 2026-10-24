<script lang="ts">
  import { onMount, onDestroy, tick } from "svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import { AdminButton } from "$components/patterns/admin";
  import type { ApiClient } from "$lib/webapp/publicApi";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import {
    readResourceOperation,
    resourceReconcile,
    resourceEvidence,
    resourceRecovery,
    resourceErrorKey,
    resourceRejected,
    type ResourceOperation,
    type ResourceEvidence,
  } from "$lib/admin/resourceOperations";
  import ResourceOperationStatus from "./ResourceOperationStatus.svelte";
  import NodeOnboardingProgress from "./NodeOnboardingProgress.svelte";
  import ResourceOperationEvidence from "./ResourceOperationEvidence.svelte";
  import ResourceOperationReview from "./ResourceOperationReview.svelte";
  import ConsoleResourcePreviewResult from "./ConsoleResourcePreviewResult.svelte";
  import ConsoleServiceDetail from "../services/ConsoleServiceDetail.svelte";
  import { nodeRelatedUrl } from "$lib/admin/consoleNodesNavigation";
  let {
    api,
    at,
    operationId,
    routePrefix = "",
    onclose,
    onOpenUserCard,
    onOpenOperation,
  }: {
    api: ApiClient["api"];
    at: ConsoleNodesTranslate;
    operationId: string;
    routePrefix?: string;
    onclose: () => void;
    onOpenUserCard: (id: unknown) => void;
    onOpenOperation: (id: string) => void;
  } = $props();
  let operation = $state<ResourceOperation | null>(null);
  let busy = $state(false);
  let error = $state("");
  let uncertainVersion = $state<number | null>(null);
  let mode = $state<"view" | "retry" | "recovery">("view");
  let serviceId = $state("");
  let active = true;
  let content: HTMLDivElement | undefined;
  const currentUrl = typeof window === "undefined" ? "https://console.test/" : window.location.href;
  const recovery = $derived(operation ? resourceRecovery(operation) : null);
  function accept(value: ResourceOperation) {
    if (!active) return;
    if (value.id !== operationId) {
      onOpenOperation(value.id);
      return;
    }
    operation = value;
    mode = "view";
    if (uncertainVersion !== null && value.version !== uncertainVersion) uncertainVersion = null;
  }
  async function refresh() {
    if (busy) return;
    busy = true;
    error = "";
    try {
      accept(await readResourceOperation(api, operationId));
    } catch (failure) {
      error = resourceErrorKey(failure);
    } finally {
      busy = false;
    }
  }
  async function write(body?: ResourceEvidence) {
    if (!operation || busy || operation.status !== "unknown" || (body && uncertainVersion !== null))
      return;
    const version = operation.version;
    busy = true;
    error = "";
    try {
      accept(
        (body
          ? await resourceEvidence(api, operation.id, body)
          : await resourceReconcile(api, operation)
        ).operation
      );
    } catch (failure) {
      error = resourceErrorKey(failure);
      if (!resourceRejected(failure)) uncertainVersion = version;
      try {
        accept(await readResourceOperation(api, operation.id));
      } catch {
        /* Keep the last authoritative state and its unresolved command. */
      }
    } finally {
      busy = false;
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
    void refresh();
  });
  onDestroy(() => {
    active = false;
  });
</script>

<Dialog
  open={!serviceId}
  portal
  size="wide"
  class="admin-dialog resource-operation-dialog"
  title={at("resource_ops_detail")}
  focusKey={`${mode}:${operation?.status ?? "loading"}`}
  closeLabel={at("close")}
  {onclose}
>
  <div class="resource-operation-detail" bind:this={content} aria-busy={busy}>
    {#if error}<p role="alert">{at(error)}</p>{/if}
    {#if uncertainVersion !== null}<p role="status">{at("resource_ops_command_unknown")}</p>{/if}
    <div><AdminButton disabled={busy} onclick={refresh}>{at("refresh")}</AdminButton></div>
    {#if operation}
      <ResourceOperationStatus {operation} {at} />
      {#if operation.change.operation === "node_create"}{#key operation.target_id}<NodeOnboardingProgress
            {api}
            {at}
            {operation}
            {routePrefix}
          />{/key}{/if}
      {#if mode !== "view"}
        <div>
          <AdminButton
            disabled={busy}
            onclick={() => {
              mode = "view";
            }}>{at("resource_ops_back_record")}</AdminButton
          >
        </div>
        {#if mode === "retry" || recovery}{#key `${mode}:${operation.id}:${operation.version}`}<ResourceOperationReview
              {api}
              {at}
              {routePrefix}
              {currentUrl}
              {onOpenUserCard}
              onOpenService={(id) => {
                serviceId = id;
              }}
              change={mode === "retry" ? operation.change : recovery!}
              retry={mode === "retry" ? operation : null}
              recoveryOf={mode === "recovery" ? operation.id : null}
              onAccepted={accept}
              onUncertain={(version) => {
                uncertainVersion = version;
              }}
            />{/key}{/if}
      {:else}
        <div class="actions">
          {#if operation.status === "unknown"}<AdminButton disabled={busy} onclick={() => write()}
              >{at("resource_ops_reconcile")}</AdminButton
            >{/if}
          {#if operation.can_retry}<AdminButton
              disabled={busy || uncertainVersion !== null}
              onclick={() => {
                mode = "retry";
              }}>{at("resource_ops_retry_preview")}</AdminButton
            >{/if}
          {#if recovery}<AdminButton
              disabled={busy || uncertainVersion !== null}
              onclick={() => {
                mode = "recovery";
              }}>{at("resource_ops_recovery_preview")}</AdminButton
            >{/if}
        </div>
        {#if operation.status === "unknown" && operation.attempts.length}{#key operation.version}<ResourceOperationEvidence
              {operation}
              {at}
              {busy}
              disabled={uncertainVersion !== null}
              onsubmit={write}
            />{/key}{/if}
        <h4>{at("resource_ops_original_preview")}</h4>
        <ConsoleResourcePreviewResult
          preview={operation.preview}
          {at}
          {currentUrl}
          {routePrefix}
          {onOpenUserCard}
          serviceHref={(id) => nodeRelatedUrl(currentUrl, { serviceId: id }, routePrefix).href}
          onOpenService={(id) => {
            serviceId = id;
          }}
        />
      {/if}
    {:else if busy}<p role="status">{at("loading")}</p>{/if}
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
  .resource-operation-detail {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  p,
  h4 {
    margin: 0;
    overflow-wrap: anywhere;
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    min-width: 0;
  }
  .actions :global(.admin-btn) {
    max-width: 100%;
    min-width: 0;
    min-height: 34px;
    height: auto;
    padding-block: 8px;
    white-space: normal;
    overflow-wrap: anywhere;
  }
  :global(.resource-operation-dialog > .dialog-body-scroll) {
    padding-inline-end: 12px;
  }
  :global(
    .resource-operation-dialog
      > .dialog-body-scroll
      > .scroll-area__scrollbar[data-orientation="vertical"]
  ) {
    transform: none;
  }
</style>
