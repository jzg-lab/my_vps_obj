<script lang="ts">
  import { onDestroy, untrack } from "svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import { Input } from "$components/ui/index.js";
  import { AdminButton, AdminField, AdminFormGrid } from "$components/patterns/admin/index.js";
  import type { ApiClient } from "$lib/webapp/publicApi";
  import type { ConsoleNode, ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import {
    clearConsoleNodeMetadata,
    consoleNodeMetadataDraftReady,
    consoleNodeMetadataErrorKey,
    saveConsoleNodeMetadata,
    type ConsoleNodeMetadata,
    type ConsoleNodeMetadataDraft,
  } from "$lib/admin/consoleNodeMetadata";

  let {
    api,
    at,
    node,
    onclose,
    onsaved,
  }: {
    api: ApiClient["api"];
    at: ConsoleNodesTranslate;
    node: ConsoleNode;
    onclose: () => void;
    onsaved: (metadata: ConsoleNodeMetadata | null) => void;
  } = $props();
  const initial = untrack(() => node);
  let draft = $state<ConsoleNodeMetadataDraft>({
    display_name: initial.display_name ?? "",
    region: initial.region ?? "",
    provider: initial.provider ?? "",
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
  async function submit(clear = false) {
    if (busy || (!clear && !consoleNodeMetadataDraftReady(draft))) return;
    busy = true;
    error = "";
    try {
      if (clear) {
        await clearConsoleNodeMetadata(api, node.id);
        if (!disposed) onsaved(null);
      } else {
        const saved = await saveConsoleNodeMetadata(api, node.id, draft);
        if (!disposed) onsaved(saved);
      }
    } catch (failure) {
      if (!disposed) error = consoleNodeMetadataErrorKey(failure);
    } finally {
      if (!disposed) busy = false;
    }
  }
</script>

<Dialog
  open
  portal
  class="admin-dialog"
  title={at("console_nodes_metadata_title")}
  description={at("console_nodes_metadata_scope")}
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
    <p>{at("console_nodes_panel_name")}: {node.name}</p>
    <AdminFormGrid columns={1}>
      <AdminField
        label={at("console_nodes_display_name")}
        hint={at("console_nodes_display_name_hint")}
      >
        <Input
          aria-label={at("console_nodes_display_name")}
          bind:value={draft.display_name}
          maxlength={120}
          disabled={busy}
        />
      </AdminField>
      <AdminField label={at("console_nodes_region")} hint={at("console_nodes_local_value_hint")}>
        <Input
          aria-label={at("console_nodes_region")}
          bind:value={draft.region}
          maxlength={120}
          disabled={busy}
        />
      </AdminField>
      <AdminField label={at("console_nodes_provider")} hint={at("console_nodes_local_value_hint")}>
        <Input
          aria-label={at("console_nodes_provider")}
          bind:value={draft.provider}
          maxlength={120}
          disabled={busy}
        />
      </AdminField>
    </AdminFormGrid>
    {#if error}<p role="alert">{at(error)}</p>{/if}
    <div class="admin-dialog-actions">
      <AdminButton disabled={busy} onclick={close}>{at("cancel")}</AdminButton>
      {#if node.display_name || node.region || node.provider}<AdminButton
          disabled={busy}
          onclick={() => void submit(true)}>{at("console_nodes_metadata_clear")}</AdminButton
        >{/if}
      <AdminButton
        type="submit"
        variant="primary"
        disabled={busy || !consoleNodeMetadataDraftReady(draft)}
      >
        {at(busy ? "console_nodes_metadata_saving" : "console_nodes_metadata_save")}
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
