<script lang="ts">
  import type { DedicatedExit, ServiceTranslate } from "$lib/admin/servicePlans";
  import DedicatedExitServiceLink from "./DedicatedExitServiceLink.svelte";
  import { exitHasHold } from "./availability";

  let {
    resource,
    at,
    currentUrl,
    routePrefix = "",
    disabled = false,
    onOpenService,
  }: {
    resource: DedicatedExit;
    at: ServiceTranslate;
    currentUrl: string;
    routePrefix?: string;
    disabled?: boolean;
    onOpenService: (serviceId: string) => void;
  } = $props();
</script>

{#if resource.service_id || !exitHasHold(resource)}
  <DedicatedExitServiceLink
    serviceId={resource.service_id}
    {at}
    {currentUrl}
    {routePrefix}
    {disabled}
    {onOpenService}
  />
{/if}
{#if exitHasHold(resource)}
  <div class="hold-owner">
    <span>{at("services_exit_hold_service")}</span>
    {#if resource.hold_service_id}
      <DedicatedExitServiceLink
        serviceId={resource.hold_service_id}
        {at}
        {currentUrl}
        {routePrefix}
        {disabled}
        {onOpenService}
      />
    {:else}<span>{at("console_unknown")}</span>{/if}
  </div>
{/if}

<style>
  .hold-owner {
    display: grid;
    gap: 4px;
    overflow-wrap: anywhere;
  }
</style>
