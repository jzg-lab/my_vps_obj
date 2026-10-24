<script lang="ts">
  import { AdminBadge } from "$components/patterns/admin/index.js";
  import type { components } from "$lib/api/openapi.generated";
  import type { ServiceTranslate } from "$lib/admin/servicePlans";
  import { serviceDate } from "$lib/webapp/independentServices";

  let {
    summary,
    at,
  }: {
    summary?: components["schemas"]["ConsoleCustomerServicesOut"] | null;
    at: ServiceTranslate;
  } = $props();

  const states = [
    "active",
    "pending",
    "paused",
    "expired",
    "exhausted",
    "cancelled",
    "account_banned",
  ] as const;
  const health = [
    "sync_error",
    "sync_pending",
    "cycle_pending",
    "sync_unobserved",
    "usage_unobserved",
  ] as const;
  const observations = [
    { key: "sync", oldest: "oldest_sync_confirmed_at", latest: "latest_sync_confirmed_at" },
    { key: "usage", oldest: "oldest_usage_sync_at", latest: "latest_usage_sync_at" },
  ] as const;
</script>

<div class="customer-service-summary">
  {#if summary}
    <div class="summary-badges">
      <strong data-customer-service-total={summary.total}>
        {at("console_customers_service_count", { count: summary.total })}
      </strong>
      {#if summary.sync_error > 0}
        <AdminBadge wrap variant="danger" data-service-alert="sync_error">
          {at("console_customers_sync_error")}: {summary.sync_error}
        </AdminBadge>
      {/if}
      {#if summary.sync_pending > 0 || summary.cycle_pending > 0}
        <AdminBadge wrap variant="warning" data-service-alert="pending">
          {at("console_customers_pending")}
        </AdminBadge>
      {/if}
      {#if summary.sync_unobserved > 0 || summary.usage_unobserved > 0}
        <AdminBadge wrap variant="warning" data-service-alert="unobserved">
          {at("console_customers_unobserved")}
        </AdminBadge>
      {/if}
    </div>
    {#if summary.total > 0}
      <div class="summary-badges" aria-label={at("console_customers_business_states")}>
        {#each states as state (state)}
          {#if summary.by_status[state] > 0}
            <span class:restricted={state !== "active"} data-service-state={state}>
              {at(`services_status_${state}`)}: {summary.by_status[state]}
            </span>
          {/if}
        {/each}
      </div>
    {/if}
    <!-- Keep keyboard events after text selection inside the disclosure, not the customer row. -->
    <details tabindex="-1">
      <summary>{at("console_customers_details")}</summary>
      <div class="summary-detail">
        {#if summary.total > 0}
          <div class="summary-badges" aria-label={at("console_customers_sync_counts")}>
            {#each health as field (field)}
              <AdminBadge
                wrap
                variant={summary[field] > 0
                  ? field === "sync_error"
                    ? "danger"
                    : "warning"
                  : "muted"}
                data-service-health={field}
              >
                {at(`console_customers_${field}`)}: {summary[field]}
              </AdminBadge>
            {/each}
          </div>
          <dl class="summary-observations">
            {#each observations as observation (observation.key)}
              <div>
                <dt>{at(`console_customers_${observation.key}_times`)}</dt>
                <dd data-service-observation={observation.key}>
                  {#if summary[observation.oldest] && summary[observation.latest]}
                    <time datetime={summary[observation.oldest] ?? undefined}
                      >{serviceDate(summary[observation.oldest])}</time
                    >
                    {#if summary[observation.latest] !== summary[observation.oldest]}
                      <span> / </span><time datetime={summary[observation.latest] ?? undefined}
                        >{serviceDate(summary[observation.latest])}</time
                      >
                    {/if}
                  {:else}
                    {at("console_customers_no_observation")}
                  {/if}
                </dd>
              </div>
            {/each}
          </dl>
        {/if}
        <span class="summary-meta">
          {at("console_customers_observed_at")}:
          <time datetime={summary.observed_at}>{serviceDate(summary.observed_at)}</time>
        </span>
      </div>
    </details>
  {:else}
    <span class="summary-meta" data-customer-summary-unknown
      >{at("console_customers_summary_unknown")}</span
    >
  {/if}
  <span class="summary-meta">{at("console_customers_activity_uncollected")}</span>
</div>

<style>
  .customer-service-summary {
    display: grid;
    gap: 3px;
    min-width: 0;
    font-size: 12px;
    line-height: 1.45;
    white-space: normal;
    overflow-wrap: anywhere;
    font-variant-numeric: tabular-nums;
  }
  .summary-badges {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 4px;
    min-width: 0;
  }
  [data-service-state] + [data-service-state]::before {
    content: " / ";
    color: var(--admin-muted);
  }
  .restricted {
    font-weight: 600;
  }
  summary {
    width: fit-content;
    color: var(--admin-muted);
    cursor: pointer;
    font-size: 11px;
  }
  summary:focus-visible {
    outline: 2px solid var(--admin-ring);
    outline-offset: 2px;
  }
  .summary-detail {
    display: grid;
    gap: 6px;
    padding-block: 6px;
  }
  .summary-observations {
    display: grid;
    gap: 3px;
    margin: 0;
    color: var(--admin-muted);
    font-size: 11px;
  }
  .summary-observations > div {
    display: flex;
    flex-wrap: wrap;
    column-gap: 6px;
  }
  .summary-observations dd {
    min-width: 0;
    margin: 0;
  }
  .summary-meta {
    color: var(--admin-muted);
    font-size: 11px;
  }
</style>
