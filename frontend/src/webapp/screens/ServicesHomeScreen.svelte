<script lang="ts">
  import HomeBrand from "../HomeBrand.svelte";
  import { ArrowRight, WalletCards } from "$components/ui/icons.js";
  import Button from "$components/ui/button.svelte";
  import Card from "$components/ui/card.svelte";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi.js";
  import type { BrandConfig, Translate, VoidAction } from "$lib/webapp/types.js";

  let {
    api,
    brand,
    brandTitle,
    goServices,
    t,
  }: {
    api: ApiClient["api"];
    brand: BrandConfig;
    brandTitle: string;
    goServices: VoidAction;
    t: Translate;
  } = $props();

  let total = $state<number | null>(null);
  let failed = $state(false);
  let revision = $state(0);
  $effect(() => {
    void revision;
    const controller = new AbortController();
    total = null;
    failed = false;
    void (async () => {
      try {
        const result = unwrap(
          await api(builtApiPath<"/api/services">("/services?limit=1"), {
            signal: controller.signal,
          })
        );
        if (!controller.signal.aborted) total = result.total;
      } catch {
        if (!controller.signal.aborted) failed = true;
      }
    })();
    return () => controller.abort();
  });
</script>

<main class="home-layout services-home">
  <HomeBrand {brand} {brandTitle} />
  <div class="home-bottom">
    <Card class="services-home-summary" aria-busy={total === null && !failed}>
      <div class="summary-heading">
        <WalletCards size={24} />
        <div>
          <h2>{t("wa_services_nav")}</h2>
          {#if failed}
            <p role="alert">{t("wa_services_load_failed")}</p>
          {:else if total === null}
            <p role="status">{t("wa_loading")}</p>
          {:else if total === 0}
            <p>{t("wa_services_empty")}</p>
          {:else}
            <p>{t("wa_services_home_count", { count: total })}</p>
          {/if}
        </div>
      </div>
      <p class="summary-hint">{t("wa_services_home_hint")}</p>
      <div class="summary-actions">
        {#if failed}
          <Button variant="secondary" onclick={() => revision++}>{t("wa_services_refresh")}</Button>
        {/if}
        <Button onclick={goServices}>{t("wa_services_home_open")}<ArrowRight size={18} /></Button>
      </div>
    </Card>
  </div>
</main>

<style>
  .summary-heading {
    display: flex;
    align-items: center;
    gap: 14px;
  }
  .summary-heading > :global(svg) {
    flex-shrink: 0;
    color: var(--accent);
  }
  h2 {
    margin: 0;
    font-size: 18px;
  }
  p {
    margin: 5px 0 0;
    color: var(--muted);
    font-size: 13px;
    line-height: 1.5;
    overflow-wrap: anywhere;
  }
  .summary-hint {
    margin-top: 14px;
  }
  .summary-actions {
    display: flex;
    gap: 8px;
    margin-top: 18px;
  }
  .summary-actions :global(button) {
    flex: 1;
  }
</style>
