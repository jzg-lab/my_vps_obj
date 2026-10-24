import { readFileSync } from "node:fs";
import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import { resolveLocaleKey } from "$lib/webapp/constants";
import { consoleNodeFixture } from "$lib/admin/consoleNodesFixtures";
import {
  consoleResourcePreviewFixture,
  consoleResourceCatalogFixture,
  consoleResourceDraftPreviewFixture,
} from "$lib/webapp/mockApi/consoleResourcePreview";
import { initialDraft } from "./resourceDraftPreview";
import ConsoleResourcePreviewResult from "./ConsoleResourcePreviewResult.svelte";
import { nodeOperations, type NodeChange, type ResourcePreview } from "./resourcePreview";
import { nodePreviewUrl } from "./resourcePreviewNavigation";

const change: NodeChange = {
  operation: "node_disable",
  target_id: consoleNodeFixture.id,
  force_restart: false,
};
const currentUrl = `https://console.test/app/admin/nodes?node_id=${consoleNodeFixture.id}&nodes_q=HK&nodes_page=2&nodes_related_page=1&resource_preview=node&resource_action=node_disable`;
const at = (key: string) => key;
const serviceHref = (serviceId: string) =>
  nodePreviewUrl(
    currentUrl,
    {
      open: true,
      operation: change.operation,
      forceRestart: false,
      serviceId,
    },
    "/app"
  ).href;
function html(preview: ResourcePreview) {
  return render(ConsoleResourcePreviewResult, {
    props: {
      preview,
      at,
      currentUrl,
      routePrefix: "/app",
      serviceHref,
      onOpenService: () => {},
      onOpenUserCard: () => {},
    },
  }).body;
}

describe("resource preview presentation", () => {
  it("shows group replacement and every safe Host field without unrelated node controls", () => {
    const catalog = consoleResourceCatalogFixture();
    const group = html(
      consoleResourceDraftPreviewFixture({
        operation: "group_inbounds",
        target_id: catalog.groups[0].id,
        inbound_ids: [],
      })
    );
    expect(group).toContain("console_nodes_inbounds");
    expect(group).toContain("console_resource_none");
    expect(group).toContain("console_resource_recovery_inbounds");
    expect(group).not.toContain("console_resource_disabled");
    const change = initialDraft(catalog, { kind: "host", id: catalog.hosts[0].id })!;
    if (change.operation !== "host_update") throw new Error("wrong fixture");
    change.patch = {
      ...change.patch,
      is_hidden: true,
      group_mode: "ALLOW_ONLY",
      group_ids: [catalog.groups[1].id],
    };
    const host = html(consoleResourceDraftPreviewFixture(change));
    for (const key of [
      "console_draft_hidden",
      "console_draft_group_mode",
      "console_nodes_node",
      "console_nodes_groups",
      "console_nodes_profile",
      "console_nodes_inbounds",
      "console_resource_disabled",
      "console_resource_recovery_host",
      "console_draft_exclude",
      "console_draft_allow_only",
    ])
      expect(host).toContain(key);
    expect(host).not.toContain("console_resource_force_restart");
    expect(host).not.toContain("<button");
  });
  it("renders every affected service including other reload groups, and a deduplicated customer list", () => {
    const preview = consoleResourcePreviewFixture(change);
    const service = preview.direct.services[0];
    preview.possible_reload = {
      group_ids: ["other-group"],
      node_ids: [consoleNodeFixture.id],
      profile_ids: ["other-profile"],
      services: Array.from({ length: 31 }, (_, index) => ({
        ...service,
        service_id: String(index + 1).padStart(32, "b"),
        name: `Reload service ${index + 1}`,
        group_ids: ["other-group"],
      })),
      service_total: 31,
      customer_ids: [service.customer_id],
      customer_total: 1,
    };
    preview.affected_service_ids.push(
      ...preview.possible_reload.services.map((item) => item.service_id)
    );
    preview.affected_customer_ids.push(service.customer_id);
    const result = html(preview);
    expect(result).toContain("console_resource_affected_services: 32");
    expect(result).toContain("console_resource_affected_customers: 1");
    for (const item of [service, ...preview.possible_reload.services]) {
      expect(result).toContain(item.name);
      expect(result).toContain(serviceHref(item.service_id).replaceAll("&", "&amp;"));
    }
    expect(result).toContain("Reload service 31");
    expect(result).toContain("other-group");
    expect(result).toContain("console_resource_direct_hint");
    expect(result).toContain("console_resource_reload_hint");
    expect(result).toContain("console_resource_scope");
    expect(result).toContain(`/app/admin/users/${service.customer_id}?`);
    expect(result).toContain("nodes_q=HK&amp;nodes_page=2&amp;nodes_related_page=1");
    expect(result).not.toContain("<button");
  });

  it("shows current and proposed values with source time, version, fingerprint and recovery", () => {
    const preview = consoleResourcePreviewFixture(change);
    const result = html(preview);
    expect(result).toMatch(/data-label="console_resource_current"[^>]*>no<\/td>/);
    expect(result).toMatch(/data-label="console_resource_proposed"[^>]*>yes<\/td>/);
    expect(result).toContain(consoleNodeFixture.profile_id!);
    expect(result).toContain(consoleNodeFixture.inbound_ids[0]);
    expect(result).toContain(preview.fingerprint!);
    expect(result).toContain("3.4.5");
    expect(result).toContain("console_resource_observed_at");
    expect(result).toContain("console_resource_authorizations_verified");
    expect(result).toContain("console_resource_source_profiles");
    expect(result).toContain("console_resource_recovery_inverse");
    const restart = html(
      consoleResourcePreviewFixture({ ...change, operation: "node_restart", force_restart: true })
    );
    expect(restart).toContain("console_resource_force_restart");
    expect(restart).toContain("console_resource_recovery_restart");
  });

  it("keeps incomplete empty observations distinct from verified absence", () => {
    const preview = consoleResourcePreviewFixture({ ...change, target_id: "unknown" });
    preview.remote_authorization_verified = false;
    preview.sources[0].availability = "invalid";
    const result = html(preview);
    expect(result).toContain("console_nodes_coverage_partial");
    expect(result).toContain("console_resource_authorizations_unverified");
    expect(result).toContain("console_resource_source_invalid");
    expect(result).toContain('role="alert"');
    expect(result).toContain("console_resource_blocker_target_not_found");
    expect(result).not.toContain("(target_not_found)");
    expect(result).toContain("console_resource_no_services");
    expect(result).toContain("console_resource_no_customers");
    expect(result).toMatch(/data-label="console_resource_current"[^>]*>console_unknown<\/td>/);
  });

  it("explains unknown blockers without exposing raw private details", () => {
    const preview = consoleResourcePreviewFixture({ ...change, target_id: "unknown" });
    preview.blockers = ["future_private_detail"];
    const result = html(preview);
    expect(result).toContain("console_resource_blocker_unknown");
    expect(result).not.toContain("future_private_detail");
  });

  it("explains replacement holds and incomplete ownership without claiming authorization", () => {
    const preview = consoleResourcePreviewFixture(change);
    preview.coverage = "partial";
    preview.remote_authorization_verified = false;
    preview.blockers = [
      "replacement_scope_unconfirmed",
      "replacement_service_unconfirmed",
      "replacement_customer_unavailable",
      "replacement_resource_held",
      "replacement_state_invalid",
      "exit_replacement_in_progress",
    ];
    const result = html(preview);
    expect(result).toContain("console_resource_authorizations_unverified");
    expect(result).not.toContain("console_resource_blocker_unknown");
    for (const key of [
      "console_resource_blocker_replacement_scope",
      "console_resource_blocker_replacement_service",
      "console_resource_blocker_replacement_customer",
      "console_resource_blocker_replacement_held",
      "console_exit_replacement_state_invalid",
      "console_exit_replacement_in_progress",
    ])
      expect(result).toContain(key);
  });

  it.each(["en", "ru", "zh-hans"])(
    "uses actual base locale entries in %s, including dynamic keys",
    (language) => {
      const locale: Record<string, string> = JSON.parse(
        readFileSync(new URL(`../../../../../locales/${language}.json`, import.meta.url), "utf8")
      );
      const components = [
        "ConsoleNodeResourcePreview.svelte",
        "ConsoleResourcePreviewResult.svelte",
        "ConsoleResourceImpact.svelte",
        "resourcePreviewMessages.ts",
      ];
      const keys = new Set<string>([
        ...nodeOperations.map((value) => `console_resource_${value}`),
        ...["metadata", "groups", "profiles", "services", "authorizations"].map(
          (value) => `console_resource_source_${value}`
        ),
        ...["unchanged", "changed", "incomplete"].map(
          (value) => `console_resource_revalidate_${value}`
        ),
        ...["unavailable", "invalid", "unsupported"].map(
          (value) => `console_resource_blocker_source_${value}`
        ),
      ]);
      for (const component of components) {
        const source = readFileSync(new URL(component, import.meta.url), "utf8");
        for (const match of source.matchAll(/"(console_resource_[a-z_]+)"/g)) keys.add(match[1]);
      }
      for (const key of keys)
        expect(locale[resolveLocaleKey(`admin_${key}`)], `${language}: ${key}`).toBeTruthy();
    }
  );
});
