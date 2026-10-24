<script lang="ts">
  import { Input, Checkbox, DateInput } from "$components/ui";
  import { AdminButton, AdminField, AdminSelect } from "$components/patterns/admin";
  import type { ServiceTranslate } from "$lib/admin/servicePlans";
  import {
    emptyReplacementFields,
    replacementWrite,
    replacementLabel,
    type ReplacementAction,
    type ReplacementFields,
    type ReplacementState,
  } from "$lib/admin/exitReplacement";
  let {
    at,
    data,
    action,
    userId,
    disabled,
    onsubmit,
  }: {
    at: ServiceTranslate;
    data: ReplacementState;
    action: ReplacementAction;
    userId: number;
    disabled: boolean;
    onsubmit: (fields: ReplacementFields, exitId: string) => void;
  } = $props();
  let fields = $state(emptyReplacementFields());
  let target = $state("");
  const exitId = $derived(
    action === "candidate_cleanup" ? (data.replacement?.candidate_exit.id ?? "") : target
  );
  const metering = $derived(action === "stop_evidence" || action === "close_evidence");
  const reclamation = $derived(action === "reclaim" || action === "candidate_cleanup");
  const evidence = $derived(action !== "confirm" && action !== "retry");
  const valid = $derived.by(() => {
    try {
      replacementWrite(data, userId, action, fields, exitId, "validation-only");
      return true;
    } catch {
      return false;
    }
  });
  const targets = $derived(
    data.replacement
      ? [data.replacement.old_exit, data.replacement.candidate_exit].filter(
          (item) => item.hold_order_id === data.replacement?.operation.order_id
        )
      : []
  );
</script>

<form
  class="replacement-evidence"
  onsubmit={(event) => {
    event.preventDefault();
    if (!disabled && valid) onsubmit(fields, exitId);
  }}
>
  {#if evidence}<p>{at("replacement_administrator_notice")}</p>{/if}
  {#if action === "candidate_cleanup"}<p role="status">{at("replacement_cleanup_notice")}</p>{/if}
  {#if action === "close_evidence"}<p role="status">{at("replacement_close_notice")}</p>{/if}
  {#if action === "reclaim"}<AdminField label={at("replacement_reclaim_target")}
      ><AdminSelect
        bind:value={target}
        ariaLabel={at("replacement_reclaim_target")}
        {disabled}
        items={targets.map((item) => ({
          value: item.id,
          label: `${item.label} · ${item.ip_address}`,
        }))}
      /></AdminField
    >{/if}
  {#if action === "verify"}<AdminField label={at("services_exit_observed_ip")}
      ><Input required maxlength={45} bind:value={fields.observedIp} {disabled} /></AdminField
    >{/if}
  {#if evidence}
    <AdminField label={at("services_exit_checked_at")}
      ><DateInput
        bind:value={fields.checkedAt}
        withTime
        ariaLabel={at("services_exit_checked_at")}
        clearLabel={at("clear")}
        {disabled}
      /></AdminField
    >
    <AdminField label={at("replacement_digest")}
      ><Input
        required
        minlength={64}
        maxlength={64}
        pattern={"[0-9a-f]{64}"}
        bind:value={fields.digest}
        {disabled}
      /></AdminField
    >
  {/if}
  {#if metering}
    <AdminField label={at("replacement_usage_at")}
      ><DateInput
        bind:value={fields.usageAt}
        withTime
        ariaLabel={at("replacement_usage_at")}
        clearLabel={at("clear")}
        {disabled}
      /></AdminField
    >
    {#each [["total", "replacement_usage_total"], ["raw", "replacement_usage_raw"], ["offset", "replacement_usage_offset"]] as [field, label]}
      {#if field === "total" || field === "raw" || field === "offset"}<AdminField label={at(label)}
          ><Input
            required
            inputmode="numeric"
            pattern="(0|[1-9][0-9]*)"
            bind:value={fields[field]}
            {disabled}
          /></AdminField
        >{/if}
    {/each}
    <AdminField label={at("replacement_usage_digest")}
      ><Input
        required
        minlength={64}
        maxlength={64}
        pattern={"[0-9a-f]{64}"}
        bind:value={fields.usageDigest}
        {disabled}
      /></AdminField
    >
    <label
      ><Checkbox
        bind:checked={fields.authorizationRemoved}
        {disabled}
        ariaLabel={at("replacement_authorization_removed")}
      /><span>{at("replacement_authorization_removed")}</span></label
    >
  {/if}
  {#if metering || reclamation}
    <label
      ><Checkbox
        bind:checked={fields.connectionsStopped}
        {disabled}
        ariaLabel={at("replacement_connections_stopped")}
      /><span>{at("replacement_connections_stopped")}</span></label
    >
    <label
      ><Checkbox
        bind:checked={fields.oldConfigRejected}
        {disabled}
        ariaLabel={at("replacement_old_config_rejected")}
      /><span>{at("replacement_old_config_rejected")}</span></label
    >
  {/if}
  {#if action === "verify"}
    <label
      ><Checkbox bind:checked={fields.fixed} {disabled} ariaLabel={at("replacement_fixed")} /><span
        >{at("replacement_fixed")}</span
      ></label
    >
    <label
      ><Checkbox
        bind:checked={fields.exclusive}
        {disabled}
        ariaLabel={at("replacement_exclusive")}
      /><span>{at("replacement_exclusive")}</span></label
    >
  {/if}
  {#if action === "resolve_write"}
    <p>{at("replacement_resolve_notice")}</p>
    <AdminField label={at("replacement_write_result")}
      ><AdminSelect
        value={fields.result}
        onValueChange={(value) => {
          if (value === "applied" || value === "not_applied") fields.result = value;
        }}
        ariaLabel={at("replacement_write_result")}
        {disabled}
        items={[
          { value: "applied", label: at("replacement_applied") },
          { value: "not_applied", label: at("replacement_not_applied") },
        ]}
      /></AdminField
    >
  {/if}
  {#if action === "confirm"}<label
      ><Checkbox
        bind:checked={fields.confirmed}
        {disabled}
        ariaLabel={at("replacement_confirm_terms")}
      /><span>{at("replacement_confirm_terms")}</span></label
    >{/if}
  {#if action === "retry"}<p>{at("replacement_retry_notice")}</p>{/if}
  <div class="admin-dialog-actions">
    <AdminButton type="submit" variant="primary" disabled={disabled || !valid}
      >{at(replacementLabel("action", action))}</AdminButton
    >
  </div>
</form>

<style>
  form {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  label {
    display: flex;
    gap: 10px;
    align-items: start;
  }
  p {
    margin: 0;
  }
  p,
  span {
    overflow-wrap: anywhere;
  }
</style>
