<script lang="ts">
  import { onMount, untrack } from "svelte";
  import { AdminButton, AdminEmptyState } from "$components/patterns/admin/index.js";
  import { ExternalLink } from "$components/ui/icons.js";
  import type { ServiceTranslate } from "$lib/admin/servicePlans";
  import { createMaintenanceStore } from "$lib/admin/stores/maintenanceStore.svelte";
  import type { ApiClient } from "$lib/webapp/publicApi";

  let {
    at,
    api,
  }: {
    at: ServiceTranslate;
    api: ApiClient["api"];
  } = $props();
  const store = createMaintenanceStore(untrack(() => api));
  onMount(() => {
    void store.load();
    return store.dispose;
  });
</script>

<section
  class="maintenance"
  aria-label={at("maintenance_title", {}, "Advanced maintenance")}
  aria-busy={store.state.status === "loading"}
>
  <p>
    {at(
      "maintenance_purpose",
      {},
      "Open Remnawave for low-frequency protocol, inbound and routing maintenance. Daily customer and service operations remain here."
    )}
  </p>
  <p>
    {at(
      "maintenance_auth",
      {},
      "This is an external administration panel. Its existing sign-in is required; this site does not pass login credentials."
    )}
  </p>
  {#if store.state.status === "loading"}
    <AdminEmptyState role="status">{at("loading", {}, "Loading…")}</AdminEmptyState>
  {:else if store.state.status === "error"}
    <p role="alert">
      {at(
        "maintenance_load_failed",
        {},
        "The maintenance address could not be loaded. Please try again."
      )}
    </p>
    <AdminButton onclick={store.load}>{at("retry", {}, "Retry")}</AdminButton>
  {:else if store.state.status === "ready"}
    <dl class="admin-meta-list">
      <div>
        <dt>{at("maintenance_destination", {}, "External destination")}</dt>
        <dd>{store.state.destination}</dd>
      </div>
    </dl>
    <a
      href={store.state.destination}
      target="_blank"
      rel="noopener noreferrer"
      referrerpolicy="no-referrer"
    >
      <ExternalLink size={16} aria-hidden="true" />
      {at("maintenance_open", {}, "Open Remnawave in a new tab")}
    </a>
  {:else}
    <AdminEmptyState role="status">
      {at(
        "maintenance_unconfigured",
        {},
        "A public maintenance address is not configured. Configure the public Remnawave address before opening advanced maintenance."
      )}
    </AdminEmptyState>
  {/if}
</section>

<style>
  .maintenance {
    display: grid;
    gap: 16px;
    max-width: 760px;
  }
  p,
  dl,
  dd {
    margin: 0;
  }
  dd {
    overflow-wrap: anywhere;
  }
  a {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    width: fit-content;
    max-width: 100%;
  }
  a :global(svg) {
    flex: none;
  }
</style>
