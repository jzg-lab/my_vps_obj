<script lang="ts">
  import { tick } from "svelte";
  import { AdminButton } from "$components/patterns/admin";
  import { serviceChangeActions } from "$lib/admin/serviceChanges";
  import type { ServiceTranslate, UserService } from "$lib/admin/servicePlans";
  import type { ApiClient } from "$lib/webapp/publicApi";
  import ServiceChangeDialog from "./ServiceChangeDialog.svelte";
  import ServiceDeliverDialog from "./ServiceDeliverDialog.svelte";
  import ServiceOrdersDialog from "./ServiceOrdersDialog.svelte";
  import ServiceRevokeDialog from "./ServiceRevokeDialog.svelte";
  import ServiceDiagnosticsDialog from "./ServiceDiagnosticsDialog.svelte";
  import ServiceExitReplacementDialog from "./ServiceExitReplacementDialog.svelte";
  import { canInspectReplacement } from "$lib/admin/exitReplacement";

  let {
    api,
    at,
    service,
    readonly = false,
    banned = false,
    disabled = false,
    routePrefix = "",
    dialogOpen = $bindable(false),
    onrefresh,
    onOpenDetail,
  }: {
    api: ApiClient["api"];
    at: ServiceTranslate;
    service: UserService;
    readonly?: boolean;
    banned?: boolean;
    disabled?: boolean;
    routePrefix?: string;
    dialogOpen?: boolean;
    onrefresh: () => void | Promise<void>;
    onOpenDetail?: () => void;
  } = $props();
  type Action = "history" | "change" | "deliver" | "revoke" | "diagnostics" | "replacement";
  let action = $state<Action | null>(null);
  const editable = $derived(!readonly && service.user_id !== null);
  const deliverable = $derived(
    editable &&
      !banned &&
      service.status === "pending" &&
      service.connection_state === "pending" &&
      service.last_usage_sync_at &&
      !service.usage_error &&
      !service.sync_pending &&
      !service.replacement_order_id &&
      (service.resource_type === "shared" || service.exit_verified)
  );
  function open(next: Action) {
    action = next;
    dialogOpen = true;
  }
  async function close() {
    const returnFocusId =
      action === "replacement" ? `service-exit-replacement-${service.id}` : null;
    const refresh = action !== "history";
    action = null;
    dialogOpen = false;
    // Closing an uncertain write also reloads the authoritative service state.
    if (refresh) await onrefresh();
    if (returnFocusId) {
      // Refresh remounts the action buttons in both service consumers.
      await tick();
      document.getElementById(returnFocusId)?.focus();
    }
  }
</script>

<div class="service-actions">
  {#if deliverable}<AdminButton
      size="sm"
      variant="primary"
      disabled={disabled || dialogOpen}
      onclick={() => open("deliver")}>{at("services_deliver")}</AdminButton
    >{/if}
  {#if onOpenDetail}<AdminButton size="sm" disabled={disabled || dialogOpen} onclick={onOpenDetail}
      >{at("console_service_detail")}</AdminButton
    >{/if}
  <AdminButton size="sm" disabled={disabled || dialogOpen} onclick={() => open("history")}
    >{at("services_view_history")}</AdminButton
  >
  <AdminButton size="sm" disabled={disabled || dialogOpen} onclick={() => open("diagnostics")}
    >{at("console_ops_title")}</AdminButton
  >
  {#if canInspectReplacement(service)}<AdminButton
      id={`service-exit-replacement-${service.id}`}
      size="sm"
      disabled={disabled || dialogOpen}
      onclick={() => open("replacement")}>{at("replacement_title")}</AdminButton
    >{/if}
  {#if editable && serviceChangeActions(service).length}<AdminButton
      size="sm"
      disabled={disabled || dialogOpen}
      onclick={() => open("change")}>{at("services_manage")}</AdminButton
    >{/if}
  {#if editable && service.desired_status !== "cancelled" && service.connection_state !== "revoked"}<AdminButton
      size="sm"
      variant="danger"
      disabled={disabled || dialogOpen}
      onclick={() => open("revoke")}>{at("services_revoke")}</AdminButton
    >{/if}
</div>

{#if action === "replacement"}{#key service.id}<ServiceExitReplacementDialog
      {api}
      {at}
      {service}
      {routePrefix}
      readonly={!editable}
      onclose={close}
    />{/key}
{:else if action === "history"}<ServiceOrdersDialog {api} {at} {service} onclose={close} />
{:else if action === "diagnostics"}{#key service.id}<ServiceDiagnosticsDialog
      {api}
      {at}
      {service}
      {readonly}
      onclose={close}
    />{/key}
{:else if action === "change"}<ServiceChangeDialog
    {api}
    {at}
    {service}
    onclose={close}
    onsaved={close}
  />
{:else if action === "deliver"}<ServiceDeliverDialog
    {api}
    {at}
    {service}
    onclose={close}
    onsaved={close}
  />
{:else if action === "revoke"}<ServiceRevokeDialog
    {api}
    {at}
    {service}
    onclose={close}
    onsaved={close}
  />{/if}

<style>
  .service-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
</style>
