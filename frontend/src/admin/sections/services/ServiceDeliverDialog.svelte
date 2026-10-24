<script lang="ts">
  import { Checkbox } from "$components/ui/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { AdminButton } from "$components/patterns/admin/index.js";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi.js";
  import {
    serviceErrorKey,
    type ServiceTranslate,
    type UserService,
  } from "$lib/admin/servicePlans.js";

  let {
    api,
    at,
    service,
    onclose,
    onsaved,
  }: {
    api: ApiClient["api"];
    at: ServiceTranslate;
    service: UserService;
    onclose: () => void;
    onsaved: () => void;
  } = $props();
  let confirmed = $state(false);
  let busy = $state(false);
  let error = $state("");
  async function save() {
    if (busy || !confirmed || service.user_id === null) return;
    busy = true;
    error = "";
    try {
      unwrap(
        await api(
          builtApiPath<"/api/admin/services/{service_id}/deliver">(
            `/admin/services/${service.id}/deliver`
          ),
          {
            method: "POST",
            body: JSON.stringify({
              user_id: service.user_id,
              expected_revision: service.revision,
              idempotency_key: `deliver:${service.id}:${service.revision}`,
            }),
          }
        )
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
  portal
  title={at("services_deliver")}
  description={at("services_deliver_hint")}
  closeLabel={at("close")}
  class="admin-dialog"
  onclose={() => {
    if (!busy) onclose();
  }}
>
  <p>{service.name} · {service.id}</p>
  <label
    ><Checkbox
      bind:checked={confirmed}
      ariaLabel={at("services_deliver_confirm")}
      disabled={busy}
    /><span>{at("services_deliver_confirm")}</span></label
  >
  {#if error}<p role="alert">{at(error)}</p>{/if}
  <div class="admin-dialog-actions">
    <AdminButton disabled={busy} onclick={onclose}>{at("close")}</AdminButton><AdminButton
      variant="primary"
      disabled={busy || !confirmed}
      onclick={save}>{at(busy ? "services_saving" : "services_deliver")}</AdminButton
    >
  </div>
</Dialog>

<style>
  label {
    display: flex;
    gap: 10px;
    align-items: start;
    margin: 16px 0;
  }
  p,
  span {
    overflow-wrap: anywhere;
  }
</style>
