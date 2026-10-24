import { readFileSync } from "node:fs";
import type { ComponentProps } from "svelte";
import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import { consoleNodeServiceFixture } from "$lib/admin/consoleNodesFixtures";
import type { UserService } from "$lib/admin/servicePlans";
import { serviceChangeActions } from "$lib/admin/serviceChanges";
import { resolveLocaleKey } from "$lib/webapp/constants";
import ServiceActions from "./ServiceActions.svelte";
import ServiceActivationAction from "./ServiceActivationAction.svelte";

const api = vi.fn().mockResolvedValue({ ok: true });
const at = (key: string) => key;
const noop = () => {};
const service = consoleNodeServiceFixture.service;
const pending: UserService = {
  ...service,
  status: "pending",
  connection_state: "pending",
};
function actions(value: UserService, props: Partial<ComponentProps<typeof ServiceActions>> = {}) {
  return render(ServiceActions, {
    props: { api, at, service: value, onrefresh: noop, ...props },
  }).body;
}

describe("shared service lifecycle actions", () => {
  it("shows history, management and revoke for an active service", () => {
    const html = actions(service);
    for (const key of ["services_view_history", "services_manage", "services_revoke"])
      expect(html).toContain(key);
    expect(html).not.toContain("services_deliver");
    expect(html).not.toContain("console_service_detail");
    expect(actions(service, { onOpenDetail: noop })).toContain("console_service_detail");
  });

  it("keeps archived services and the history consumer read only", () => {
    for (const html of [
      actions({ ...service, user_id: null }),
      actions(service, { readonly: true }),
    ]) {
      expect(html).toContain("services_view_history");
      for (const key of ["services_manage", "services_revoke", "services_deliver"])
        expect(html).not.toContain(key);
    }
  });

  it.each([
    { last_usage_sync_at: null },
    { usage_error: "panel_usage_reset" },
    { sync_pending: true },
    { connection_state: "ready" },
    { status: "account_banned" },
    { status: "expired" },
    { resource_type: "dedicated", exit_verified: false },
  ] satisfies Partial<UserService>[])("does not offer delivery before readiness: %j", (patch) => {
    expect(actions({ ...pending, ...patch })).not.toContain("services_deliver");
  });

  it("offers delivery for metered shared or verified dedicated pending services", () => {
    expect(actions(pending)).toContain("services_deliver");
    expect(actions({ ...pending, resource_type: "dedicated", exit_verified: true })).toContain(
      "services_deliver"
    );
  });

  it("does not deliver for a banned account even if the service view is stale", () => {
    const html = actions(pending, { banned: true });
    expect(html).not.toContain("services_deliver");
    expect(html).toContain("services_revoke");
    expect(html).toContain("services_view_history");
  });

  it.each(["shared", "dedicated"] as const)(
    "blocks %s delivery during replacement even if sync_pending was lost, retaining other actions",
    (resource_type) => {
      const replacing: UserService = {
        ...pending,
        resource_type,
        exit_verified: true,
        sync_pending: false,
        replacement_order_id: "replacement-order",
      };
      const html = actions(replacing);
      expect(html).not.toContain("services_deliver");
      for (const key of ["services_manage", "services_revoke", "services_view_history"])
        expect(html).toContain(key);
      expect(html).not.toMatch(/<button\b[^>]*\sdisabled(?:\s|=|>)/);
      expect(serviceChangeActions(replacing)).toEqual(expect.arrayContaining(["renew", "pause"]));
      expect(actions({ ...replacing, replacement_order_id: null })).toContain("services_deliver");
    }
  );

  it("keeps exact usage reconciliation available after cancellation until revocation", () => {
    const cancelled: UserService = {
      ...service,
      status: "cancelled",
      desired_status: "cancelled",
      usage_error: "panel_usage_regressed",
    };
    expect(actions(cancelled)).toContain("services_manage");
    expect(actions(cancelled)).not.toContain("services_revoke");
    expect(actions({ ...cancelled, usage_error: null })).not.toContain("services_manage");
    expect(actions({ ...cancelled, connection_state: "revoked" })).not.toContain("services_manage");
  });

  it("disables all triggers while a sibling or service dialog owns the interaction", () => {
    for (const props of [{ disabled: true }, { dialogOpen: true }]) {
      const buttons = [
        ...actions(pending, { ...props, onOpenDetail: noop }).matchAll(/<button\b[^>]*>/g),
      ];
      expect(buttons).toHaveLength(6);
      for (const [button] of buttons) expect(button).toMatch(/\sdisabled(?:\s|=|>)/);
    }
  });
});

describe("shared activation entry", () => {
  it("never opens activation for a null archived owner", () => {
    const html = render(ServiceActivationAction, {
      props: { api, at, userId: null, oncreated: noop, onrefresh: noop },
    }).body;
    expect(html).not.toContain("<button");
    expect(html).not.toContain("services_activate");
  });
  it.each([{ banned: true }, { disabled: true }])(
    "prevents starting activation with %j",
    (props) => {
      const html = render(ServiceActivationAction, {
        props: { api, at, userId: 17, oncreated: noop, onrefresh: noop, ...props },
      }).body;
      expect(html).toContain("services_activate");
      expect(html).toMatch(/<button\b[^>]*\sdisabled(?:\s|=|>)/);
    }
  );
  it("allows an available account to open the existing activation flow", () => {
    const html = render(ServiceActivationAction, {
      props: { api, at, userId: 17, oncreated: noop, onrefresh: noop },
    }).body;
    expect(html).not.toMatch(/<button\b[^>]*\sdisabled(?:\s|=|>)/);
  });
});

const files = [
  "ServiceActions.svelte",
  "ServiceActivationAction.svelte",
  "ServiceActivationDialog.svelte",
  "ServiceChangeDialog.svelte",
  "ServiceDeliverDialog.svelte",
  "ServiceRevokeDialog.svelte",
  "ServiceOrdersDialog.svelte",
  "ServiceDiagnosticsDialog.svelte",
  "ServiceExitReplacementDialog.svelte",
  "ServiceDiagnostics.svelte",
  "ServiceOperationList.svelte",
  "ServicePreflight.svelte",
] as const;
const source = (file: string) => readFileSync(new URL(`./${file}`, import.meta.url), "utf8");

describe("shared consumers and localization", () => {
  it("offers replacement inspection in both consumers without disabling pause, renew or revoke", () => {
    const dedicated: UserService = { ...service, resource_type: "dedicated" };
    for (const key of ["replacement_title", "services_manage", "services_revoke"])
      expect(actions(dedicated)).toContain(key);
    expect(actions({ ...dedicated, user_id: null })).toContain("replacement_title");
    expect(actions({ ...dedicated, user_id: null })).not.toContain("services_manage");
  });
  it.each(["UserServices.svelte", "ConsoleServiceDetail.svelte"])(
    "%s delegates both lifecycle and activation to the shared components",
    (file) => {
      const content = source(file);
      expect(content).toContain("<ServiceActions");
      expect(content).toContain("<ServiceActivationAction");
      expect(content).not.toContain("serviceChangeActions");
      for (const dialog of files.filter((name) => name.endsWith("Dialog.svelte")))
        expect(content).not.toContain(`import ${dialog.replace(".svelte", "")}`);
    }
  );
  it("renders child dialogs outside transformed detail and table ancestors", () => {
    for (const file of files.filter((name) => name.endsWith("Dialog.svelte")))
      expect(source(file)).toMatch(/<Dialog\s+open\s+portal\b/);
  });
  it.each(["en", "ru", "zh-hans"])(
    "provides existing action and dialog labels in %s",
    (language) => {
      const locale: Record<string, string> = JSON.parse(
        readFileSync(new URL(`../../../../../locales/${language}.json`, import.meta.url), "utf8")
      );
      const keys = [...files, "ConsoleServiceDetail.svelte"].flatMap((file) =>
        [...source(file).matchAll(/at\("([^"]+)"/g)].map((match) => match[1])
      );
      keys.push(
        "services_activating",
        "services_saving",
        "services_renew",
        "services_pause",
        "services_resume",
        "services_reconcile_usage"
      );
      for (const key of new Set(keys))
        expect(locale[resolveLocaleKey(`admin_${key}`)], key).toBeTruthy();
    }
  );
});
