<script lang="ts">
  import { getAdminApi } from "$lib/admin/context.js";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminListToolbar,
    AdminPagination,
    AdminTable,
  } from "$components/patterns/admin/index.js";
  import { builtApiPath, unwrap } from "$lib/webapp/publicApi.js";
  import {
    serviceBytes,
    type UserService,
    type ServiceTranslate,
  } from "$lib/admin/servicePlans.js";
  import ServiceActivationDialog from "./ServiceActivationDialog.svelte";
  let {
    at,
    userId,
    banned = false,
  }: { at: ServiceTranslate; userId: number; banned?: boolean } = $props();
  const api = getAdminApi();
  let services = $state<UserService[]>([]);
  let total = $state(0);
  let page = $state(0);
  let loading = $state(false);
  let failed = $state(false);
  let activationOpen = $state(false);
  let request = 0;
  const date = (value: string) =>
    new Intl.DateTimeFormat("sv-SE", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
      timeZone: "Asia/Shanghai",
    }).format(new Date(value));
  async function load(currentPage: number, owner: number) {
    const id = ++request;
    loading = true;
    failed = false;
    try {
      const result = unwrap(
        await api(
          builtApiPath<"/api/admin/services">(
            `/admin/services?user_id=${owner}&limit=25&offset=${currentPage * 25}`
          )
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
    void load(page, userId);
  });
</script>

<section class="user-services" aria-label={at("services_title")} aria-busy={loading}>
  <h3>{at("services_title")}</h3>
  <AdminListToolbar {total} totalLabel={at("services_count")}>
    {#snippet actions()}<AdminButton disabled={loading} onclick={() => load(page, userId)}
        >{at("refresh")}</AdminButton
      ><AdminButton
        variant="primary"
        disabled={banned}
        onclick={() => {
          activationOpen = true;
        }}>{at("services_activate")}</AdminButton
      >{/snippet}
  </AdminListToolbar>
  {#if failed}<p role="alert">{at("services_request_failed")}</p>{:else if loading}<p role="status">
      {at("loading")}
    </p>{:else if !services.length}<AdminEmptyState tone="card"
      >{at("services_no_services")}</AdminEmptyState
    >{:else}
    <AdminTable
      ><thead
        ><tr
          >{#each ["services_name", "status", "services_used", "services_remaining", "services_expires", "services_next_reset", "services_exit_ip"] as key}<th
              >{at(key)}</th
            >{/each}</tr
        ></thead
      ><tbody>
        {#each services as service (service.id)}<tr>
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
              </div></td
            >
            <td data-label={at("services_used")}
              ><div>
                {serviceBytes(service.used_bytes)} / {serviceBytes(service.quota_bytes)}<small
                  >{at("services_last_sync")}: {service.last_usage_sync_at
                    ? date(service.last_usage_sync_at)
                    : at("services_never_synced")}</small
                >
              </div></td
            >
            <td data-label={at("services_remaining")}
              ><div>{serviceBytes(Math.max(0, service.quota_bytes - service.used_bytes))}</div></td
            >
            <td data-label={at("services_expires")}><div>{date(service.expires_at)}</div></td>
            <td data-label={at("services_next_reset")}
              ><div>{service.cycle_ends_at ? date(service.cycle_ends_at) : "—"}</div></td
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
          </tr>{/each}
      </tbody></AdminTable
    >
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
    totalLabel={at("services_count")}
    jumpLabel={at("services_page")}
    jumpAriaLabel={at("services_go_page")}
    goLabel={at("services_go_page")}
  />
</section>
{#if activationOpen}<ServiceActivationDialog
    {api}
    {at}
    {userId}
    onclose={() => {
      activationOpen = false;
    }}
    oncreated={() => {
      activationOpen = false;
      page = 0;
      void load(0, userId);
    }}
  />{/if}

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
