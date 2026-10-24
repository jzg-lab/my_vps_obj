<script lang="ts">
  import { AdminBadge, AdminButton, AdminTable } from "$components/patterns/admin/index.js";
  import { Pencil, Trash2 } from "$components/ui/icons.js";
  import type { NodeAsset, NodeAssetAction } from "$lib/admin/consoleNodeAssets";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";

  let {
    assets,
    at,
    onAction,
  }: {
    assets: NodeAsset[];
    at: ConsoleNodesTranslate;
    onAction: (action: NodeAssetAction, trigger: HTMLElement) => void;
  } = $props();
</script>

<AdminTable layout="fixed" minWidth="760px" aria-label={at("console_node_assets_pending")}>
  <thead
    ><tr>
      <th>{at("console_node_assets_name")}</th>
      <th>{at("console_node_assets_address")}</th>
      <th>{at("console_node_assets_notes")}</th>
      <th>{at("actions")}</th>
    </tr></thead
  >
  <tbody
    >{#each assets as asset (asset.id)}<tr data-asset-id={asset.id}>
        <td data-label={at("console_node_assets_name")}>
          <div class="asset-name">
            <strong>{asset.name}</strong>
            <AdminBadge variant="muted">{at("console_node_assets_unmanaged")}</AdminBadge>
          </div>
        </td>
        <td data-label={at("console_node_assets_address")}><code>{asset.address}</code></td>
        <td data-label={at("console_node_assets_notes")}
          ><span class="asset-notes">{asset.notes || at("console_node_assets_no_notes")}</span></td
        >
        <td data-label={at("actions")}
          ><div class="asset-actions">
            <AdminButton
              size="icon"
              title={at("console_node_assets_edit")}
              aria-label={`${at("console_node_assets_edit")}: ${asset.name}`}
              onclick={(event) => {
                if (event.currentTarget instanceof HTMLElement)
                  onAction({ kind: "edit", asset }, event.currentTarget);
              }}><Pencil size={16} /></AdminButton
            >
            <AdminButton
              size="icon"
              variant="dangerSoft"
              title={at("console_node_assets_delete")}
              aria-label={`${at("console_node_assets_delete")}: ${asset.name}`}
              onclick={(event) => {
                if (event.currentTarget instanceof HTMLElement)
                  onAction({ kind: "delete", asset }, event.currentTarget);
              }}><Trash2 size={16} /></AdminButton
            >
          </div></td
        >
      </tr>{/each}</tbody
  >
</AdminTable>

<style>
  .asset-name {
    display: grid;
    justify-items: start;
    gap: 6px;
    min-width: 0;
  }
  .asset-notes {
    white-space: pre-wrap;
  }
  strong,
  code,
  .asset-notes {
    overflow-wrap: anywhere;
  }
  .asset-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
</style>
