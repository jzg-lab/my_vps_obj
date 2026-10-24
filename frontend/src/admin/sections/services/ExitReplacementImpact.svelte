<script lang="ts">
  import { AdminEntityLink, AdminTable } from "$components/patterns/admin";
  import { nodeRelatedUrl } from "$lib/admin/consoleNodesNavigation";
  import type { components } from "$lib/api/openapi.generated";
  import type { ServiceTranslate } from "$lib/admin/servicePlans";

  let {
    impacts,
    at,
    currentUrl = "",
    routePrefix = "",
  }: {
    impacts: components["schemas"]["ReplacementImpactOut"][];
    at: ServiceTranslate;
    currentUrl?: string;
    routePrefix?: string;
  } = $props();
</script>

<div class="replacement-impact">
  <AdminTable layout="fixed" aria-label={at("replacement_impact_entities")}>
    <thead
      ><tr>
        <th>{at("replacement_service")}</th><th>{at("console_customer")}</th>
        <th>{at("services_squads")}</th><th>{at("replacement_impact")}</th>
      </tr></thead
    >
    <tbody>
      {#each impacts as impact}
        {#snippet service()}
          <AdminEntityLink
            kind="code"
            label={impact.service_name ??
              at(
                impact.service_id ? "replacement_service_unnamed" : "replacement_service_external"
              )}
            idText={impact.service_id ?? ""}
          />
        {/snippet}
        <tr>
          <td data-label={at("replacement_service")}>
            {#if currentUrl && impact.service_id}<a
                href={nodeRelatedUrl(currentUrl, { serviceId: impact.service_id }, routePrefix)
                  .href}
                target="_blank"
                rel="noopener noreferrer"
                title={at("replacement_open_reference")}>{@render service()}</a
              >
            {:else}{@render service()}{/if}
          </td>
          <td data-label={at("console_customer")}>
            {#if impact.customer_id !== null && impact.customer_id !== undefined}
              {#if currentUrl}<a
                  href={nodeRelatedUrl(currentUrl, { userId: impact.customer_id }, routePrefix)
                    .href}
                  target="_blank"
                  rel="noopener noreferrer"
                  title={at("replacement_open_reference")}
                  ><AdminEntityLink label={String(impact.customer_id)} /></a
                >
              {:else}<AdminEntityLink label={String(impact.customer_id)} />{/if}
            {:else}<span>{at("replacement_customer_unknown")}</span>{/if}
          </td>
          <td data-label={at("services_squads")}
            >{impact.group_ids.join(", ") || at("console_unknown")}</td
          >
          <td data-label={at("replacement_impact")}
            >{at(
              impact.kind === "direct_authorization"
                ? "console_resource_direct"
                : impact.kind === "possible_reload"
                  ? "console_resource_reload"
                  : "console_unknown"
            )}</td
          >
        </tr>
      {:else}<tr><td colspan="4">{at("console_resource_no_services")}</td></tr>{/each}
    </tbody>
  </AdminTable>
</div>

<style>
  .replacement-impact {
    min-width: 0;
  }
  a {
    color: var(--accent);
    text-decoration: none;
  }
  a:hover {
    text-decoration: underline;
  }
  a:focus-visible {
    outline: 2px solid var(--admin-ring);
    outline-offset: 2px;
  }
  td {
    overflow-wrap: anywhere;
  }
  .replacement-impact :global(.admin-entity-link-label),
  .replacement-impact :global(.admin-entity-link-id) {
    white-space: normal;
    overflow: visible;
    overflow-wrap: anywhere;
  }
</style>
