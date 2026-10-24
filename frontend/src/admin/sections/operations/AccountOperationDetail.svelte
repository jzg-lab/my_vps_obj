<script lang="ts">
  import { onDestroy } from "svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import { AdminButton } from "$components/patterns/admin";
  import type { ApiClient } from "$lib/webapp/publicApi";
  import type { ServiceTranslate } from "$lib/admin/servicePlans";
  import { readAccountOperation, type AccountOperation } from "$lib/admin/consoleAccountOperations";
  import AccountOperationTable from "./AccountOperationTable.svelte";

  let {
    api,
    at,
    operationId,
    onclose,
    onOpenUserCard,
  }: {
    api: ApiClient["api"];
    at: ServiceTranslate;
    operationId: string;
    onclose: () => void;
    onOpenUserCard: (id: unknown) => void;
  } = $props();
  let operation = $state<AccountOperation | null>(null);
  let busy = $state(true);
  let failed = $state(false);
  let sequence = 0;
  let controller: AbortController | null = null;

  async function load(id: string) {
    const token = ++sequence;
    controller?.abort();
    controller = new AbortController();
    busy = true;
    failed = false;
    operation = null;
    try {
      const result = await readAccountOperation(api, id, controller.signal);
      if (token === sequence) operation = result;
    } catch {
      if (token === sequence) failed = true;
    } finally {
      if (token === sequence) busy = false;
    }
  }
  $effect(() => {
    void load(operationId);
  });
  onDestroy(() => {
    sequence++;
    controller?.abort();
  });
</script>

<Dialog
  open
  portal
  size="wide"
  class="admin-dialog account-operation-dialog"
  title={at("account_ops_detail")}
  closeLabel={at("close")}
  {onclose}
>
  <section class="account-operation-detail" aria-busy={busy}>
    <div>
      <AdminButton disabled={busy} onclick={() => load(operationId)}>{at("refresh")}</AdminButton>
    </div>
    {#if failed}<p role="alert">{at("account_ops_detail_failed")}</p>
    {:else if busy}<p role="status">{at("loading")}</p>
    {:else if operation}
      <p>{at("account_ops_scope")}</p>
      <p>{at("account_ops_record")}: <span data-account-operation-code>{operation.id}</span></p>
      <AccountOperationTable operations={[operation]} {at} {onOpenUserCard} />
    {/if}
  </section>
</Dialog>

<style>
  .account-operation-detail {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  p {
    margin: 0;
    overflow-wrap: anywhere;
  }
</style>
