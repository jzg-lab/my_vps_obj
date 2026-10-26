<script lang="ts">
  import { onMount, tick } from "svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminEntityLink,
    AdminPagination,
  } from "$components/patterns/admin/index.js";
  import { nodeRelatedUrl } from "$lib/admin/consoleNodesNavigation";
  import type { ConsoleNodeDetail, ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import type { ApiClient } from "$lib/webapp/publicApi";
  import ConsoleNodeSources from "./ConsoleNodeSources.svelte";
  import ConsoleNodeTable from "./ConsoleNodeTable.svelte";
  import NodeSystemMetrics from "./NodeSystemMetrics.svelte";
  import ConsoleNodeResourcePreview from "./ConsoleNodeResourcePreview.svelte";
  import ConsoleResourceDraftPreview from "./ConsoleResourceDraftPreview.svelte";
  import type { DraftTarget } from "./resourceDraftPreview";
  let {
    api,
    detail,
    at,
    currentUrl,
    routePrefix = "",
    page,
    loading = false,
    onPageChange,
    onBack,
    onOpenUserCard,
  }: {
    api: ApiClient["api"];
    detail: ConsoleNodeDetail;
    at: ConsoleNodesTranslate;
    currentUrl: string;
    routePrefix?: string;
    page: number;
    loading?: boolean;
    onPageChange: (page: number) => void;
    onBack: () => void;
    onOpenUserCard: (userId: unknown) => void;
  } = $props();
  let heading: HTMLHeadingElement | undefined;
  let draftTarget = $state<DraftTarget | null>(null);
  let draftTrigger: HTMLElement | null = null;
  function openDraft(target: DraftTarget, event: MouseEvent) {
    draftTrigger = event.currentTarget instanceof HTMLElement ? event.currentTarget : null;
    draftTarget = target;
  }
  async function closeDraft() {
    draftTarget = null;
    await tick();
    draftTrigger?.focus();
  }
  onMount(() => heading?.focus());
</script>

{#snippet related()}
  <section class="node-related-panel" aria-label={at("console_nodes_potential")}>
    <h4>{at("console_nodes_potential")}</h4>
    <p>{at("console_nodes_association_scope")}</p>
    <p>
      {at("console_nodes_service_total")}: {detail.service_total ?? at("console_unknown")} · {at(
        "console_nodes_customer_total"
      )}: {detail.customer_total ?? at("console_unknown")}
    </p>
    {#if !detail.associations_complete}<p role="status">
        {at("console_nodes_incomplete_relations")}
      </p>{/if}
    {#if detail.services.length}
      <div class="related-services">
        {#each detail.services as service (service.id)}
          <article>
            <a href={nodeRelatedUrl(currentUrl, { serviceId: service.id }, routePrefix).href}
              ><AdminEntityLink kind="code" label={service.name} idText={service.id} /></a
            >
            <a
              href={nodeRelatedUrl(currentUrl, { userId: service.user_id }, routePrefix).href}
              onclick={(event) => {
                if (
                  event.button !== 0 ||
                  event.metaKey ||
                  event.ctrlKey ||
                  event.shiftKey ||
                  event.altKey
                )
                  return;
                event.preventDefault();
                onOpenUserCard(service.user_id);
              }}><AdminEntityLink label={String(service.user_id)} /></a
            >
            <div>
              <AdminBadge>{at(`services_status_${service.status}`)}</AdminBadge><small
                >{at(
                  service.currently_eligible ? "console_nodes_eligible" : "console_nodes_ineligible"
                )}</small
              >
            </div>
          </article>
        {/each}
      </div>
    {:else}<p>
        {at(
          detail.associations_complete
            ? "console_nodes_no_services"
            : "console_nodes_no_known_services"
        )}
      </p>{/if}
    <AdminPagination
      {page}
      total={detail.service_total}
      pageCount={detail.service_total === null
        ? null
        : Math.ceil(detail.service_total / detail.page_size)}
      disabled={loading}
      onPageChange={detail.service_total === null ? null : onPageChange}
      onPrev={() => onPageChange(page - 1)}
      onNext={() => onPageChange(page + 1)}
      prevDisabled={page === 0}
      nextDisabled={detail.services.length < detail.page_size}
      prevLabel={at("services_previous")}
      nextLabel={at("services_next")}
      pageLabel={at("services_page")}
      ofLabel={at("services_of")}
      totalLabel={at("services_count")}
      jumpLabel={at("services_page")}
      jumpAriaLabel={at("services_go_page")}
      goLabel={at("services_go_page")}
    />
  </section>
{/snippet}

<section class="node-detail" aria-label={at("console_nodes_detail")}>
  <div><AdminButton onclick={onBack}>{at("console_nodes_back")}</AdminButton></div>
  <header class="node-heading">
    <div>
      <h3 bind:this={heading} tabindex="-1">{detail.node.name}</h3>
      <p class="node-id">{detail.node.id}</p>
    </div>
    <ConsoleNodeResourcePreview
      {api}
      node={detail.node}
      {at}
      {currentUrl}
      {routePrefix}
      {onOpenUserCard}
    />
  </header>
  <dl class="node-facts">
    <div>
      <dt>{at("console_nodes_address")}</dt>
      <dd>{detail.node.address ?? at("console_unknown")}</dd>
    </div>
    <div>
      <dt>{at("console_node_metrics_cpu_model")}</dt>
      <dd>{detail.node.system?.cpu_model ?? at("console_unknown")}</dd>
    </div>
  </dl>
  <NodeSystemMetrics
    node={detail.node}
    traffic={detail.traffic}
    source={detail.sources.find((source) => source.source === "nodes")}
    {at}
    {related}
  />
  <ConsoleNodeTable
    nodes={[detail.node]}
    traffic={detail.traffic ?? null}
    source={detail.sources.find((source) => source.source === "nodes")}
    {at}
  />
  <dl>
    <div>
      <dt>{at("console_nodes_profile")}</dt>
      <dd>{detail.node.profile_id ?? at("console_unknown")}</dd>
    </div>
    <div>
      <dt>{at("console_nodes_inbounds")}</dt>
      <dd>{detail.node.inbound_ids.join(", ") || at("console_unknown")}</dd>
    </div>
    <div>
      <dt>{at("console_nodes_groups")}</dt>
      <dd>
        {#each detail.groups as group (group.id)}<span
            >{group.name ?? at("console_unknown")} · {group.id}</span
          ><AdminButton onclick={(event) => openDraft({ kind: "group", id: group.id }, event)}
            >{at("console_draft_group_open")}</AdminButton
          >{:else}{at("console_nodes_no_known_groups")}{/each}
      </dd>
    </div>
    <div>
      <dt>{at("console_nodes_hosts")}</dt>
      <dd>
        {#each detail.hosts as host (host.id)}<span
            >{host.name ?? at("console_unknown")} · {host.id}</span
          ><AdminButton onclick={(event) => openDraft({ kind: "host", id: host.id }, event)}
            >{at("console_draft_host_open")}</AdminButton
          >{:else}{at("console_nodes_no_known_hosts")}{/each}
      </dd>
    </div>
  </dl>
  <ConsoleNodeSources coverage={detail.coverage} sources={detail.sources} {at} />
</section>

{#if draftTarget}
  {#key `${detail.node.id}:${draftTarget.kind}:${draftTarget.id}`}
    <ConsoleResourceDraftPreview
      {api}
      target={draftTarget}
      {at}
      {currentUrl}
      {routePrefix}
      {onOpenUserCard}
      onclose={closeDraft}
    />
  {/key}
{/if}

<style>
  .related-services {
    display: grid;
    gap: 12px;
    min-width: 0;
  }
  .related-services article {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 6px 12px;
    padding: 8px 0;
    border-bottom: 1px solid var(--admin-border);
    min-width: 0;
  }
  .related-services a {
    color: var(--admin-text);
    text-decoration: none;
    min-width: 0;
  }
  .related-services a:hover {
    text-decoration: underline;
  }
  .related-services article > div {
    grid-column: 1 / -1;
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
  }
  .related-services small,
  .node-related-panel > p {
    font-size: 12px;
    color: var(--admin-muted);
    line-height: 1.6;
  }
  .related-services :global(.admin-entity-link-id) {
    white-space: normal;
    overflow-wrap: anywhere;
  }

  .node-related-panel {
    display: grid;
    gap: 8px;
    min-width: 0;
  }

  .node-detail {
    display: grid;
    gap: 16px;
    min-width: 0;
  }
  h3,
  h4,
  p,
  dl {
    margin: 0;
  }
  dl {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
  }
  dt {
    color: var(--admin-muted);
  }
  dd {
    margin: 4px 0 0;
    overflow-wrap: anywhere;
  }
  dd span {
    display: block;
  }
  .node-id {
    overflow-wrap: anywhere;
    color: var(--admin-muted);
    font-size: 12px;
    margin-top: 6px;
  }
  .node-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }
  .node-heading h3 {
    font-size: 24px;
  }
  .node-facts {
    padding: 16px;
    background: var(--admin-surface);
    border: 1px solid var(--admin-border);
    border-radius: 12px;
    font-size: 13px;
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
