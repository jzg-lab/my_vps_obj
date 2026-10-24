<script lang="ts">
  import { AdminBadge, AdminButton, AdminEntityLink, AdminTable } from "$components/patterns/admin";
  import type { ServiceTranslate } from "$lib/admin/servicePlans";
  import { serviceDate } from "$lib/webapp/independentServices";
  import { consoleServiceLabel } from "$lib/admin/consoleServiceOperations";
  import {
    accountBanKey,
    accountOperationCustomer,
    accountOperationErrorKey,
    type AccountOperation,
  } from "$lib/admin/consoleAccountOperations";

  let {
    operations,
    at,
    onOpenUserCard,
    onOpenOperation,
  }: {
    operations: AccountOperation[];
    at: ServiceTranslate;
    onOpenUserCard: (id: unknown) => void;
    onOpenOperation?: (id: string) => void;
  } = $props();
  const date = (value: string | null) => (value ? serviceDate(value) : at("console_unknown"));
</script>

<AdminTable layout="fixed">
  <thead
    ><tr>
      {#each ["account_ops_record", "account_ops_target", "services_actor", "account_ops_change", "console_ops_result", "console_ops_times"] as key}
        <th>{at(key)}</th>
      {/each}
    </tr></thead
  >
  <tbody>
    {#each operations as operation (operation.id)}
      {@const customer = accountOperationCustomer(operation)}
      <tr data-account-operation-id={operation.id}>
        <td data-label={at("account_ops_record")} data-account-record>
          <AdminEntityLink
            kind="code"
            label={at(operation.desired_banned ? "account_ops_ban" : "account_ops_unban")}
            idText={operation.id}
            onclick={onOpenOperation ? () => onOpenOperation?.(operation.id) : undefined}
          />
          <small
            >{at("account_ops_source")}: {at(
              consoleServiceLabel("source", operation.source)
            )}</small
          >
        </td>
        <td data-label={at("account_ops_target")} data-account-target>
          <span>{operation.target_id}</span>
          {#if customer === null}<small>{at("services_history_title")}</small>
          {:else}
            <AdminEntityLink
              label={at("account_ops_current_customer")}
              idText={String(customer)}
              title={at("account_ops_open_customer")}
              onclick={() => onOpenUserCard(customer)}
            />
          {/if}
        </td>
        <td data-label={at("services_actor")}>
          {operation.actor_id ?? at("console_unknown")}
        </td>
        <td data-label={at("account_ops_change")}>
          {at(accountBanKey(operation.before_banned))} → {at(
            accountBanKey(operation.desired_banned)
          )}
        </td>
        <td data-label={at("console_ops_result")}>
          <AdminBadge
            wrap
            variant={operation.status === "succeeded"
              ? "success"
              : operation.status === "failed"
                ? "danger"
                : "muted"}
          >
            {at(consoleServiceLabel("operation", operation.status))}
          </AdminBadge>
          <small>{at("console_ops_attempt_count")}: {operation.attempt_count}</small>
          {#if operation.error_code}<p>{at(accountOperationErrorKey(operation.error_code))}</p>{/if}
          {#if operation.needs_attention}
            <small>{at("console_global_attention")}</small>
            {#if customer !== null}
              <AdminButton size="sm" onclick={() => onOpenUserCard(customer)}
                >{at("account_ops_review_customer")}</AdminButton
              >
            {/if}
          {/if}
        </td>
        <td data-label={at("console_ops_times")}>
          <small>{at("services_recorded_at")}: {date(operation.created_at)}</small>
          <small>{at("console_ops_attempted_at")}: {date(operation.attempted_at)}</small>
          <small>{at("console_ops_first_failed_at")}: {date(operation.first_failed_at)}</small>
          <small>{at("console_ops_completed_at")}: {date(operation.completed_at)}</small>
        </td>
      </tr>
    {/each}
  </tbody>
</AdminTable>

<style>
  td,
  p {
    overflow-wrap: anywhere;
  }
  p {
    margin: 4px 0;
  }
  small {
    display: block;
    color: var(--admin-muted);
    margin-top: 4px;
  }
  td :global(.admin-btn) {
    max-width: 100%;
    height: auto;
    white-space: normal;
    overflow-wrap: anywhere;
    padding-block: 8px;
  }
</style>
