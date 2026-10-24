<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import ConsoleNodeSources from "../nodes/ConsoleNodeSources.svelte";
  import { AdminButton } from "$components/patterns/admin";
  import { unwrap, type ApiClient } from "$lib/webapp/publicApi";
  import { serviceDate } from "$lib/webapp/independentServices";
  import type { ServiceTranslate } from "$lib/admin/servicePlans";
  import {
    consoleServiceErrorKey,
    consoleServiceLabel,
    type ServicePreflight,
    type ServicePreflightBody,
  } from "$lib/admin/consoleServiceOperations";

  let {
    api,
    at,
    body,
    disabled = false,
    onresult,
  }: {
    api: ApiClient["api"];
    at: ServiceTranslate;
    body: ServicePreflightBody;
    disabled?: boolean;
    onresult: (result: ServicePreflight | null) => void;
  } = $props();
  let result = $state<ServicePreflight | null>(null);
  let loading = $state(true);
  let failed = $state(false);
  let request = 0;
  let controller: AbortController | null = null;
  async function load() {
    const token = ++request;
    controller?.abort();
    controller = new AbortController();
    result = null;
    onresult(null);
    failed = false;
    loading = true;
    try {
      const response = unwrap(
        await api("/admin/console/service-preflight", {
          method: "POST",
          body: JSON.stringify(body),
          signal: controller.signal,
        })
      );
      if (token !== request) return;
      result = response;
      onresult(response);
    } catch {
      if (token === request) failed = true;
    } finally {
      if (token === request) loading = false;
    }
  }
  onMount(() => {
    void load();
  });
  onDestroy(() => {
    request++;
    controller?.abort();
  });
</script>

<section aria-label={at("console_preflight_title")} aria-busy={loading}>
  <header>
    <h4>{at("console_preflight_title")}</h4>
    <AdminButton size="sm" disabled={disabled || loading} onclick={load}
      >{at("refresh")}</AdminButton
    >
  </header>
  <p>{at("console_preflight_hint")}</p>
  {#if loading}<p role="status">{at("loading")}</p>
  {:else if failed}<p role="alert">{at("console_preflight_failed")}</p>
  {:else if result}
    <p role="status">
      <strong
        >{at(
          result.allow_pending_creation
            ? "console_preflight_creation_allowed"
            : "console_preflight_creation_blocked"
        )}</strong
      >
    </p>
    <p>
      {at("console_preflight_readiness")}: {at(
        consoleServiceLabel("readiness", result.resource_readiness)
      )}
    </p>
    <p>{at("console_preflight_not_deliverable")}</p>
    <dl>
      <dt>{at("console_ops_observed_local")}</dt>
      <dd>{serviceDate(result.local_observed_at)}</dd>
      <dt>{at("console_preflight_plan_revision")}</dt>
      <dd>{result.plan_revision ?? at("console_unknown")}</dd>
      {#if result.exit_id}<dt>{at("console_preflight_exit_revision")}</dt>
        <dd>{result.exit_revision ?? at("console_unknown")}</dd>{/if}
    </dl>
    <ul>
      {#each result.checks as check}<li>
          <strong>{at(consoleServiceLabel("check", check.code))}</strong>: {at(
            consoleServiceLabel("checkStatus", check.status)
          )}
          {#if check.reason}<p>{at(consoleServiceErrorKey(check.reason))}</p>{/if}
        </li>{/each}
    </ul>
    <ConsoleNodeSources
      {at}
      sources={result.sources}
      coverage={result.checks.find((item) => item.code === "resource_sources")?.status === "passed"
        ? "complete"
        : result.sources.some((item) => item.availability === "available")
          ? "partial"
          : "unavailable"}
    />
  {/if}
</section>

<style>
  section {
    display: grid;
    gap: 12px;
    min-width: 0;
    border-top: 1px solid var(--admin-border);
    padding-top: 16px;
  }
  header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  h4,
  p,
  dl {
    margin: 0;
  }
  p,
  dt {
    color: var(--admin-muted);
  }
  dl {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }
  dd {
    margin: 0;
    overflow-wrap: anywhere;
  }
  ul {
    display: grid;
    gap: 8px;
    margin: 0;
    padding-left: 20px;
  }
  [role="alert"] {
    color: var(--danger);
  }
</style>
