<script lang="ts">
  import { onDestroy } from "svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import { AdminBadge, AdminButton, AdminEntityLink } from "$components/patterns/admin/index.js";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi";
  import { customerLabel } from "$lib/admin/consoleServices";
  import type { components } from "$lib/api/openapi.generated";
  import { serviceBytes, type ServiceTranslate } from "$lib/admin/servicePlans";
  import { serviceDate, serviceResetState, serviceUsage } from "$lib/webapp/independentServices";
  import { isTemporaryServiceReadFailure } from "$lib/webapp/serviceReadFailure";
  import ServiceActions from "./ServiceActions.svelte";
  import ServiceActivationAction from "./ServiceActivationAction.svelte";
  import ServiceUsageVisual from "./ServiceUsageVisual.svelte";

  let {
    api,
    at,
    serviceId,
    routePrefix = "",
    onOpenUserCard,
    onclose,
  }: {
    api: ApiClient["api"];
    at: ServiceTranslate;
    serviceId: string;
    routePrefix?: string;
    onOpenUserCard: (id: unknown) => void;
    onclose: () => void;
  } = $props();
  let row = $state<components["schemas"]["ConsoleServiceDetailOut"] | null>(null);
  let failed = $state(false);
  let loading = $state(true);
  let readAt = $state("");
  let scope = "";
  let scopeApi: ApiClient["api"] | undefined;
  let actionOpen = $state(false);
  let activationOpen = $state(false);
  const ownerId = $derived(row?.service.user_id == null ? null : (row?.customer.user_id ?? null));
  let request = 0;
  let controller: AbortController | null = null;
  const connectionTimes = [
    "attempted_at",
    "sync_attempted_at",
    "usage_attempted_at",
    "revoked_at",
  ] as const;
  async function load(id: string) {
    const token = ++request;
    controller?.abort();
    controller = new AbortController();
    loading = true;
    failed = false;
    if (scope !== id || scopeApi !== api) {
      scope = id;
      scopeApi = api;
      row = null;
      readAt = "";
    }
    try {
      const result = unwrap(
        await api(
          builtApiPath<"/api/admin/console/services/{service_id}">(
            `/admin/console/services/${encodeURIComponent(id)}`
          ),
          { signal: controller.signal }
        )
      );
      if (request === token) {
        row = result;
        readAt = new Date().toISOString();
      }
    } catch (error) {
      if (request === token) {
        failed = true;
        if (!isTemporaryServiceReadFailure(error)) {
          row = null;
          readAt = "";
        }
      }
    } finally {
      if (request === token) loading = false;
    }
  }
  $effect(() => {
    void load(serviceId);
  });
  onDestroy(() => {
    request++;
    controller?.abort();
  });
</script>

<Dialog
  open
  size="wide"
  title={at("console_service_detail")}
  closeLabel={at("close")}
  focusOnOpen={!actionOpen && !activationOpen}
  focusKey={`${loading}:${actionOpen}:${activationOpen}`}
  {onclose}
  class="admin-dialog"
>
  <div class="console-service-detail" aria-busy={loading}>
    {#if failed}<p role="alert">
        {at("console_detail_failed")}
        {readAt
          ? at("services_snapshot_stale", { time: serviceDate(readAt) })
          : at("services_snapshot_unknown")}
      </p>
      {#if !row}<AdminButton onclick={() => load(serviceId)}>{at("refresh")}</AdminButton>{/if}
    {:else if loading}<p role="status">{at("loading")}</p>
    {/if}
    {#if row}
      {@const service = row.service}
      {@const customer = row.customer}
      {@const usage = serviceUsage(service)}
      {@const reset = serviceResetState(service)}
      <h3>{service.name}</h3>
      <p class="service-id">{service.id}</p>
      {#if ownerId === null}
        <p><strong>{at("user_deleted")}</strong> · {at("services_history_title")}</p>
        <p class="admin-muted">{at("services_history_hint")}</p>
      {:else}
        <AdminEntityLink
          label={customerLabel(customer)}
          idText={customer.minishop_id ?? undefined}
          onclick={() => onOpenUserCard(ownerId)}
        />
      {/if}
      <AdminBadge variant={service.status === "active" ? "success" : "muted"}
        >{at(`services_status_${service.status}`)}</AdminBadge
      >
      <dl>
        <div>
          <dt>{at("services_used")}</dt>
          <dd>
            {service.last_usage_sync_at ? serviceBytes(service.used_bytes) : at("console_unknown")} /
            {serviceBytes(service.quota_bytes)}
          </dd>
        </div>
        <div>
          <dt>{at("services_remaining")}</dt>
          <dd>
            {usage.remaining === null ? at("console_unknown") : serviceBytes(usage.remaining)}
          </dd>
        </div>
        <div>
          <dt>{at("services_last_sync")}</dt>
          <dd>
            {service.last_usage_sync_at
              ? serviceDate(service.last_usage_sync_at)
              : at("services_never_synced")}
          </dd>
        </div>
        <div>
          <dt>{at("services_expires")}</dt>
          <dd>{serviceDate(service.expires_at)}</dd>
        </div>
        {#if service.traffic_rule === "monthly"}<div>
            <dt>{at("services_next_reset")}</dt>
            <dd>
              {reset === "ended"
                ? at("services_no_further_reset")
                : reset === "expires_first"
                  ? at("services_expires_before_reset")
                  : reset === "scheduled"
                    ? serviceDate(service.cycle_ends_at)
                    : at("console_unknown")}
            </dd>
          </div>{/if}
        <div>
          <dt>{at("services_exit_ip")}</dt>
          <dd>
            {service.exit_ip || "—"}{#if service.exit_ip}
              · {at(service.exit_verified ? "services_verified" : "services_unverified")}{/if}
          </dd>
        </div>
        <div>
          <dt>{at("console_delivery")}</dt>
          <dd>{at(`console_connection_${service.connection_state}`)}</dd>
        </div>
      </dl>
      {#if service.sync_error}<p role="status">
          {at("console_filter_sync_error")}
        </p>{:else if service.sync_pending}<p role="status">{at("services_sync_pending")}</p>{/if}
      {#if usage.overage !== null && usage.overage > 0}<p role="status">
          {at("services_usage_overage", { amount: serviceBytes(usage.overage) })}
        </p>{/if}
      {#if service.usage_error}<p role="status">
          {at(service.last_usage_sync_at ? "services_usage_stale" : "services_usage_unconfirmed")}
        </p>{/if}
      {#if !service.last_usage_sync_at}<p role="status">{at("services_usage_missing")}</p>{/if}
      {#if service.cycle_pending}<p role="status">{at("services_cycle_pending")}</p>{/if}
      <section aria-label={at("console_connection_details")}>
        <h4>{at("console_connection_details")}</h4>
        <dl>
          <div>
            <dt>{at("console_connection_identity")}</dt>
            <dd>{row.connection?.panel_user_uuid || at("console_unknown")}</dd>
          </div>
          {#each connectionTimes as field}
            {@const value = row.connection?.[field]}
            <div>
              <dt>{at(`console_connection_${field}`)}</dt>
              <dd>{value ? serviceDate(value) : at("console_unknown")}</dd>
            </div>
          {/each}
          <div>
            <dt>{at("console_latest_success")}</dt>
            <dd>
              {service.sync_confirmed_at
                ? serviceDate(service.sync_confirmed_at)
                : at("console_unknown")}
            </dd>
          </div>
        </dl>
        {#if row.connection?.last_error}<p role="status">{at("console_connection_error")}</p>{/if}
      </section>
      <section aria-label={at("console_terms_snapshot")}>
        <h4>{at("console_terms_snapshot")}</h4>
        <p class="admin-muted">{at("services_order_history_hint")}</p>
        <dl>
          <div>
            <dt>{at("services_name")}</dt>
            <dd>{row.terms.name}</dd>
          </div>
          <div>
            <dt>{at("services_revision", { revision: service.plan_revision })}</dt>
            <dd>{service.plan_id}</dd>
          </div>
          <div>
            <dt>{at("services_resource_type")}</dt>
            <dd>{at(`services_${row.terms.resource_type}`)}</dd>
          </div>
          <div>
            <dt>{at("services_traffic_rule")}</dt>
            <dd>{at(`services_${row.terms.traffic_rule}`)}</dd>
          </div>
          <div>
            <dt>{at("services_quota")}</dt>
            <dd>{serviceBytes(row.terms.quota_bytes)}</dd>
          </div>
          <div>
            <dt>{at("services_validity_days")}</dt>
            <dd>{row.terms.validity_days}</dd>
          </div>
          <div>
            <dt>{at("services_recorded_price")}</dt>
            <dd>{row.terms.price} {row.terms.currency}</dd>
          </div>
          <div>
            <dt>{at("services_squads")}</dt>
            <dd>{row.terms.squad_uuids?.join(", ") || "—"}</dd>
          </div>
          <div>
            <dt>{at("services_pool")}</dt>
            <dd>{row.terms.resource_pool || "—"}</dd>
          </div>
        </dl>
        {#if row.terms.description}<p>{row.terms.description}</p>{/if}
      </section>
      <div class="actions">
        <ServiceActions
          {api}
          {at}
          {service}
          {routePrefix}
          readonly={ownerId === null}
          banned={customer.is_banned === true}
          disabled={loading || failed || activationOpen}
          bind:dialogOpen={actionOpen}
          onrefresh={() => load(serviceId)}
        />
        <ServiceActivationAction
          {api}
          {at}
          userId={ownerId}
          banned={customer.is_banned === true}
          disabled={loading || failed || actionOpen}
          bind:dialogOpen={activationOpen}
          oncreated={() => {
            if (ownerId !== null) onOpenUserCard(ownerId);
          }}
          onrefresh={() => void load(serviceId)}
        />
        <AdminButton
          disabled={loading || actionOpen || activationOpen}
          onclick={() => load(serviceId)}>{at("refresh")}</AdminButton
        >{#if ownerId !== null}<AdminButton
            disabled={actionOpen || activationOpen}
            onclick={() => onOpenUserCard(ownerId)}>{at("console_manage_customer")}</AdminButton
          >{/if}
      </div>
      <p class="admin-muted">{at("console_period_scope")}</p>
      <ServiceUsageVisual {api} {at} {service} {routePrefix} />
    {/if}
  </div>
</Dialog>

<style>
  .console-service-detail {
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
  h4 {
    font-size: 14px;
    margin-bottom: 12px;
  }
  .service-id {
    overflow-wrap: anywhere;
    color: var(--admin-muted);
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
  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  @media (max-width: 560px) {
    dl {
      grid-template-columns: 1fr;
    }
  }
</style>
