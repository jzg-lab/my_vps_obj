<script lang="ts">
  import { onDestroy } from "svelte";
  import {
    serviceDate as date,
    serviceResetState,
    serviceUsage,
  } from "$lib/webapp/independentServices";
  import ServiceActions from "./ServiceActions.svelte";
  import CustomerServiceUsage from "./CustomerServiceUsage.svelte";
  import ConsoleServiceResources from "../nodes/ConsoleServiceResources.svelte";
  import ServiceActivationAction from "./ServiceActivationAction.svelte";
  import { getAdminApi } from "$lib/admin/context.js";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminEntityLink,
    AdminListToolbar,
    AdminPagination,
    AdminTable,
  } from "$components/patterns/admin/index.js";
  import { readServicesRoute, servicesRouteUrl } from "$lib/admin/consoleServices";
  import { builtApiPath, unwrap } from "$lib/webapp/publicApi.js";
  import { isTemporaryServiceReadFailure } from "$lib/webapp/serviceReadFailure";
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
    customerName = "",
  }: {
    at: ServiceTranslate;
    userId: number | null;
    banned?: boolean;
    routePrefix?: string;
    customerName?: string;
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
  let readAt = $state("");
  let scope = "";
  let controller: AbortController | null = null;
  let request = 0;
  async function load(currentPage: number, owner: number | null) {
    const id = ++request;
    controller?.abort();
    controller = new AbortController();
    loading = true;
    failed = false;
    const nextScope = JSON.stringify([owner, currentPage, banned]);
    if (scope !== nextScope) {
      scope = nextScope;
      services = [];
      total = undefined;
      readAt = "";
    }
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
        readAt = new Date().toISOString();
      }
    } catch (error) {
      if (id === request) {
        failed = true;
        if (!isTemporaryServiceReadFailure(error)) {
          services = [];
          total = undefined;
          readAt = "";
        }
      }
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
  {#if failed}<p role="alert">
      {at("services_load_failed")}
      {readAt
        ? at("services_snapshot_stale", { time: date(readAt) })
        : at("services_snapshot_unknown")}
    </p>{:else if loading}<p role="status">
      {at("loading")}
    </p>{/if}
  {#if readAt && !services.length}<AdminEmptyState tone="card"
      >{at(userId === null ? "services_no_history" : "services_no_services")}</AdminEmptyState
    >{:else if services.length}
    {#if userId !== null}
      <section
        class="customer-relations"
        aria-label={at("console_customer_relations")}
        data-customer-relations
      >
        <h3>{at("console_customer_relations")}</h3>
        <p>{at("console_nodes_resource_scope")}</p>
        <div class="customer-flow">
          <div class="customer-identity">
            <small>{at("console_customer")}</small><AdminEntityLink
              label={customerName || String(userId)}
              idText={String(userId)}
            />
          </div>
          <div class="service-branches">
            {#each services as service (service.id)}
              <div class="service-branch">
                <ConsoleServiceResources
                  {api}
                  {at}
                  serviceId={service.id}
                  {service}
                  {routePrefix}
                  onOpenService={openService}
                />
              </div>
            {/each}
          </div>
        </div>
        <p>{at("console_customer_relations_scope")}</p>
      </section>
      <CustomerServiceUsage {services} {api} {at} />
    {/if}
    <details open={userId === null}>
      <summary>{at("console_visual_service_list")}</summary>
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
                  >{#if service.status === "pending"}<small>{at("services_pending_hint")}</small
                    >{/if}
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
                      >{at("services_usage_overage", {
                        amount: serviceBytes(usage.overage),
                      })}</small
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
                  disabled={loading || failed}
                  readonly={userId === null}
                  onOpenDetail={userId === null ? undefined : () => openService(service.id)}
                  onrefresh={() => load(page, userId)}
                /></td
              >
            </tr>{/each}
        </tbody></AdminTable
      >
    </details>
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
  .customer-relations {
    display: grid;
    gap: 16px;
    min-width: 0;
    padding: 20px;
    border: 1px solid var(--admin-border);
    border-radius: 14px;
    background: var(--admin-surface);
  }
  .customer-relations p {
    color: var(--admin-muted);
    font-size: 12px;
    line-height: 1.6;
  }
  .customer-flow {
    display: grid;
    grid-template-columns: minmax(140px, 0.7fr) minmax(0, 2fr);
    align-items: center;
    gap: 24px;
  }
  .customer-identity {
    display: grid;
    gap: 12px;
    padding: 18px;
    min-width: 0;
    border: 1px solid color-mix(in srgb, var(--accent) 50%, var(--admin-border));
    border-radius: 12px;
    background: color-mix(in srgb, var(--accent) 8%, var(--admin-surface));
    position: relative;
  }
  .customer-identity::after {
    content: "";
    position: absolute;
    left: 100%;
    top: 50%;
    width: 24px;
    height: 2px;
    background: var(--accent);
  }
  .service-branches {
    display: grid;
    gap: 24px;
    border-left: 2px solid var(--accent);
    padding-left: 20px;
    min-width: 0;
  }
  .service-branch {
    position: relative;
    min-width: 0;
  }
  .service-branch::before {
    content: "";
    position: absolute;
    right: 100%;
    top: 48px;
    width: 22px;
    height: 2px;
    background: var(--accent);
  }
  @media (max-width: 760px) {
    .customer-flow {
      grid-template-columns: minmax(0, 1fr);
      gap: 20px;
    }
    .customer-identity::after {
      top: 100%;
      left: 20px;
      width: 2px;
      height: 20px;
    }
    .service-branches {
      margin-left: 20px;
      padding-left: 16px;
    }
    .service-branch::before {
      width: 18px;
    }
  }
  summary {
    cursor: pointer;
    padding: 12px 0;
  }
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
