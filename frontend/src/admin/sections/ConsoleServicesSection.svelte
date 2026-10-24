<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import Input from "$components/ui/input.svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminEntityLink,
    AdminField,
    AdminListToolbar,
    AdminPagination,
    AdminSelect,
    AdminTable,
  } from "$components/patterns/admin/index.js";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi";
  import { serviceBytes, type ServiceTranslate } from "$lib/admin/servicePlans";
  import { serviceDate } from "$lib/webapp/independentServices";
  import {
    consoleSorts,
    consoleStatuses,
    customerLabel,
    readServicesRoute,
    servicesRouteUrl,
    type ConsoleService,
    type ServicesRoute,
  } from "$lib/admin/consoleServices";
  import ConsoleServiceDetail from "./services/ConsoleServiceDetail.svelte";

  let {
    api,
    at,
    routePrefix = "",
    onOpenUserCard,
  }: {
    api: ApiClient["api"];
    at: ServiceTranslate;
    routePrefix?: string;
    onOpenUserCard: (id: unknown) => void;
  } = $props();
  let route = $state(
    readServicesRoute(typeof window === "undefined" ? "" : window.location.search)
  );
  let searchText = $state(
    readServicesRoute(typeof window === "undefined" ? "" : window.location.search).q
  );
  let rows = $state<ConsoleService[]>([]);
  let total = $state<number | undefined>();
  let observedAt = $state("");
  let loading = $state(true);
  let failed = $state(false);
  let request = 0;
  let controller: AbortController | null = null;
  const statusItems = $derived(
    consoleStatuses.map((value) => ({
      value,
      label: at(value === "all" ? "console_all" : `console_filter_${value}`),
    }))
  );
  const sortItems = $derived(
    consoleSorts.map((value) => ({ value, label: at(`console_sort_${value}`) }))
  );

  function navigate(patch: Partial<ServicesRoute>) {
    route = { ...route, ...patch };
    window.history.pushState(null, "", servicesRouteUrl(window.location.href, route, routePrefix));
  }
  async function load(current: ServicesRoute) {
    const id = ++request;
    controller?.abort();
    controller = new AbortController();
    loading = true;
    failed = false;
    total = undefined;
    const params = new URLSearchParams({
      q: current.q,
      status: current.status,
      sort: current.sort,
      page: String(current.page),
      page_size: "25",
      expiring_within_days: "7",
    });
    if (current.userId) params.set("user_id", current.userId);
    try {
      const result = unwrap(
        await api(
          builtApiPath<"/api/admin/console/services">(`/admin/console/services?${params}`),
          { signal: controller.signal }
        )
      );
      if (id !== request) return;
      rows = result.services;
      total = result.total;
      observedAt = result.observed_at;
      if (current.page > 0 && current.page * result.page_size >= result.total)
        navigate({ page: Math.max(0, Math.ceil(result.total / result.page_size) - 1) });
    } catch {
      if (id === request) failed = true;
    } finally {
      if (id === request) loading = false;
    }
  }
  $effect(() => {
    const { q, status, sort, page, userId } = route;
    void load({ q, status, sort, page, userId, serviceId: "" });
  });
  onMount(() => {
    const restore = () => {
      route = readServicesRoute(window.location.search);
      searchText = route.q;
    };
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  });
  onDestroy(() => {
    request++;
    controller?.abort();
  });
</script>

<section class="console-services" aria-busy={loading} aria-label={at("console_services")}>
  <AdminListToolbar
    {total}
    totalLabel={at("services_count")}
    columns={2}
    onsubmit={() => navigate({ q: searchText.trim(), page: 0 })}
  >
    {#snippet search()}<Input
        bind:value={searchText}
        maxlength={200}
        aria-label={at("console_search")}
        placeholder={at("console_search")}
      />{/snippet}
    {#snippet searchActions()}<AdminButton type="submit">{at("search")}</AdminButton>{/snippet}
    {#snippet filters()}
      <AdminField label={at("status")}
        ><AdminSelect
          value={route.status}
          items={statusItems}
          ariaLabel={at("status")}
          onValueChange={(status) => navigate({ status, page: 0 })}
        /></AdminField
      >
      <AdminField label={at("sort")}
        ><AdminSelect
          value={route.sort}
          items={sortItems}
          ariaLabel={at("sort")}
          onValueChange={(sort) => navigate({ sort, page: 0 })}
        /></AdminField
      >
    {/snippet}
    {#snippet actions()}<AdminButton disabled={loading} onclick={() => load(route)}
        >{at("refresh")}</AdminButton
      >{/snippet}
  </AdminListToolbar>
  <p class="admin-muted">{at("console_services_scope")}</p>
  {#if route.userId}<p>
      {at("console_customer_filter", { id: route.userId })}
      <AdminButton size="sm" onclick={() => navigate({ userId: "", page: 0 })}
        >{at("console_clear_customer")}</AdminButton
      >
    </p>{/if}
  {#if failed}<p role="alert">{at("services_load_failed")}</p>
  {:else if loading}<p role="status">{at("loading")}</p>
  {:else if !rows.length}<AdminEmptyState tone="card">{at("console_no_services")}</AdminEmptyState>
  {:else}
    <AdminTable
      ><thead
        ><tr
          >{#each ["console_customer", "services_name", "status", "services_used", "services_expires", "services_exit_ip"] as key}<th
              >{at(key)}</th
            >{/each}</tr
        ></thead
      >
      <tbody
        >{#each rows as row (row.service.id)}
          <tr>
            <td data-label={at("console_customer")}
              >{#if row.customer.user_id === null}
                {at("services_history_title")}
              {:else}<AdminEntityLink
                  label={customerLabel(row.customer)}
                  idText={row.customer.minishop_id ?? undefined}
                  onclick={() => onOpenUserCard(row.customer.user_id)}
                />{/if}</td
            >
            <td data-label={at("services_name")}
              ><AdminEntityLink
                kind="code"
                label={row.service.name}
                idText={row.service.id}
                onclick={() => navigate({ serviceId: row.service.id })}
              /></td
            >
            <td data-label={at("status")}
              ><AdminBadge variant={row.service.status === "active" ? "success" : "muted"}
                >{at(`services_status_${row.service.status}`)}</AdminBadge
              >
              {#if row.service.sync_error}<small>{at("console_filter_sync_error")}</small
                >{:else if row.service.sync_pending}<small>{at("services_sync_pending")}</small
                >{/if}
              {#if row.service.usage_error}<small
                  >{at(
                    row.service.last_usage_sync_at
                      ? "services_usage_stale"
                      : "services_usage_unconfirmed"
                  )}</small
                >{/if}
            </td>
            <td data-label={at("services_used")}
              >{row.service.last_usage_sync_at
                ? serviceBytes(row.service.used_bytes)
                : at("console_unknown")} / {serviceBytes(row.service.quota_bytes)}<small
                >{at("services_last_sync")}: {row.service.last_usage_sync_at
                  ? serviceDate(row.service.last_usage_sync_at)
                  : at("services_never_synced")}</small
              ></td
            >
            <td data-label={at("services_expires")}>{serviceDate(row.service.expires_at)}</td>
            <td data-label={at("services_exit_ip")}
              >{row.service.exit_ip || "—"}{#if row.service.exit_ip}<small
                  >{at(
                    row.service.exit_verified ? "services_verified" : "services_unverified"
                  )}</small
                >{/if}</td
            >
          </tr>
        {/each}</tbody
      >
    </AdminTable>
  {/if}
  {#if observedAt}<small>{at("console_observed_at")}: {serviceDate(observedAt)}</small>{/if}
  {#if total !== undefined}<AdminPagination
      page={route.page}
      pageCount={Math.ceil(total / 25)}
      {total}
      disabled={loading || failed}
      onPageChange={(page) => navigate({ page })}
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
{#if route.serviceId}{#key route.serviceId}<ConsoleServiceDetail
      {api}
      {at}
      {routePrefix}
      serviceId={route.serviceId}
      {onOpenUserCard}
      onclose={() => navigate({ serviceId: "" })}
    />{/key}{/if}

<style>
  .console-services {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  p {
    margin: 0;
  }
  small {
    display: block;
    color: var(--admin-muted);
    overflow-wrap: anywhere;
  }
</style>
