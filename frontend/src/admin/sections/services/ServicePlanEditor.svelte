<script lang="ts">
  import { onMount } from "svelte";
  import { Input, Textarea, Checkbox } from "$components/ui/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { AdminButton, AdminField, AdminSelect } from "$components/patterns/admin/index.js";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi.js";
  import {
    servicePlanDraft,
    servicePlanBody,
    serviceErrorKey,
    type ServicePlan,
    type ServiceTranslate,
  } from "$lib/admin/servicePlans.js";

  let {
    api,
    at,
    plan = null,
    onclose,
    onsaved,
  }: {
    api: ApiClient["api"];
    at: ServiceTranslate;
    plan?: ServicePlan | null;
    onclose: () => void;
    onsaved: () => void;
  } = $props();
  let draft = $state(servicePlanDraft());
  let loaded = $state(false);
  let squads = $state<{ uuid: string; name: string }[]>([]);
  let loadingSquads = $state(true);
  let squadsFailed = $state(false);
  let busy = $state(false);
  let error = $state("");
  let quotaReason = $state("");
  $effect(() => {
    if (!loaded) {
      draft = servicePlanDraft(plan);
      loaded = true;
    }
  });
  const squadOptions = $derived([
    ...squads,
    ...draft.squadUuids
      .filter((id) => !squads.some((item) => item.uuid === id))
      .map((uuid) => ({ uuid, name: uuid })),
  ]);
  async function loadSquads() {
    loadingSquads = true;
    squadsFailed = false;
    try {
      squads = unwrap(await api("/admin/panel/internal-squads")).squads;
    } catch {
      squadsFailed = true;
    } finally {
      loadingSquads = false;
    }
  }
  onMount(() => {
    void loadSquads();
  });
  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (busy) return;
    error = "";
    busy = true;
    try {
      const body = servicePlanBody(draft);
      if (plan) {
        if (body.terms.quota_bytes !== plan.terms.quota_bytes && !quotaReason.trim())
          throw new Error("services_quota_change_reason_required");
        unwrap(
          await api(
            builtApiPath<"/api/admin/service-plans/{plan_id}">(`/admin/service-plans/${plan.id}`),
            {
              method: "PUT",
              body: JSON.stringify({
                ...body,
                expected_revision: plan.revision,
                quota_change_reason: quotaReason.trim() || null,
              }),
            }
          )
        );
      } else {
        unwrap(await api("/admin/service-plans", { method: "POST", body: JSON.stringify(body) }));
      }
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
  title={at(plan ? "services_edit_plan" : "services_new_plan")}
  description={at("services_snapshot_hint")}
  closeLabel={at("close")}
  onclose={() => {
    if (!busy) onclose();
  }}
  class="admin-dialog service-plan-editor"
>
  <form class="service-form" onsubmit={save}>
    <fieldset disabled={busy}>
      <div class="fields">
        <AdminField label={at("services_name")}
          ><Input bind:value={draft.name} required maxlength={160} /></AdminField
        >
        <AdminField label={at("services_resource_type")}
          ><AdminSelect
            value={draft.resourceType}
            ariaLabel={at("services_resource_type")}
            items={[
              { value: "shared", label: at("services_shared") },
              { value: "dedicated", label: at("services_dedicated") },
            ]}
            onValueChange={(value) => {
              draft.resourceType = value === "dedicated" ? "dedicated" : "shared";
            }}
          /></AdminField
        >
        <AdminField label={at("services_traffic_rule")}
          ><AdminSelect
            value={draft.trafficRule}
            ariaLabel={at("services_traffic_rule")}
            items={[
              { value: "total", label: at("services_total") },
              { value: "monthly", label: at("services_monthly") },
            ]}
            onValueChange={(value) => {
              draft.trafficRule = value === "monthly" ? "monthly" : "total";
            }}
          /></AdminField
        >
        <AdminField label={at("services_quota_gib")} hint={at("services_quota_hint")}
          ><Input
            bind:value={draft.quotaGiB}
            type="number"
            required
            min="0.000000001"
            step="any"
          /></AdminField
        >
        <AdminField label={at("services_validity_days")}
          ><Input
            bind:value={draft.validityDays}
            type="number"
            required
            min="1"
            max="36500"
            step="1"
          /></AdminField
        >
        <AdminField label={at("services_price")}
          ><Input
            bind:value={draft.price}
            inputmode="decimal"
            required
            pattern={String.raw`[0-9]{1,12}(\.[0-9]{1,2})?`}
          /></AdminField
        >
        <AdminField label={at("services_currency")}
          ><Input
            bind:value={draft.currency}
            required
            minlength={3}
            maxlength={3}
            pattern={"[A-Za-z]{3}"}
          /></AdminField
        >
        <label class="enabled"
          ><Checkbox bind:checked={draft.enabled} ariaLabel={at("services_enabled")} />{at(
            "services_enabled"
          )}</label
        >
      </div>
      <AdminField label={at("description")}
        ><Textarea
          bind:value={draft.description}
          maxlength={2000}
          ariaLabel={at("description")}
        /></AdminField
      >
      {#if plan}
        <AdminField label={at("services_quota_reason")} hint={at("services_quota_scope_hint")}>
          <Textarea
            bind:value={quotaReason}
            maxlength={1000}
            ariaLabel={at("services_quota_reason")}
          />
        </AdminField>
      {/if}
      {#if draft.trafficRule === "monthly"}<p>{at("services_monthly_hint")}</p>{/if}
      {#if draft.resourceType === "dedicated"}
        <AdminField label={at("services_pool")} hint={at("services_pool_hint")}
          ><Input bind:value={draft.resourcePool} required maxlength={120} /></AdminField
        >
      {:else}
        <fieldset class="squads">
          <legend>{at("services_squads")}</legend>
          {#if loadingSquads}<p role="status">{at("loading")}</p>{/if}
          {#if squadsFailed}<p role="alert">{at("services_squads_failed")}</p>
            <AdminButton onclick={loadSquads} disabled={loadingSquads}>{at("refresh")}</AdminButton
            >{/if}
          {#each squadOptions as squad (squad.uuid)}
            <label class="enabled"
              ><Checkbox
                checked={draft.squadUuids.includes(squad.uuid)}
                ariaLabel={squad.name}
                onCheckedChange={(checked) => {
                  draft.squadUuids = checked
                    ? [...draft.squadUuids, squad.uuid]
                    : draft.squadUuids.filter((id) => id !== squad.uuid);
                }}
              /><span>{squad.name}</span></label
            >
          {/each}
          {#if !loadingSquads && !squadsFailed && !squadOptions.length}<p>
              {at("services_no_squads")}
            </p>{/if}
        </fieldset>
      {/if}
    </fieldset>
    {#if error}<p role="alert" class="error">{at(error)}</p>{/if}
    <div class="admin-dialog-actions">
      <AdminButton disabled={busy} onclick={onclose}>{at("cancel")}</AdminButton><AdminButton
        type="submit"
        variant="primary"
        disabled={busy}>{at(busy ? "services_saving" : "save")}</AdminButton
      >
    </div>
  </form>
</Dialog>

<style>
  :global(.service-plan-editor) {
    width: min(760px, 100%);
  }
  .service-form,
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
  .fields {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
  }
  .enabled {
    display: flex;
    align-items: center;
    gap: 10px;
    overflow-wrap: anywhere;
  }
  .squads {
    padding: 12px;
    border: 1px solid var(--admin-border);
    border-radius: 8px;
  }
  p {
    margin: 0;
    color: var(--admin-muted);
    font-size: 13px;
  }
  .error {
    color: var(--danger);
  }
  @media (max-width: 520px) {
    .fields {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
