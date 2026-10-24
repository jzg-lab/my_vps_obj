<script lang="ts">
  import { onDestroy } from "svelte";
  import {
    serviceDate as date,
    serviceResetState,
    serviceUsage,
  } from "$lib/webapp/independentServices";
  import ServiceActions from "./ServiceActions.svelte";
  import ServiceActivationAction from "./ServiceActivationAction.svelte";
  import { getAdminApi } from "$lib/admin/context.js";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminListToolbar,
    AdminPagination,
    AdminTable,
  } from "$components/patterns/admin/index.js";
  import { readServicesRoute, servicesRouteUrl } from "$lib/admin/consoleServices";
  import { builtApiPath, unwrap } from "$lib/webapp/publicApi.js";
  import {
    serviceBytes,
    type UserService,
    type ServiceTranslate,
  } from "$lib/admin/servicePlans.js";
  let {
    at,
    userId,
    banned = false,
    routePrefix = "",
  }: {
    at: ServiceTranslate;
    userId: number | null;
    banned?: boolean;
    routePrefix?: string;
  } = $props();
  const api = getAdminApi();
  function openService(serviceId: string) {
    const route = { ...readServicesRoute(""), serviceId, userId: String(userId) };
    window.history.pushState(null, "", servicesRouteUrl(window.location.href, route, routePrefix));
    window.dispatchEvent(new PopStateEvent("popstate"));
  }
  let services = $state<UserService[]>([]);
  let total = $state<number | undefined>();
  let page = $state(0);
  let loading = $state(true);
  let failed = $state(false);
  let controller: AbortController | null = null;
  let request = 0;
  async function load(currentPage: number, owner: number | null) {
    const id = ++request;
    controller?.abort();
    controller = new AbortController();
    loading = true;
    failed = false;
    try {
      const result = unwrap(
        await api(
          builtApiPath<"/api/admin/services">(
            `/admin/services?${owner === null ? "deleted=true" : `user_id=${owner}`}&limit=25&offset=${currentPage * 25}`
          ),
          { signal: controller.signal }
        )
      );
      if (id === request) {
        services = result.services;
        total = result.total;
      }
    } catch {
      if (id === request) failed = true;
    } finally {
      if (id === request) loading = false;
    }
  }
  $effect(() => {
    void userId;
    page = 0;
    total = undefined;
  });
  $effect(() => {
    void banned;
    void load(page, userId);
  });
  onDestroy(() => {
    request++;
    controller?.abort();
  });
</script>

<section
  class="user-services"
  aria-label={at(userId === null ? "services_history_title" : "services_title")}
  aria-busy={loading}
>
  {#if userId === null}<p>{at("services_history_hint")}</p>{:else}<h3>
      {at("services_title")}
    </h3>{/if}
  <AdminListToolbar {total} totalLabel={at("services_count")}>
    {#snippet actions()}<AdminButton disabled={loading} onclick={() => load(page, userId)}
        >{at("refresh")}</AdminButton
      >{#if userId !== null}{#key userId}<ServiceActivationAction
            {api}
            {at}
            {userId}
            {banned}
            disabled={loading || failed}
            onrefresh={() => void load(page, userId)}
            oncreated={() => {
              page = 0;
              void load(0, userId);
            }}
          />{/key}{/if}{/snippet}
  </AdminListToolbar>
  {#if failed}<p role="alert">{at("services_load_failed")}</p>{:else if loading}<p role="status">
      {at("loading")}
    </p>{:else if !services.length}<AdminEmptyState tone="card"
      >{at(userId === null ? "services_no_history" : "services_no_services")}</AdminEmptyState
    >{:else}
    <AdminTable
      ><thead
        ><tr
          >{#each ["services_name", "status", "services_used", "services_remaining", "services_expires", "services_next_reset", "services_exit_ip", "services_order_history"] as key}<th
              >{at(key)}</th
            >{/each}</tr
        ></thead
      ><tbody>
        {#each services as service (service.id)}
          {@const usage = serviceUsage(service)}
          {@const reset = serviceResetState(service)}
          <tr>
            <td data-label={at("services_name")}
              ><div>
                <strong>{service.name}</strong><small
                  >{at(`services_${service.traffic_rule}`)}</small
                ><small>{service.id}</small>
              </div></td
            >
            <td data-label={at("status")}
              ><div>
                <AdminBadge
                  class="service-status"
                  variant={service.status === "active" ? "success" : "muted"}
                  >{at(`services_status_${service.status}`)}</AdminBadge
                >{#if service.status === "pending"}<small>{at("services_pending_hint")}</small>{/if}
                {#if service.sync_pending}<small role="status"
                    >{at(
                      service.sync_error ? "services_sync_retrying" : "services_sync_pending"
                    )}</small
                  >
                {:else if service.sync_confirmed_at}<small
                    >{at("services_sync_confirmed")}: {date(service.sync_confirmed_at)}</small
                  >{/if}
              </div></td
            >
            <td data-label={at("services_used")}
              ><div>
                {usage.remaining === null
                  ? at("console_unknown")
                  : serviceBytes(service.used_bytes)} / {serviceBytes(service.quota_bytes)}<small
                  >{at("services_last_sync")}: {service.last_usage_sync_at
                    ? date(service.last_usage_sync_at)
                    : at("services_never_synced")}</small
                >
                {#if service.usage_error}<small role="status"
                    >{at(
                      service.last_usage_sync_at
                        ? "services_usage_stale"
                        : "services_usage_unconfirmed"
                    )}</small
                  >
                  {#if ["panel_usage_regressed", "panel_usage_reset"].includes(service.usage_error)}<small
                      >{at("services_usage_reconcile")}</small
                    >{/if}
                {/if}
              </div></td
            >
            <td data-label={at("services_remaining")}
              ><div>
                {usage.remaining === null ? at("console_unknown") : serviceBytes(usage.remaining)}
                {#if usage.overage !== null && usage.overage > 0}<small
                    >{at("services_usage_overage", { amount: serviceBytes(usage.overage) })}</small
                  >{/if}
              </div></td
            >
            <td data-label={at("services_expires")}><div>{date(service.expires_at)}</div></td>
            <td data-label={at("services_next_reset")}
              ><div>
                {reset === "ended"
                  ? at("services_no_further_reset")
                  : reset === "expires_first"
                    ? at("services_expires_before_reset")
                    : reset === "scheduled"
                      ? date(service.cycle_ends_at)
                      : reset === "not_monthly"
                        ? "—"
                        : at("console_unknown")}{#if service.cycle_pending}<small role="status"
                    >{at("services_cycle_pending")}</small
                  >{/if}
              </div></td
            >
            <td data-label={at("services_exit_ip")}
              ><div>
                {service.exit_ip || "—"}{#if service.exit_ip}<small
                    >{at(
                      service.exit_verified ? "services_verified" : "services_unverified"
                    )}</small
                  >{/if}
              </div></td
            >
            <td data-label={at("services_order_history")}
              ><ServiceActions
                {api}
                {at}
                {service}
                {routePrefix}
                {banned}
                readonly={userId === null}
                onOpenDetail={userId === null ? undefined : () => openService(service.id)}
                onrefresh={() => load(page, userId)}
              /></td
            >
          </tr>{/each}
      </tbody></AdminTable
    >
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
      totalLabel={at("services_count")}
      jumpLabel={at("services_page")}
      jumpAriaLabel={at("services_go_page")}
      goLabel={at("services_go_page")}
    />{/if}
</section>

<style>
  .user-services {
    display: grid;
    gap: 16px;
    margin-bottom: 24px;
  }
  h3,
  p {
    margin: 0;
  }
  :global(.service-status) {
    white-space: normal;
    max-width: 100%;
  }
  small {
    display: block;
    color: var(--admin-muted);
    overflow-wrap: anywhere;
  }
</style>
