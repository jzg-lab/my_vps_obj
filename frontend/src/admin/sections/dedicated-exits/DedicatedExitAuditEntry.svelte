<script lang="ts">
  import type { components } from "$lib/api/openapi.generated";
  import type { ServiceTranslate } from "$lib/admin/servicePlans";
  import { serviceDate } from "$lib/webapp/independentServices";
  import DedicatedExitServiceLink from "./DedicatedExitServiceLink.svelte";
  import { exitAuditActionLabel } from "./auditAction";

  let {
    item,
    at,
    currentUrl,
    routePrefix = "",
    disabled = false,
    onOpenService,
  }: {
    item: components["schemas"]["ExitAuditOut"];
    at: ServiceTranslate;
    currentUrl: string;
    routePrefix?: string;
    disabled?: boolean;
    onOpenService: (serviceId: string) => void;
  } = $props();
  const label = $derived(exitAuditActionLabel(item.action));
</script>

<li>
  <strong>{at(label)}</strong> · {serviceDate(item.created_at)}
  <p>{at("services_exit_actor")}: {item.actor_id}</p>
  <DedicatedExitServiceLink
    serviceId={item.service_id}
    {currentUrl}
    {routePrefix}
    {at}
    {onOpenService}
    {disabled}
  />
  {#if (item.action === "verify" || item.action === "reclaim") && typeof item.evidence.evidence === "string"}
    <p>{item.evidence.evidence}</p>
  {/if}
</li>

<style>
  li {
    margin-bottom: 16px;
    overflow-wrap: anywhere;
  }
</style>
