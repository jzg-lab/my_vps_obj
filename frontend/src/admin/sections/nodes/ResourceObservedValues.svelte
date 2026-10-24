<script lang="ts">
  import { AdminTable } from "$components/patterns/admin";
  import type { components } from "$lib/api/openapi.generated";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  let {
    values,
    at,
  }: { values: components["schemas"]["ResourceValuesOut"]; at: ConsoleNodesTranslate } = $props();
  const fields = [
    ["id", "resource_ops_target_id"],
    ["name", "console_resource_name"],
    ["address", "console_catalog_endpoint"],
    ["port", "console_catalog_port"],
    ["profile_id", "console_nodes_profile"],
    ["inbound_ids", "console_nodes_inbounds"],
    ["node_ids", "console_nodes_node"],
    ["group_mode", "console_draft_group_mode"],
    ["group_ids", "console_nodes_groups"],
    ["is_disabled", "console_resource_disabled"],
    ["is_hidden", "console_draft_hidden"],
  ] as const;
  function display(value: string | string[] | number | boolean | null | undefined) {
    if (value === null || value === undefined) return at("console_unknown");
    if (typeof value === "boolean") return at(value ? "yes" : "no");
    if (Array.isArray(value)) return value.join(", ") || at("console_resource_none");
    if (value === "EXCLUDE") return at("console_draft_exclude");
    if (value === "ALLOW_ONLY") return at("console_draft_allow_only");
    return value;
  }
</script>

<AdminTable layout="fixed">
  <thead
    ><tr><th>{at("console_resource_field")}</th><th>{at("console_resource_current")}</th></tr
    ></thead
  >
  <tbody
    >{#each fields as [field, key]}<tr
        ><td data-label={at("console_resource_field")}>{at(key)}</td><td
          data-label={at("console_resource_current")}>{display(values[field])}</td
        ></tr
      >{/each}</tbody
  >
</AdminTable>

<style>
  td {
    overflow-wrap: anywhere;
  }
</style>
