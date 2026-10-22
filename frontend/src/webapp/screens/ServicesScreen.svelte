<script lang="ts">
  import { onDestroy } from "svelte";
  import ServiceSubscription from "../ServiceSubscription.svelte";
  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import { RefreshCw, ArrowRight } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";
  import Badge from "$components/ui/badge.svelte";
  import Dialog from "$components/ui/dialog.svelte";
  import { AdminPagination } from "$components/patterns/admin/index.js";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi.js";
  import { serviceBytes } from "$lib/admin/servicePlans.js";
  import {
    serviceDate,
    serviceUsage,
    serviceStatusKey,
    type UserService,
    type CatalogPlan,
  } from "$lib/webapp/independentServices.js";
  import type { Translate, BrandConfig } from "$lib/webapp/types.js";

  let {
    api,
    t,
    brand,
    brandTitle,
  }: {
    api: ApiClient["api"];
    t: Translate;
    brand: BrandConfig;
    brandTitle: string;
  } = $props();
  let tab = $state<"services" | "catalog">("services");
  let page = $state(0);
  let revision = $state(0);
  let services = $state<UserService[]>([]);
  let plans = $state<CatalogPlan[]>([]);
  let total = $state(0);
  let loading = $state(true);
  let failed = $state(false);
  let selectedId = $state("");
  let detail = $state<UserService | null>(null);
  let detailLoading = $state(false);
  let detailFailed = $state(false);
  let detailController: AbortController | undefined;
  const pageSize = 10;

  $effect(() => {
    const currentTab = tab;
    const currentPage = page;
    void revision;
    const controller = new AbortController();
    loading = true;
    failed = false;
    void (async () => {
      try {
        const query = `?limit=${pageSize}&offset=${currentPage * pageSize}`;
        if (currentTab === "services") {
          const result = unwrap(
            await api(builtApiPath<"/api/services">(`/services${query}`), {
              signal: controller.signal,
            })
          );
          if (controller.signal.aborted) return;
          services = result.services;
          total = result.total;
        } else {
          const result = unwrap(
            await api(builtApiPath<"/api/service-catalog">(`/service-catalog${query}`), {
              signal: controller.signal,
            })
          );
          if (controller.signal.aborted) return;
          plans = result.plans;
          total = result.total;
        }
        if (currentPage > 0 && currentPage * pageSize >= total)
          page = Math.max(0, Math.ceil(total / pageSize) - 1);
      } catch {
        if (!controller.signal.aborted) failed = true;
      } finally {
        if (!controller.signal.aborted) loading = false;
      }
    })();
    return () => controller.abort();
  });

  async function openDetail(id: string) {
    detailController?.abort();
    const controller = new AbortController();
    detailController = controller;
    selectedId = id;
    detail = null;
    detailLoading = true;
    detailFailed = false;
    try {
      const result = unwrap(
        await api(
          builtApiPath<"/api/services/{service_id}">(`/services/${encodeURIComponent(id)}`),
          {
            signal: controller.signal,
          }
        )
      );
      if (!controller.signal.aborted) detail = result.service;
    } catch {
      if (!controller.signal.aborted) detailFailed = true;
    } finally {
      if (!controller.signal.aborted) detailLoading = false;
    }
  }
  function closeDetail() {
    detailController?.abort();
    selectedId = "";
    detail = null;
  }
  onDestroy(() => detailController?.abort());
</script>

{#snippet terms(item: UserService | CatalogPlan)}
  <p class="service-kind">
    {t(`wa_services_resource_${item.resource_type}`)} · {t(`wa_services_rule_${item.traffic_rule}`)}
  </p>
{/snippet}

{#snippet serviceFacts(service: UserService)}
  {@const usage = serviceUsage(service)}
  <dl class="service-facts">
    <div>
      <dt>{t("wa_services_used")}</dt>
      <dd>{serviceBytes(service.used_bytes)} / {serviceBytes(service.quota_bytes)}</dd>
    </div>
    <div>
      <dt>{t("wa_services_remaining")}</dt>
      <dd>{serviceBytes(usage.remaining)}</dd>
    </div>
    <div>
      <dt>{t("wa_services_expires")}</dt>
      <dd>{serviceDate(service.expires_at)}</dd>
    </div>
    {#if service.traffic_rule === "monthly"}
      <div>
        <dt>{t("wa_services_next_reset")}</dt>
        <dd>{serviceDate(service.cycle_ends_at)}</dd>
      </div>
    {/if}
  </dl>
  <progress value={usage.percent} max="100" aria-label={t("wa_services_used")}></progress>
  {#if usage.overage > 0}<p class="service-warning">
      {t("wa_services_overage", { amount: serviceBytes(usage.overage) })}
    </p>{/if}
  <p class="service-sync">
    {t("wa_services_last_sync")}: {service.last_usage_sync_at
      ? serviceDate(service.last_usage_sync_at)
      : t("wa_services_not_synced")}
  </p>
  {#if service.cycle_pending}<p class="service-sync" role="status">
      {t("wa_services_cycle_pending")}
    </p>{/if}
  {#if service.sync_pending}<p class="service-sync" role="status">
      {t("wa_services_change_pending")}
    </p>{/if}
  {#if service.usage_error}<p class="service-sync" role="status">
      {t("wa_services_usage_unconfirmed")}
    </p>{/if}
{/snippet}

<main class="content with-nav services-screen">
  <header class="services-header">
    <div class="brand-row"><BrandMark {brand} /><strong>{brandTitle}</strong></div>
    <h1>{t("wa_services_title")}</h1>
    <p>{t("wa_services_independent_hint")}</p>
  </header>
  <div class="services-toolbar">
    <div class="services-tabs" role="group" aria-label={t("wa_services_title")}>
      <Button
        variant={tab === "services" ? "default" : "secondary"}
        aria-pressed={tab === "services"}
        onclick={() => {
          tab = "services";
          page = 0;
        }}>{t("wa_services_title")}</Button
      >
      <Button
        variant={tab === "catalog" ? "default" : "secondary"}
        aria-pressed={tab === "catalog"}
        onclick={() => {
          tab = "catalog";
          page = 0;
        }}>{t("wa_services_catalog")}</Button
      >
    </div>
    <Button variant="ghost" disabled={loading} onclick={() => revision++}
      ><RefreshCw size={16} />{t("wa_services_refresh")}</Button
    >
  </div>
  <section
    aria-label={t(tab === "services" ? "wa_services_title" : "wa_services_catalog")}
    aria-busy={loading}
  >
    {#if loading}<Card><p role="status">{t("wa_loading")}</p></Card>
    {:else if failed}<Card
        ><p role="alert">{t("wa_services_load_failed")}</p>
        <Button variant="secondary" onclick={() => revision++}>{t("wa_services_retry")}</Button
        ></Card
      >
    {:else if tab === "services"}
      {#if !services.length}<Card
          ><h2>{t("wa_services_empty")}</h2>
          <p>{t("wa_services_manual_hint")}</p></Card
        >{/if}
      <div class="services-grid">
        {#each services as service (service.id)}
          <Card data-service-id={service.id}>
            <div class="service-heading">
              <h2>{service.name}</h2>
              <Badge wrap variant={service.status === "active" ? "success" : "muted"}
                >{t(serviceStatusKey(service.status))}</Badge
              >
            </div>
            {@render terms(service)}
            <p class="service-id">{t("wa_services_id")}: {service.id}</p>
            {@render serviceFacts(service)}
            <Button variant="secondary" onclick={() => openDetail(service.id)}
              >{t("wa_services_details")}<ArrowRight size={16} /></Button
            >
          </Card>
        {/each}
      </div>
    {:else}
      <p>{t("wa_services_manual_hint")}</p>
      {#if !plans.length}<Card><p>{t("wa_services_catalog_empty")}</p></Card>{/if}
      <div class="services-grid">
        {#each plans as plan (plan.id)}
          <Card>
            <h2>{plan.name}</h2>
            {@render terms(plan)}
            {#if plan.description}<p class="service-description">{plan.description}</p>{/if}
            <dl class="service-facts">
              <div>
                <dt>{t("wa_services_quota")}</dt>
                <dd>{serviceBytes(plan.quota_bytes)}</dd>
              </div>
              <div>
                <dt>{t("wa_services_validity")}</dt>
                <dd>{t("wa_services_days", { days: plan.validity_days })}</dd>
              </div>
              <div>
                <dt>{t("wa_services_price")}</dt>
                <dd>{plan.price} {plan.currency}</dd>
              </div>
            </dl>
          </Card>
        {/each}
      </div>
    {/if}
    {#if !loading && !failed && total > pageSize}
      <AdminPagination
        appearance="webapp"
        {page}
        {total}
        pageCount={Math.ceil(total / pageSize)}
        onPageChange={(value) => (page = value)}
        prevLabel={t("wa_services_previous")}
        nextLabel={t("wa_services_next")}
        pageLabel={t("wa_services_page")}
        ofLabel="/"
        totalLabel={t("wa_services_count")}
        jumpLabel={t("wa_services_page")}
        jumpAriaLabel={t("wa_services_page")}
        goLabel={t("wa_services_go")}
      />
    {/if}
  </section>
  <p class="service-sync">{t("wa_services_timezone")}</p>
</main>

<Dialog
  open={Boolean(selectedId)}
  title={detail?.name || t("wa_services_details")}
  closeLabel={t("wa_close")}
  onclose={closeDetail}
>
  {#if detailLoading}<p role="status">{t("wa_loading")}</p>
  {:else if detailFailed}<p role="alert">{t("wa_services_load_failed")}</p>
    <Button onclick={() => openDetail(selectedId)}>{t("wa_services_retry")}</Button>
  {:else if detail}
    <div class="service-detail">
      <Badge wrap variant={detail.status === "active" ? "success" : "muted"}
        >{t(serviceStatusKey(detail.status))}</Badge
      >
      {@render terms(detail)}
      <p class="service-id">{t("wa_services_id")}: {detail.id}</p>
      {#if detail.description}<p class="service-description">{detail.description}</p>{/if}
      {@render serviceFacts(detail)}
      <dl class="service-facts">
        <div>
          <dt>{t("wa_services_started")}</dt>
          <dd>{serviceDate(detail.starts_at)}</dd>
        </div>
        {#if detail.resource_type === "dedicated"}<div>
            <dt>{t("wa_services_exit")}</dt>
            <dd>
              {detail.exit_ip || "—"} · {t(
                detail.exit_verified ? "wa_services_exit_verified" : "wa_services_exit_pending"
              )}
            </dd>
          </div>{/if}
      </dl>
      {#if detail.status === "active" && !detail.sync_pending}
        {#key detail.id}<ServiceSubscription {api} {t} serviceId={detail.id} />{/key}
      {:else}<p>
          {t(
            detail.status === "pending"
              ? "wa_services_connection_pending"
              : "wa_services_connection_unavailable"
          )}
        </p>
      {/if}
      {#if detail.traffic_rule === "monthly"}<p class="service-sync">
          {t("wa_services_monthly_hint")}
        </p>{/if}
      <p class="service-sync">{t("wa_services_timezone")}</p>
    </div>
  {/if}
</Dialog>

<style>
  .services-screen,
  .service-detail {
    min-width: 0;
  }
  .services-header {
    margin: 8px 0 20px;
  }
  h1 {
    margin: 20px 0 8px;
    font-size: 26px;
  }
  h2 {
    margin: 0;
    font-size: 18px;
    overflow-wrap: anywhere;
  }
  p {
    line-height: 1.6;
  }
  .services-header p,
  .service-kind,
  .service-sync,
  dt {
    color: var(--muted);
  }
  .services-toolbar,
  .services-tabs,
  .service-heading {
    display: flex;
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
  }
  .services-toolbar {
    justify-content: space-between;
    margin-bottom: 18px;
  }
  .services-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr));
    gap: 16px;
  }
  .services-grid :global(.card) {
    min-width: 0;
    margin: 0;
  }
  .service-heading {
    justify-content: space-between;
    align-items: start;
  }
  .service-heading h2 {
    flex: 1 1 150px;
  }
  .service-facts {
    display: grid;
    gap: 12px;
    margin: 18px 0;
  }
  .service-facts > div {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 12px;
    flex-wrap: wrap;
  }
  dt {
    font-size: 13px;
  }
  dd {
    margin: 0;
    font-variant-numeric: tabular-nums;
    overflow-wrap: anywhere;
  }
  .service-sync,
  .service-id {
    font-size: 12px;
  }
  .service-id {
    color: var(--muted);
    overflow-wrap: anywhere;
    font-family: monospace;
  }
  .service-description {
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .service-warning {
    color: var(--danger, #e44b4b);
  }
  progress {
    width: 100%;
    height: 8px;
    accent-color: var(--accent);
  }
</style>
