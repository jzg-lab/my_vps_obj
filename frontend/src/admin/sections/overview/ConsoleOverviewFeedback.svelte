<script lang="ts">
  import {
    SupportInboxRow,
    AdminButton,
    AdminEmptyState,
    AdminEntityLink,
  } from "$components/patterns/admin/index.js";
  import { buildAdminSupportPath } from "$lib/webapp/publicApi";
  import { withRoutePrefix } from "$lib/webapp/routes";
  import { nodeRelatedUrl } from "$lib/admin/consoleNodesNavigation";
  import { serviceDate } from "$lib/webapp/independentServices";
  import type { components } from "$lib/api/openapi.generated";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  let {
    stats,
    tickets,
    failed,
    listFailed,
    readAt,
    loading,
    at,
    routePrefix,
    onOpen,
  }: {
    stats: components["schemas"]["AdminSupportStatsOut"] | null;
    tickets: components["schemas"]["AdminSupportTicketOut"][] | null;
    failed: boolean;
    listFailed: boolean;
    readAt: string | null;
    loading: boolean;
    at: ConsoleNodesTranslate;
    routePrefix: string;
    onOpen: () => void;
  } = $props();
</script>

<h3>{at("console_feedback_title")}</h3>
<p>{at("console_ops_feedback_scope")}</p>
{#if failed}<p role="status">{at("console_feedback_failed")}</p>{/if}
<dl>
  <div>
    <dt>{at("console_feedback_waiting")}</dt>
    <dd data-feedback-waiting>{stats?.awaiting_admin ?? at("console_unknown")}</dd>
  </div>
  <div>
    <dt>{at("console_feedback_unread")}</dt>
    <dd data-feedback-unread>{stats?.total_unread_admin ?? at("console_unknown")}</dd>
  </div>
</dl>
{#if listFailed}<p role="status">{at("console_ops_feedback_list_failed")}</p>
{:else if tickets?.length}
  <ul class="feedback-list">
    {#each tickets as ticket (ticket.ticket_id)}
      <li>
        <SupportInboxRow
          wrap
          {ticket}
          {at}
          onOpen={() => {
            window.history.pushState(
              null,
              "",
              withRoutePrefix(buildAdminSupportPath(ticket.ticket_id), routePrefix)
            );
            window.dispatchEvent(new PopStateEvent("popstate"));
          }}
        />
        <AdminEntityLink
          kind="user"
          label={at("console_customers")}
          idText={String(ticket.user_id)}
          onclick={() => {
            window.history.pushState(
              null,
              "",
              nodeRelatedUrl(window.location.href, { userId: ticket.user_id }, routePrefix)
            );
            window.dispatchEvent(new PopStateEvent("popstate"));
          }}
        />
      </li>
    {/each}
  </ul>
{:else if tickets && !loading}<AdminEmptyState>{at("console_ops_feedback_empty")}</AdminEmptyState
  >{/if}
{#if readAt}<small>{at("console_nodes_last_success")}: {serviceDate(readAt)}</small>{/if}
<p>{at("support_filter_active")}: {stats?.active ?? at("console_unknown")}</p>
<AdminButton size="sm" onclick={onOpen}>{at("console_feedback_open")}</AdminButton>

<style>
  h3 {
    margin: 0;
    font-size: 16px;
  }
  p {
    color: var(--admin-muted);
    font-size: 12px;
    line-height: 1.6;
    margin: 10px 0;
  }
  dl {
    display: flex;
    flex-wrap: wrap;
    gap: 24px;
    margin: 16px 0;
  }
  dl > div {
    display: grid;
    gap: 8px;
  }
  dt,
  small {
    color: var(--admin-muted);
    font-size: 12px;
    overflow-wrap: anywhere;
  }
  dd {
    margin: 0;
    font-size: 26px;
    font-weight: 700;
  }
  .feedback-list {
    list-style: none;
    padding: 0;
    margin: 0 0 16px;
  }
  li {
    display: grid;
    gap: 8px;
    padding: 14px 0;
    border-top: 1px solid var(--admin-border);
    min-width: 0;
  }
</style>
