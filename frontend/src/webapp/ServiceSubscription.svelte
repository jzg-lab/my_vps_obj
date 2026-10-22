<script lang="ts">
  import { onDestroy } from "svelte";
  import Button from "$components/ui/button.svelte";
  import CopyLinkField from "$components/patterns/CopyLinkField.svelte";
  import { lazyScreen } from "$lib/webapp/lazyScreen.svelte.js";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi.js";
  import type { Translate } from "$lib/webapp/types.js";

  let { api, serviceId, t }: { api: ApiClient["api"]; serviceId: string; t: Translate } = $props();
  let url = $state("");
  let busy = $state(false);
  let failed = $state(false);
  let copied = $state(false);
  let controller: AbortController | undefined;
  let guideController: AbortController | undefined;
  let guideConfig = $state<Record<string, unknown> | null>(null);
  let guideLoading = $state(false);
  let guideFailed = $state(false);
  const guideScreen = lazyScreen(() => import("./screens/InstallGuideScreen.svelte"));
  async function loadGuide() {
    guideScreen.load();
    if (guideConfig || guideLoading) return;
    guideController?.abort();
    const current = new AbortController();
    guideController = current;
    guideLoading = true;
    guideFailed = false;
    try {
      const result = unwrap(
        await api(builtApiPath<"/api/service-guides">("/service-guides"), {
          signal: current.signal,
        })
      );
      if (!current.signal.aborted) guideConfig = result.config;
    } catch {
      if (!current.signal.aborted) guideFailed = true;
    } finally {
      if (!current.signal.aborted) guideLoading = false;
    }
  }
  async function load() {
    controller?.abort();
    const current = new AbortController();
    controller = current;
    busy = true;
    failed = false;
    url = "";
    copied = false;
    try {
      const result = unwrap(
        await api(
          builtApiPath<"/api/services/{service_id}/subscription">(
            `/services/${encodeURIComponent(serviceId)}/subscription`
          ),
          { signal: current.signal }
        )
      );
      if (!current.signal.aborted && result.subscription.service_id === serviceId)
        url = result.subscription.subscription_url;
    } catch {
      if (!current.signal.aborted) failed = true;
    } finally {
      if (!current.signal.aborted) busy = false;
    }
  }
  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      copied = true;
    } catch {
      copied = false;
    }
  }
  onDestroy(() => {
    controller?.abort();
    guideController?.abort();
  });
</script>

<section class="service-subscription" aria-label={t("wa_services_subscription")}>
  <Button disabled={busy} onclick={load}
    >{t(url ? "wa_services_subscription_refresh" : "wa_services_subscription")}</Button
  >
  {#if busy}<p role="status">{t("wa_loading")}</p>{/if}
  {#if failed}<p role="alert">{t("wa_services_delivery_failed")}</p>{/if}
  {#if url}
    <CopyLinkField
      value={url}
      inputLabel={t("wa_services_subscription")}
      copyLabel={t("wa_copy")}
      {copied}
      oncopy={copy}
    />
    <p>{t("wa_services_subscription_private")}</p>
    <p>{t("wa_services_subscription_import")}</p>
    <p>{t("wa_services_subscription_update")}</p>
    <details
      class="service-guide"
      ontoggle={(event) => event.currentTarget.open && void loadGuide()}
    >
      <summary>{t("wa_install_title")}</summary>
      {#if guideScreen.component && guideConfig}
        {@const Guide = guideScreen.component}
        <Guide
          serviceMode
          serviceConfig={guideConfig}
          currentLang={typeof document === "undefined" ? "ru" : document.documentElement.lang}
          subscription={{ config_link: url }}
          {t}
          copyText={async (value) => copy(value)}
          openExternalLink={(value) => window.open(value, "_blank", "noopener,noreferrer")}
        />
      {:else if guideFailed || guideScreen.failed}
        <p role="alert">{t("wa_install_unavailable")}</p>
        <Button onclick={loadGuide}>{t("wa_install_retry")}</Button>
      {:else}
        <p role="status">{t("wa_install_loading")}</p>
      {/if}
    </details>
  {/if}
</section>

<style>
  .service-subscription {
    display: grid;
    gap: 12px;
    min-width: 0;
  }
  p {
    margin: 0;
    color: var(--muted);
    line-height: 1.6;
    overflow-wrap: anywhere;
  }
  .service-guide {
    min-width: 0;
  }
  .service-guide summary {
    cursor: pointer;
    font-weight: 600;
  }
</style>
