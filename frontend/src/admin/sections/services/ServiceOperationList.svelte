<script lang="ts">
  import {
    AdminButton,
    AdminEmptyState,
    AdminPagination,
    AdminTable,
  } from "$components/patterns/admin";
  import type { ServiceTranslate } from "$lib/admin/servicePlans";
  import OperationEvidenceCells from "../operations/OperationEvidenceCells.svelte";
  import {
    consoleServiceErrorKey,
    type ServiceOperation,
    type ServiceOperations,
    type ServiceRetryBody,
  } from "$lib/admin/consoleServiceOperations";
  let {
    at,
    data,
    pending,
    readonly,
    disabled,
    onretry,
    onpage,
  }: {
    at: ServiceTranslate;
    data: ServiceOperations;
    pending: Record<string, ServiceRetryBody>;
    readonly: boolean;
    disabled: boolean;
    onretry: (id: string) => void;
    onpage: (page: number) => void;
  } = $props();
  // The single-service contract uses a null phase only for historical orders.
  const operationKey = (operation: ServiceOperation) =>
    `${operation.phase === null ? "order" : "execution"}:${operation.id}`;
</script>

<section aria-label={at("console_ops_operations")}>
  <h4>{at("console_ops_operations")}</h4>
  <p>{at("console_ops_retry_hint")}</p>
  {#if !data.operations.length}<AdminEmptyState tone="card"
      >{at("console_ops_empty")}</AdminEmptyState
    >
  {:else}<AdminTable>
      <thead
        ><tr
          >{#each ["console_ops_operation", "console_ops_result", "console_ops_times", "console_ops_retry"] as key}<th
              >{at(key)}</th
            >{/each}</tr
        ></thead
      >
      <tbody
        >{#each data.operations as operation (operationKey(operation))}
          {@const receipt = operation.phase === null ? undefined : pending[operation.id]}
          <tr data-operation-key={operationKey(operation)}>
            <OperationEvidenceCells {at} {operation} />
            <td data-label={at("console_ops_retry")}>
              {#if receipt}<p>{at("console_ops_uncertain_receipt")}</p>{/if}
              {#if !readonly && operation.phase !== null && (operation.retryable || receipt)}<AdminButton
                  size="sm"
                  {disabled}
                  onclick={() => onretry(operation.id)}
                  >{at(receipt ? "console_ops_confirm_receipt" : "console_ops_retry")}</AdminButton
                >{/if}
              {#if operation.retry_block_reason}<small
                  >{at(consoleServiceErrorKey(operation.retry_block_reason))}</small
                >{/if}
            </td>
          </tr>
        {/each}</tbody
      >
    </AdminTable>{/if}
  <AdminPagination
    page={Math.floor(data.offset / data.limit)}
    pageCount={Math.ceil(data.total / data.limit)}
    total={data.total}
    {disabled}
    onPageChange={onpage}
    prevLabel={at("services_previous")}
    nextLabel={at("services_next")}
    pageLabel={at("services_page")}
    ofLabel={at("services_of")}
    totalLabel={at("console_ops_operations")}
    jumpLabel={at("services_page")}
    jumpAriaLabel={at("services_go_page")}
    goLabel={at("services_go_page")}
  />
</section>

<style>
  section {
    display: grid;
    gap: 16px;
    min-width: 0;
    border-top: 1px solid var(--admin-border);
    padding-top: 16px;
  }
  h4,
  p {
    margin: 0;
  }
  h4 {
    font-size: 14px;
  }
  small {
    display: block;
    color: var(--admin-muted);
    margin-top: 4px;
  }
  td {
    overflow-wrap: anywhere;
  }
</style>
