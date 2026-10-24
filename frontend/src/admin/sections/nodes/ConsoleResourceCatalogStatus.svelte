<script lang="ts">
  import { AdminBadge } from "$components/patterns/admin";
  import type { ResourceCatalog } from "$lib/admin/consoleResources";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import { serviceDate } from "$lib/webapp/independentServices";
  import { resourceBlockerText } from "./resourcePreviewMessages";
  let { catalog, at }: { catalog: ResourceCatalog; at: ConsoleNodesTranslate } = $props();
  const sourceKeys: Record<string, string> = {
    metadata: "console_resource_source_metadata",
    nodes: "console_nodes_source_nodes",
    hosts: "console_nodes_source_hosts",
    groups: "console_resource_source_groups",
    profiles: "console_resource_source_profiles",
    services: "console_resource_source_services",
    authorizations: "console_resource_source_authorizations",
  };
  const availabilityKeys: Record<string, string> = {
    available: "console_nodes_availability_available",
    unavailable: "console_nodes_availability_unavailable",
    unsupported: "console_nodes_availability_unsupported",
    invalid: "console_resource_source_invalid",
  };
</script>

<div class="catalog-status">
  <div>
    <AdminBadge variant={catalog.coverage === "complete" ? "muted" : "warning"}
      >{at(
        catalog.coverage === "complete"
          ? "console_nodes_coverage_complete"
          : "console_nodes_coverage_partial"
      )}</AdminBadge
    >
  </div>
  <p>{at("console_resource_observed_at")}: {serviceDate(catalog.observed_at)}</p>
  <p>
    {at("console_resource_reviewed_version")}: {catalog.reviewed_panel_version} · {at(
      "console_resource_observed_version"
    )}: {catalog.observed_panel_version ?? at("console_unknown")}
  </p>
  {#if catalog.blockers.length}<ul role="alert">
      {#each catalog.blockers as blocker}<li>{resourceBlockerText(blocker, at)}</li>{/each}
    </ul>{/if}
  <ul>
    {#each catalog.sources as source}<li>
        {at(
          Object.hasOwn(sourceKeys, source.source) ? sourceKeys[source.source] : "console_unknown"
        )}:
        {at(
          Object.hasOwn(availabilityKeys, source.availability)
            ? availabilityKeys[source.availability]
            : "console_unknown"
        )}
        · {serviceDate(source.observed_at)}
      </li>{/each}
  </ul>
</div>

<style>
  .catalog-status {
    display: grid;
    gap: 8px;
    min-width: 0;
    overflow-wrap: anywhere;
  }
  p,
  ul {
    margin: 0;
  }
  ul {
    padding-left: 20px;
  }
</style>
