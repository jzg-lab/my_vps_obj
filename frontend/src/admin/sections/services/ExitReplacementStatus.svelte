<script lang="ts">
  import { AdminBadge, AdminTable } from "$components/patterns/admin";
  import type { ServiceTranslate } from "$lib/admin/servicePlans";
  import { replacementLabel, type ReplacementState } from "$lib/admin/exitReplacement";
  import { consoleServiceErrorKey, consoleServiceLabel } from "$lib/admin/consoleServiceOperations";
  import { serviceDate } from "$lib/webapp/independentServices";
  import ExitReplacementImpact from "./ExitReplacementImpact.svelte";
  let {
    data,
    at,
    currentUrl = "",
    routePrefix = "",
  }: {
    data: ReplacementState;
    at: ServiceTranslate;
    currentUrl?: string;
    routePrefix?: string;
  } = $props();
  const row = $derived(data.replacement ?? data.draft);
  const sourceNames: Record<string, string> = {
    nodes: "console_nodes_source_nodes",
    hosts: "console_nodes_source_hosts",
    ...Object.fromEntries(
      ["metadata", "groups", "profiles", "services", "authorizations"].map((v) => [
        v,
        `console_resource_source_${v}`,
      ])
    ),
  };
</script>

<div class="replacement-status">
  {#if row}
    <section aria-label={at("replacement_resources")}>
      <h4>{at("replacement_resources")}</h4>
      <AdminTable>
        <thead
          ><tr
            >{#each ["services_resource_type", "services_name", "services_exit_ip", "services_pool", "services_squads"] as key}<th
                >{at(key)}</th
              >{/each}</tr
          ></thead
        >
        <tbody
          >{#each [["replacement_old_exit", row.old_exit], ["replacement_candidate", row.candidate_exit]] as [label, resource]}
            {#if typeof label === "string" && typeof resource !== "string"}
              <tr
                ><td data-label={at("services_resource_type")}>{at(label)}</td><td
                  data-label={at("services_name")}
                  >{resource.label}<small>{resource.id}</small>{#if resource.hold_order_id}<small
                      >{at("services_exit_held")}</small
                    >{/if}</td
                ><td data-label={at("services_exit_ip")}>{resource.ip_address}</td><td
                  data-label={at("services_pool")}>{resource.resource_pool}</td
                ><td data-label={at("services_squads")}>{resource.squad_uuid}</td></tr
              >
            {/if}
          {/each}</tbody
        >
      </AdminTable>
    </section>
    <section aria-label={at("console_resource_title")}>
      <h4>{at("console_resource_title")}</h4>
      <p>{at("console_resource_scope")}</p>
      <AdminBadge variant={row.coverage === "complete" ? "muted" : "warning"}
        >{at(
          row.coverage === "complete"
            ? "console_nodes_coverage_complete"
            : "console_nodes_coverage_partial"
        )}</AdminBadge
      >
      <p>{at("replacement_observed_at")}: {serviceDate(row.observed_at)}</p>
      {#each row.block_reasons as reason}<p role="alert">
          {at(consoleServiceErrorKey(reason))}
        </p>{/each}
      <ul>
        {#each row.sources as source}<li>
            {at(
              Object.hasOwn(sourceNames, source.source)
                ? sourceNames[source.source]
                : "console_unknown"
            )}:
            {at(
              source.availability === "available"
                ? "replacement_source_available"
                : source.availability === "unavailable"
                  ? "replacement_source_unavailable"
                  : source.availability === "invalid"
                    ? "console_resource_source_invalid"
                    : source.availability === "unsupported"
                      ? "replacement_source_unsupported"
                      : "console_unknown"
            )}
            · {serviceDate(source.observed_at)}
          </li>{/each}
      </ul>
      <ExitReplacementImpact impacts={row.impacts ?? []} {at} {currentUrl} {routePrefix} />
    </section>
  {/if}
  {#if data.replacement}
    {@const current = data.replacement}
    <section aria-label={at("replacement_results")}>
      <h4>{at("replacement_results")}</h4>
      <dl>
        <div>
          <dt>{at("replacement_operation")}</dt>
          <dd>{current.operation.id}</dd>
        </div>
        <div>
          <dt>{at("status")}</dt>
          <dd>
            {at(consoleServiceLabel("operation", current.operation.status))} · {at(
              replacementLabel("stage", current.progress.stage)
            )}
          </dd>
        </div>
        <div>
          <dt>{at("replacement_switch")}</dt>
          <dd>{at(replacementLabel("switch", current.switch_result))}</dd>
        </div>
        <div>
          <dt>{at("replacement_restore")}</dt>
          <dd>{at(replacementLabel("restore", current.progress.restore_result))}</dd>
        </div>
        <div>
          <dt>{at("replacement_old_resource")}</dt>
          <dd>{at(replacementLabel("old", current.old_resource_state))}</dd>
        </div>
        <div>
          <dt>{at("replacement_restore_requested")}</dt>
          <dd>{at(current.restore_requested ? "yes" : "no")}</dd>
        </div>
      </dl>
      {#each current.progress.restore_block_reasons ?? [] as reason}<p role="status">
          {at(replacementLabel("block", reason))}
        </p>{/each}
      {#if current.operation.error_code}<p role="alert">
          {at(consoleServiceErrorKey(current.operation.error_code))}
        </p>{/if}
      {#if current.progress.pending_action}<p role="alert">
          {at("console_exit_replacement_write_unknown")}
        </p>
        <p>
          {at(replacementLabel("write", current.progress.pending_action))} · {at(
            "replacement_attempt"
          )}: {current.operation.attempt_count ?? at("console_unknown")}
        </p>{/if}
      {#each [["replacement_action_stop_evidence", current.old_stop], ["replacement_action_verify", current.candidate_verification]] as [label, evidence]}
        {#if typeof label === "string" && typeof evidence !== "string"}<p>
            {at(label)}: {#if evidence}{at(
                evidence.provenance === "machine"
                  ? "replacement_machine_evidence"
                  : evidence.provenance === "administrator"
                    ? "replacement_administrator_evidence"
                    : "console_unknown"
              )} · {serviceDate(evidence.observed_at)} · {at(
                evidence.valid ? "replacement_evidence_valid" : "replacement_evidence_stale"
              )}{:else}{at("services_exit_no_evidence")}{/if}
          </p>{/if}
      {/each}
      <p>
        {at("replacement_accounting")}: {current.accounting.usage_total_bytes ??
          at("console_unknown")} / {current.accounting.usage_raw_bytes ?? at("console_unknown")} / {current
          .accounting.usage_lifetime_offset}
      </p>
      <p>
        {at("services_last_sync")}: {current.accounting.observed_at
          ? serviceDate(current.accounting.observed_at)
          : at("console_unknown")}
      </p>
      {#if current.accounting.error_code}<p role="alert">
          {at(consoleServiceErrorKey(current.accounting.error_code))}
        </p>{/if}
      {#if current.accounting.cycle_pending}<p role="status">{at("services_cycle_pending")}</p>{/if}
    </section>
  {/if}
</div>

<style>
  .replacement-status,
  section {
    display: grid;
    gap: 12px;
    min-width: 0;
  }
  h4,
  p,
  dl {
    margin: 0;
  }
  h4 {
    font-size: 14px;
  }
  dl {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
  }
  dt,
  small {
    color: var(--admin-muted);
  }
  dd {
    margin: 4px 0 0;
  }
  dd,
  td,
  p,
  li {
    overflow-wrap: anywhere;
  }
  small {
    display: block;
  }
  @media (max-width: 560px) {
    dl {
      grid-template-columns: 1fr;
    }
  }
</style>
