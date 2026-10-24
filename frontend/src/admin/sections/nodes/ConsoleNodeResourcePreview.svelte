<script lang="ts">
  import { onDestroy, onMount, tick, untrack } from "svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import { Checkbox } from "$components/ui/index.js";
  import { AdminButton, AdminField, AdminSelect } from "$components/patterns/admin/index.js";
  import type { ApiClient } from "$lib/webapp/publicApi";
  import type { ConsoleNode, ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import ConsoleServiceDetail from "../services/ConsoleServiceDetail.svelte";
  import ConsoleResourcePreviewResult from "./ConsoleResourcePreviewResult.svelte";
  import ResourceOperationSubmit from "./ResourceOperationSubmit.svelte";
  import { canReviewPreview, createResourcePreview, nodeOperations } from "./resourcePreview";
  import {
    nodePreviewChange,
    nodePreviewUrl,
    readNodePreviewRoute,
    type NodePreviewRoute,
  } from "./resourcePreviewNavigation";

  let {
    api,
    node,
    at,
    currentUrl,
    routePrefix = "",
    onOpenUserCard,
  }: {
    api: ApiClient["api"];
    node: ConsoleNode;
    at: ConsoleNodesTranslate;
    currentUrl: string;
    routePrefix?: string;
    onOpenUserCard: (id: unknown) => void;
  } = $props();
  const previewState = untrack(() => createResourcePreview(api));
  let route = $state(readNodePreviewRoute(""));
  let sourceUrl = $state("");
  let content: HTMLDivElement | undefined;
  const reviewable = $derived(
    !$previewState.busy &&
      $previewState.validation !== "incomplete" &&
      canReviewPreview($previewState.preview)
  );
  const items = $derived(
    nodeOperations.map((value) => ({ value, label: at(`console_resource_${value}`) }))
  );

  function setRoute(next: NodePreviewRoute) {
    route = next;
    previewState.setChange(nodePreviewChange(node.id, next));
  }
  function navigate(patch: Partial<NodePreviewRoute>) {
    setRoute({ ...route, ...patch });
    const url = nodePreviewUrl(window.location.href, route, routePrefix);
    window.history.pushState(null, "", url);
    sourceUrl = url.href;
  }
  function serviceHref(serviceId: string) {
    return nodePreviewUrl(sourceUrl || currentUrl, { ...route, serviceId }, routePrefix).href;
  }
  async function closeService() {
    const serviceId = route.serviceId;
    navigate({ serviceId: "" });
    await tick();
    content
      ?.querySelector<HTMLAnchorElement>(`[data-resource-service-id="${CSS.escape(serviceId)}"]`)
      ?.focus();
  }
  $effect(() => previewState.setChange(nodePreviewChange(node.id, route)));
  onMount(() => {
    const restore = () => {
      sourceUrl = window.location.href;
      setRoute(readNodePreviewRoute(window.location.search));
      if (route.open && route.operation && !$previewState.preview && !$previewState.busy)
        void previewState.load();
    };
    restore();
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  });
  onDestroy(() => previewState.destroy());
</script>

<AdminButton onclick={() => navigate({ open: true })}>{at("console_resource_open")}</AdminButton>
<Dialog
  open={route.open && !route.serviceId}
  portal
  size="wide"
  class="admin-dialog"
  title={at("console_resource_title")}
  description={at("resource_ops_review_scope")}
  closeLabel={at("close")}
  onclose={() => navigate({ open: false, operation: "", forceRestart: false, serviceId: "" })}
>
  <div bind:this={content} class="node-resource-preview" aria-busy={Boolean($previewState.busy)}>
    <p>{node.name} · {node.id}</p>
    <AdminField label={at("console_resource_operation")}>
      <AdminSelect
        value={route.operation}
        {items}
        ariaLabel={at("console_resource_operation")}
        placeholder={at("console_resource_choose_operation")}
        onValueChange={(value) =>
          navigate({
            operation: nodeOperations.find((operation) => operation === value) ?? "",
            forceRestart: false,
          })}
      />
    </AdminField>
    {#if route.operation === "node_restart"}<label class="confirmation">
        <Checkbox
          checked={route.forceRestart}
          onCheckedChange={(forceRestart) => navigate({ forceRestart })}
          ariaLabel={at("console_resource_force_restart")}
        />
        <span>{at("console_resource_force_restart")}</span>
      </label>{/if}
    <div>
      <AdminButton
        disabled={!$previewState.change || Boolean($previewState.busy)}
        onclick={() => previewState.load()}>{at("console_resource_preview")}</AdminButton
      >
    </div>
    {#if $previewState.busy}<p role="status">{at("loading")}</p>{/if}
    {#if $previewState.failed}<p role="alert">
        {at(
          $previewState.validation === "failed"
            ? "console_resource_revalidate_failed"
            : "services_request_failed"
        )}
      </p>{/if}
    {#if $previewState.validation && $previewState.validation !== "failed"}
      <p role="status">{at(`console_resource_revalidate_${$previewState.validation}`)}</p>
    {/if}
    {#if $previewState.preview}
      <ConsoleResourcePreviewResult
        preview={$previewState.preview}
        {at}
        currentUrl={sourceUrl || currentUrl}
        {routePrefix}
        {serviceHref}
        onOpenService={(serviceId) => navigate({ serviceId })}
        {onOpenUserCard}
      />
      <label class="confirmation"
        ><Checkbox
          checked={$previewState.confirmed}
          disabled={!reviewable}
          onCheckedChange={(value) => previewState.confirm(value)}
          ariaLabel={at("console_resource_confirm")}
        />
        <span>{at("console_resource_confirm")}</span></label
      >
      <div>
        <AdminButton disabled={!reviewable} onclick={() => previewState.revalidate()}
          >{at("console_resource_revalidate")}</AdminButton
        >
      </div>
      <ResourceOperationSubmit
        {api}
        {at}
        {routePrefix}
        preview={$previewState.preview}
        confirmed={$previewState.confirmed && reviewable}
      />
    {/if}
  </div>
</Dialog>
{#if route.open && route.serviceId}
  <ConsoleServiceDetail
    {api}
    {at}
    serviceId={route.serviceId}
    {routePrefix}
    {onOpenUserCard}
    onclose={closeService}
  />
{/if}

<style>
  .node-resource-preview {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  p {
    margin: 0;
    overflow-wrap: anywhere;
  }
  .confirmation {
    display: flex;
    align-items: start;
    gap: 10px;
  }
  .confirmation span {
    overflow-wrap: anywhere;
  }
</style>
