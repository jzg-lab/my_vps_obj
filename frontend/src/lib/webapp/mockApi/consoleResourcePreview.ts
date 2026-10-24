import type { components, paths } from "$lib/api/openapi.generated";
import type { CatalogResource } from "$lib/admin/consoleResources";
import { consoleNodeFixture, consoleNodeDetailFixture } from "$lib/admin/consoleNodesFixtures";
import type {
  DraftChange,
  ResourceCatalog,
} from "../../../admin/sections/nodes/resourceDraftPreview";

type NodeChange = components["schemas"]["ResourceNodeChange"];
type Preview = components["schemas"]["ConsoleResourcePreviewOut"];
type PreviewResponse =
  paths["/api/admin/console/resources/preview"]["post"]["responses"][200]["content"]["application/json"];
type RevalidateResponse =
  paths["/api/admin/console/resources/revalidate"]["post"]["responses"][200]["content"]["application/json"];

export function consoleResourcePreviewFixture(change: NodeChange): Preview {
  const current: components["schemas"]["ResourceValuesOut"] = {
    kind: "node",
    id: consoleNodeFixture.id,
    name: consoleNodeFixture.name,
    profile_id: consoleNodeFixture.profile_id,
    inbound_ids: [...consoleNodeFixture.inbound_ids],
    node_ids: [],
    is_disabled: false,
    is_hidden: null,
    group_ids: [],
    group_mode: null,
    address: null,
    port: null,
    force_restart: null,
  };
  const direct: components["schemas"]["ResourceImpactOut"] = {
    group_ids: consoleNodeFixture.groups.map((group) => group.id),
    node_ids: [consoleNodeFixture.id],
    profile_ids: consoleNodeFixture.profile_id ? [consoleNodeFixture.profile_id] : [],
    services: consoleNodeDetailFixture.services.map((service) => ({
      service_id: service.id,
      customer_id: service.user_id,
      name: service.name,
      group_ids: consoleNodeFixture.groups.map((group) => group.id),
      configured_group_ids: consoleNodeFixture.groups.map((group) => group.id),
      observed_group_ids: consoleNodeFixture.groups.map((group) => group.id),
      connection_state: service.connection_state,
    })),
    customer_ids: [...new Set(consoleNodeDetailFixture.services.map((service) => service.user_id))],
    service_total: consoleNodeDetailFixture.services.length,
    customer_total: new Set(consoleNodeDetailFixture.services.map((service) => service.user_id))
      .size,
  };
  const found = change.target_id === consoleNodeFixture.id;
  const fingerprint =
    (change.operation === "node_enable" ? "1" : change.operation === "node_disable" ? "2" : "3") +
    (change.force_restart ? "1" : "0");
  return {
    change: { ...change },
    current: found ? current : null,
    proposed: found
      ? {
          ...current,
          is_disabled: change.operation === "node_disable",
          force_restart: change.operation === "node_restart" ? change.force_restart : null,
        }
      : null,
    direct: found
      ? direct
      : {
          group_ids: [],
          node_ids: [],
          profile_ids: [],
          services: [],
          customer_ids: [],
          service_total: 0,
          customer_total: 0,
        },
    possible_reload: {
      group_ids: [],
      node_ids: [],
      profile_ids: [],
      services: [],
      customer_ids: [],
      service_total: 0,
      customer_total: 0,
    },
    affected_service_ids: found ? direct.services.map((service) => service.service_id) : [],
    affected_customer_ids: found ? direct.customer_ids : [],
    association_basis: "configured_and_observed_scope_not_live_connections",
    blockers: found ? [] : ["target_not_found"],
    coverage: found ? "complete" : "partial",
    execution_available: false,
    fingerprint: found ? fingerprint.padEnd(64, "0") : null,
    observed_at: "2026-10-24T08:00:00Z",
    observed_panel_version: "3.4.5",
    reviewed_panel_version: "3.4.5",
    remote_authorization_verified: true,
    recovery:
      change.operation === "node_restart"
        ? "restart_has_no_automatic_rollback"
        : "inverse_node_action_requires_fresh_preview",
    sources: (
      ["metadata", "nodes", "hosts", "groups", "profiles", "services", "authorizations"] as const
    ).map((source) => ({
      source,
      availability: "available",
      observed_at: "2026-10-24T08:00:00Z",
    })),
  };
}

export function consoleResourceCatalogFixture(): ResourceCatalog & {
  groups: CatalogResource[];
  hosts: CatalogResource[];
  nodes: CatalogResource[];
} {
  const preview = consoleResourcePreviewFixture({
    operation: "node_disable",
    target_id: consoleNodeFixture.id,
    force_restart: false,
  });
  const node = { ...preview.current!, id: consoleNodeFixture.id };
  const profileId = consoleNodeFixture.profile_id!;
  const inboundId = consoleNodeFixture.inbound_ids[0];
  const group = {
    ...node,
    kind: "group" as const,
    id: consoleNodeFixture.groups[0].id,
    name: consoleNodeFixture.groups[0].name ?? "Shared HK",
    profile_id: null,
    is_disabled: null,
  };
  const host = {
    ...node,
    kind: "host" as const,
    id: consoleNodeDetailFixture.hosts[0].id,
    name: consoleNodeDetailFixture.hosts[0].name ?? "HK subscription entry",
    node_ids: [node.id],
    is_hidden: false,
    group_mode: "EXCLUDE" as const,
    group_ids: [],
    address: "hk.example.test",
    port: 443,
  };
  return {
    groups: [
      group,
      {
        ...group,
        id: "40000000-0000-0000-0000-000000000002",
        inbound_ids: ["30000000-0000-0000-0000-000000000002"],
      },
    ],
    hosts: [host],
    nodes: [node],
    profiles: [
      {
        id: profileId,
        name: "HK profile",
        node_ids: [node.id],
        config_digest: "a".repeat(64),
        inbounds: [
          { id: inboundId, profile_id: profileId, tag: "vless-main" },
          { id: "30000000-0000-0000-0000-000000000002", profile_id: profileId, tag: "vless-alt" },
        ],
      },
      {
        id: "20000000-0000-0000-0000-000000000002",
        name: "HK profile",
        node_ids: [],
        config_digest: "b".repeat(64),
        inbounds: [
          {
            id: "30000000-0000-0000-0000-000000000003",
            profile_id: "20000000-0000-0000-0000-000000000002",
            tag: "vless-other",
          },
        ],
      },
    ],
    sources: preview.sources.filter(
      (source) => !["services", "authorizations"].includes(source.source)
    ),
    coverage: "complete",
    blockers: [],
    draft_available: true,
    reviewed_panel_version: "3.4.5",
    observed_panel_version: "3.4.5",
    observed_at: preview.observed_at,
    execution_available: false,
  };
}

export function consoleResourceDraftPreviewFixture(change: DraftChange): Preview {
  const catalog = consoleResourceCatalogFixture();
  const preview = consoleResourcePreviewFixture({
    operation: "node_disable",
    target_id: consoleNodeFixture.id,
    force_restart: false,
  });
  const current =
    (change.operation === "group_inbounds" ? catalog.groups : catalog.hosts).find(
      (item) => item.id === change.target_id
    ) ?? null;
  const known = (ids: string[], options: { id: string }[]) =>
    ids.every((id) => options.some((item) => item.id === id));
  const bindingValid =
    change.operation === "group_inbounds"
      ? known(
          change.inbound_ids,
          catalog.profiles.flatMap((profile) => profile.inbounds)
        )
      : Boolean(
          catalog.profiles
            .find((profile) => profile.id === change.patch.profile_id)
            ?.inbounds.some((inbound) => inbound.id === change.patch.inbound_id)
        ) &&
        known(change.patch.node_ids, catalog.nodes) &&
        known(change.patch.group_ids, catalog.groups);
  const normalizedChange: Preview["change"] =
    change.operation === "group_inbounds"
      ? { ...change, inbound_ids: [...change.inbound_ids].sort() }
      : {
          ...change,
          patch: {
            ...change.patch,
            node_ids: [...change.patch.node_ids].sort(),
            group_ids: [...change.patch.group_ids].sort(),
            address: null,
            port: null,
          },
        };
  const proposed = !current
    ? null
    : change.operation === "group_inbounds"
      ? { ...current, inbound_ids: [...change.inbound_ids].sort() }
      : {
          ...current,
          profile_id: change.patch.profile_id,
          inbound_ids: [change.patch.inbound_id],
          node_ids: [...change.patch.node_ids].sort(),
          group_mode: change.patch.group_mode,
          group_ids: [...change.patch.group_ids].sort(),
          is_disabled: change.patch.is_disabled,
          is_hidden: change.patch.is_hidden,
        };
  // Deterministic demo comparison only; the backend supplies the authoritative fingerprint.
  let hash = 2166136261;
  for (const character of JSON.stringify(normalizedChange))
    hash = Math.imul(hash ^ character.charCodeAt(0), 16777619);
  return {
    ...preview,
    change: normalizedChange,
    current,
    proposed,
    coverage: current && bindingValid ? "complete" : "partial",
    blockers: !current
      ? ["target_not_found"]
      : bindingValid
        ? []
        : [
            change.operation === "group_inbounds"
              ? "unknown_proposed_inbound"
              : "unknown_host_selection",
          ],
    fingerprint:
      current && bindingValid ? (hash >>> 0).toString(16).padStart(8, "0").repeat(8) : null,
    possible_reload: { ...preview.direct, group_ids: [catalog.groups[1].id] },
    recovery:
      change.operation === "group_inbounds"
        ? "restore_previous_inbounds_and_recheck_profile_nodes"
        : "restore_previous_host_and_refresh_subscription",
  };
}

function record(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
function uuid(value: unknown): value is string {
  return typeof value === "string" && /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(value);
}
function ids(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(uuid) && new Set(value).size === value.length;
}
function parseDraft(value: unknown): DraftChange | null {
  if (!record(value) || !uuid(value.target_id)) return null;
  if (
    value.operation === "group_inbounds" &&
    ids(value.inbound_ids) &&
    Object.keys(value).every((key) => ["operation", "target_id", "inbound_ids"].includes(key))
  )
    return {
      operation: value.operation,
      target_id: value.target_id,
      inbound_ids: value.inbound_ids,
    };
  const patch = value.patch;
  if (
    value.operation !== "host_update" ||
    !record(patch) ||
    Object.keys(value).some((key) => !["operation", "target_id", "patch"].includes(key)) ||
    Object.keys(patch).some(
      (key) =>
        ![
          "profile_id",
          "inbound_id",
          "node_ids",
          "group_mode",
          "group_ids",
          "is_disabled",
          "is_hidden",
        ].includes(key)
    ) ||
    !uuid(patch.profile_id) ||
    !uuid(patch.inbound_id) ||
    !ids(patch.node_ids) ||
    !ids(patch.group_ids) ||
    (patch.group_mode !== "EXCLUDE" && patch.group_mode !== "ALLOW_ONLY") ||
    typeof patch.is_disabled !== "boolean" ||
    typeof patch.is_hidden !== "boolean"
  )
    return null;
  return {
    operation: value.operation,
    target_id: value.target_id,
    patch: {
      profile_id: patch.profile_id,
      inbound_id: patch.inbound_id,
      node_ids: patch.node_ids,
      group_mode: patch.group_mode,
      group_ids: patch.group_ids,
      is_disabled: patch.is_disabled,
      is_hidden: patch.is_hidden,
    },
  };
}

export function consoleResourcePreviewDemoResponse(path: string, options: RequestInit): unknown {
  const route = new URL(path, "https://demo.test").pathname;
  if (route === "/admin/console/resources/catalog")
    return !options.method || options.method === "GET"
      ? { ok: true, ...consoleResourceCatalogFixture() }
      : { ok: false, error: "method_not_allowed" };
  if (
    route !== "/admin/console/resources/preview" &&
    route !== "/admin/console/resources/revalidate"
  )
    return undefined;
  if (options.method !== "POST") return { ok: false, error: "method_not_allowed" };
  let body: unknown;
  try {
    body = JSON.parse(typeof options.body === "string" ? options.body : "");
  } catch {
    return { ok: false, error: "invalid_request" };
  }
  if (!body || typeof body !== "object" || !("change" in body))
    return { ok: false, error: "invalid_request" };
  const change = body.change;
  const draft = parseDraft(change);
  let preview: Preview;
  if (draft) preview = consoleResourceDraftPreviewFixture(draft);
  else {
    if (
      !change ||
      typeof change !== "object" ||
      !("operation" in change) ||
      (change.operation !== "node_enable" &&
        change.operation !== "node_disable" &&
        change.operation !== "node_restart") ||
      !("target_id" in change) ||
      typeof change.target_id !== "string" ||
      !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(change.target_id) ||
      ("force_restart" in change && typeof change.force_restart !== "boolean") ||
      (change.operation !== "node_restart" && "force_restart" in change && change.force_restart) ||
      Object.keys(change).some((key) => !["operation", "target_id", "force_restart"].includes(key))
    )
      return { ok: false, error: "invalid_request" };
    preview = consoleResourcePreviewFixture({
      operation: change.operation,
      target_id: change.target_id,
      force_restart: "force_restart" in change && change.force_restart === true,
    });
  }
  if (route.endsWith("/preview")) {
    if (Object.keys(body).some((key) => key !== "change"))
      return { ok: false, error: "invalid_request" };
    return { ok: true, ...preview } satisfies PreviewResponse;
  }
  if (
    !("expected_fingerprint" in body) ||
    typeof body.expected_fingerprint !== "string" ||
    !/^[a-f0-9]{64}$/.test(body.expected_fingerprint) ||
    Object.keys(body).some((key) => !["change", "expected_fingerprint"].includes(key))
  )
    return { ok: false, error: "invalid_request" };
  const reason =
    preview.coverage !== "complete"
      ? "incomplete"
      : preview.fingerprint === body.expected_fingerprint
        ? "unchanged"
        : "changed";
  return { ok: true, valid: reason === "unchanged", reason, preview } satisfies RevalidateResponse;
}
