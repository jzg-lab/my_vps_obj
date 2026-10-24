<script lang="ts">
  import { onMount } from "svelte";
  import { Input, Textarea } from "$components/ui";
  import Dialog from "$components/ui/dialog.svelte";
  import { AdminButton, AdminField, AdminSelect } from "$components/patterns/admin";
  import type { ApiClient } from "$lib/webapp/publicApi";
  import { serviceDate } from "$lib/webapp/independentServices";
  import {
    serviceErrorKey,
    type UserService,
    type ServiceTranslate,
  } from "$lib/admin/servicePlans";
  import {
    pendingServiceChange,
    serviceChangeActions,
    submitServiceChange,
    type ServiceChangeBody,
    type ServiceAction,
  } from "$lib/admin/serviceChanges";

  let {
    api,
    at,
    service,
    onclose,
    onsaved,
  }: {
    api: ApiClient["api"];
    at: ServiceTranslate;
    service: UserService;
    onclose: () => void;
    onsaved: () => void;
  } = $props();
  let action = $state<ServiceAction>("renew");
  let days = $state<number | undefined>();
  let price = $state("");
  let currency = $state("CNY");
  let verifiedTotal = $state("");
  let expectedRaw = $state("");
  let evidence = $state("");
  let loaded = $state(false);
  let pending = $state<ServiceChangeBody | null>(null);
  let busy = $state(false);
  let storageFailed = $state(false);
  let rejected = $state(false);
  let error = $state("");
  onMount(() => {
    try {
      if (service.user_id === null) return;
      pending = pendingServiceChange(sessionStorage, service.user_id, service.id);
      if (pending) {
        action = pending.change.action;
        days = pending.change.days ?? undefined;
        price = String(pending.change.price ?? "");
        currency = pending.change.currency ?? "CNY";
        verifiedTotal = String(pending.change.verified_total_bytes ?? "");
        expectedRaw = String(pending.change.expected_raw_bytes ?? "");
        evidence = pending.change.evidence ?? "";
      } else if (service.desired_status === "cancelled") {
        action = "reconcile_usage";
      }
    } catch {
      storageFailed = true;
      error = "services_storage_failed";
    } finally {
      loaded = true;
    }
  });
  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (busy || storageFailed || rejected || service.user_id === null) return;
    if (
      !pending &&
      action === "renew" &&
      (!days ||
        !Number.isSafeInteger(days) ||
        days > 36500 ||
        !/^\d{1,12}(\.\d{1,2})?$/.test(price) ||
        !/^[A-Z]{3}$/.test(currency))
    ) {
      error = "services_invalid_terms";
      return;
    }
    if (
      !pending &&
      action === "reconcile_usage" &&
      (!/^\d+$/.test(verifiedTotal) ||
        !Number.isSafeInteger(Number(verifiedTotal)) ||
        Number(verifiedTotal) < (service.usage_total_bytes ?? service.used_bytes) ||
        !/^\d+$/.test(expectedRaw) ||
        !Number.isSafeInteger(Number(expectedRaw)) ||
        !evidence.trim())
    ) {
      error = "services_invalid_terms";
      return;
    }
    const body: ServiceChangeBody = pending ?? {
      user_id: service.user_id,
      expected_revision: service.revision,
      idempotency_key: crypto.randomUUID(),
      change:
        action === "renew"
          ? {
              action,
              days: days ?? null,
              price,
              currency,
              verified_total_bytes: null,
              expected_raw_bytes: null,
              evidence: null,
            }
          : action === "reconcile_usage"
            ? {
                action,
                days: null,
                price: null,
                currency: null,
                verified_total_bytes: Number(verifiedTotal),
                expected_raw_bytes: Number(expectedRaw),
                evidence: evidence.trim(),
              }
            : {
                action,
                days: null,
                price: null,
                currency: null,
                verified_total_bytes: null,
                expected_raw_bytes: null,
                evidence: null,
              },
    };
    busy = true;
    error = "";
    pending = body;
    try {
      await submitServiceChange(api, sessionStorage, service.id, body);
      onsaved();
    } catch (failure) {
      error = serviceErrorKey(failure);
      try {
        pending = pendingServiceChange(sessionStorage, service.user_id, service.id);
        rejected = !pending;
      } catch {
        storageFailed = true;
        error = "services_storage_failed";
      }
    } finally {
      busy = false;
    }
  }
</script>

<Dialog
  open
  portal
  title={at("services_manage")}
  description={at("services_change_hint")}
  closeLabel={at("close")}
  focusKey={error}
  onclose={() => {
    if (!busy) onclose();
  }}
  class="admin-dialog"
>
  <form class="service-change" onsubmit={save}>
    <p><strong>{service.name}</strong><br />{service.id}</p>
    <p>{at("services_expires")}: {serviceDate(service.expires_at)}</p>
    {#if pending}<p role="status">{at("services_change_pending_request")}</p>{/if}
    <fieldset disabled={busy || !loaded || Boolean(pending) || storageFailed || rejected}>
      <AdminField label={at("services_action")}>
        <AdminSelect
          value={action}
          ariaLabel={at("services_action")}
          items={serviceChangeActions(service).map((value) => ({
            value,
            label: at(`services_${value}`),
          }))}
          onValueChange={(value) => {
            if (
              value === "renew" ||
              value === "pause" ||
              value === "resume" ||
              value === "reconcile_usage"
            )
              action = value;
          }}
        />
      </AdminField>
      {#if action === "reconcile_usage"}
        <p>{at("services_reconcile_hint")}</p>
        <p>{at("services_last_total_bytes")}: {service.usage_total_bytes ?? service.used_bytes}</p>
        <AdminField label={at("services_verified_total_bytes")}
          ><Input bind:value={verifiedTotal} inputmode="numeric" required /></AdminField
        >
        <AdminField label={at("services_expected_raw_bytes")}
          ><Input bind:value={expectedRaw} inputmode="numeric" required /></AdminField
        >
        <AdminField label={at("services_reconcile_evidence")}
          ><Textarea
            bind:value={evidence}
            maxlength={1000}
            required
            ariaLabel={at("services_reconcile_evidence")}
          /></AdminField
        >
      {/if}
      {#if action === "renew"}
        <p>{at("services_renew_hint")}</p>
        <AdminField label={at("services_renew_days")}
          ><Input
            type="number"
            value={days ?? ""}
            oninput={(event) => {
              days = event.currentTarget.value ? event.currentTarget.valueAsNumber : undefined;
            }}
            min="1"
            max="36500"
            step="1"
            required
          /></AdminField
        >
        <AdminField label={at("services_recorded_price")}
          ><Input bind:value={price} inputmode="decimal" required /></AdminField
        >
        <AdminField label={at("services_currency")}
          ><Input bind:value={currency} maxlength={3} required /></AdminField
        >
      {/if}
    </fieldset>
    {#if error}<p role="alert">{at(error)}</p>{/if}
    {#if rejected}<p>{at("services_change_reload")}</p>{/if}
    <div class="admin-dialog-actions">
      <AdminButton disabled={busy} onclick={onclose}>{at("cancel")}</AdminButton>
      <AdminButton
        type="submit"
        variant="primary"
        disabled={busy || !loaded || storageFailed || rejected}>{at("save")}</AdminButton
      >
    </div>
  </form>
</Dialog>

<style>
  .service-change,
  fieldset {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  fieldset {
    border: 0;
    padding: 0;
    margin: 0;
  }
  p {
    margin: 0;
    color: var(--admin-muted);
    overflow-wrap: anywhere;
  }
  [role="alert"] {
    color: var(--danger);
  }
</style>
