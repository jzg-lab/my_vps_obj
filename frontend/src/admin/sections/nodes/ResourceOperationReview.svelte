<script lang="ts">
  import { onMount, onDestroy, untrack } from "svelte";
  import { Checkbox } from "$components/ui";
  import { AdminButton } from "$components/patterns/admin";
  import type { ApiClient } from "$lib/webapp/publicApi";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import { canReviewPreview, createResourcePreview, type ResourceChange } from "./resourcePreview";
  import {
    resourceErrorKey,
    resourceRejected,
    resourceRetry,
    readResourceOperation,
    type ResourceOperation,
  } from "$lib/admin/resourceOperations";
  import { nodeRelatedUrl } from "$lib/admin/consoleNodesNavigation";
  import ConsoleResourcePreviewResult from "./ConsoleResourcePreviewResult.svelte";
  import ResourceOperationSubmit from "./ResourceOperationSubmit.svelte";
  let {
    api,
    at,
    change,
    routePrefix = "",
    currentUrl,
    onOpenUserCard,
    onOpenService,
    recoveryOf = null,
    retry = null,
    onAccepted = () => {},
    onUncertain = () => {},
  }: {
    api: ApiClient["api"];
    at: ConsoleNodesTranslate;
    change: ResourceChange;
    routePrefix?: string;
    currentUrl: string;
    onOpenUserCard: (id: unknown) => void;
    onOpenService: (id: string) => void;
    recoveryOf?: string | null;
    retry?: ResourceOperation | null;
    onAccepted?: (operation: ResourceOperation) => void;
    onUncertain?: (version: number) => void;
  } = $props();
  const review = untrack(() => createResourcePreview(api));
  let busy = $state(false);
  let error = $state("");
  let uncertain = $state(false);
  onMount(() => {
    review.setChange(change);
    void review.load();
  });
  onDestroy(() => review.destroy());
  async function retryOriginal() {
    if (
      !retry ||
      busy ||
      uncertain ||
      !$review.confirmed ||
      !$review.preview?.execution_available ||
      $review.preview.fingerprint !== retry.preview.fingerprint
    )
      return;
    busy = true;
    error = "";
    try {
      await review.revalidate();
      if ($review.validation !== "unchanged" || !$review.confirmed || !$review.preview?.fingerprint)
        return;
      const current = await readResourceOperation(api, retry.id);
      if (current.version !== retry.version || !current.can_retry) {
        error = "resource_ops_error_changed";
        onAccepted(current);
        return;
      }
      try {
        onAccepted((await resourceRetry(api, current, $review.preview.fingerprint)).operation);
      } catch (failure) {
        uncertain = !resourceRejected(failure);
        if (uncertain) onUncertain(current.version);
        error = resourceErrorKey(failure);
        onAccepted(await readResourceOperation(api, retry.id));
      }
    } catch (failure) {
      error = resourceErrorKey(failure);
    } finally {
      busy = false;
    }
  }
</script>

<div class="resource-review">
  {#if $review.busy}<p role="status">{at("loading")}</p>{/if}
  {#if $review.failed}<p role="alert">{at("resource_ops_error_incomplete")}</p>{/if}
  {#if error}<p role="alert">{at(error)}</p>{/if}
  <div>
    <AdminButton disabled={busy || uncertain || Boolean($review.busy)} onclick={() => review.load()}
      >{at("console_resource_preview")}</AdminButton
    >
  </div>
  {#if $review.preview}
    <ConsoleResourcePreviewResult
      preview={$review.preview}
      {at}
      {currentUrl}
      {routePrefix}
      {onOpenUserCard}
      {onOpenService}
      serviceHref={(serviceId) => nodeRelatedUrl(currentUrl, { serviceId }, routePrefix).href}
    />
    {#if retry && $review.preview.fingerprint !== retry.preview.fingerprint}<p role="alert">
        {at("resource_ops_retry_changed")}
      </p>{/if}
    <label
      ><Checkbox
        checked={$review.confirmed}
        disabled={busy || uncertain || !canReviewPreview($review.preview)}
        ariaLabel={at("console_resource_confirm")}
        onCheckedChange={(value) => review.confirm(value)}
      /><span>{at("console_resource_confirm")}</span></label
    >
    {#if retry}<div>
        <AdminButton
          disabled={busy ||
            uncertain ||
            !$review.confirmed ||
            !$review.preview.execution_available ||
            $review.preview.fingerprint !== retry.preview.fingerprint}
          onclick={retryOriginal}>{at("resource_ops_retry")}</AdminButton
        >
      </div>
    {:else}<ResourceOperationSubmit
        {api}
        {at}
        preview={$review.preview}
        confirmed={$review.confirmed && !$review.busy}
        {recoveryOf}
        {routePrefix}
        {onAccepted}
      />{/if}
  {/if}
</div>

<style>
  .resource-review {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  p {
    margin: 0;
    overflow-wrap: anywhere;
  }
  label {
    display: flex;
    gap: 8px;
    align-items: start;
  }
  span {
    overflow-wrap: anywhere;
  }
</style>
