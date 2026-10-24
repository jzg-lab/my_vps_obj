<script lang="ts">
  import { onMount } from "svelte";
  import ServicePreflight from "./ServicePreflight.svelte";
  import { exitAvailable } from "../dedicated-exits/availability";
  import {
    preflightSelectionKey,
    type ServicePreflight as PreflightResult,
    type ServicePreflightBody,
  } from "$lib/admin/consoleServiceOperations";
  import Dialog from "$components/ui/dialog.svelte";
  import { AdminButton, AdminField, AdminSelect } from "$components/patterns/admin/index.js";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi.js";
  import {
    serviceBytes,
    serviceErrorKey,
    type ServicePlan,
    type DedicatedExit,
    type ServiceTranslate,
  } from "$lib/admin/servicePlans.js";
  import {
    pendingServiceActivation,
    submitServiceActivation,
    type ServiceActivation,
  } from "$lib/admin/serviceActivation.js";

  let {
    api,
    at,
    userId,
    onclose,
    oncreated,
  }: {
    api: ApiClient["api"];
    at: ServiceTranslate;
    userId: number;
    onclose: () => void;
    oncreated: () => void;
  } = $props();
  let plans = $state<ServicePlan[]>([]);
  let exits = $state<DedicatedExit[]>([]);
  let planId = $state("");
  let exitId = $state("");
  let loading = $state(true);
  let busy = $state(false);
  let error = $state("");
  let storageFailed = $state(false);
  let pending = $state<ServiceActivation | null>(null);
  let preflight = $state<PreflightResult | null>(null);
  let checkedSelection = $state("");
  const plan = $derived(plans.find((item) => item.id === planId));
  const availableExits = $derived(
    exits.filter((item) => exitAvailable(item, plan?.terms.resource_pool))
  );
  const selectedExit = $derived(availableExits.find((item) => item.id === exitId));
  const preflightBody = $derived<ServicePreflightBody | null>(
    !pending && plan && !loading && (plan.terms.resource_type !== "dedicated" || selectedExit)
      ? {
          user_id: userId,
          plan_id: plan.id,
          expected_revision: plan.revision,
          exit_id: plan.terms.resource_type === "dedicated" ? exitId : null,
        }
      : null
  );
  const selection = $derived(
    preflightBody
      ? preflightSelectionKey(
          preflightBody,
          exits.find((item) => item.id === preflightBody.exit_id)?.revision ?? null
        )
      : ""
  );
  const creationAllowed = $derived(
    Boolean(preflightBody && checkedSelection === selection && preflight?.allow_pending_creation)
  );
  async function load() {
    preflight = null;
    checkedSelection = "";
    loading = true;
    error = "";
    try {
      pending = pendingServiceActivation(sessionStorage, userId);
    } catch {
      storageFailed = true;
      error = "services_storage_failed";
      loading = false;
      return;
    }
    try {
      const allPlans: ServicePlan[] = [];
      const allExits: DedicatedExit[] = [];
      let planTotal = 1;
      while (allPlans.length < planTotal) {
        const result = unwrap(
          await api(
            builtApiPath<"/api/admin/service-plans">(
              `/admin/service-plans?limit=200&offset=${allPlans.length}`
            )
          )
        );
        allPlans.push(...result.plans);
        planTotal = result.total;
        if (!result.plans.length) break;
      }
      let exitTotal = 1;
      while (allExits.length < exitTotal) {
        const result = unwrap(
          await api(
            builtApiPath<"/api/admin/dedicated-exits">(
              `/admin/dedicated-exits?limit=200&offset=${allExits.length}`
            )
          )
        );
        allExits.push(...result.exits);
        exitTotal = result.total;
        if (!result.exits.length) break;
      }
      plans = allPlans.filter((item) => item.enabled || item.id === pending?.plan_id);
      exits = allExits;
      if (pending) {
        planId = pending.plan_id;
        exitId = pending.exit_id || "";
      } else {
        planId = "";
        exitId = "";
      }
    } catch (failure) {
      error = serviceErrorKey(failure);
    } finally {
      loading = false;
    }
  }
  onMount(() => {
    void load();
  });
  async function activate(event: SubmitEvent) {
    event.preventDefault();
    if (busy || storageFailed || (!pending && (!plan || !creationAllowed))) return;
    const body =
      pending ||
      (plan
        ? {
            user_id: userId,
            plan_id: plan.id,
            expected_revision: plan.revision,
            idempotency_key: crypto.randomUUID(),
            exit_id: plan.terms.resource_type === "dedicated" ? exitId : null,
          }
        : null);
    if (!body) return;
    busy = true;
    error = "";
    pending = body;
    try {
      await submitServiceActivation(api, sessionStorage, body);
      oncreated();
    } catch (failure) {
      error = serviceErrorKey(failure);
      try {
        pending = pendingServiceActivation(sessionStorage, userId);
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
  title={at("services_activate")}
  description={at("services_activation_hint")}
  closeLabel={at("close")}
  focusKey={error}
  onclose={() => {
    if (!busy) onclose();
  }}
  class="admin-dialog"
>
  <form class="activation" onsubmit={activate}>
    {#if loading}<p role="status">{at("loading")}</p>{:else}
      {#if pending}<p role="status">{at("services_activation_pending")}</p>{/if}
      <AdminField label={at("services_choose_plan")}
        ><AdminSelect
          value={planId}
          ariaLabel={at("services_choose_plan")}
          items={plans.map((item) => ({ value: item.id, label: item.terms.name }))}
          disabled={busy || Boolean(pending) || storageFailed}
          onValueChange={(id) => {
            preflight = null;
            checkedSelection = "";
            planId = id;
            exitId = "";
          }}
        /></AdminField
      >
      {#if plan}
        <dl>
          <dt>{at("services_resource_type")}</dt>
          <dd>{at(`services_${plan.terms.resource_type}`)}</dd>
          <dt>{at("services_traffic_rule")}</dt>
          <dd>{at(`services_${plan.terms.traffic_rule}`)}</dd>
          <dt>{at("services_quota")}</dt>
          <dd>{serviceBytes(plan.terms.quota_bytes)}</dd>
          <dt>{at("services_validity_days")}</dt>
          <dd>{plan.terms.validity_days}</dd>
          <dt>{at("services_price")}</dt>
          <dd>{plan.terms.price} {plan.terms.currency}</dd>
        </dl>
        {#if plan.terms.resource_type === "dedicated"}
          <AdminField label={at("services_choose_exit")}
            ><AdminSelect
              value={exitId}
              onValueChange={(id) => {
                preflight = null;
                checkedSelection = "";
                exitId = id;
              }}
              ariaLabel={at("services_choose_exit")}
              items={availableExits.map((item) => ({
                value: item.id,
                label: `${item.label} · ${item.ip_address}`,
              }))}
              disabled={busy || Boolean(pending)}
            /></AdminField
          >
          {#if !availableExits.length && !pending}<p>{at("services_no_matching_exit")}</p>{/if}
        {/if}
      {:else if !plans.length && !error}<p>{at("services_no_plans")}</p>{/if}
      {#if preflightBody}
        {#key selection}
          {@const checked = selection}
          <ServicePreflight
            {api}
            {at}
            body={preflightBody}
            disabled={busy}
            onresult={(result) => {
              if (checked === selection) {
                preflight = result;
                checkedSelection = checked;
              }
            }}
          />
        {/key}
      {/if}
      <AdminButton disabled={busy || Boolean(pending) || storageFailed} onclick={load}
        >{at("console_preflight_reload_choices")}</AdminButton
      >
    {/if}
    {#if error}<p role="alert">{at(error)}</p>
      {#if !pending && !storageFailed}<AdminButton disabled={busy} onclick={load}
          >{at("refresh")}</AdminButton
        >{/if}{/if}
    <div class="admin-dialog-actions">
      <AdminButton disabled={busy} onclick={onclose}>{at("cancel")}</AdminButton><AdminButton
        type="submit"
        variant="primary"
        disabled={busy || loading || storageFailed || (!pending && !creationAllowed)}
        >{at(busy ? "services_activating" : "services_activate")}</AdminButton
      >
    </div>
  </form>
</Dialog>

<style>
  .activation {
    display: grid;
    gap: 16px;
  }
  p {
    margin: 0;
    color: var(--admin-muted);
  }
  [role="alert"] {
    color: var(--danger);
  }
  dl {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 8px;
    margin: 0;
  }
  dt {
    color: var(--admin-muted);
  }
  dd {
    margin: 0;
    overflow-wrap: anywhere;
  }
</style>
