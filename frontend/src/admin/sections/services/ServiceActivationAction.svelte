<script lang="ts">
  import { AdminButton } from "$components/patterns/admin";
  import type { ServiceTranslate } from "$lib/admin/servicePlans";
  import type { ApiClient } from "$lib/webapp/publicApi";
  import ServiceActivationDialog from "./ServiceActivationDialog.svelte";

  let {
    api,
    at,
    userId,
    banned = false,
    disabled = false,
    dialogOpen = $bindable(false),
    oncreated,
    onrefresh,
  }: {
    api: ApiClient["api"];
    at: ServiceTranslate;
    userId: number | null;
    banned?: boolean;
    disabled?: boolean;
    dialogOpen?: boolean;
    oncreated: () => void;
    onrefresh: () => void;
  } = $props();
</script>

{#if userId !== null}<AdminButton
    variant="primary"
    disabled={banned || disabled || dialogOpen}
    onclick={() => (dialogOpen = true)}>{at("services_activate")}</AdminButton
  >
  {#if dialogOpen}<ServiceActivationDialog
      {api}
      {at}
      {userId}
      onclose={() => {
        dialogOpen = false;
        onrefresh();
      }}
      oncreated={() => {
        dialogOpen = false;
        oncreated();
      }}
    />{/if}{/if}
