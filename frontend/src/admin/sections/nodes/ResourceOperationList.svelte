<script lang="ts">
  import { onMount, onDestroy, tick } from "svelte";
  import {
    AdminButton,
    AdminEmptyState,
    AdminListToolbar,
    AdminTable,
    AdminPagination,
    AdminEntityLink,
  } from "$components/patterns/admin";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import {
    resourceActionKey,
    resourceErrorKey,
    type ResourceOperation,
  } from "$lib/admin/resourceOperations";
  import { consoleServiceLabel } from "$lib/admin/consoleServiceOperations";
  import { serviceDate } from "$lib/webapp/independentServices";
  import ResourceOperationDetail from "./ResourceOperationDetail.svelte";
  import ResourceOperationSubmit from "./ResourceOperationSubmit.svelte";
  let {
    api,
    at,
    routePrefix = "",
    onOpenUserCard,
  }: {
    api: ApiClient["api"];
    at: ConsoleNodesTranslate;
    routePrefix?: string;
    onOpenUserCard: (id: unknown) => void;
  } = $props();
  let rows = $state<ResourceOperation[]>([]);
  let total = $state(0);
  let offset = $state(0);
  let id = $state("");
  let busy = $state(false);
  let error = $state("");
  let controller: AbortController | null = null;
  let sequence = 0;
  let content: HTMLElement | undefined;
  function restore() {
    const params = new URLSearchParams(window.location.search);
    const value = Number(params.get("resource_operations_offset") ?? 0);
    offset = Number.isSafeInteger(value) && value >= 0 && value <= 1000000 ? value : 0;
    const selected = params.get("resource_operation_id") ?? "";
    id = /^[a-f0-9]{32}$/.test(selected) ? selected : "";
    void load();
  }
  function navigate(nextOffset: number, operationId = "") {
    const url = new URL(window.location.href);
    url.searchParams.set("resource_operations_offset", String(nextOffset));
    if (operationId) url.searchParams.set("resource_operation_id", operationId);
    else url.searchParams.delete("resource_operation_id");
    window.history.pushState(window.history.state, "", url);
    const changed = offset !== nextOffset;
    offset = nextOffset;
    id = operationId;
    if (changed) void load();
  }
  async function load() {
    const token = ++sequence;
    controller?.abort();
    controller = new AbortController();
    busy = true;
    error = "";
    try {
      const data = unwrap(
        await api(
          builtApiPath<"/api/admin/console/resources/operations">(
            `/admin/console/resources/operations?offset=${offset}&limit=25`
          ),
          { signal: controller.signal }
        )
      );
      if (token === sequence) {
        rows = data.items;
        total = data.total;
      }
    } catch (failure) {
      if (token === sequence) error = resourceErrorKey(failure);
    } finally {
      if (token === sequence) busy = false;
    }
  }
  async function closeDetail() {
    const previous = id;
    navigate(offset);
    await load();
    await tick();
    (
      content?.querySelector<HTMLButtonElement>(
        `[data-resource-operation-id="${previous}"] button`
      ) ?? content?.querySelector<HTMLButtonElement>("button")
    )?.focus();
  }
  onMount(() => {
    restore();
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  });
  onDestroy(() => {
    sequence++;
    controller?.abort();
  });
</script>

<section
  class="resource-operations-list"
  bind:this={content}
  aria-label={at("resource_ops_title")}
  aria-busy={busy}
>
  <AdminListToolbar total={error ? undefined : total} totalLabel={at("resource_ops_count")}
    >{#snippet actions()}<AdminButton disabled={busy} onclick={load}>{at("refresh")}</AdminButton
      >{/snippet}</AdminListToolbar
  >
  <ResourceOperationSubmit
    {api}
    {at}
    {routePrefix}
    onAccepted={(operation) => {
      navigate(offset, operation.id);
      void load();
    }}
  />
  {#if error}<p role="alert">{at(error)}</p>{:else if busy}<p role="status">{at("loading")}</p>
  {:else if rows.length}<AdminTable layout="fixed"
      ><thead
        ><tr
          ><th>{at("resource_ops_detail")}</th><th>{at("status")}</th><th
            >{at("resource_ops_target_id")}</th
          ><th>{at("resource_ops_created")}</th></tr
        ></thead
      ><tbody
        >{#each rows as row (row.id)}<tr>
            <td data-label={at("resource_ops_detail")} data-resource-operation-id={row.id}
              ><AdminEntityLink
                kind="code"
                label={at(resourceActionKey(row.change.operation))}
                idText={row.id}
                onclick={() => navigate(offset, row.id)}
              /></td
            >
            <td data-label={at("status")}
              >{at(consoleServiceLabel("operation", row.status))}<br />{at(
                row.gate_active ? "resource_ops_gate_held" : "resource_ops_gate_released"
              )}</td
            >
            <td data-label={at("resource_ops_target_id")}
              >{row.target_id ?? at("console_unknown")}</td
            ><td data-label={at("resource_ops_created")}>{serviceDate(row.created_at)}</td>
          </tr>{/each}</tbody
      ></AdminTable
    >{:else}<AdminEmptyState tone="card">{at("resource_ops_empty")}</AdminEmptyState>{/if}
  <AdminPagination
    {total}
    totalLabel={at("resource_ops_count")}
    prevLabel={at("services_previous")}
    nextLabel={at("services_next")}
    prevDisabled={busy || offset === 0}
    nextDisabled={busy || offset + 25 >= total}
    onPrev={() => navigate(Math.max(0, offset - 25))}
    onNext={() => navigate(offset + 25)}
  />
</section>
{#if id}{#key id}<ResourceOperationDetail
      {api}
      {at}
      {routePrefix}
      operationId={id}
      {onOpenUserCard}
      onOpenOperation={(next) => navigate(offset, next)}
      onclose={closeDetail}
    />{/key}{/if}

<style>
  .resource-operations-list {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  p,
  td {
    margin: 0;
    overflow-wrap: anywhere;
  }
</style>
