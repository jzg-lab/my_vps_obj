<script lang="ts">
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminListToolbar,
    AdminPagination,
    AdminTable,
  } from "$components/patterns/admin/index.js";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi.js";
  import {
    serviceBytes,
    type ServicePlan,
    type ServiceTranslate,
  } from "$lib/admin/servicePlans.js";
  import ServicePlanEditor from "./services/ServicePlanEditor.svelte";

  let { api, at }: { api: ApiClient["api"]; at: ServiceTranslate } = $props();
  let plans = $state<ServicePlan[]>([]);
  let total = $state(0);
  let page = $state(0);
  let loading = $state(false);
  let failed = $state(false);
  let editing = $state<ServicePlan | null>(null);
  let editorOpen = $state(false);
  let request = 0;
  async function load(currentPage: number) {
    const id = ++request;
    loading = true;
    failed = false;
    try {
      const result = unwrap(
        await api(
          builtApiPath<"/api/admin/service-plans">(
            `/admin/service-plans?limit=25&offset=${currentPage * 25}`
          )
        )
      );
      if (id === request) {
        plans = result.plans;
        total = result.total;
      }
    } catch {
      if (id === request) failed = true;
    } finally {
      if (id === request) loading = false;
    }
  }
  $effect(() => {
    void load(page);
  });
</script>

<section class="service-plans" aria-busy={loading}>
  <AdminListToolbar {total} totalLabel={at("services_plans_count")}>
    {#snippet actions()}
      <AdminButton disabled={loading} onclick={() => load(page)}>{at("refresh")}</AdminButton>
      <AdminButton
        variant="primary"
        onclick={() => {
          editing = null;
          editorOpen = true;
        }}>{at("services_new_plan")}</AdminButton
      >
    {/snippet}
  </AdminListToolbar>
  <p class="admin-muted">{at("services_snapshot_hint")}</p>
  {#if failed}<p role="alert">{at("services_request_failed")}</p>
  {:else if loading}<p role="status">{at("loading")}</p>
  {:else if !plans.length}<AdminEmptyState tone="card">{at("services_no_plans")}</AdminEmptyState>
  {:else}
    <AdminTable>
      <thead
        ><tr
          >{#each ["services_name", "services_resource_type", "services_traffic_rule", "services_quota", "services_validity_days", "services_price", "status", "actions"] as key}<th
              >{at(key)}</th
            >{/each}</tr
        ></thead
      >
      <tbody
        >{#each plans as plan (plan.id)}<tr>
            <td data-label={at("services_name")}
              ><strong>{plan.terms.name}</strong><small
                >{at("services_revision", { revision: plan.revision })}</small
              ></td
            >
            <td data-label={at("services_resource_type")}
              >{at(`services_${plan.terms.resource_type}`)}</td
            >
            <td data-label={at("services_traffic_rule")}
              >{at(`services_${plan.terms.traffic_rule}`)}</td
            >
            <td data-label={at("services_quota")}>{serviceBytes(plan.terms.quota_bytes)}</td>
            <td data-label={at("services_validity_days")}>{plan.terms.validity_days}</td>
            <td data-label={at("services_price")}>{plan.terms.price} {plan.terms.currency}</td>
            <td data-label={at("status")}
              ><AdminBadge variant={plan.enabled ? "success" : "muted"}
                >{at(plan.enabled ? "services_enabled" : "services_disabled")}</AdminBadge
              ></td
            >
            <td data-label={at("actions")}
              ><AdminButton
                size="sm"
                onclick={() => {
                  editing = plan;
                  editorOpen = true;
                }}>{at("services_edit_plan")}</AdminButton
              ></td
            >
          </tr>{/each}</tbody
      >
    </AdminTable>
  {/if}
  <AdminPagination
    {page}
    pageCount={Math.ceil(total / 25)}
    {total}
    disabled={loading}
    onPageChange={(value) => {
      page = value;
    }}
    prevLabel={at("services_previous")}
    nextLabel={at("services_next")}
    pageLabel={at("services_page")}
    ofLabel={at("services_of")}
    totalLabel={at("services_plans_count")}
    jumpLabel={at("services_page")}
    jumpAriaLabel={at("services_go_page")}
    goLabel={at("services_go_page")}
  />
</section>
{#if editorOpen}<ServicePlanEditor
    {api}
    {at}
    plan={editing}
    onclose={() => {
      editorOpen = false;
    }}
    onsaved={() => {
      editorOpen = false;
      void load(page);
    }}
  />{/if}

<style>
  .service-plans {
    display: grid;
    gap: 16px;
  }
  p {
    margin: 0;
  }
  small {
    display: block;
    color: var(--admin-muted);
  }
</style>
