<script lang="ts">
  import { onDestroy } from "svelte";
  import { Input, Textarea } from "$components/ui";
  import { AdminButton, AdminField } from "$components/patterns/admin";
  import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi";
  import type { components } from "$lib/api/openapi.generated";
  import type { ConsoleNodesTranslate } from "$lib/admin/consoleNodesTypes";
  import { resourcePort } from "$lib/admin/resourceIntent";
  import { resourceErrorKey } from "$lib/admin/resourceOperations";
  let {
    api,
    at,
    available,
  }: { api: ApiClient["api"]; at: ConsoleNodesTranslate; available: boolean } = $props();
  let port = $state("");
  let credentials = $state<components["schemas"]["ConsoleNodeDeploymentOut"] | null>(null);
  let busy = $state(false);
  let error = $state("");
  let active = true;
  let controller: AbortController | null = null;
  const config = $derived(
    credentials
      ? `services:\n  node:\n    image: remnawave/node:${credentials.recorded_node_version}\n    network_mode: host\n    environment:\n      NODE_PORT: ${JSON.stringify(String(credentials.management_port))}\n      SECRET_KEY: ${JSON.stringify(credentials.secret_key)}\n`
      : ""
  );
  async function generate() {
    if (!available || busy || !/^\d+$/.test(port) || !resourcePort(Number(port))) return;
    busy = true;
    error = "";
    credentials = null;
    controller = new AbortController();
    try {
      const value = unwrap(
        await api(
          builtApiPath<"/api/admin/console/nodes/onboarding/deployment">(
            "/admin/console/nodes/onboarding/deployment"
          ),
          {
            method: "POST" as const,
            body: JSON.stringify({
              management_port: Number(port),
            } satisfies components["schemas"]["ConsoleNodeDeploymentBody"]),
            signal: controller.signal,
          }
        )
      );
      if (active) credentials = value;
    } catch (failure) {
      if (active) error = resourceErrorKey(failure);
    } finally {
      if (active) busy = false;
    }
  }
  onDestroy(() => {
    active = false;
    controller?.abort();
    credentials = null;
  });
</script>

<section class="node-deployment" aria-label={at("resource_ops_deployment")}>
  <h3>{at("resource_ops_deployment")}</h3>
  <p>{at("resource_ops_deployment_scope")}</p>
  <form
    onsubmit={(event) => {
      event.preventDefault();
      void generate();
    }}
  >
    <AdminField label={at("resource_ops_management_port")}
      ><Input
        bind:value={port}
        disabled={busy}
        inputmode="numeric"
        maxlength={5}
        required
        pattern={"[0-9]+"}
        aria-label={at("resource_ops_management_port")}
      /></AdminField
    >
    <div>
      <AdminButton
        type="submit"
        disabled={!available || busy || !/^\d+$/.test(port) || !resourcePort(Number(port))}
        >{at("resource_ops_deployment_generate")}</AdminButton
      >
    </div>
  </form>
  {#if !available}<p role="status">{at("resource_ops_error_disabled")}</p>{/if}
  {#if error}<p role="alert">{at(error)}</p>{/if}
  {#if credentials}<p>
      {at("resource_ops_deployment_versions")}: Panel {credentials.panel_version} · Node {credentials.recorded_node_version}
    </p>
    <p>{at("resource_ops_deployment_secret")}</p>
    <Textarea
      readonly
      value={config}
      rows={9}
      spellcheck={false}
      autocomplete="off"
      ariaLabel={at("resource_ops_deployment_config")}
    />
    <code>docker compose up -d</code>
    <div>
      <AdminButton
        onclick={() => {
          credentials = null;
        }}>{at("resource_ops_deployment_clear")}</AdminButton
      >
    </div>
  {/if}
</section>

<style>
  .node-deployment,
  form {
    display: grid;
    gap: 12px;
    min-width: 0;
  }
  h3,
  p {
    margin: 0;
    overflow-wrap: anywhere;
  }
  .node-deployment :global(.textarea) {
    width: 100%;
    min-width: 0;
    box-sizing: border-box;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
</style>
