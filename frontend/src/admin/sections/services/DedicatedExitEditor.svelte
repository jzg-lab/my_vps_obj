<script lang="ts">
  import { onMount } from "svelte";
  import { Input } from "$components/ui/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { AdminButton, AdminField, AdminSelect } from "$components/patterns/admin/index.js";
  import { unwrap, type ApiClient } from "$lib/webapp/publicApi.js";
  import { serviceErrorKey, type ServiceTranslate } from "$lib/admin/servicePlans.js";

  let {
    api,
    at,
    onclose,
    onsaved,
  }: { api: ApiClient["api"]; at: ServiceTranslate; onclose: () => void; onsaved: () => void } =
    $props();
  let label = $state("");
  let ip = $state("");
  let pool = $state("");
  let squadId = $state("");
  let squads = $state<{ uuid: string; name: string }[]>([]);
  let loading = $state(true);
  let loadFailed = $state(false);
  let busy = $state(false);
  let error = $state("");
  async function loadSquads() {
    loading = true;
    loadFailed = false;
    try {
      squads = unwrap(await api("/admin/panel/internal-squads")).squads;
    } catch {
      loadFailed = true;
    } finally {
      loading = false;
    }
  }
  onMount(() => {
    void loadSquads();
  });
  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (busy || !squadId) return;
    error = "";
    busy = true;
    try {
      unwrap(
        await api("/admin/dedicated-exits", {
          method: "POST",
          body: JSON.stringify({
            label: label.trim(),
            ip_address: ip.trim(),
            resource_pool: pool.trim(),
            squad_uuid: squadId,
          }),
        })
      );
      onsaved();
    } catch (failure) {
      error = serviceErrorKey(failure);
    } finally {
      busy = false;
    }
  }
</script>

<Dialog
  open
  title={at("services_new_exit")}
  description={at("services_exit_registration_hint")}
  closeLabel={at("close")}
  onclose={() => {
    if (!busy) onclose();
  }}
  class="admin-dialog"
>
  <form class="exit-form" onsubmit={save}>
    <AdminField label={at("services_exit_label")}
      ><Input bind:value={label} required maxlength={160} disabled={busy} /></AdminField
    >
    <AdminField label={at("services_exit_ip")}
      ><Input bind:value={ip} required maxlength={45} disabled={busy} /></AdminField
    >
    <AdminField label={at("services_pool")}
      ><Input bind:value={pool} required maxlength={120} disabled={busy} /></AdminField
    >
    <AdminField label={at("services_dedicated_squad")} hint={at("services_dedicated_squad_hint")}
      ><AdminSelect
        bind:value={squadId}
        ariaLabel={at("services_dedicated_squad")}
        items={squads.map((squad) => ({ value: squad.uuid, label: squad.name }))}
        disabled={busy || loading}
      /></AdminField
    >
    {#if loading}<p role="status">{at("loading")}</p>{:else if loadFailed}<p role="alert">
        {at("services_squads_failed")}
      </p>
      <AdminButton onclick={loadSquads}>{at("refresh")}</AdminButton>{:else if !squads.length}<p>
        {at("services_no_squads")}
      </p>{/if}
    {#if error}<p role="alert">{at(error)}</p>{/if}
    <div class="admin-dialog-actions">
      <AdminButton disabled={busy} onclick={onclose}>{at("cancel")}</AdminButton><AdminButton
        type="submit"
        variant="primary"
        disabled={busy || !squadId}>{at(busy ? "services_saving" : "save")}</AdminButton
      >
    </div>
  </form>
</Dialog>

<style>
  .exit-form {
    display: grid;
    gap: 16px;
  }
  p {
    margin: 0;
    color: var(--admin-muted);
  }
  [role="alert"] {
    color: var(--danger);
  }
</style>
