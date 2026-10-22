<script lang="ts">
  import { onDestroy } from "svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import {
    AdminButton,
    AdminEmptyState,
    AdminListToolbar,
    AdminPagination,
    AdminTable,
  } from "$components/patterns/admin/index.js";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi";
  import { serviceDate } from "$lib/webapp/independentServices";
  import { serviceBytes, type UserService, type ServiceTranslate } from "$lib/admin/servicePlans";
  import { serviceOrderSnapshot, type ServiceOrder } from "$lib/admin/serviceHistory";

  let {
    api,
    at,
    service,
    onclose,
  }: {
    api: ApiClient["api"];
    at: ServiceTranslate;
    service: UserService;
    onclose: () => void;
  } = $props();
  let orders = $state<ServiceOrder[]>([]);
  let total = $state<number | undefined>();
  let page = $state(0);
  let loading = $state(false);
  let failed = $state(false);
  let request = 0;
  let controller: AbortController | null = null;
  async function load(currentPage: number, selected: UserService) {
    const id = ++request;
    controller?.abort();
    controller = new AbortController();
    loading = true;
    failed = false;
    try {
      const owner = selected.user_id === null ? "deleted=true" : `user_id=${selected.user_id}`;
      const result = unwrap(
        await api(
          builtApiPath<"/api/admin/service-orders">(
            `/admin/service-orders?${owner}&service_id=${selected.id}&limit=25&offset=${currentPage * 25}`
          ),
          { signal: controller.signal }
        )
      );
      if (id === request) {
        orders = result.orders;
        total = result.total;
      }
    } catch {
      if (id === request) failed = true;
    } finally {
      if (id === request) loading = false;
    }
  }
  $effect(() => {
    void load(page, service);
  });
  onDestroy(() => {
    request++;
    controller?.abort();
  });
</script>

<Dialog
  open
  size="wide"
  title={at("services_order_history")}
  description={at("services_order_history_hint")}
  closeLabel={at("close")}
  {onclose}
  class="admin-dialog"
>
  <div class="service-orders" aria-busy={loading}>
    <p><strong>{service.name}</strong><br />{at("services_service_id")}: {service.id}</p>
    <AdminListToolbar {total} totalLabel={at("services_orders_count")}>
      {#snippet actions()}<AdminButton disabled={loading} onclick={() => load(page, service)}
          >{at("refresh")}</AdminButton
        >{/snippet}
    </AdminListToolbar>
    {#if failed}<p role="alert">{at("services_load_failed")}</p>
    {:else if loading}<p role="status">{at("loading")}</p>
    {:else if !orders.length}<AdminEmptyState tone="card"
        >{at("services_no_orders")}</AdminEmptyState
      >
    {:else}
      <AdminTable>
        <thead
          ><tr
            >{#each ["services_order_id", "services_action", "services_name", "services_recorded_price", "services_quota", "services_period", "services_actor", "services_recorded_at"] as key}<th
                >{at(key)}</th
              >{/each}</tr
          ></thead
        >
        <tbody
          >{#each orders as order (order.id)}
            {@const snapshot = serviceOrderSnapshot(order)}
            <tr>
              <td data-label={at("services_order_id")}>{order.id}</td>
              <td data-label={at("services_action")}
                >{at(snapshot ? `services_${snapshot.kind}` : "services_snapshot_unavailable")}</td
              >
              <td data-label={at("services_name")}>
                <div>
                  {#if snapshot}<strong>{snapshot.name}</strong><small
                      >{at(`services_${snapshot.resourceType}`)} · {at("services_revision", {
                        revision: snapshot.revision,
                      })}</small
                    >
                    {#if snapshot.beforeStatus}<small
                        >{at(`services_status_${snapshot.beforeStatus}`)} → {at(
                          `services_status_${snapshot.desiredStatus}`
                        )}</small
                      >{/if}
                  {:else}<span role="status">{at("services_snapshot_unavailable")}</span>{/if}
                </div>
              </td>
              <td data-label={at("services_recorded_price")}
                >{snapshot?.price !== null && snapshot
                  ? `${snapshot.price} ${snapshot.currency}`
                  : "—"}</td
              >
              <td data-label={at("services_quota")}
                ><div>
                  {#if snapshot}{serviceBytes(snapshot.quotaBytes)}<small
                      >{at(`services_${snapshot.trafficRule}`)}</small
                    >{:else}—{/if}
                </div></td
              >
              <td data-label={at("services_period")}
                >{#if snapshot}{serviceDate(snapshot.startsAt)}<br />→ {serviceDate(
                    snapshot.expiresAt
                  )}{:else}—{/if}</td
              >
              <td data-label={at("services_actor")}>{order.actor_id}</td>
              <td data-label={at("services_recorded_at")}>{serviceDate(order.created_at)}</td>
            </tr>
          {/each}</tbody
        >
      </AdminTable>
    {/if}
    {#if total !== undefined}<AdminPagination
        {page}
        pageCount={Math.ceil(total / 25)}
        {total}
        disabled={loading || failed}
        onPageChange={(value) => {
          page = value;
        }}
        prevLabel={at("services_previous")}
        nextLabel={at("services_next")}
        pageLabel={at("services_page")}
        ofLabel={at("services_of")}
        totalLabel={at("services_orders_count")}
        jumpLabel={at("services_page")}
        jumpAriaLabel={at("services_go_page")}
        goLabel={at("services_go_page")}
      />{/if}
  </div>
</Dialog>

<style>
  .service-orders {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  p {
    margin: 0;
    overflow-wrap: anywhere;
  }
  td {
    overflow-wrap: anywhere;
  }
  small {
    display: block;
    color: var(--admin-muted);
  }
</style>
