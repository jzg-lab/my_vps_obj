<script lang="ts">
  import type { ServiceTranslate } from "$lib/admin/servicePlans";
  import { serviceBytes } from "$lib/admin/servicePlans";
  import { serviceDate } from "$lib/webapp/independentServices";
  import {
    consoleServiceErrorKey,
    consoleServiceLabel,
    type ServiceDiagnostics,
  } from "$lib/admin/consoleServiceOperations";
  let { at, data }: { at: ServiceTranslate; data: ServiceDiagnostics } = $props();
  const date = (value: string | null) => (value ? serviceDate(value) : at("console_unknown"));
  const observed = (value: boolean | null) =>
    at(value === null ? "console_unknown" : value ? "console_ops_yes" : "console_ops_no");
</script>

<section aria-label={at("console_ops_diagnostics")}>
  <h4>{at("console_ops_local")}</h4>
  <dl>
    <dt>{at("console_ops_observed_local")}</dt>
    <dd>{date(data.local_observed_at)}</dd>
    <dt>{at("console_ops_service_revision")}</dt>
    <dd>{data.service_revision}</dd>
    <dt>{at("console_ops_business_status")}</dt>
    <dd>{at(consoleServiceLabel("status", data.status))}</dd>
    <dt>{at("console_ops_desired_status")}</dt>
    <dd>{at(consoleServiceLabel("status", data.desired_status))}</dd>
    <dt>{at("console_ops_target_access")}</dt>
    <dd>{at(consoleServiceLabel("access", data.target_access))}</dd>
    <dt>{at("console_delivery")}</dt>
    <dd>{at(consoleServiceLabel("connection", data.connection_state))}</dd>
    <dt>{at("services_sync_pending")}</dt>
    <dd>{observed(data.sync_pending)}</dd>
    <dt>{at("services_last_sync")}</dt>
    <dd>{date(data.last_usage_sync_at)}</dd>
    <dt>{at("console_latest_success")}</dt>
    <dd>{date(data.sync_confirmed_at)}</dd>
    {#each Object.entries(data.errors) as [phase, error]}
      <dt>{at(consoleServiceLabel("phase", phase === "preparation" ? "prepare" : phase))}</dt>
      <dd>
        {error ? at(consoleServiceErrorKey(error)) : at("console_ops_no_reported_error")}
      </dd>
    {/each}
  </dl>
  <h4>{at("console_ops_remote")}</h4>
  <p>{at("console_ops_remote_scope")}</p>
  <dl>
    <dt>{at("console_ops_availability")}</dt>
    <dd>{at(consoleServiceLabel("remote", data.remote.availability))}</dd>
    <dt>{at("console_ops_attempted_at")}</dt>
    <dd>{date(data.remote.attempted_at)}</dd>
    <dt>{at("console_ops_observed_remote")}</dt>
    <dd>{date(data.remote.observed_at)}</dd>
    <dt>{at("console_ops_remote_status")}</dt>
    <dd>{at(consoleServiceLabel("remoteStatus", data.remote.status))}</dd>
    <dt>{at("console_ops_identity_matches")}</dt>
    <dd>{observed(data.remote.identity_matches)}</dd>
    <dt>{at("console_ops_terms_match")}</dt>
    <dd>{observed(data.remote.terms_match)}</dd>
    <dt>{at("console_ops_usage_readable")}</dt>
    <dd>{observed(data.remote.usage_readable)}</dd>
    <dt>{at("console_ops_raw_usage")}</dt>
    <dd>
      {data.remote.raw_used_bytes === null
        ? at("console_unknown")
        : serviceBytes(data.remote.raw_used_bytes)}
    </dd>
  </dl>
  {#if data.remote.error}<p role="status">{at(consoleServiceErrorKey(data.remote.error))}</p>{/if}
  <h4>{at("console_ops_next_steps")}</h4>
  <ul>
    {#each data.next_steps as step}<li>
        {at(
          consoleServiceLabel("next", step) === "console_unknown"
            ? "console_ops_next_unknown"
            : consoleServiceLabel("next", step)
        )}
      </li>{/each}
  </ul>
  <p>{at("console_ops_data_plane_unverified")}</p>
</section>

<style>
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
  p,
  dt {
    color: var(--admin-muted);
  }
  dl {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px 16px;
  }
  dd {
    margin: 0;
    overflow-wrap: anywhere;
  }
  ul {
    margin: 0;
    padding-left: 20px;
  }
  @media (max-width: 560px) {
    dl {
      grid-template-columns: 1fr;
    }
    dd {
      margin-bottom: 8px;
    }
  }
</style>
