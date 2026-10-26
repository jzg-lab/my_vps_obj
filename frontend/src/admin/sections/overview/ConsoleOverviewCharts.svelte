<script lang="ts">
  import { AdminTrafficCard } from "$components/patterns/admin/index.js";
  import ConsoleNodeTrafficChart from "../nodes/ConsoleNodeTrafficChart.svelte";
  import type { ConsoleNodesPage, ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import type { components } from "$lib/api/openapi.generated";
  let {
    nodes,
    tickets,
    stale,
    listFailed,
    loading,
    at,
    onNode,
  }: {
    nodes: ConsoleNodesPage | null;
    tickets: components["schemas"]["AdminSupportTicketOut"][] | null;
    stale: boolean;
    listFailed: boolean;
    loading: boolean;
    at: ConsoleNodesTranslate;
    onNode: (id: string) => void;
  } = $props();
  const topics = $derived.by(() => {
    const counts = new Map<string, number>();
    for (const ticket of tickets ?? [])
      counts.set(ticket.category, (counts.get(ticket.category) ?? 0) + 1);
    return [...counts];
  });
</script>

<div class="overview-charts">
  <ConsoleNodeTrafficChart {nodes} {stale} {at} {onNode} />
  <section class="topics" aria-label={at("console_visual_topics")}>
    <h3>{at("console_visual_topics")}</h3>
    <p>{at("console_visual_topics_scope")}</p>
    {#if listFailed}<p role="status">{at("console_ops_feedback_list_failed")}</p>
    {:else if loading && !tickets}<p>{at("loading")}</p>
    {:else if topics.length}{#each topics as [category, count]}<AdminTrafficCard
          title={at(`support_category_${category}`)}
          value={String(count)}
          percent={tickets?.length ? Math.round((count / tickets.length) * 100) : 0}
        />{/each}
    {:else}<p>{at("console_ops_feedback_empty")}</p>{/if}
  </section>
</div>

<style>
  .overview-charts {
    display: grid;
    grid-template-columns: minmax(0, 1.65fr) minmax(270px, 0.85fr);
    gap: 16px;
    min-width: 0;
    align-items: start;
  }
  .topics {
    display: grid;
    gap: 16px;
    min-width: 0;
    padding: 20px;
    border: 1px solid var(--admin-border);
    border-radius: 14px;
    background: var(--admin-surface);
  }
  h3,
  p {
    margin: 0;
  }
  h3 {
    font-size: 16px;
  }
  p {
    font-size: 12px;
    color: var(--admin-muted);
    line-height: 1.6;
  }
  @media (max-width: 1050px) {
    .overview-charts {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
