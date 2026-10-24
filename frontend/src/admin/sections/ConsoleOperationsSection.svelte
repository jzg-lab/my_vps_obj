<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { Input, Checkbox } from "$components/ui";
  import {
    AdminButton,
    AdminEmptyState,
    AdminField,
    AdminListToolbar,
    AdminPagination,
    AdminSelect,
  } from "$components/patterns/admin";
  import type { ApiClient } from "$lib/webapp/publicApi";
  import type { ServiceTranslate } from "$lib/admin/servicePlans";
  import { serviceDate } from "$lib/webapp/independentServices";
  import { consoleServiceLabel } from "$lib/admin/consoleServiceOperations";
  import {
    operationArchives,
    operationPhases,
    operationStatuses,
    operationHistoryState,
    operationQuery,
    operationsRouteUrl,
    readGlobalOperations,
    readOperationTrail,
    readOperationsRoute,
    validOperationIds,
    type GlobalOperations,
    type OperationsRoute,
  } from "$lib/admin/consoleGlobalOperations";
  import GlobalOperationTable from "./operations/GlobalOperationTable.svelte";
  import ConsoleServiceDetail from "./services/ConsoleServiceDetail.svelte";
  import ResourceOperationList from "./nodes/ResourceOperationList.svelte";
  import AccountOperationList from "./operations/AccountOperationList.svelte";
  import { operationViews, readOperationView } from "$lib/admin/consoleAccountOperations";

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
  const initial = readOperationsRoute(typeof window === "undefined" ? "" : window.location.search);
  let route = $state(initial);
  let userInput = $state(initial.userId);
  let serviceInput = $state(initial.serviceId);
  let trail = $state<string[]>(
    typeof window === "undefined" ? [] : readOperationTrail(window.history.state, initial)
  );
  let data = $state<GlobalOperations | null>(null);
  let loading = $state(true);
  let failed = $state(false);
  let invalid = $state(false);
  let view = $state(readOperationView(typeof window === "undefined" ? "" : window.location.search));
  function changeView(value: string) {
    view = operationViews.find((item) => item === value) ?? "services";
    const url = new URL(window.location.href);
    url.searchParams.set("operations_view", view);
    window.history.pushState(window.history.state, "", url);
  }
  let request = 0;
  let controller: AbortController | null = null;
  const statuses = $derived(
    operationStatuses.map((value) => ({
      value,
      label: at(value === "all" ? "console_all" : consoleServiceLabel("operation", value)),
    }))
  );
  const phases = $derived(
    operationPhases.map((value) => ({
      value,
      label: at(value === "all" ? "console_all" : consoleServiceLabel("phase", value)),
    }))
  );
  const archives = $derived(
    operationArchives.map((value) => ({ value, label: at(`console_global_archived_${value}`) }))
  );

  function navigate(next: OperationsRoute, cursors = trail) {
    trail = cursors;
    route = next;
    window.history.pushState(
      operationHistoryState(next, cursors),
      "",
      operationsRouteUrl(window.location.href, next, routePrefix)
    );
  }
  function filter(patch: Partial<OperationsRoute>) {
    invalid = false;
    navigate({ ...route, ...patch, cursor: "", detailServiceId: "" }, []);
  }
  function applyIds() {
    const userId = userInput.trim();
    const serviceId = serviceInput.trim();
    invalid = !validOperationIds(userId, serviceId);
    if (!invalid) filter({ userId, serviceId });
  }
  function previous() {
    if (loading || failed || !trail.length) return;
    navigate({ ...route, cursor: trail.at(-1)! }, trail.slice(0, -1));
  }
  function next() {
    if (loading || failed || !data?.next_cursor) return;
    navigate({ ...route, cursor: data.next_cursor }, [...trail, route.cursor]);
  }
  async function load(query: string) {
    const token = ++request;
    controller?.abort();
    controller = new AbortController();
    loading = true;
    failed = false;
    data = null;
    const current = readOperationsRoute(query);
    if (!validOperationIds(current.userId, current.serviceId)) {
      invalid = true;
      loading = false;
      return;
    }
    try {
      const result = await readGlobalOperations(api, current, controller.signal);
      if (token === request) data = result;
    } catch {
      if (token === request) failed = true;
    } finally {
      if (token === request) loading = false;
    }
  }
  const query = $derived(operationQuery(route).toString());
  $effect(() => {
    if (view === "services") void load(query);
    else {
      request++;
      controller?.abort();
    }
  });
  onMount(() => {
    const restore = () => {
      view = readOperationView(window.location.search);
      route = readOperationsRoute(window.location.search);
      trail = readOperationTrail(window.history.state, route);
      userInput = route.userId;
      serviceInput = route.serviceId;
      invalid = false;
    };
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  });
  onDestroy(() => {
    request++;
    controller?.abort();
  });
</script>

<AdminField label={at("resource_ops_view")}
  ><AdminSelect
    value={view}
    wrapLabels
    ariaLabel={at("resource_ops_view")}
    items={[
      { value: "services", label: at("resource_ops_service_view") },
      { value: "resources", label: at("resource_ops_title") },
      { value: "accounts", label: at("account_ops_title") },
    ]}
    onValueChange={changeView}
  /></AdminField
>
{#if view === "resources"}<ResourceOperationList {api} {at} {routePrefix} {onOpenUserCard} />
{:else if view === "accounts"}<AccountOperationList
    {api}
    {at}
    {routePrefix}
    {onOpenUserCard}
  />{:else}
  <section class="console-operations" aria-label={at("console_global_title")} aria-busy={loading}>
    <AdminListToolbar
      total={data?.total}
      totalLabel={at("console_global_count")}
      columns={3}
      mobileColumns={1}
      onsubmit={applyIds}
    >
      {#snippet filters()}
        <AdminField label={at("status")}
          ><AdminSelect
            value={route.status}
            items={statuses}
            ariaLabel={at("status")}
            onValueChange={(value) =>
              filter({ status: operationStatuses.find((item) => item === value) ?? "all" })}
          /></AdminField
        >
        <AdminField label={at("console_global_phase")}
          ><AdminSelect
            value={route.phase}
            items={phases}
            ariaLabel={at("console_global_phase")}
            onValueChange={(value) =>
              filter({ phase: operationPhases.find((item) => item === value) ?? "all" })}
          /></AdminField
        >
        <AdminField label={at("console_global_archived")}
          ><AdminSelect
            value={route.archived}
            items={archives}
            ariaLabel={at("console_global_archived")}
            onValueChange={(value) =>
              filter({ archived: operationArchives.find((item) => item === value) ?? "all" })}
          /></AdminField
        >
        <AdminField label={at("console_global_customer_id")}
          ><Input
            value={userInput}
            oninput={(event) => (userInput = event.currentTarget.value)}
            aria-label={at("console_global_customer_id")}
            maxlength={17}
          /></AdminField
        >
        <AdminField label={at("console_global_service_id")}
          ><Input
            value={serviceInput}
            oninput={(event) => (serviceInput = event.currentTarget.value)}
            aria-label={at("console_global_service_id")}
            maxlength={32}
          /></AdminField
        >
        <label class="attention"
          ><Checkbox
            checked={route.needsAttention}
            onCheckedChange={(needsAttention) => filter({ needsAttention })}
            ariaLabel={at("console_global_attention")}
          /><span>{at("console_global_attention")}</span></label
        >
      {/snippet}
      {#snippet actions()}
        <AdminButton type="submit">{at("search")}</AdminButton>
        <AdminButton disabled={loading} onclick={() => load(query)}>{at("refresh")}</AdminButton>
        <AdminButton
          onclick={() => {
            userInput = "";
            serviceInput = "";
            filter(readOperationsRoute(""));
          }}>{at("console_global_reset")}</AdminButton
        >
      {/snippet}
    </AdminListToolbar>
    <p class="admin-muted">{at("console_global_attention_scope")}</p>
    {#if invalid}<p role="alert">{at("console_global_invalid_ids")}</p>{/if}
    {#if failed}<p role="alert">{at("console_ops_load_failed")}</p>
    {:else if loading}<p role="status">{at("loading")}</p>
    {:else if data}
      {#if data.operations.length}
        <GlobalOperationTable
          {at}
          operations={data.operations}
          {onOpenUserCard}
          onOpenService={(detailServiceId) => navigate({ ...route, detailServiceId })}
        />
      {:else}<AdminEmptyState tone="card">{at("console_global_empty")}</AdminEmptyState>{/if}
      <p class="admin-muted">{at("console_observed_at")}: {serviceDate(data.observed_at)}</p>
      <AdminPagination
        total={data.total}
        totalLabel={at("console_global_count")}
        prevLabel={at("services_previous")}
        nextLabel={at("services_next")}
        prevDisabled={!trail.length}
        nextDisabled={!data.next_cursor}
        onPrev={previous}
        onNext={next}
      />
    {/if}
    {#if route.cursor}<div>
        <AdminButton disabled={loading} onclick={() => filter({})}
          >{at("console_global_first_page")}</AdminButton
        >
      </div>{/if}
  </section>
  {#if route.detailServiceId}{#key route.detailServiceId}<ConsoleServiceDetail
        {api}
        {at}
        {routePrefix}
        serviceId={route.detailServiceId}
        {onOpenUserCard}
        onclose={() => navigate({ ...route, detailServiceId: "" })}
      />{/key}{/if}
{/if}

<style>
  .console-operations {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  p {
    margin: 0;
    overflow-wrap: anywhere;
  }
  .attention {
    display: flex;
    align-items: center;
    gap: 8px;
    min-height: 36px;
    overflow-wrap: anywhere;
  }
</style>
