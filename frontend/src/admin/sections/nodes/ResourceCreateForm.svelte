<script lang="ts">
  import { Input, Checkbox } from "$components/ui";
  import { AdminButton, AdminField, AdminSelect } from "$components/patterns/admin";
  import type { ResourceCatalog } from "$lib/admin/consoleResources";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import { validResourceChange } from "$lib/admin/resourceIntent";
  import type { ResourceChange } from "./resourcePreview";
  let {
    kind,
    catalog,
    at,
    onReview,
  }: {
    kind: "node" | "group" | "host";
    catalog: ResourceCatalog;
    at: ConsoleNodesTranslate;
    onReview: (change: ResourceChange) => void;
  } = $props();
  let name = $state("");
  let address = $state("");
  let port = $state("");
  let profileId = $state("");
  let inboundIds = $state<string[]>([]);
  let inboundId = $state("");
  let nodeIds = $state<string[]>([]);
  let groupIds = $state<string[]>([]);
  let groupMode = $state<"EXCLUDE" | "ALLOW_ONLY">("EXCLUDE");
  let disabled = $state(true);
  let hidden = $state(false);
  const inbounds = $derived(
    catalog.profiles.find((profile) => profile.id === profileId)?.inbounds ?? []
  );
  function toggle(ids: string[], id: string, checked: boolean) {
    return checked ? [...new Set([...ids, id])].sort() : ids.filter((item) => item !== id);
  }
  function draft(): ResourceChange {
    if (kind === "group") return { operation: "group_create", name, inbound_ids: [...inboundIds] };
    if (kind === "node")
      return {
        operation: "node_create",
        name,
        address,
        port: /^\d+$/.test(port) ? Number(port) : NaN,
        profile_id: profileId,
        inbound_ids: [...inboundIds],
      };
    return {
      operation: "host_create",
      name,
      address,
      port: /^\d+$/.test(port) ? Number(port) : NaN,
      profile_id: profileId,
      inbound_id: inboundId,
      node_ids: [...nodeIds],
      group_ids: [...groupIds],
      group_mode: groupMode,
      is_disabled: disabled,
      is_hidden: hidden,
    };
  }
  const valid = $derived(validResourceChange(draft()));
</script>

<form
  class="resource-create-form"
  onsubmit={(event) => {
    event.preventDefault();
    const change = draft();
    if (validResourceChange(change)) onReview(change);
  }}
>
  <AdminField label={at("console_resource_name")}
    ><Input
      bind:value={name}
      aria-label={at("console_resource_name")}
      required
      minlength={kind === "node" ? 3 : kind === "group" ? 2 : 1}
      maxlength={kind === "host" ? 100 : 30}
      pattern={kind === "group" ? "[A-Za-z0-9_\\s-]+" : undefined}
    /></AdminField
  >
  {#if kind === "group"}<p>{at("resource_ops_group_name_rule")}</p>
  {:else}
    <AdminField label={at("console_nodes_address")}
      ><Input
        bind:value={address}
        aria-label={at("console_nodes_address")}
        required
        maxlength={253}
      /></AdminField
    >
    <AdminField
      label={at(kind === "node" ? "resource_ops_management_port" : "console_catalog_port")}
      ><Input
        bind:value={port}
        aria-label={at(kind === "node" ? "resource_ops_management_port" : "console_catalog_port")}
        required
        inputmode="numeric"
        pattern={"[0-9]+"}
        maxlength={5}
      /></AdminField
    >
    <AdminField label={at("console_nodes_profile")}
      ><AdminSelect
        wrapLabels
        value={profileId}
        ariaLabel={at("console_nodes_profile")}
        items={catalog.profiles.map((profile) => ({
          value: profile.id,
          label: `${profile.name} · ${profile.id}`,
        }))}
        onValueChange={(value) => {
          profileId = value;
          inboundIds = [];
          inboundId = "";
        }}
      /></AdminField
    >
  {/if}
  {#if kind === "host"}
    <AdminField label={at("console_nodes_inbounds")}
      ><AdminSelect
        wrapLabels
        value={inboundId}
        ariaLabel={at("console_nodes_inbounds")}
        items={inbounds.map((item) => ({ value: item.id, label: `${item.tag} · ${item.id}` }))}
        onValueChange={(value) => {
          inboundId = value;
        }}
      /></AdminField
    >
    <fieldset>
      <legend>{at("console_nodes_node")}</legend>{#each catalog.nodes as node}{#if node.id}<label
            ><Checkbox
              checked={nodeIds.includes(node.id)}
              ariaLabel={`${node.name} · ${node.id}`}
              onCheckedChange={(value) => {
                if (node.id) nodeIds = toggle(nodeIds, node.id, value);
              }}
            /><span>{node.name} · {node.id}</span></label
          >{/if}{/each}
    </fieldset>
    <AdminField label={at("console_draft_group_mode")}
      ><AdminSelect
        wrapLabels
        value={groupMode}
        ariaLabel={at("console_draft_group_mode")}
        items={[
          { value: "EXCLUDE", label: at("console_draft_exclude") },
          { value: "ALLOW_ONLY", label: at("console_draft_allow_only") },
        ]}
        onValueChange={(value) => {
          if (value === "EXCLUDE" || value === "ALLOW_ONLY") groupMode = value;
        }}
      /></AdminField
    >
    <fieldset>
      <legend>{at("console_nodes_groups")}</legend
      >{#each catalog.groups as group}{#if group.id}<label
            ><Checkbox
              checked={groupIds.includes(group.id)}
              ariaLabel={`${group.name} · ${group.id}`}
              onCheckedChange={(value) => {
                if (group.id) groupIds = toggle(groupIds, group.id, value);
              }}
            /><span>{group.name} · {group.id}</span></label
          >{/if}{/each}
    </fieldset>
    <label
      ><Checkbox bind:checked={disabled} ariaLabel={at("console_resource_disabled")} /><span
        >{at("console_resource_disabled")}</span
      ></label
    >
    <label
      ><Checkbox bind:checked={hidden} ariaLabel={at("console_draft_hidden")} /><span
        >{at("console_draft_hidden")}</span
      ></label
    >
  {:else}
    <fieldset>
      <legend>{at("console_nodes_inbounds")}</legend>
      {#each kind === "group" ? catalog.profiles : catalog.profiles.filter((profile) => profile.id === profileId) as profile}<p
        >
          {profile.name} · {profile.id}
        </p>
        {#each profile.inbounds as inbound}<label
            ><Checkbox
              checked={inboundIds.includes(inbound.id)}
              ariaLabel={`${inbound.tag} · ${inbound.id}`}
              onCheckedChange={(value) => {
                inboundIds = toggle(inboundIds, inbound.id, value);
              }}
            /><span>{inbound.tag} · {inbound.id}</span></label
          >{/each}
      {/each}
    </fieldset>
  {/if}
  {#if !valid}<p role="status">{at("resource_ops_complete_fields")}</p>{/if}
  <div>
    <AdminButton type="submit" disabled={!valid}>{at("console_resource_preview")}</AdminButton>
  </div>
</form>

<style>
  .resource-create-form,
  fieldset {
    display: grid;
    gap: 12px;
    min-width: 0;
  }
  fieldset {
    margin: 0;
    padding: 12px;
    border: 1px solid var(--admin-border);
  }
  p {
    margin: 0;
  }
  p,
  span,
  legend {
    overflow-wrap: anywhere;
  }
  label {
    display: flex;
    align-items: start;
    gap: 8px;
  }
</style>
