<script lang="ts">
  import { onDestroy, untrack } from "svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import { Input, Textarea } from "$components/ui/index.js";
  import { AdminButton, AdminField, AdminFormGrid } from "$components/patterns/admin/index.js";
  import type { ApiClient } from "$lib/webapp/publicApi";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import {
    deleteNodeAsset,
    saveNodeAsset,
    nodeAssetDraftReady,
    nodeAssetErrorKey,
    type NodeAssetAction,
    type NodeAssetBody,
  } from "$lib/admin/consoleNodeAssets";

  let {
    api,
    at,
    action,
    onclose,
    onsaved,
  }: {
    api: ApiClient["api"];
    at: ConsoleNodesTranslate;
    action: NodeAssetAction;
    onclose: () => void;
    onsaved: (kind: NodeAssetAction["kind"]) => void;
  } = $props();
  const initial = untrack(() => (action.kind === "create" ? null : action.asset));
  let draft = $state<NodeAssetBody>({
    name: initial?.name ?? "",
    address: initial?.address ?? "",
    notes: initial?.notes ?? "",
  });
  let busy = $state(false);
  let error = $state("");
  let disposed = false;
  onDestroy(() => {
    disposed = true;
  });
  function close() {
    if (!busy) onclose();
  }
  async function submit() {
    if (busy || (action.kind !== "delete" && !nodeAssetDraftReady(draft))) return;
    busy = true;
    error = "";
    try {
      if (action.kind === "delete") await deleteNodeAsset(api, action.asset.id);
      else await saveNodeAsset(api, action.kind === "edit" ? action.asset.id : null, draft);
      if (!disposed) onsaved(action.kind);
    } catch (failure) {
      if (!disposed) error = nodeAssetErrorKey(failure);
    } finally {
      if (!disposed) busy = false;
    }
  }
</script>

<Dialog
  open
  portal
  class="admin-dialog"
  title={at(
    action.kind === "delete"
      ? "console_node_assets_delete_title"
      : action.kind === "edit"
        ? "console_node_assets_edit"
        : "console_node_assets_add"
  )}
  description={at(
    action.kind === "delete" ? "console_node_assets_delete_hint" : "console_node_assets_scope"
  )}
  closeLabel={at("cancel")}
  showCloseButton={!busy}
  onclose={close}
>
  <form
    onsubmit={(event) => {
      event.preventDefault();
      void submit();
    }}
    aria-busy={busy}
  >
    {#if action.kind === "delete"}
      <p><strong>{action.asset.name}</strong></p>
      <p><code>{action.asset.address}</code></p>
    {:else}
      <AdminFormGrid columns={1}>
        <AdminField
          label={at("console_node_assets_name")}
          hint={at("console_node_assets_name_hint")}
        >
          <Input
            aria-label={at("console_node_assets_name")}
            bind:value={draft.name}
            required
            maxlength={120}
            disabled={busy}
          />
        </AdminField>
        <AdminField
          label={at("console_node_assets_address")}
          hint={at("console_node_assets_address_hint")}
        >
          <Input
            aria-label={at("console_node_assets_address")}
            bind:value={draft.address}
            required
            maxlength={253}
            disabled={busy}
          />
        </AdminField>
        <AdminField
          label={at("console_node_assets_notes")}
          hint={at("console_node_assets_notes_hint")}
        >
          <Textarea
            ariaLabel={at("console_node_assets_notes")}
            bind:value={draft.notes}
            maxlength={2000}
            rows={4}
            disabled={busy}
          />
        </AdminField>
      </AdminFormGrid>
    {/if}
    {#if error}<p role="alert">{at(error)}</p>{/if}
    <div class="admin-dialog-actions">
      <AdminButton disabled={busy} onclick={close}>{at("cancel")}</AdminButton>
      <AdminButton
        type="submit"
        variant={action.kind === "delete" ? "danger" : "primary"}
        disabled={busy || (action.kind !== "delete" && !nodeAssetDraftReady(draft))}
      >
        {at(
          busy
            ? "console_node_assets_saving"
            : action.kind === "delete"
              ? "console_node_assets_delete"
              : "console_node_assets_save"
        )}
      </AdminButton>
    </div>
  </form>
</Dialog>

<style>
  form {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  p {
    margin: 0;
    overflow-wrap: anywhere;
  }
  .admin-dialog-actions {
    flex-wrap: wrap;
  }
</style>
