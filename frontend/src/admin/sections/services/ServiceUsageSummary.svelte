<script lang="ts">
  import { AdminBadge, AdminTrafficCard } from "$components/patterns/admin/index.js";
  import { serviceBytes, type UserService, type ServiceTranslate } from "$lib/admin/servicePlans";
  import { serviceUsage, serviceDate, serviceResetState } from "$lib/webapp/independentServices";
  let { service, at }: { service: UserService; at: ServiceTranslate } = $props();
  const usage = $derived(serviceUsage(service));
  const reset = $derived(serviceResetState(service));
</script>

<div class="quota">
  <h4>{service.name}</h4>
  <AdminBadge variant={service.status === "active" ? "success" : "muted"}
    >{at(`services_status_${service.status}`)}</AdminBadge
  >
  {#if usage.remaining !== null}
    <AdminTrafficCard
      title={at("services_used")}
      value={`${serviceBytes(service.used_bytes)} / ${serviceBytes(service.quota_bytes)}`}
      percent={usage.percent ?? 0}
      warning={Boolean(service.usage_error)}
      left={`${at("services_remaining")}: ${serviceBytes(usage.remaining)}`}
    />
  {:else}<p>
      {at(service.usage_error ? "services_usage_unconfirmed" : "services_usage_missing")} · {at(
        "services_used"
      )}: {at("console_unknown")} / {serviceBytes(service.quota_bytes)}
    </p>{/if}
  <p>{at("console_visual_cycle")}: {at(`services_${service.traffic_rule}`)}</p>
  {#if service.last_usage_sync_at}<p>
      {at("services_last_sync")}: {serviceDate(service.last_usage_sync_at)}
    </p>{/if}
  {#if service.traffic_rule === "monthly"}<p>
      {at("services_next_reset")}: {reset === "ended"
        ? at("services_no_further_reset")
        : reset === "expires_first"
          ? at("services_expires_before_reset")
          : reset === "scheduled"
            ? serviceDate(service.cycle_ends_at)
            : at("console_unknown")}
    </p>{/if}
  <p>{at("services_expires")}: {serviceDate(service.expires_at)}</p>
  {#if service.usage_error && service.last_usage_sync_at}<p role="status">
      {at("services_usage_stale")}
    </p>{/if}
</div>

<style>
  .quota {
    display: grid;
    gap: 12px;
    min-width: 0;
    padding: 20px;
    border: 1px solid var(--admin-border);
    border-radius: 14px;
    background: var(--admin-surface);
  }
  h4,
  p {
    margin: 0;
  }
  p {
    font-size: 12px;
    color: var(--admin-muted);
    line-height: 1.6;
    overflow-wrap: anywhere;
  }
  .quota :global(.admin-badge) {
    justify-self: start;
  }
</style>
