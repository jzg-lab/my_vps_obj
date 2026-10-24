<script lang="ts">
  import { AdminBadge, AdminTable } from "$components/patterns/admin";
  import { serviceDate } from "$lib/webapp/independentServices";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import {
    resourceActionKey,
    resourceErrorKey,
    type ResourceOperation,
  } from "$lib/admin/resourceOperations";
  import ResourceObservedValues from "./ResourceObservedValues.svelte";
  let { operation, at }: { operation: ResourceOperation; at: ConsoleNodesTranslate } = $props();
  function label(group: string, value: string) {
    const options: Record<string, string[]> = {
      status: ["pending", "unknown", "failed", "succeeded", "superseded"],
      configuration: ["matched", "different", "missing", "unavailable"],
      restart: ["not_requested", "accepted_unverified", "may_be_noop", "unknown"],
      correlation: [
        "response_uuid",
        "creation_marker",
        "administrator_attestation",
        "known_uuid",
        "unresolved",
      ],
      receipt: ["unknown", "accepted", "rejected"],
      evidence: ["applied", "not_applied", "partial", "externally_removed"],
    };
    return at(
      options[group]?.includes(value) ? `resource_ops_${group}_${value}` : "console_unknown"
    );
  }
</script>

<div class="resource-operation-status">
  <h3>{at(resourceActionKey(operation.change.operation))}</h3>
  <p>{operation.id}</p>
  <p>
    <AdminBadge
      wrap
      variant={operation.status === "succeeded"
        ? "success"
        : operation.status === "failed"
          ? "danger"
          : "warning"}>{label("status", operation.status)}</AdminBadge
    >
  </p>
  <p>{at(operation.gate_active ? "resource_ops_gate_held" : "resource_ops_gate_released")}</p>
  <p>{at("resource_ops_runtime_unverified")}</p>
  {#if operation.error_code}<p role="alert">{at(resourceErrorKey(operation.error_code))}</p>{/if}
  {#if operation.error_code === "resource_target_removed"}
    <p role="note">{at("resource_ops_removed_warning")}</p>
  {/if}
  <p>{at("resource_ops_target_id")}: {operation.target_id ?? at("console_unknown")}</p>
  <p>
    {at("resource_ops_created")}: {serviceDate(operation.created_at)} · {at(
      "resource_ops_completed"
    )}: {operation.completed_at ? serviceDate(operation.completed_at) : at("console_unknown")}
  </p>
  {#if operation.observation}
    <p>
      {at("resource_ops_configuration")}: {label(
        "configuration",
        operation.observation.configuration
      )}
    </p>
    <p>
      {at("resource_ops_correlation")}: {label("correlation", operation.observation.correlation)}
    </p>
    <p>{at("resource_ops_restart")}: {label("restart", operation.observation.restart)}</p>
    <p>{at("console_observed_at")}: {serviceDate(operation.observation.observed_at)}</p>
    {#if operation.observation.values}<ResourceObservedValues
        values={operation.observation.values}
        {at}
      />{/if}
  {/if}
  <AdminTable layout="fixed"
    ><thead
      ><tr
        ><th>{at("resource_ops_attempt")}</th><th>{at("resource_ops_receipt")}</th><th
          >{at("console_observed_at")}</th
        ></tr
      ></thead
    ><tbody
      >{#each operation.attempts as attempt}<tr
          ><td data-label={at("resource_ops_attempt")}>{attempt.number}</td><td
            data-label={at("resource_ops_receipt")}>{label("receipt", attempt.receipt)}</td
          ><td data-label={at("console_observed_at")}>{serviceDate(attempt.started_at)}</td></tr
        >{:else}<tr><td colspan="3">{at("resource_ops_not_sent")}</td></tr>{/each}</tbody
    ></AdminTable
  >
  {#if operation.evidence.length}<h4>{at("resource_ops_attestation_title")}</h4>
    <p>{at("resource_ops_attestation")}</p>
    <ul>
      {#each operation.evidence as evidence}<li>
          #{evidence.attempt} · {label("evidence", evidence.result)} · {serviceDate(
            evidence.observed_at
          )} · {at("resource_ops_actor")}: {evidence.actor_id}
        </li>{/each}
    </ul>{/if}
</div>

<style>
  .resource-operation-status {
    display: grid;
    gap: 12px;
    min-width: 0;
  }
  h3,
  h4,
  p,
  ul {
    margin: 0;
    overflow-wrap: anywhere;
  }
  td {
    overflow-wrap: anywhere;
  }
</style>
