<script lang="ts">
  import { AdminBadge, AdminEntityLink, AdminTable } from "$components/patterns/admin/index.js";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import { nodeRelatedUrl } from "$lib/admin/consoleNodesNavigation";
  import { serviceDate } from "$lib/webapp/independentServices";
  import type { ResourcePreview } from "./resourcePreview";
  import { resourceBlockerText, resourceRecoveryKey } from "./resourcePreviewMessages";
  import ConsoleResourceImpact from "./ConsoleResourceImpact.svelte";
  let {
    preview,
    at,
    currentUrl,
    routePrefix = "",
    serviceHref,
    onOpenService,
    onOpenUserCard,
  }: {
    preview: ResourcePreview;
    at: ConsoleNodesTranslate;
    currentUrl: string;
    routePrefix?: string;
    serviceHref: (serviceId: string) => string;
    onOpenService: (serviceId: string) => void;
    onOpenUserCard: (id: unknown) => void;
  } = $props();
  const nodeFields = [
    ["is_disabled", "console_resource_disabled"],
    ["profile_id", "console_nodes_profile"],
    ["inbound_ids", "console_nodes_inbounds"],
    ["force_restart", "console_resource_force_restart"],
  ] as const;
  const fields = $derived(
    preview.change.operation === "group_inbounds" || preview.change.operation === "group_create"
      ? ([
          ["name", "console_resource_name"],
          ["inbound_ids", "console_nodes_inbounds"],
        ] as const)
      : preview.change.operation === "host_update" || preview.change.operation === "host_create"
        ? ([
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
          ] as const)
        : preview.change.operation === "node_create"
          ? ([
              ["name", "console_resource_name"],
              ["address", "console_nodes_address"],
              ["port", "resource_ops_management_port"],
              ...nodeFields,
            ] as const)
          : nodeFields
  );
  const customers = $derived([...new Set(preview.affected_customer_ids)]);
  const serviceIds = $derived([...new Set(preview.affected_service_ids)]);
  function display(value: string | string[] | number | boolean | null | undefined) {
    if (value === null || value === undefined) return at("console_unknown");
    if (typeof value === "boolean") return at(value ? "yes" : "no");
    if (Array.isArray(value)) return value.join(", ") || at("console_resource_none");
    if (value === "EXCLUDE") return at("console_draft_exclude");
    if (value === "ALLOW_ONLY") return at("console_draft_allow_only");
    return value;
  }
  function follow(event: MouseEvent, open: () => void) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
      return;
    event.preventDefault();
    open();
  }
</script>

<div class="resource-preview-result">
  <p>{at("console_resource_scope")}</p>
  <div role="status">
    <AdminBadge variant={preview.coverage === "complete" ? "muted" : "warning"}
      >{at(`console_nodes_coverage_${preview.coverage}`)}</AdminBadge
    >
    <p>
      {at(
        preview.remote_authorization_verified
          ? "console_resource_authorizations_verified"
          : "console_resource_authorizations_unverified"
      )}
    </p>
    {#if preview.coverage !== "complete"}<p>{at("console_nodes_incomplete_relations")}</p>{/if}
  </div>
  {#if preview.blockers.length}<div role="alert">
      <h4>{at("console_resource_blockers")}</h4>
      <ul>
        {#each preview.blockers as blocker}<li>
            {resourceBlockerText(blocker, at)}
          </li>{/each}
      </ul>
    </div>{/if}
  <AdminTable>
    <thead
      ><tr
        ><th>{at("console_resource_field")}</th><th>{at("console_resource_current")}</th><th
          >{at("console_resource_proposed")}</th
        ></tr
      ></thead
    >
    <tbody>
      {#each fields as [field, key]}
        {#if field !== "force_restart" || preview.change.operation === "node_restart"}
          <tr
            ><td data-label={at("console_resource_field")}>{at(key)}</td>
            <td data-label={at("console_resource_current")}>{display(preview.current?.[field])}</td>
            <td data-label={at("console_resource_proposed")}
              >{display(preview.proposed?.[field])}</td
            ></tr
          >
        {/if}
      {/each}
    </tbody>
  </AdminTable>
  <section aria-label={at("console_resource_affected_services")}>
    <h4>{at("console_resource_affected_services")}: {serviceIds.length}</h4>
    <ul>
      {#each serviceIds as serviceId}<li>
          <a
            href={serviceHref(serviceId)}
            data-resource-service-id={serviceId}
            onclick={(event) => follow(event, () => onOpenService(serviceId))}
          >
            <AdminEntityLink kind="code" label={serviceId} />
          </a>
        </li>{:else}<li>{at("console_resource_no_services")}</li>{/each}
    </ul>
  </section>
  <section aria-label={at("console_resource_affected_customers")}>
    <h4>{at("console_resource_affected_customers")}: {customers.length}</h4>
    <ul>
      {#each customers as customerId}<li>
          <a
            href={nodeRelatedUrl(currentUrl, { userId: customerId }, routePrefix).href}
            onclick={(event) => follow(event, () => onOpenUserCard(customerId))}
          >
            <AdminEntityLink label={String(customerId)} />
          </a>
        </li>{:else}<li>{at("console_resource_no_customers")}</li>{/each}
    </ul>
  </section>
  <section aria-label={at("console_resource_direct")}>
    <h4>{at("console_resource_direct")}</h4>
    <p>{at("console_resource_direct_hint")}</p>
    <ConsoleResourceImpact
      impact={preview.direct}
      {at}
      {currentUrl}
      {routePrefix}
      {serviceHref}
      {onOpenService}
      {onOpenUserCard}
    />
  </section>
  <section aria-label={at("console_resource_reload")}>
    <h4>{at("console_resource_reload")}</h4>
    <p>{at("console_resource_reload_hint")}</p>
    <ConsoleResourceImpact
      impact={preview.possible_reload}
      {at}
      {currentUrl}
      {routePrefix}
      {serviceHref}
      {onOpenService}
      {onOpenUserCard}
    />
  </section>
  <dl>
    <div>
      <dt>{at("console_resource_observed_at")}</dt>
      <dd>{serviceDate(preview.observed_at)}</dd>
    </div>
    <div>
      <dt>{at("console_resource_reviewed_version")}</dt>
      <dd>{preview.reviewed_panel_version}</dd>
    </div>
    <div>
      <dt>{at("console_resource_observed_version")}</dt>
      <dd>{preview.observed_panel_version ?? at("console_unknown")}</dd>
    </div>
    <div>
      <dt>{at("console_resource_fingerprint")}</dt>
      <dd><code>{preview.fingerprint ?? at("console_unknown")}</code></dd>
    </div>
  </dl>
  <ul class="resource-sources">
    {#each preview.sources as source (source.source)}<li>
        <strong
          >{at(
            source.source === "nodes" || source.source === "hosts"
              ? `console_nodes_source_${source.source}`
              : `console_resource_source_${source.source}`
          )}</strong
        >:
        {at(
          source.availability === "invalid"
            ? "console_resource_source_invalid"
            : `console_nodes_availability_${source.availability}`
        )}
        <span>{at("console_resource_observed_at")}: {serviceDate(source.observed_at)}</span>
      </li>{/each}
  </ul>
  <section>
    <h4>{at("console_resource_recovery")}</h4>
    <p>{at(resourceRecoveryKey(preview.recovery))}</p>
  </section>
</div>

<style>
  .resource-preview-result,
  section {
    display: grid;
    gap: 12px;
    min-width: 0;
  }
  p,
  h4,
  dl,
  ul {
    margin: 0;
  }
  dl {
    display: grid;
    gap: 12px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  dt {
    color: var(--admin-muted);
  }
  dd {
    margin: 4px 0 0;
  }
  p,
  li,
  dd,
  td {
    overflow-wrap: anywhere;
  }
  ul {
    padding-left: 20px;
  }
  .resource-sources {
    display: grid;
    gap: 8px;
  }
  .resource-sources span {
    display: block;
  }
  a {
    color: var(--accent);
    text-decoration: none;
  }
  a:hover {
    text-decoration: underline;
  }
  @media (max-width: 720px) {
    dl {
      grid-template-columns: 1fr;
    }
  }
</style>
