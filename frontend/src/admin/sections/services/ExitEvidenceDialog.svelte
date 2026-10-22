<script lang="ts">
  import { onMount } from "svelte";
  import { Input, Checkbox, DateInput, Textarea } from "$components/ui/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import {
    AdminButton,
    AdminField,
    AdminSelect,
    AdminPagination,
  } from "$components/patterns/admin/index.js";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi.js";
  import {
    serviceErrorKey,
    type DedicatedExit,
    type ServiceTranslate,
  } from "$lib/admin/servicePlans.js";
  import { serviceDate } from "$lib/webapp/independentServices.js";
  import type { components } from "$lib/api/openapi.generated.js";

  let {
    api,
    at,
    resource,
    onclose,
    onsaved,
  }: {
    api: ApiClient["api"];
    at: ServiceTranslate;
    resource: DedicatedExit;
    onclose: () => void;
    onsaved: () => void;
  } = $props();
  let action = $state("verify");
  let observedIp = $state("");
  let evidence = $state("");
  let checkedAt = $state("");
  let confirmed = $state(false);
  let busy = $state(false);
  let error = $state("");
  let pending = $state<
    components["schemas"]["ExitVerifyBody"] | components["schemas"]["ExitReclaimBody"] | null
  >(null);
  let audit = $state<components["schemas"]["ExitAuditOut"][]>([]);
  let total = $state(0);
  let page = $state(0);
  let auditFailed = $state(false);
  async function loadAudit(currentPage: number) {
    auditFailed = false;
    try {
      const result = unwrap(
        await api(
          builtApiPath<"/api/admin/dedicated-exits/{exit_id}/audit">(
            `/admin/dedicated-exits/${resource.id}/audit?limit=10&offset=${currentPage * 10}`
          )
        )
      );
      audit = result.audit;
      total = result.total;
    } catch {
      auditFailed = true;
    }
  }
  onMount(() => {
    const now = new Date();
    checkedAt = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
      .toISOString()
      .slice(0, 23);
  });
  $effect(() => {
    void loadAudit(page);
  });
  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (busy || !confirmed || !checkedAt || (action === "reclaim" && !resource.service_id)) return;
    const observed = new Date(checkedAt);
    if (!Number.isFinite(observed.getTime()) || observed.getTime() > Date.now()) {
      error = "services_exit_evidence_invalid";
      return;
    }
    pending ??= {
      expected_revision: resource.revision,
      service_id: resource.service_id,
      idempotency_key: crypto.randomUUID(),
      checked_at: observed.toISOString(),
      evidence: evidence.trim(),
      ...(action === "verify"
        ? { observed_ip: observedIp.trim(), fixed: true, exclusive: true }
        : {
            service_id: resource.service_id!,
            connections_stopped: true,
            old_config_rejected: true,
          }),
    };
    busy = true;
    error = "";
    try {
      const response =
        action === "verify"
          ? await api(
              builtApiPath<"/api/admin/dedicated-exits/{exit_id}/verify">(
                `/admin/dedicated-exits/${resource.id}/verify`
              ),
              { method: "POST", body: JSON.stringify(pending) }
            )
          : await api(
              builtApiPath<"/api/admin/dedicated-exits/{exit_id}/reclaim">(
                `/admin/dedicated-exits/${resource.id}/reclaim`
              ),
              { method: "POST", body: JSON.stringify(pending) }
            );
      unwrap(response);
      onsaved();
    } catch (failure) {
      error = serviceErrorKey(failure);
    } finally {
      busy = false;
    }
  }
</script>

<Dialog
  open
  title={at("services_exit_evidence")}
  description={at("services_exit_evidence_hint")}
  closeLabel={at("close")}
  class="admin-dialog"
  onclose={() => {
    if (!busy) onclose();
  }}
>
  <p>{resource.label} · {resource.ip_address}</p>
  <form class="exit-evidence" onsubmit={save}>
    <AdminField label={at("services_exit_action")}
      ><AdminSelect
        bind:value={action}
        ariaLabel={at("services_exit_action")}
        disabled={busy || Boolean(pending)}
        items={[
          { value: "verify", label: at("services_exit_verify") },
          ...(resource.service_id
            ? [{ value: "reclaim", label: at("services_exit_reclaim") }]
            : []),
        ]}
      /></AdminField
    >
    {#if action === "verify"}<AdminField label={at("services_exit_observed_ip")}
        ><Input required bind:value={observedIp} disabled={busy || Boolean(pending)} /></AdminField
      >{/if}
    <AdminField label={at("services_exit_checked_at")}
      ><DateInput
        bind:value={checkedAt}
        withTime
        ariaLabel={at("services_exit_checked_at")}
        clearLabel={at("clear")}
        disabled={busy || Boolean(pending)}
      /></AdminField
    >
    <AdminField label={at("services_exit_evidence_note")}
      ><Textarea
        required
        minlength={10}
        maxlength={2000}
        bind:value={evidence}
        disabled={busy || Boolean(pending)}
      /></AdminField
    >
    <label class="confirmation"
      ><Checkbox
        bind:checked={confirmed}
        disabled={busy || Boolean(pending)}
        ariaLabel={at(
          action === "verify" ? "services_exit_verify_confirm" : "services_exit_reclaim_confirm"
        )}
      /><span
        >{at(
          action === "verify" ? "services_exit_verify_confirm" : "services_exit_reclaim_confirm"
        )}</span
      ></label
    >
    {#if error}<p role="alert">{at(error)}</p>
      <p>{at("services_exit_retry_hint")}</p>{/if}
    <div class="admin-dialog-actions">
      <AdminButton disabled={busy} onclick={onclose}>{at("close")}</AdminButton><AdminButton
        type="submit"
        variant="primary"
        disabled={busy || !confirmed || !checkedAt}
        >{at(busy ? "services_saving" : "save")}</AdminButton
      >
    </div>
  </form>
  <h3>{at("services_exit_audit")}</h3>
  {#if auditFailed}<p role="alert">{at("services_request_failed")}</p>
    <AdminButton onclick={() => loadAudit(page)}>{at("refresh")}</AdminButton
    >{:else if !audit.length}<p>{at("services_exit_no_evidence")}</p>{:else}
    <ol>
      {#each audit as item (item.id)}<li>
          <strong
            >{at(
              item.action === "verify" ? "services_exit_verify" : "services_exit_reclaim"
            )}</strong
          >
          · {serviceDate(item.created_at)}
          <p>{at("services_exit_actor")}: {item.actor_id}</p>
          <p>{item.service_id || "—"}</p>
          <p>{String(item.evidence.evidence || "")}</p>
        </li>{/each}
    </ol>
  {/if}
  <AdminPagination
    {page}
    {total}
    pageCount={Math.ceil(total / 10)}
    onPageChange={(value) => (page = value)}
    prevLabel={at("services_previous")}
    nextLabel={at("services_next")}
    pageLabel={at("services_page")}
    ofLabel={at("services_of")}
    totalLabel={at("services_exit_audit")}
    jumpLabel={at("services_page")}
    jumpAriaLabel={at("services_go_page")}
    goLabel={at("services_go_page")}
  />
</Dialog>

<style>
  .exit-evidence {
    display: grid;
    gap: 16px;
  }
  .confirmation {
    display: flex;
    gap: 10px;
    align-items: start;
  }
  p,
  li,
  span {
    overflow-wrap: anywhere;
  }
  li {
    margin-bottom: 16px;
  }
</style>
