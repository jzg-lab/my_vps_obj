<script lang="ts">
  import { Textarea, Checkbox } from "$components/ui/index.js";
  import Dialog from "$components/ui/dialog.svelte";
  import { AdminButton, AdminField } from "$components/patterns/admin/index.js";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi.js";
  import {
    serviceErrorKey,
    type ServiceTranslate,
    type UserService,
  } from "$lib/admin/servicePlans.js";
  import type { components } from "$lib/api/openapi.generated.js";

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
  let reason = $state("");
  let confirmed = $state(false);
  let busy = $state(false);
  let error = $state("");
  let pending = $state<components["schemas"]["ServiceRevokeBody"] | null>(null);
  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (busy || !confirmed || service.user_id === null) return;
    pending ??= {
      user_id: service.user_id,
      expected_revision: service.revision,
      idempotency_key: `revoke:${service.id}:${service.revision}`,
      reason: reason.trim(),
    };
    busy = true;
    error = "";
    try {
      unwrap(
        await api(
          builtApiPath<"/api/admin/services/{service_id}/revoke">(
            `/admin/services/${service.id}/revoke`
          ),
          { method: "POST", body: JSON.stringify(pending) }
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
  title={at("services_revoke")}
  description={at("services_revoke_hint")}
  closeLabel={at("close")}
  class="admin-dialog"
  onclose={() => {
    if (!busy) onclose();
  }}
>
  <p>{service.name} · {service.id}</p>
  <form onsubmit={save}>
    <AdminField label={at("services_revoke_reason")}
      ><Textarea
        required
        minlength={3}
        maxlength={1000}
        bind:value={reason}
        disabled={busy || Boolean(pending)}
      /></AdminField
    >
    <label
      ><Checkbox
        bind:checked={confirmed}
        ariaLabel={at("services_revoke_confirm")}
        disabled={busy || Boolean(pending)}
      /><span>{at("services_revoke_confirm")}</span></label
    >
    {#if error}<p role="alert">{at(error)}</p>{/if}
    <div class="admin-dialog-actions">
      <AdminButton disabled={busy} onclick={onclose}>{at("close")}</AdminButton><AdminButton
        type="submit"
        variant="danger"
        disabled={busy || !confirmed}
        >{at(busy ? "services_saving" : "services_revoke")}</AdminButton
      >
    </div>
  </form>
</Dialog>

<style>
  form {
    display: grid;
    gap: 16px;
  }
  label {
    display: flex;
    gap: 10px;
    align-items: start;
  }
  p,
  span {
    overflow-wrap: anywhere;
  }
</style>
