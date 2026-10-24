<script lang="ts">
  import { onDestroy, onMount, tick, untrack } from "svelte";
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
    accountArchives,
    accountSources,
    accountStatuses,
    accountOperationQuery,
    accountOperationsUrl,
    readAccountOperations,
    readAccountOperationsRoute,
    validAccountOperationsRoute,
    type AccountOperations,
    type AccountOperationsRoute,
  } from "$lib/admin/consoleAccountOperations";
  import AccountOperationTable from "./AccountOperationTable.svelte";
  import AccountOperationDetail from "./AccountOperationDetail.svelte";

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
  const initial = readAccountOperationsRoute(
    typeof window === "undefined" ? "" : window.location.search
  );
  let route = $state(initial);
  let userInput = $state(initial.userId);
  let actorInput = $state(initial.actorId);
  let data = $state<AccountOperations | null>(null);
  let loading = $state(true);
  let failed = $state(false);
  let invalid = $state(false);
  let sequence = 0;
  let controller: AbortController | null = null;
  let content: HTMLElement | undefined;
  const statuses = $derived(
    accountStatuses.map((value) => ({
      value,
      label: at(value === "all" ? "console_all" : consoleServiceLabel("operation", value)),
    }))
  );
  const sources = $derived(
    accountSources.map((value) => ({
      value,
      label: at(value === "all" ? "console_all" : consoleServiceLabel("source", value)),
    }))
  );
  const archives = $derived(
    accountArchives.map((value) => ({ value, label: at(`console_global_archived_${value}`) }))
  );

  function navigate(next: AccountOperationsRoute) {
    route = next;
    window.history.pushState(
      window.history.state,
      "",
      accountOperationsUrl(window.location.href, next, routePrefix)
    );
  }
  function filter(patch: Partial<AccountOperationsRoute>) {
    invalid = false;
    navigate({ ...route, ...patch, page: 0, operationId: "" });
  }
  function applyIds() {
    const next = { ...route, userId: userInput.trim(), actorId: actorInput.trim(), page: 0 };
    invalid = !validAccountOperationsRoute(next);
    if (!invalid) filter(next);
  }
  async function load(current: AccountOperationsRoute) {
    const token = ++sequence;
    controller?.abort();
    controller = new AbortController();
    loading = true;
    failed = false;
    data = null;
    const valid = validAccountOperationsRoute(current);
    invalid = !valid;
    if (!valid) {
      loading = false;
      return;
    }
    try {
      const result = await readAccountOperations(api, current, controller.signal);
      if (token !== sequence) return;
      data = result;
      if (current.page > 0 && current.page * result.page_size >= result.total)
        navigate({ ...route, page: Math.max(0, Math.ceil(result.total / result.page_size) - 1) });
    } catch {
      if (token === sequence) failed = true;
    } finally {
      if (token === sequence) loading = false;
    }
  }
  async function closeDetail() {
    const previous = route.operationId;
    navigate({ ...route, operationId: "" });
    await tick();
    content
      ?.querySelector<HTMLButtonElement>(
        `[data-account-operation-id="${previous}"] [data-account-record] button`
      )
      ?.focus();
  }
  const query = $derived(accountOperationQuery(route).toString());
  $effect(() => {
    // Detail navigation keeps the loaded page and its keyboard return target.
    void query;
    untrack(() => {
      void load(route);
    });
  });
  onMount(() => {
    const restore = () => {
      route = readAccountOperationsRoute(window.location.search);
      userInput = route.userId;
      actorInput = route.actorId;
      invalid = false;
    };
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  });
  onDestroy(() => {
    sequence++;
    controller?.abort();
  });
</script>

<section
  class="account-operations-list"
  aria-label={at("account_ops_title")}
  aria-busy={loading}
  bind:this={content}
>
  <AdminListToolbar
    total={data?.total}
    totalLabel={at("account_ops_count")}
    columns={3}
    mobileColumns={1}
    onsubmit={applyIds}
  >
    {#snippet filters()}
      <AdminField label={at("status")}
        ><AdminSelect
          wrapLabels
          value={route.status}
          items={statuses}
          ariaLabel={at("status")}
          onValueChange={(value) =>
            filter({ status: accountStatuses.find((item) => item === value) ?? "all" })}
        /></AdminField
      >
      <AdminField label={at("account_ops_source")}
        ><AdminSelect
          value={route.source}
          items={sources}
          ariaLabel={at("account_ops_source")}
          onValueChange={(value) =>
            filter({ source: accountSources.find((item) => item === value) ?? "all" })}
        /></AdminField
      >
      <AdminField label={at("console_global_archived")}
        ><AdminSelect
          value={route.archived}
          items={archives}
          ariaLabel={at("console_global_archived")}
          onValueChange={(value) =>
            filter({ archived: accountArchives.find((item) => item === value) ?? "all" })}
        /></AdminField
      >
      <AdminField label={at("account_ops_target")}
        ><Input
          value={userInput}
          oninput={(event) => (userInput = event.currentTarget.value)}
          aria-label={at("account_ops_target")}
          maxlength={17}
        /></AdminField
      >
      <AdminField label={at("services_actor")}
        ><Input
          value={actorInput}
          oninput={(event) => (actorInput = event.currentTarget.value)}
          aria-label={at("services_actor")}
          maxlength={17}
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
      <AdminButton disabled={loading} onclick={() => load(route)}>{at("refresh")}</AdminButton>
      <AdminButton
        onclick={() => {
          userInput = "";
          actorInput = "";
          filter(readAccountOperationsRoute(""));
        }}>{at("console_global_reset")}</AdminButton
      >
    {/snippet}
  </AdminListToolbar>
  <p class="admin-muted">{at("account_ops_scope")}</p>
  <p class="admin-muted">{at("account_ops_attention_scope")}</p>
  {#if invalid}<p role="alert">{at("account_ops_invalid_filters")}</p>{/if}
  {#if failed}<p role="alert">{at("account_ops_load_failed")}</p>
  {:else if loading}<p role="status">{at("loading")}</p>
  {:else if data}
    {#if data.operations.length}
      <AccountOperationTable
        operations={data.operations}
        {at}
        {onOpenUserCard}
        onOpenOperation={(operationId) => navigate({ ...route, operationId })}
      />
    {:else}<AdminEmptyState tone="card">{at("account_ops_empty")}</AdminEmptyState>{/if}
    <p class="admin-muted">{at("console_observed_at")}: {serviceDate(data.observed_at)}</p>
    <AdminPagination
      page={data.page}
      pageCount={Math.ceil(data.total / data.page_size)}
      total={data.total}
      disabled={loading || failed}
      onPageChange={(page) => navigate({ ...route, page, operationId: "" })}
      prevLabel={at("services_previous")}
      nextLabel={at("services_next")}
      pageLabel={at("services_page")}
      ofLabel={at("services_of")}
      totalLabel={at("account_ops_count")}
      jumpLabel={at("services_page")}
      jumpAriaLabel={at("services_go_page")}
      goLabel={at("services_go_page")}
    />
  {/if}
</section>
{#if route.operationId}{#key route.operationId}<AccountOperationDetail
      {api}
      {at}
      operationId={route.operationId}
      onclose={closeDetail}
      {onOpenUserCard}
    />{/key}{/if}

<style>
  .account-operations-list {
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
