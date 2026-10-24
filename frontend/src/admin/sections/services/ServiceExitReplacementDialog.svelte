<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import { Textarea, Checkbox } from "$components/ui";
  import { AdminButton, AdminField, AdminSelect } from "$components/patterns/admin";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi";
  import type { DedicatedExit, ServiceTranslate, UserService } from "$lib/admin/servicePlans";
  import { consoleServiceErrorKey } from "$lib/admin/consoleServiceOperations";
  import {
    replacementActions,
    replacementAvailable,
    replacementLabel,
    replacementSnapshot,
    replacementWrite,
    startReplacementWrite,
    readReplacement,
    postReplacement,
    type ReplacementState,
    type ReplacementAction,
    type ReplacementFields,
    type ReplacementWrite,
  } from "$lib/admin/exitReplacement";
  import {
    readPendingReplacement,
    savePendingReplacement,
    clearPendingReplacement,
    canReplayReplacement,
    replacementRejected,
    type PendingReplacement,
  } from "$lib/admin/exitReplacementPending";
  import ExitReplacementStatus from "./ExitReplacementStatus.svelte";
  import ExitReplacementForm from "./ExitReplacementForm.svelte";

  let {
    api,
    at,
    service,
    readonly = false,
    routePrefix = "",
    onclose,
  }: {
    api: ApiClient["api"];
    at: ServiceTranslate;
    service: UserService;
    readonly?: boolean;
    routePrefix?: string;
    onclose: () => void;
  } = $props();
  let data = $state<ReplacementState | null>(null);
  let currentUrl = $state("");
  let owner = $state<number | null>(null);
  let resourcePool = $state<string | null>(null);
  let exits = $state<DedicatedExit[]>([]);
  let candidate = $state("");
  let draftMode = $state(false);
  let operationId = $state("");
  let action = $state<ReplacementAction | "">("");
  let reason = $state("");
  let impactConfirmed = $state(false);
  let loading = $state(true);
  let failed = $state(false);
  let inventoryFailed = $state(false);
  let busy = $state(false);
  let storageFailed = $state(false);
  let error = $state("");
  let accepted = $state(false);
  let pending = $state<PendingReplacement | null>(null);
  let request = 0;
  let alive = true;
  let controller: AbortController | null = null;
  const editable = $derived(!readonly && owner !== null && owner === service.user_id);
  const frozen = $derived(busy || loading || failed || storageFailed || !editable);
  const snapshotKey = $derived(data ? replacementSnapshot(data) : "");
  const allowed = $derived(
    data?.replacement
      ? replacementActions.filter((item) => data?.replacement?.allowed_actions.includes(item))
      : []
  );
  const candidates = $derived(
    exits.filter(
      (item) =>
        resourcePool !== null &&
        item.resource_pool === resourcePool &&
        item.enabled &&
        !item.service_id &&
        !item.hold_order_id &&
        !item.hold_service_id &&
        item.id !== data?.draft?.old_exit.id
    )
  );
  const replayable = $derived(data && pending ? canReplayReplacement(pending, data) : false);
  const changedPending = $derived(
    data && pending ? pending.snapshot !== replacementSnapshot(data) : false
  );

  function query() {
    return draftMode && candidate
      ? { candidate_exit_id: candidate }
      : operationId
        ? { operation_id: operationId }
        : {};
  }
  async function snapshot(signal?: AbortSignal): Promise<ReplacementState> {
    const detail = unwrap(
      await api(
        builtApiPath<"/api/admin/console/services/{service_id}">(
          `/admin/console/services/${service.id}`
        ),
        { signal }
      )
    );
    if (alive) {
      owner = detail.service.user_id;
      resourcePool = detail.terms.resource_pool ?? null;
    }
    return readReplacement(api, service.id, query(), signal);
  }
  async function load() {
    const token = ++request;
    controller?.abort();
    controller = new AbortController();
    loading = true;
    failed = false;
    try {
      const next = await snapshot(controller.signal);
      if (!alive || token !== request) return;
      if (data && replacementSnapshot(next) !== replacementSnapshot(data)) impactConfirmed = false;
      data = next;
      if (next.replacement) operationId = next.replacement.operation.id;
      if (action && !next.replacement?.allowed_actions.includes(action)) action = "";
    } catch {
      if (alive && token === request) failed = true;
    } finally {
      if (alive && token === request) loading = false;
    }
  }
  async function loadExits() {
    inventoryFailed = false;
    try {
      const rows: DedicatedExit[] = [];
      let total = 1;
      while (rows.length < total) {
        const result = unwrap(
          await api(
            builtApiPath<"/api/admin/dedicated-exits">(
              `/admin/dedicated-exits?limit=200&offset=${rows.length}`
            )
          )
        );
        if (!alive) return;
        if (!result.exits.length && rows.length < result.total)
          throw new Error("incomplete inventory");
        rows.push(...result.exits);
        total = result.total;
      }
      exits = rows;
    } catch {
      if (alive) inventoryFailed = true;
    }
  }
  async function selectCandidate(value: string) {
    if (frozen || pending) return;
    candidate = value;
    draftMode = true;
    operationId = "";
    impactConfirmed = false;
    action = "";
    data = null;
    await load();
  }
  async function submit(write: ReplacementWrite, replay = false) {
    if (frozen || !data || owner === null || (!replay && pending)) return;
    busy = true;
    error = "";
    accepted = false;
    const displayed = replacementSnapshot(data);
    try {
      const fresh = await snapshot();
      if (!alive) return;
      data = fresh;
      if (owner !== service.user_id || owner === null) throw { error: "idempotency_owner_changed" };
      if (
        displayed !== replacementSnapshot(fresh) ||
        (replay && (!pending || !canReplayReplacement(pending, fresh)))
      ) {
        impactConfirmed = false;
        throw { error: "exit_replacement_scope_changed" };
      }
      if (write.action !== "start" && !replacementAvailable(fresh, write.action))
        throw { error: "operation_not_retryable" };
      if (write.action === "start" && fresh.draft?.allowed_to_start !== true)
        throw { error: "exit_replacement_not_available" };
      const saved =
        replay && pending
          ? pending
          : { serviceId: service.id, userId: owner, snapshot: displayed, write };
      savePendingReplacement(sessionStorage, saved);
      pending = saved;
      await postReplacement(api, service.id, saved.write);
      clearPendingReplacement(sessionStorage, service.id);
      pending = null;
      accepted = true;
      action = "";
      draftMode = false;
      if (write.action === "start") operationId = "";
    } catch (failure) {
      if (alive) error = consoleServiceErrorKey(failure);
      if (pending && replacementRejected(failure)) {
        clearPendingReplacement(sessionStorage, service.id);
        pending = null;
      }
    } finally {
      // Both lost replies and explicit rejections require a fresh authoritative observation.
      if (alive) {
        await load();
        busy = false;
      }
    }
  }
  function start(event: SubmitEvent) {
    event.preventDefault();
    if (frozen || pending || !impactConfirmed || !data || owner === null) return;
    try {
      void submit(startReplacementWrite(data, owner, reason));
    } catch (failure) {
      error = consoleServiceErrorKey(failure);
    }
  }
  function evidence(fields: ReplacementFields, exitId: string) {
    if (frozen || pending || !data || !action || owner === null) return;
    try {
      void submit(replacementWrite(data, owner, action, fields, exitId));
    } catch (failure) {
      error = consoleServiceErrorKey(failure);
    }
  }
  async function useLatest() {
    if (frozen || !pending || !changedPending) return;
    clearPendingReplacement(sessionStorage, service.id);
    pending = null;
    action = "";
    impactConfirmed = false;
    draftMode = false;
    operationId = "";
    error = "";
    await load();
  }
  onMount(() => {
    currentUrl = window.location.href;
    try {
      if (service.user_id !== null)
        pending = readPendingReplacement(sessionStorage, service.id, service.user_id);
      if (pending?.write.action === "start") {
        candidate = pending.write.body.new_exit_id;
        draftMode = true;
        reason = pending.write.body.reason;
      } else if (pending) {
        const write = pending.write;
        operationId =
          write.action === "retry"
            ? write.operationId
            : "operation_id" in write.body
              ? write.body.operation_id
              : "replacement_operation_id" in write.body
                ? write.body.replacement_operation_id
                : "";
      }
    } catch {
      storageFailed = true;
    }
    void load();
    if (!readonly && service.user_id !== null) void loadExits();
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
  title={at("replacement_title")}
  description={at("replacement_boundary")}
  closeLabel={at("close")}
  focusKey={`${loading}:${busy}:${action}:${snapshotKey}`}
  onclose={() => {
    if (!busy) onclose();
  }}
  class="admin-dialog"
>
  <div class="exit-replacement" aria-busy={busy || loading}>
    <header>
      <p><strong>{service.name}</strong><br />{service.id}</p>
      <AdminButton
        disabled={busy || loading}
        onclick={() => {
          void load();
          if (editable) void loadExits();
        }}>{at("refresh")}</AdminButton
      >
    </header>
    {#if error}<p role="alert">{at(error)}</p>{/if}
    {#if accepted}<p role="status">{at("console_ops_accepted")}</p>{/if}
    {#if storageFailed}<p role="alert">{at("services_storage_failed")}</p>{/if}
    {#if failed}<p role="alert">{at("console_ops_load_failed")}</p>{/if}
    {#if loading}<p role="status">{at("loading")}</p>{/if}
    {#if data}<ExitReplacementStatus {at} {data} {currentUrl} {routePrefix} />{/if}
    {#if !loading && (readonly || owner === null)}<p>
        {at("services_history_hint")}
      </p>{:else if !loading && owner !== service.user_id}<p role="alert">
        {at("services_idempotency_owner_changed")}
      </p>{/if}
    {#if pending}
      <p role="alert">{at("replacement_pending_request")}</p>
      {#if changedPending}<p>{at("replacement_changed")}</p>
        <AdminButton disabled={frozen} onclick={useLatest}
          >{at("replacement_use_latest")}</AdminButton
        >
      {:else if replayable}<AdminButton
          disabled={frozen}
          onclick={() => {
            if (pending) void submit(pending.write, true);
          }}>{at("replacement_replay")}</AdminButton
        >{/if}
    {/if}
    {#if editable && !storageFailed}
      {#if !data?.replacement || draftMode}
        {#if inventoryFailed}<p role="alert">{at("services_load_failed")}</p>{/if}
        <AdminField label={at("replacement_candidate")}
          ><AdminSelect
            wrapLabels
            value={candidate}
            ariaLabel={at("replacement_candidate")}
            disabled={frozen || inventoryFailed || !!pending}
            onValueChange={(value) => void selectCandidate(value)}
            items={candidates.map((item) => ({
              value: item.id,
              label: `${item.label} · ${item.ip_address} · ${item.resource_pool}`,
            }))}
          /></AdminField
        >
        {#if data?.draft}
          <form class="replacement-start" onsubmit={start}>
            <AdminField label={at("replacement_reason")}
              ><Textarea
                required
                minlength={3}
                maxlength={1000}
                bind:value={reason}
                disabled={frozen || !!pending}
              /></AdminField
            >
            <label
              ><Checkbox
                bind:checked={impactConfirmed}
                disabled={frozen || !!pending || !data.draft.allowed_to_start}
                ariaLabel={at("replacement_impact_confirm")}
              /><span>{at("replacement_impact_confirm")}</span></label
            >
            <AdminButton
              type="submit"
              variant="primary"
              disabled={frozen ||
                !!pending ||
                !data.draft.allowed_to_start ||
                !impactConfirmed ||
                reason.trim().length < 3}>{at("replacement_start")}</AdminButton
            >
          </form>
        {/if}
      {:else}
        {#if allowed.length}<AdminField label={at("services_exit_action")}
            ><AdminSelect
              wrapLabels
              value={action}
              ariaLabel={at("services_exit_action")}
              disabled={frozen || !!pending}
              items={allowed.map((item) => ({
                value: item,
                label: at(replacementLabel("action", item)),
                disabled: !replacementAvailable(data!, item),
              }))}
              onValueChange={(value) => {
                action = allowed.find((item) => item === value) ?? "";
              }}
            /></AdminField
          >{/if}
        {#if action && allowed.includes(action) && owner !== null}{#key `${snapshotKey}:${action}`}<ExitReplacementForm
              {at}
              {data}
              {action}
              userId={owner}
              disabled={frozen || !!pending}
              onsubmit={evidence}
            />{/key}{/if}
        {#if !data.replacement.gate_active && !data.replacement.progress.pending_action}<AdminButton
            disabled={frozen || !!pending}
            onclick={() => {
              draftMode = true;
              candidate = "";
              action = "";
              impactConfirmed = false;
            }}>{at("replacement_new")}</AdminButton
          >{/if}
      {/if}
    {/if}
  </div>
</Dialog>

<style>
  .exit-replacement,
  form {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  header,
  label {
    display: flex;
    align-items: start;
    gap: 12px;
  }
  header {
    justify-content: space-between;
  }
  p {
    margin: 0;
  }
  p,
  span {
    overflow-wrap: anywhere;
  }
</style>
