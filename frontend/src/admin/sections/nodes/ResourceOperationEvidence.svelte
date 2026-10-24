<script lang="ts">
  import { Input, DateInput, Checkbox } from "$components/ui";
  import { AdminButton, AdminField, AdminSelect } from "$components/patterns/admin";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import {
    resourceEvidenceBody,
    type ResourceEvidence,
    type ResourceOperation,
  } from "$lib/admin/resourceOperations";
  let {
    operation,
    at,
    busy,
    disabled = false,
    onsubmit,
  }: {
    operation: ResourceOperation;
    at: ConsoleNodesTranslate;
    busy: boolean;
    disabled?: boolean;
    onsubmit: (body: ResourceEvidence) => void;
  } = $props();
  let result = $state<ResourceEvidence["result"] | "">("");
  let digest = $state("");
  let checkedAt = $state("");
  let targetId = $state("");
  let confirmed = $state(false);
  let terminated = $state(false);
  const body = $derived(
    resourceEvidenceBody(operation, result, digest, checkedAt, targetId, terminated)
  );
</script>

<form
  class="resource-evidence"
  onsubmit={(event) => {
    event.preventDefault();
    const current = resourceEvidenceBody(
      operation,
      result,
      digest,
      checkedAt,
      targetId,
      terminated
    );
    if (current && confirmed && !busy && !disabled) onsubmit(current);
  }}
>
  <p>{at("resource_ops_attestation")}</p>
  <AdminField label={at("resource_ops_evidence_result")}
    ><AdminSelect
      value={result}
      wrapLabels
      disabled={busy || disabled}
      ariaLabel={at("resource_ops_evidence_result")}
      items={[
        "applied",
        "not_applied",
        "partial",
        ...(operation.target_id ? ["externally_removed"] : []),
      ].map((value) => ({
        value,
        label: at(`resource_ops_evidence_${value}`),
      }))}
      onValueChange={(value) => {
        if (
          value === "applied" ||
          value === "not_applied" ||
          value === "partial" ||
          value === "externally_removed"
        )
          result = value;
        confirmed = false;
        terminated = false;
      }}
    /></AdminField
  >
  <AdminField label={at("services_exit_checked_at")}
    ><DateInput
      withTime
      bind:value={checkedAt}
      disabled={busy || disabled}
      ariaLabel={at("services_exit_checked_at")}
      clearLabel={at("clear")}
    /></AdminField
  >
  <AdminField label={at("replacement_digest")}
    ><Input
      bind:value={digest}
      disabled={busy || disabled}
      required
      pattern={"[a-f0-9]{64}"}
      maxlength={64}
      aria-label={at("replacement_digest")}
    /></AdminField
  >
  {#if operation.change.operation.endsWith("_create") || result === "externally_removed"}<AdminField
      label={at("resource_ops_target_id")}
      ><Input
        bind:value={targetId}
        disabled={busy || disabled}
        maxlength={36}
        required={result !== "not_applied"}
        aria-label={at("resource_ops_target_id")}
      /></AdminField
    >{/if}
  {#if result === "externally_removed"}
    <p role="note">{at("resource_ops_removed_warning")}</p>
    <label>
      <Checkbox
        bind:checked={terminated}
        disabled={busy || disabled}
        ariaLabel={at("resource_ops_request_terminated")}
      /><span>{at("resource_ops_request_terminated")}</span>
    </label>
  {/if}
  <label
    ><Checkbox
      bind:checked={confirmed}
      disabled={busy || disabled}
      ariaLabel={at("resource_ops_attest_confirm")}
    /><span>{at("resource_ops_attest_confirm")}</span></label
  >
  <div>
    <AdminButton type="submit" disabled={!body || !confirmed || busy || disabled}
      >{at("save")}</AdminButton
    >
  </div>
</form>

<style>
  .resource-evidence {
    display: grid;
    gap: 12px;
    min-width: 0;
  }
  p {
    margin: 0;
    overflow-wrap: anywhere;
  }
  label {
    display: flex;
    gap: 8px;
    align-items: start;
  }
</style>
