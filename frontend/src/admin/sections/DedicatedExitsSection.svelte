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
  import type { DedicatedExit, ServiceTranslate } from "$lib/admin/servicePlans.js";
  import ExitEvidenceDialog from "./services/ExitEvidenceDialog.svelte";
  import DedicatedExitEditor from "./services/DedicatedExitEditor.svelte";
  let { api, at }: { api: ApiClient["api"]; at: ServiceTranslate } = $props();
  let exits = $state<DedicatedExit[]>([]);
  let total = $state(0);
  let page = $state(0);
  let loading = $state(false);
  let failed = $state(false);
  let selected = $state<DedicatedExit | null>(null);
  let editorOpen = $state(false);
  let request = 0;
  async function load(currentPage: number) {
    const id = ++request;
    loading = true;
    failed = false;
    try {
      const result = unwrap(
        await api(
          builtApiPath<"/api/admin/dedicated-exits">(
            `/admin/dedicated-exits?limit=25&offset=${currentPage * 25}`
          )
        )
      );
      if (id === request) {
        exits = result.exits;
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

<section class="exits" aria-busy={loading}>
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
        {#each exits as resource (resource.id)}<tr>
            <td data-label={at("services_exit_label")}>{resource.label}</td>
            <td data-label={at("services_exit_ip")}>{resource.ip_address}</td>
            <td data-label={at("services_pool")}>{resource.resource_pool}</td>
            <td data-label={at("services_allocation")}
              ><AdminBadge
                variant={resource.service_id ? "muted" : resource.enabled ? "success" : "muted"}
                >{at(
                  resource.service_id
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
            <td data-label={at("services_service_id")}>{resource.service_id || "—"}</td>
            <td data-label={at("services_exit_evidence")}
              ><AdminButton size="sm" onclick={() => (selected = resource)}
                >{at("services_exit_evidence")}</AdminButton
              ></td
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
    totalLabel={at("services_exits_count")}
    jumpLabel={at("services_page")}
    jumpAriaLabel={at("services_go_page")}
    goLabel={at("services_go_page")}
  />
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

{#if selected}{#key selected.id}<ExitEvidenceDialog
      {api}
      {at}
      resource={selected}
      onclose={() => {
        selected = null;
        void load(page);
      }}
      onsaved={() => {
        selected = null;
        void load(page);
      }}
    />{/key}{/if}

<style>
  .exits {
    display: grid;
    gap: 16px;
  }
  p {
    margin: 0;
  }
</style>
