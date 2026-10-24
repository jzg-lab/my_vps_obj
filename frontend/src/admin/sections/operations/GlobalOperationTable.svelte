<script lang="ts">
  import { AdminEntityLink, AdminTable } from "$components/patterns/admin";
  import type { ServiceTranslate } from "$lib/admin/servicePlans";
  import type { GlobalOperation } from "$lib/admin/consoleGlobalOperations";
  import { customerLabel } from "$lib/admin/consoleServices";
  import OperationEvidenceCells from "./OperationEvidenceCells.svelte";
  let {
    at,
    operations,
    onOpenService,
    onOpenUserCard,
  }: {
    at: ServiceTranslate;
    operations: GlobalOperation[];
    onOpenService: (id: string) => void;
    onOpenUserCard: (id: unknown) => void;
  } = $props();
</script>

<AdminTable>
  <thead
    ><tr
      >{#each ["console_customer", "services_name", "console_ops_operation", "console_ops_result", "console_ops_times"] as key}<th
          >{at(key)}</th
        >{/each}</tr
    ></thead
  >
  <tbody>
    {#each operations as operation (`${operation.record_type}:${operation.id}`)}
      <tr data-operation-key={`${operation.record_type}:${operation.id}`}>
        <td data-label={at("console_customer")}>
          {#if operation.archived || operation.customer.user_id === null}
            {at("services_history_title")}
          {:else}
            <AdminEntityLink
              label={customerLabel(operation.customer) || String(operation.customer.user_id)}
              idText={operation.customer.minishop_id ?? undefined}
              onclick={() => onOpenUserCard(operation.customer.user_id)}
            />
          {/if}
        </td>
        <td data-label={at("services_name")}>
          <AdminEntityLink
            kind="code"
            label={operation.service_name}
            idText={operation.service_id}
            title={at("console_global_open_service")}
            onclick={() => onOpenService(operation.service_id)}
          />
        </td>
        <OperationEvidenceCells {at} {operation} global={operation} />
      </tr>
    {/each}
  </tbody>
</AdminTable>
