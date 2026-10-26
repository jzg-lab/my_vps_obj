<script lang="ts">
  import { AdminButton } from "$components/patterns/admin/index.js";
  import type { ConsoleNodesPage, ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import type { components } from "$lib/api/openapi.generated";
  import { nodeControlStatus } from "../nodes/nodeSystemMetrics";

  let {
    nodes,
    stale,
    stats,
    at,
    onNodes,
    onFeedback,
  }: {
    nodes: ConsoleNodesPage | null;
    stale: boolean;
    stats: components["schemas"]["AdminSupportStatsOut"] | null;
    at: ConsoleNodesTranslate;
    onNodes: (status?: "all" | "online" | "offline" | "unknown") => void;
    onFeedback: () => void;
  } = $props();
  const hasInventory = $derived(
    Boolean(nodes && (nodes.nodes.length || nodes.coverage === "complete"))
  );
  const source = $derived(nodes?.sources.find((s) => s.source === "nodes"));
  const unknownStatus = $derived(
    stale ||
      Boolean(
        nodes?.nodes.length &&
        source?.availability !== "available" &&
        source?.availability !== "partial"
      )
  );
  const statuses = $derived(
    nodes?.nodes.map((node) => (unknownStatus ? "unknown" : nodeControlStatus(node, source))) ?? []
  );
</script>

<div class="overview-signals" aria-label={at("console_ops_signals")}>
  <article>
    <span>{at("console_ops_online_sample")}</span><strong
      >{hasInventory && nodes
        ? `${unknownStatus ? at("console_unknown") : statuses.filter((s) => s === "online").length} / ${nodes.nodes.length}`
        : at("console_unknown")}</strong
    ><AdminButton size="sm" onclick={() => onNodes()}>{at("console_open_nodes")}</AdminButton>
  </article>
  <article class="attention">
    <span>{at("console_ops_check_sample")}</span><strong
      >{hasInventory
        ? statuses.filter((s) => s !== "online").length
        : at("console_unknown")}</strong
    ><small>{at("console_ops_check_scope")}</small>
    {#if !unknownStatus && hasInventory}
      <div class="attention-links">
        {#each ["offline", "unknown"] as status}<AdminButton
            size="sm"
            onclick={() => onNodes(status === "offline" ? "offline" : "unknown")}
          >
            {at(status === "offline" ? "console_check_offline" : "console_check_unknown")}
          </AdminButton>{/each}
      </div>
    {:else}<AdminButton size="sm" onclick={() => onNodes()}>{at("console_open_nodes")}</AdminButton
      >{/if}
  </article>
  <article>
    <span>{at("console_feedback_waiting")}</span><strong
      >{stats?.awaiting_admin ?? at("console_unknown")}</strong
    ><AdminButton size="sm" onclick={onFeedback}>{at("console_feedback_open")}</AdminButton>
  </article>
  <article>
    <span>{at("console_feedback_unread")}</span><strong
      >{stats?.total_unread_admin ?? at("console_unknown")}</strong
    ><small>{at("console_feedback_scope")}</small>
  </article>
</div>

<style>
  .attention-links {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
  .overview-signals {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
  }
  article {
    min-width: 0;
    display: grid;
    align-content: start;
    justify-items: start;
    gap: 10px;
    padding: 16px;
    border-top: 2px solid var(--admin-border);
    background: var(--admin-surface);
    overflow-wrap: anywhere;
  }
  span,
  small {
    color: var(--admin-muted);
    font-size: 12px;
  }
  strong {
    color: var(--accent);
    font-size: 30px;
    line-height: 1.1;
  }
  .attention strong {
    color: var(--warning);
  }
  @media (max-width: 760px) {
    .overview-signals {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
</style>
