<script lang="ts">
  import { AdminEntityLink } from "$components/patterns/admin/index.js";
  import type { ServiceTranslate } from "$lib/admin/servicePlans";
  import { dedicatedExitsUrl, readDedicatedExitsRoute } from "./navigation";

  let {
    serviceId,
    currentUrl,
    routePrefix = "",
    at,
    disabled = false,
    onOpenService,
  }: {
    serviceId: string | null;
    currentUrl: string;
    routePrefix?: string;
    at: ServiceTranslate;
    disabled?: boolean;
    onOpenService: (serviceId: string) => void;
  } = $props();
  const href = $derived(
    dedicatedExitsUrl(
      currentUrl,
      { ...readDedicatedExitsRoute(new URL(currentUrl).search), serviceId: serviceId ?? "" },
      routePrefix
    ).href
  );
</script>

{#if serviceId}
  {#if disabled}
    <AdminEntityLink kind="code" label={serviceId} />
  {:else}
    <a
      {href}
      data-service-id={serviceId}
      title={at("console_service_detail")}
      onclick={(event) => {
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
          return;
        event.preventDefault();
        onOpenService(serviceId!);
      }}><AdminEntityLink kind="code" label={serviceId} /></a
    >
  {/if}
{:else}
  <span>—</span>
{/if}

<style>
  a {
    color: var(--accent);
    text-decoration: none;
  }
  a:hover {
    text-decoration: underline;
  }
</style>
