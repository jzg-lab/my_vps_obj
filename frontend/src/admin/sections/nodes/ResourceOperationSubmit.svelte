<script lang="ts">
  import { onMount, onDestroy, untrack } from "svelte";
  import { AdminButton } from "$components/patterns/admin";
  import type { ApiClient } from "$lib/webapp/publicApi";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import { createResourceIntent } from "$lib/admin/resourceIntent";
  import { resourceOperationsUrl, type ResourceOperation } from "$lib/admin/resourceOperations";
  import type { ResourcePreview } from "./resourcePreview";
  let {
    api,
    at,
    preview = null,
    confirmed = false,
    recoveryOf = null,
    routePrefix = "",
    onAccepted,
  }: {
    api: ApiClient["api"];
    at: ConsoleNodesTranslate;
    preview?: ResourcePreview | null;
    confirmed?: boolean;
    recoveryOf?: string | null;
    routePrefix?: string;
    onAccepted?: (operation: ResourceOperation) => void;
  } = $props();
  let intent = $state<ReturnType<typeof createResourceIntent> | null>(null);
  let notified = "";
  onMount(() => {
    intent = createResourceIntent(api, sessionStorage);
    void intent.initialize();
  });
  onDestroy(() => intent?.destroy());
  $effect(() => {
    const current = preview;
    if (current) untrack(() => intent?.resetPreview());
  });
  $effect(() => {
    if ($intent?.operation && $intent.operation.id !== notified) {
      notified = $intent.operation.id;
      onAccepted?.($intent.operation);
    }
  });
  const href = $derived(
    resourceOperationsUrl(
      typeof window === "undefined" ? "https://console.test/" : window.location.href,
      routePrefix,
      $intent?.operation?.id ?? ""
    ).href
  );
</script>

<div class="resource-submit" aria-busy={$intent?.busy ?? false}>
  {#if $intent?.error}<p role="alert">{at($intent.error)}</p>{/if}
  {#if $intent?.operation}
    <p role="status">{at("resource_ops_recorded")}</p>
    <p>{$intent.operation.id}</p>
    <a {href}>{at("resource_ops_open_record")}</a>
  {:else if $intent?.pending}
    <p role="status">{at("resource_ops_pending_intent")}</p>
    <AdminButton disabled={$intent.busy} onclick={() => intent?.resume()}
      >{at("resource_ops_resume_intent")}</AdminButton
    >
    <a {href}>{at("resource_ops_title")}</a>
  {:else if preview}
    {#if !preview.execution_available}<p role="status">{at("resource_ops_error_disabled")}</p>{/if}
    <AdminButton
      disabled={!$intent?.ready ||
        $intent.busy ||
        $intent.needsPreview ||
        !confirmed ||
        !preview.execution_available}
      onclick={() => {
        if (preview) void intent?.submit(preview, confirmed, recoveryOf);
      }}>{at("resource_ops_submit")}</AdminButton
    >
  {/if}
  {#if $intent && !$intent.ready && !$intent.busy}<AdminButton onclick={() => intent?.initialize()}
      >{at("refresh")}</AdminButton
    >{/if}
</div>

<style>
  .resource-submit {
    display: grid;
    gap: 12px;
    min-width: 0;
  }
  p {
    margin: 0;
    overflow-wrap: anywhere;
  }
  a {
    color: var(--accent);
  }
</style>
