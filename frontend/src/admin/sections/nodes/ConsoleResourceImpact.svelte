<script lang="ts">
  import { AdminEntityLink, AdminTable } from "$components/patterns/admin/index.js";
  import type { components } from "$lib/api/openapi.generated";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import { nodeRelatedUrl } from "$lib/admin/consoleNodesNavigation";
  let {
    impact,
    at,
    currentUrl,
    routePrefix = "",
    serviceHref,
    onOpenService,
    onOpenUserCard,
  }: {
    impact: components["schemas"]["ResourceImpactOut"];
    at: ConsoleNodesTranslate;
    currentUrl: string;
    routePrefix?: string;
    serviceHref: (serviceId: string) => string;
    onOpenService: (serviceId: string) => void;
    onOpenUserCard: (id: unknown) => void;
  } = $props();
  function follow(event: MouseEvent, open: () => void) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
      return;
    event.preventDefault();
    open();
  }
</script>

<div class="resource-impact">
  <p>
    {at("console_nodes_service_total")}: {impact.service_total} · {at(
      "console_nodes_customer_total"
    )}: {impact.customer_total}
  </p>
  <dl>
    <div>
      <dt>{at("console_nodes_groups")}</dt>
      <dd>{impact.group_ids.join(", ") || at("console_resource_none")}</dd>
    </div>
    <div>
      <dt>{at("console_nodes_node")}</dt>
      <dd>{impact.node_ids.join(", ") || at("console_resource_none")}</dd>
    </div>
    <div>
      <dt>{at("console_nodes_profile")}</dt>
      <dd>{impact.profile_ids.join(", ") || at("console_resource_none")}</dd>
    </div>
  </dl>
  {#if impact.services.length}
    <AdminTable>
      <thead
        ><tr
          ><th>{at("services_name")}</th><th>{at("console_customer")}</th><th
            >{at("console_nodes_groups")}</th
          ></tr
        ></thead
      >
      <tbody>
        {#each impact.services as service (service.service_id)}
          <tr>
            <td data-label={at("services_name")}>
              <a
                href={serviceHref(service.service_id)}
                data-resource-service-id={service.service_id}
                onclick={(event) => follow(event, () => onOpenService(service.service_id))}
              >
                <AdminEntityLink kind="code" label={service.name} idText={service.service_id} />
              </a>
            </td>
            <td data-label={at("console_customer")}>
              <a
                href={nodeRelatedUrl(currentUrl, { userId: service.customer_id }, routePrefix).href}
                onclick={(event) => follow(event, () => onOpenUserCard(service.customer_id))}
              >
                <AdminEntityLink label={String(service.customer_id)} />
              </a>
            </td>
            <td data-label={at("console_nodes_groups")}
              >{service.group_ids.join(", ") || at("console_resource_none")}</td
            >
          </tr>
        {/each}
      </tbody>
    </AdminTable>
  {:else}<p>{at("console_resource_no_services")}</p>{/if}
</div>

<style>
  .resource-impact {
    display: grid;
    gap: 12px;
    min-width: 0;
  }
  p,
  dl {
    margin: 0;
  }
  dl {
    display: grid;
    gap: 8px;
  }
  dt {
    color: var(--admin-muted);
  }
  dd {
    margin: 4px 0 0;
  }
  dd,
  td {
    overflow-wrap: anywhere;
  }
  a {
    color: var(--accent);
    text-decoration: none;
  }
  a:hover {
    text-decoration: underline;
  }
</style>
