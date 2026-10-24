<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import { AdminButton } from "$components/patterns/admin";
  import type { ApiClient } from "$lib/webapp/publicApi";
  import type { ServiceTranslate, UserService } from "$lib/admin/servicePlans";
  import {
    consoleServiceErrorKey,
    pendingOperationRetry,
    readServiceDiagnostics,
    readServiceOperations,
    retryBodyForSnapshot,
    submitOperationRetry,
    type ServiceDiagnostics as Diagnostics,
    type ServiceOperations,
    type ServiceRetryBody,
  } from "$lib/admin/consoleServiceOperations";
  import ServiceDiagnostics from "./ServiceDiagnostics.svelte";
  import ServiceOperationList from "./ServiceOperationList.svelte";
  let {
    api,
    at,
    service,
    readonly = false,
    onclose,
  }: {
    api: ApiClient["api"];
    at: ServiceTranslate;
    service: UserService;
    readonly?: boolean;
    onclose: () => void;
  } = $props();
  let diagnostics = $state<Diagnostics | null>(null);
  let operations = $state<ServiceOperations | null>(null);
  let pending = $state<Record<string, ServiceRetryBody>>({});
  let page = $state(0);
  let loading = $state(true);
  let failed = $state(false);
  let busy = $state(false);
  let storageFailed = $state(false);
  let error = $state("");
  let accepted = $state(false);
  let request = 0;
  let controller: AbortController | null = null;
  let alive = true;
  async function snapshot(signal?: AbortSignal) {
    const [diagnostic, list] = await Promise.all([
      readServiceDiagnostics(api, service.id, signal),
      readServiceOperations(api, service.id, page, signal),
    ]);
    return { diagnostic, list };
  }
  async function load() {
    const token = ++request;
    controller?.abort();
    controller = new AbortController();
    loading = true;
    failed = false;
    diagnostics = null;
    operations = null;
    pending = {};
    try {
      const { diagnostic, list } = await snapshot(controller.signal);
      if (token !== request) return;
      diagnostics = diagnostic;
      operations = list;
      storageFailed = false;
      try {
        const saved: Record<string, ServiceRetryBody> = {};
        for (const item of list.operations) {
          const body = pendingOperationRetry(sessionStorage, service.id, item.id);
          if (body) saved[item.id] = body;
        }
        pending = saved;
      } catch {
        storageFailed = true;
      }
    } catch {
      if (token === request) failed = true;
    } finally {
      if (token === request) loading = false;
    }
  }
  async function retry(operationId: string) {
    if (
      busy ||
      loading ||
      readonly ||
      storageFailed ||
      service.user_id === null ||
      !diagnostics ||
      diagnostics.user_id !== service.user_id
    )
      return;
    busy = true;
    error = "";
    accepted = false;
    try {
      const { diagnostic, list } = await snapshot();
      if (!alive) return;
      const saved = pendingOperationRetry(sessionStorage, service.id, operationId);
      const body = retryBodyForSnapshot(diagnostic, list, operationId, diagnostics, saved);
      await submitOperationRetry(api, sessionStorage, service.id, operationId, body);
      if (alive) accepted = true;
    } catch (failure) {
      if (alive)
        error =
          failure instanceof Error && failure.message === "services_storage_failed"
            ? "services_storage_failed"
            : consoleServiceErrorKey(failure);
    } finally {
      // Success, explicit rejection and a lost reply all require authoritative reads.
      if (alive) {
        await load();
        busy = false;
      }
    }
  }
  onMount(() => {
    void load();
  });
  onDestroy(() => {
    alive = false;
    request++;
    controller?.abort();
  });
</script>

<Dialog
  open
  portal
  size="wide"
  title={at("console_ops_title")}
  description={at("console_ops_hint")}
  closeLabel={at("close")}
  focusKey={`${loading}:${busy}:${error}`}
  onclose={() => {
    if (!busy) onclose();
  }}
  class="admin-dialog"
>
  <div class="service-diagnostics" aria-busy={loading || busy}>
    <header>
      <p><strong>{service.name}</strong><br />{service.id}</p>
      <AdminButton disabled={busy || loading} onclick={load}>{at("refresh")}</AdminButton>
    </header>
    {#if error}<p role="alert">{at(error)}</p>{/if}
    {#if accepted}<p role="status">{at("console_ops_accepted")}</p>{/if}
    {#if storageFailed}<p role="alert">{at("services_storage_failed")}</p>{/if}
    {#if failed}<p role="alert">{at("console_ops_load_failed")}</p>
    {:else if loading}<p role="status">{at("loading")}</p>
    {:else if diagnostics && operations}
      {#if diagnostics.user_id === null}<p>{at("user_deleted")} · {at("services_history_title")}</p>
      {:else if diagnostics.user_id !== service.user_id}<p role="alert">
          {at("services_idempotency_owner_changed")}
        </p>{/if}
      <ServiceDiagnostics {at} data={diagnostics} />
      <ServiceOperationList
        {at}
        data={operations}
        {pending}
        readonly={readonly ||
          diagnostics.user_id === null ||
          diagnostics.user_id !== service.user_id}
        disabled={busy || storageFailed}
        onretry={(id) => void retry(id)}
        onpage={(value) => {
          page = value;
          void load();
        }}
      />
    {/if}
    <div class="admin-dialog-actions">
      <AdminButton disabled={busy} onclick={onclose}>{at("close")}</AdminButton>
    </div>
  </div>
</Dialog>

<style>
  .service-diagnostics {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  header {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 12px;
  }
  p {
    margin: 0;
    overflow-wrap: anywhere;
  }
  [role="alert"] {
    color: var(--danger);
  }
</style>
