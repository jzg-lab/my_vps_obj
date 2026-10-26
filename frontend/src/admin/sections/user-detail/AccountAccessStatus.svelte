<script lang="ts">
  import { onDestroy } from "svelte";
  import { getAdminApi } from "$lib/admin/context";
  import { AdminBadge, AdminButton, AdminSectionHeader } from "$components/patterns/admin/index.js";
  import { builtApiPath, unwrap } from "$lib/webapp/publicApi";
  import type { components } from "$lib/api/openapi.generated";
  import type { TranslateFn, DateFormatter } from "./userDetailTypes";

  let {
    userId,
    banned,
    actionBusy,
    at,
    fmtDate,
  }: {
    userId: number;
    banned: boolean;
    actionBusy: boolean;
    at: TranslateFn;
    fmtDate: DateFormatter;
  } = $props();
  const api = getAdminApi();
  let status = $state<components["schemas"]["AccountAccessSyncOut"] | null>(null);
  let busy = $state(false);
  let failed = $state(false);
  let request = 0;
  let controller: AbortController | null = null;

  async function load(owner: number, retry = false) {
    const current = ++request;
    controller?.abort();
    controller = new AbortController();
    busy = true;
    failed = false;
    try {
      const result = unwrap(
        await api(
          builtApiPath<"/api/admin/users/{user_id}/access-sync">(
            `/admin/users/${owner}/access-sync`
          ),
          { method: retry ? "POST" : "GET", signal: controller.signal }
        )
      );
      if (current === request) status = result.access_sync;
    } catch {
      if (current === request) failed = true;
    } finally {
      if (current === request) busy = false;
    }
  }
  $effect(() => {
    void banned;
    if (!actionBusy && userId) void load(userId);
  });
  $effect(() => {
    if (!status?.pending || busy || actionBusy || failed) return;
    const timer = setTimeout(() => void load(userId), 15000);
    return () => clearTimeout(timer);
  });
  onDestroy(() => {
    request++;
    controller?.abort();
  });
</script>

<section class="access-status" aria-label={at("account_access_title")} aria-busy={busy}>
  <AdminSectionHeader title={at("account_access_title")} />
  <p>{at("account_access_scope")}</p>
  {#if failed}<p role="alert">{at("account_access_load_failed")}</p>
  {:else if status}
    <AdminBadge wrap variant={status.pending ? "warning" : "muted"}>
      {at(
        status.pending
          ? "account_access_pending"
          : status.attempted_at
            ? "account_access_confirmed"
            : "account_access_not_requested"
      )}
    </AdminBadge>
    {#if status.pending}<p role="status">{at("account_access_saved_pending")}</p>{/if}
    {#if status.attempted_at}<small
        >{at("account_access_last_attempt")}: {fmtDate(status.attempted_at)}</small
      >{/if}
  {/if}
  <div class="access-actions">
    <AdminButton size="sm" disabled={busy || actionBusy} onclick={() => load(userId)}
      >{at("refresh")}</AdminButton
    >
    {#if status?.pending}<AdminButton
        size="sm"
        disabled={busy || actionBusy}
        onclick={() => load(userId, true)}>{at("account_access_retry")}</AdminButton
      >{/if}
  </div>
</section>

<style>
  .access-status {
    display: grid;
    gap: 10px;
  }
  .access-actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  p {
    margin: 0;
  }
  small {
    color: var(--admin-muted);
  }
</style>
