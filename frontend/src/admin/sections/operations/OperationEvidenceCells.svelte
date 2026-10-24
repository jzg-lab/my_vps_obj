<script lang="ts">
  import { AdminBadge } from "$components/patterns/admin";
  import type { ServiceTranslate } from "$lib/admin/servicePlans";
  import { serviceDate } from "$lib/webapp/independentServices";
  import {
    consoleServiceErrorKey,
    consoleServiceLabel,
    type ServiceOperation,
  } from "$lib/admin/consoleServiceOperations";
  import type { GlobalOperation } from "$lib/admin/consoleGlobalOperations";
  let {
    at,
    operation,
    global,
  }: {
    at: ServiceTranslate;
    operation: ServiceOperation;
    global?: Pick<GlobalOperation, "record_type" | "needs_attention" | "last_success_at">;
  } = $props();
  const date = (value: string | null) => (value ? serviceDate(value) : at("console_unknown"));
</script>

<td data-label={at("console_ops_operation")}>
  <strong
    >{at(
      consoleServiceLabel("kind", operation.kind) === "console_unknown"
        ? consoleServiceLabel("phase", operation.phase)
        : consoleServiceLabel("kind", operation.kind)
    )}</strong
  >
  <small>{operation.id}</small>
  <small
    >{at(consoleServiceLabel("phase", operation.phase))} · {at(
      consoleServiceLabel("source", operation.source)
    )}</small
  >
  {#if global}<small
      >{at(
        global.record_type === "order" ? "console_global_order" : "console_global_execution"
      )}</small
    >{/if}
  <small
    >{at("console_ops_target_revision")}: {operation.target_revision ??
      at("console_unknown")}</small
  >
  <small>{at("services_actor")}: {operation.actor_id ?? at("console_unknown")}</small>
  <small>{at("services_order_id")}: {operation.order_id ?? at("console_unknown")}</small>
</td>
<td data-label={at("console_ops_result")}>
  <AdminBadge
    variant={operation.status === "succeeded"
      ? "success"
      : operation.status === "failed"
        ? "danger"
        : "muted"}
  >
    {at(consoleServiceLabel("operation", operation.status))}
  </AdminBadge>
  {#if global?.needs_attention}<small>{at("console_global_attention")}</small>{/if}
  {#if global?.record_type === "order"}<p>{at("console_ops_history_unknown")}</p>{/if}
  <small
    >{at("console_ops_attempt_count")}: {operation.attempt_count ?? at("console_unknown")}</small
  >
  {#if operation.error_code}<p>{at(consoleServiceErrorKey(operation.error_code))}</p>{/if}
</td>
<td data-label={at("console_ops_times")}>
  <small>{at("services_recorded_at")}: {date(operation.created_at)}</small>
  <small>{at("console_ops_attempted_at")}: {date(operation.attempted_at)}</small>
  <small>{at("console_ops_first_failed_at")}: {date(operation.first_failed_at)}</small>
  <small>{at("console_ops_completed_at")}: {date(operation.completed_at)}</small>
  {#if global}<small>{at("console_global_phase_success")}: {date(global.last_success_at)}</small
    >{/if}
</td>

<style>
  small {
    display: block;
    color: var(--admin-muted);
    margin-top: 4px;
  }
  p {
    margin: 0;
  }
  td {
    overflow-wrap: anywhere;
  }
</style>
