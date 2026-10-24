<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { Input, Checkbox, DateInput, Textarea } from "$components/ui/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import {
    AdminButton,
    AdminField,
    AdminSelect,
    AdminPagination,
  } from "$components/patterns/admin/index.js";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi.js";
  import type { DedicatedExit, ServiceTranslate } from "$lib/admin/servicePlans.js";
  import { consoleServiceErrorKey } from "$lib/admin/consoleServiceOperations";
  import type { components } from "$lib/api/openapi.generated.js";
  import DedicatedExitAuditEntry from "../dedicated-exits/DedicatedExitAuditEntry.svelte";
  import DedicatedExitOwnership from "../dedicated-exits/DedicatedExitOwnership.svelte";
  import {
    exitEvidenceBlocked,
    exitHasHold,
    readEvidenceService,
    type EvidenceService,
  } from "../dedicated-exits/availability";

  let {
    api,
    at,
    resource,
    open = true,
    currentUrl,
    routePrefix = "",
    page,
    onPageChange,
    onOpenService,
    onclose,
    onsaved,
  }: {
    api: ApiClient["api"];
    at: ServiceTranslate;
    resource: DedicatedExit;
    open?: boolean;
    currentUrl: string;
    routePrefix?: string;
    page: number;
    onPageChange: (page: number, replace?: boolean) => void;
    onOpenService: (serviceId: string) => void;
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
  let boundService = $state<EvidenceService | null>(null);
  let serviceFailed = $state(false);
  let replacementRejected = $state(false);
  let serviceRequest = 0;
  let serviceController: AbortController | null = null;
  const replacementBlocked = $derived(
    exitHasHold(resource) || boundService?.replacement_order_id != null || replacementRejected
  );
  const evidenceBlocked = $derived(
    exitEvidenceBlocked(resource, boundService) || serviceFailed || replacementRejected
  );
  async function loadBoundService(id: string | null): Promise<boolean> {
    const token = ++serviceRequest;
    serviceController?.abort();
    serviceController = new AbortController();
    boundService = null;
    serviceFailed = false;
    if (!id) return true;
    try {
      const result = await readEvidenceService(api, id, serviceController.signal);
      if (token !== serviceRequest) return false;
      boundService = result;
      return true;
    } catch {
      if (token === serviceRequest) serviceFailed = true;
      return false;
    }
  }
  let pending = $state<
    components["schemas"]["ExitVerifyBody"] | components["schemas"]["ExitReclaimBody"] | null
  >(null);
  let audit = $state<components["schemas"]["ExitAuditOut"][]>([]);
  let total = $state<number | undefined>();
  let auditLoading = $state(true);
  let auditFailed = $state(false);
  let auditRequest = 0;
  let auditController: AbortController | null = null;
  async function loadAudit(currentPage: number) {
    const token = ++auditRequest;
    auditController?.abort();
    auditController = new AbortController();
    auditLoading = true;
    auditFailed = false;
    audit = [];
    try {
      const result = unwrap(
        await api(
          builtApiPath<"/api/admin/dedicated-exits/{exit_id}/audit">(
            `/admin/dedicated-exits/${resource.id}/audit?limit=10&offset=${currentPage * 10}`
          ),
          { signal: auditController.signal }
        )
      );
      if (token !== auditRequest) return;
      total = result.total;
      if (currentPage > 0 && currentPage * 10 >= result.total) {
        onPageChange(Math.max(0, Math.ceil(result.total / 10) - 1), true);
        return;
      }
      audit = result.audit;
    } catch {
      if (token === auditRequest) auditFailed = true;
    } finally {
      if (token === auditRequest) auditLoading = false;
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
  $effect(() => {
    if (open) void loadBoundService(resource.service_id);
  });
  onDestroy(() => {
    auditRequest++;
    auditController?.abort();
    serviceRequest++;
    serviceController?.abort();
  });
  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (
      busy ||
      evidenceBlocked ||
      !confirmed ||
      !checkedAt ||
      (action === "reclaim" && !resource.service_id)
    )
      return;
    const observed = new Date(checkedAt);
    if (!Number.isFinite(observed.getTime()) || observed.getTime() > Date.now()) {
      error = "services_exit_evidence_invalid";
      return;
    }
    busy = true;
    error = "";
    try {
      const current = resource;
      if (!(await loadBoundService(current.service_id)) || resource !== current || evidenceBlocked)
        return;
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
      error = consoleServiceErrorKey(failure);
      if (error === "console_exit_replacement_in_progress") replacementRejected = true;
    } finally {
      busy = false;
    }
  }
</script>

<Dialog
  {open}
  title={at("services_exit_evidence")}
  description={at("services_exit_evidence_hint")}
  closeLabel={at("close")}
  class="admin-dialog"
  onclose={() => {
    if (!busy) onclose();
  }}
>
  <p>{resource.label} · {resource.ip_address}</p>
  <p>{at("services_service_id")}</p>
  <DedicatedExitOwnership
    {resource}
    {currentUrl}
    {routePrefix}
    {at}
    {onOpenService}
    disabled={busy}
  />
  {#if exitHasHold(resource)}
    <p role="status">{at("services_exit_held")}</p>
  {:else if replacementBlocked}
    <p role="status">{at("console_exit_replacement_in_progress")}</p>
  {:else if serviceFailed}
    <p role="alert">{at("console_detail_failed")}</p>
    <AdminButton disabled={busy} onclick={() => loadBoundService(resource.service_id)}
      >{at("refresh")}</AdminButton
    >
  {:else if evidenceBlocked}<p role="status">{at("loading")}</p>{/if}
  <form class="exit-evidence" onsubmit={save}>
    <AdminField label={at("services_exit_action")}
      ><AdminSelect
        bind:value={action}
        ariaLabel={at("services_exit_action")}
        disabled={busy || Boolean(pending) || evidenceBlocked}
        items={[
          { value: "verify", label: at("services_exit_verify") },
          ...(resource.service_id
            ? [{ value: "reclaim", label: at("services_exit_reclaim") }]
            : []),
        ]}
      /></AdminField
    >
    {#if action === "verify"}<AdminField label={at("services_exit_observed_ip")}
        ><Input
          required
          bind:value={observedIp}
          disabled={busy || Boolean(pending) || evidenceBlocked}
        /></AdminField
      >{/if}
    <AdminField label={at("services_exit_checked_at")}
      ><DateInput
        bind:value={checkedAt}
        withTime
        ariaLabel={at("services_exit_checked_at")}
        clearLabel={at("clear")}
        disabled={busy || Boolean(pending) || evidenceBlocked}
      /></AdminField
    >
    <AdminField label={at("services_exit_evidence_note")}
      ><Textarea
        required
        minlength={10}
        maxlength={2000}
        bind:value={evidence}
        disabled={busy || Boolean(pending) || evidenceBlocked}
      /></AdminField
    >
    <label class="confirmation"
      ><Checkbox
        bind:checked={confirmed}
        disabled={busy || Boolean(pending) || evidenceBlocked}
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
      {#if !replacementRejected}<p>{at("services_exit_retry_hint")}</p>{/if}{/if}
    <div class="admin-dialog-actions">
      <AdminButton disabled={busy} onclick={onclose}>{at("close")}</AdminButton><AdminButton
        type="submit"
        variant="primary"
        disabled={busy || evidenceBlocked || !confirmed || !checkedAt}
        >{at(busy ? "services_saving" : "save")}</AdminButton
      >
    </div>
  </form>
  <h3>{at("services_exit_audit")}</h3>
  {#if auditFailed}<p role="alert">{at("services_request_failed")}</p>
    <AdminButton onclick={() => loadAudit(page)}>{at("refresh")}</AdminButton
    >{:else if auditLoading}<p role="status">{at("loading")}</p>
  {:else if !audit.length}<p>{at("services_exit_no_evidence")}</p>{:else}
    <ol>
      {#each audit as item (item.id)}<DedicatedExitAuditEntry
          {item}
          {currentUrl}
          {routePrefix}
          {at}
          {onOpenService}
          disabled={busy}
        />{/each}
    </ol>
  {/if}
  {#if total !== undefined}<AdminPagination
      {page}
      {total}
      pageCount={Math.ceil(total / 10)}
      {onPageChange}
      disabled={auditLoading || auditFailed}
      prevLabel={at("services_previous")}
      nextLabel={at("services_next")}
      pageLabel={at("services_page")}
      ofLabel={at("services_of")}
      totalLabel={at("services_exit_audit")}
      jumpLabel={at("services_page")}
      jumpAriaLabel={at("services_go_page")}
      goLabel={at("services_go_page")}
    />{/if}
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
  span {
    overflow-wrap: anywhere;
  }
</style>
