<script lang="ts">
  import { onDestroy, onMount, tick } from "svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminListToolbar,
    AdminPagination,
    AdminTable,
  } from "$components/patterns/admin/index.js";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi.js";
  import type { DedicatedExit, ServiceTranslate } from "$lib/admin/servicePlans.js";
  import ExitEvidenceDialog from "./services/ExitEvidenceDialog.svelte";
  import DedicatedExitEditor from "./services/DedicatedExitEditor.svelte";
  import ConsoleServiceDetail from "./services/ConsoleServiceDetail.svelte";
  import DedicatedExitOwnership from "./dedicated-exits/DedicatedExitOwnership.svelte";
  import { exitHasHold } from "./dedicated-exits/availability";
  import {
    dedicatedExitsUrl,
    readDedicatedExitsRoute,
    type DedicatedExitsRoute,
  } from "./dedicated-exits/navigation";
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
    readDedicatedExitsRoute(typeof window === "undefined" ? "" : window.location.search)
  );
  let currentUrl = $state(
    typeof window === "undefined" ? "http://localhost/admin/dedicated-exits" : window.location.href
  );
  let exits = $state<DedicatedExit[]>([]);
  let total = $state<number | undefined>();
  let loadedPage = $state<number | null>(null);
  const page = $derived(route.page);
  let loading = $state(true);
  let failed = $state(false);
  const selected = $derived(
    loadedPage === page ? exits.find((resource) => resource.id === route.exitId) : undefined
  );
  let inventory: HTMLElement | undefined;
  let editorOpen = $state(false);
  let request = 0;
  let controller: AbortController | null = null;
  function navigate(patch: Partial<DedicatedExitsRoute>, replace = false) {
    route = { ...route, ...patch };
    const url = dedicatedExitsUrl(window.location.href, route, routePrefix);
    window.history[replace ? "replaceState" : "pushState"](null, "", url);
    currentUrl = url.href;
  }
  function openService(serviceId: string) {
    navigate({ serviceId });
  }
  async function closeEvidence() {
    const exitId = route.exitId;
    navigate({ exitId: "", auditPage: 0 });
    await load(page);
    await tick();
    const trigger = inventory?.querySelector<HTMLButtonElement>(
      `[data-exit-id="${CSS.escape(exitId)}"] button`
    );
    (trigger ?? inventory)?.focus();
  }
  async function closeService() {
    const serviceId = route.serviceId;
    navigate({ serviceId: "" });
    if (route.exitId) return;
    await tick();
    const trigger = inventory?.querySelector<HTMLAnchorElement>(
      `[data-service-id="${CSS.escape(serviceId)}"]`
    );
    (trigger ?? inventory)?.focus();
  }
  async function load(currentPage: number) {
    const id = ++request;
    controller?.abort();
    controller = new AbortController();
    loading = true;
    failed = false;
    try {
      const result = unwrap(
        await api(
          builtApiPath<"/api/admin/dedicated-exits">(
            `/admin/dedicated-exits?limit=25&offset=${currentPage * 25}`
          ),
          { signal: controller.signal }
        )
      );
      if (id === request) {
        total = result.total;
        if (currentPage > 0 && currentPage * 25 >= result.total) {
          navigate({ page: Math.max(0, Math.ceil(result.total / 25) - 1) }, true);
          return;
        }
        exits = result.exits;
        loadedPage = currentPage;
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
  onMount(() => {
    const restore = () => {
      route = readDedicatedExitsRoute(window.location.search);
      currentUrl = window.location.href;
    };
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  });
  onDestroy(() => {
    request++;
    controller?.abort();
  });
</script>

<section bind:this={inventory} class="exits" aria-busy={loading} tabindex="-1">
  <AdminListToolbar {total} totalLabel={at("services_exits_count")}>
    {#snippet actions()}<AdminButton disabled={loading} onclick={() => load(page)}
        >{at("refresh")}</AdminButton
      ><AdminButton
        variant="primary"
        onclick={() => {
          editorOpen = true;
        }}>{at("services_new_exit")}</AdminButton
      >{/snippet}
  </AdminListToolbar>
  <p class="admin-muted">{at("services_exit_registration_hint")}</p>
  {#if failed}<p role="alert">{at("services_request_failed")}</p>{:else if loading}<p role="status">
      {at("loading")}
    </p>{:else if !exits.length}<AdminEmptyState tone="card"
      >{at("services_no_exits")}</AdminEmptyState
    >{:else}
    <AdminTable
      ><thead
        ><tr
          >{#each ["services_exit_label", "services_exit_ip", "services_pool", "services_allocation", "services_verification", "services_service_id", "services_exit_evidence"] as key}<th
              >{at(key)}</th
            >{/each}</tr
        ></thead
      ><tbody>
        {#each exits as resource (resource.id)}<tr data-exit-id={resource.id}>
            <td data-label={at("services_exit_label")}>{resource.label}</td>
            <td data-label={at("services_exit_ip")}>{resource.ip_address}</td>
            <td data-label={at("services_pool")}>{resource.resource_pool}</td>
            <td data-label={at("services_allocation")}
              ><AdminBadge
                wrap
                variant={exitHasHold(resource) || resource.service_id
                  ? "muted"
                  : resource.enabled
                    ? "success"
                    : "muted"}
                >{at(
                  exitHasHold(resource)
                    ? "services_exit_held"
                    : resource.service_id
                      ? "services_allocated"
                      : resource.enabled
                        ? "services_available"
                        : "services_disabled"
                )}</AdminBadge
              ></td
            >
            <td data-label={at("services_verification")}
              >{at(resource.verified_at ? "services_verified" : "services_unverified")}</td
            >
            <td data-label={at("services_service_id")}
              ><DedicatedExitOwnership
                {resource}
                {currentUrl}
                {routePrefix}
                {at}
                onOpenService={openService}
              /></td
            >
            <td data-label={at("services_exit_evidence")}
              ><AdminButton
                size="sm"
                onclick={() => navigate({ exitId: resource.id, auditPage: 0 })}
                >{at("services_exit_evidence")}</AdminButton
              ></td
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
        navigate({ page: value, exitId: "", auditPage: 0 });
      }}
      prevLabel={at("services_previous")}
      nextLabel={at("services_next")}
      pageLabel={at("services_page")}
      ofLabel={at("services_of")}
      totalLabel={at("services_exits_count")}
      jumpLabel={at("services_page")}
      jumpAriaLabel={at("services_go_page")}
      goLabel={at("services_go_page")}
    />{/if}
</section>
{#if editorOpen}<DedicatedExitEditor
    {api}
    {at}
    onclose={() => {
      editorOpen = false;
    }}
    onsaved={() => {
      editorOpen = false;
      void load(page);
    }}
  />{/if}

{#if !loading && !failed && loadedPage === page && route.exitId && !selected}<p role="alert">
    {at("services_exit_unavailable")}
  </p>
  <AdminButton onclick={closeEvidence}>{at("close")}</AdminButton>{/if}
{#if selected}{#key selected.id}<ExitEvidenceDialog
      {api}
      {at}
      resource={selected}
      open={!route.serviceId}
      {currentUrl}
      {routePrefix}
      page={route.auditPage}
      onPageChange={(auditPage, replace) => navigate({ auditPage }, replace)}
      onOpenService={openService}
      onclose={closeEvidence}
      onsaved={closeEvidence}
    />{/key}{/if}

{#if route.serviceId}<ConsoleServiceDetail
    {api}
    {at}
    serviceId={route.serviceId}
    {routePrefix}
    {onOpenUserCard}
    onclose={closeService}
  />{/if}

<style>
  .exits {
    display: grid;
    gap: 16px;
  }
  p {
    margin: 0;
  }
</style>
