import { writable } from "svelte/store";
import type { components } from "$lib/api/openapi.generated";
import { unwrap, type ApiClient } from "$lib/webapp/publicApi";
import { canReviewPreview, type ResourcePreview } from "./resourcePreview";
import { validResourceChange } from "$lib/admin/resourceIntent";

export type ResourceCatalog = components["schemas"]["ConsoleResourceCatalogOut"];
export type DraftTarget = { kind: "group" | "host"; id: string };
type HostPatch = components["schemas"]["ResourceHostPatch"];
type SafeHostPatch = {
  [
    K in
      | "profile_id"
      | "inbound_id"
      | "node_ids"
      | "is_disabled"
      | "is_hidden"
      | "group_mode"
      | "group_ids"
  ]: NonNullable<HostPatch[K]>;
};
// The wire patch omits endpoint fields; explicit null is rejected by the backend.
export type DraftChange =
  | components["schemas"]["ResourceGroupChange"]
  | {
      operation: "host_update";
      target_id: string;
      patch: SafeHostPatch & Partial<Pick<HostPatch, "address" | "port">>;
    };
type State = {
  catalog: ResourceCatalog | null;
  change: DraftChange | null;
  preview: ResourcePreview | null;
  busy: "catalog" | "preview" | "revalidate" | null;
  failed: boolean;
  confirmed: boolean;
  validation: "unchanged" | "changed" | "incomplete" | "failed" | null;
};

export function catalogAvailable(catalog: ResourceCatalog | null): catalog is ResourceCatalog {
  return Boolean(
    catalog?.draft_available &&
    catalog.coverage === "complete" &&
    !catalog.blockers.length &&
    ["metadata", "nodes", "hosts", "groups", "profiles"].every((name) =>
      catalog.sources.some((source) => source.source === name)
    ) &&
    catalog.sources.every((source) => source.availability === "available")
  );
}

export function initialDraft(catalog: ResourceCatalog, target: DraftTarget): DraftChange | null {
  if (!catalogAvailable(catalog)) return null;
  if (target.kind === "group") {
    const group = catalog.groups.find((item) => item.id === target.id);
    return group?.id
      ? { operation: "group_inbounds", target_id: group.id, inbound_ids: [...group.inbound_ids] }
      : null;
  }
  const host = catalog.hosts.find((item) => item.id === target.id);
  if (
    !host?.id ||
    !host.profile_id ||
    !Array.isArray(host.node_ids) ||
    !Array.isArray(host.group_ids) ||
    host.inbound_ids.length !== 1 ||
    host.group_mode === null ||
    host.is_disabled === null ||
    host.is_hidden === null
  )
    return null;
  return {
    operation: "host_update",
    target_id: host.id,
    patch: {
      profile_id: host.profile_id,
      inbound_id: host.inbound_ids[0],
      node_ids: [...host.node_ids],
      group_mode: host.group_mode,
      group_ids: [...host.group_ids],
      is_disabled: host.is_disabled,
      is_hidden: host.is_hidden,
    },
  };
}

export function validDraft(catalog: ResourceCatalog | null, change: DraftChange | null): boolean {
  if (!catalogAvailable(catalog) || !change || !validResourceChange(change)) return false;
  const known = (ids: string[], options: { id: string | null }[]) =>
    new Set(ids).size === ids.length && ids.every((id) => options.some((item) => item.id === id));
  if (change.operation === "group_inbounds")
    return (
      catalog.groups.some((item) => item.id === change.target_id) &&
      known(
        change.inbound_ids,
        catalog.profiles.flatMap((profile) => profile.inbounds)
      )
    );
  const patch = change.patch;
  return (
    catalog.hosts.some((item) => item.id === change.target_id) &&
    Boolean(
      catalog.profiles
        .find((item) => item.id === patch.profile_id)
        ?.inbounds.some(
          (item) => item.id === patch.inbound_id && item.profile_id === patch.profile_id
        )
    ) &&
    known(patch.node_ids, catalog.nodes) &&
    known(patch.group_ids, catalog.groups)
  );
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return JSON.stringify([...value].sort());
  if (value && typeof value === "object")
    return JSON.stringify(
      Object.entries(value)
        .filter(([, item]) => item !== null && item !== undefined)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([key, item]) => [key, canonical(item)])
    );
  return JSON.stringify(value);
}

export function createResourceDraftPreview(api: ApiClient["api"], target: DraftTarget) {
  let state: State = {
    catalog: null,
    change: null,
    preview: null,
    busy: null,
    failed: false,
    confirmed: false,
    validation: null,
  };
  const store = writable(state);
  let sequence = 0;
  let controller: AbortController | null = null;
  let destroyed = false;
  const publish = (patch: Partial<State>) => {
    state = { ...state, ...patch };
    store.set(state);
  };
  function invalidate() {
    sequence++;
    controller?.abort();
    controller = null;
  }
  const reviewable = () =>
    validDraft(state.catalog, state.change) &&
    canReviewPreview(state.preview) &&
    !state.busy &&
    state.validation !== "incomplete" &&
    state.validation !== "failed";

  async function loadCatalog() {
    if (destroyed) return;
    invalidate();
    const token = sequence;
    controller = new AbortController();
    publish({
      catalog: null,
      change: null,
      preview: null,
      busy: "catalog",
      failed: false,
      confirmed: false,
      validation: null,
    });
    try {
      const catalog = unwrap(
        await api("/admin/console/resources/catalog", { signal: controller.signal })
      );
      if (!destroyed && token === sequence)
        publish({ catalog, change: initialDraft(catalog, target) });
    } catch {
      if (!destroyed && token === sequence) publish({ failed: true });
    } finally {
      if (!destroyed && token === sequence) publish({ busy: null });
    }
  }

  function setChange(change: DraftChange) {
    if (destroyed || state.busy === "catalog" || canonical(state.change) === canonical(change))
      return;
    invalidate();
    publish({
      change: structuredClone(change),
      preview: null,
      busy: null,
      confirmed: false,
      failed: false,
      validation: null,
    });
  }

  async function request(revalidate: boolean) {
    if (destroyed || state.busy || !state.change || !validDraft(state.catalog, state.change))
      return;
    const change = structuredClone(state.change);
    if (
      change.target_id !== target.id ||
      (change.operation === "host_update") !== (target.kind === "host")
    )
      return;
    const expected = state.preview?.fingerprint;
    if (revalidate && (!expected || !reviewable())) return;
    const wasConfirmed = state.confirmed;
    invalidate();
    const token = sequence;
    controller = new AbortController();
    const signal = controller.signal;
    publish({
      preview: null,
      busy: revalidate ? "revalidate" : "preview",
      failed: false,
      confirmed: false,
      validation: null,
    });
    try {
      let preview: ResourcePreview;
      let validation: State["validation"] = null;
      if (revalidate) {
        const result = unwrap(
          await api("/admin/console/resources/revalidate", {
            method: "POST",
            body: JSON.stringify({ change, expected_fingerprint: expected }),
            signal,
          })
        );
        preview = result.preview;
        validation =
          result.reason === "incomplete" || !canReviewPreview(preview)
            ? "incomplete"
            : result.valid && result.reason === "unchanged" && preview.fingerprint === expected
              ? "unchanged"
              : "changed";
      } else {
        preview = unwrap(
          await api("/admin/console/resources/preview", {
            method: "POST",
            body: JSON.stringify({ change }),
            signal,
          })
        );
      }
      if (destroyed || token !== sequence) return;
      if (
        canonical(preview.change) !== canonical(change) ||
        (preview.current &&
          (preview.current.id !== target.id || preview.current.kind !== target.kind)) ||
        (preview.proposed &&
          (preview.proposed.id !== target.id || preview.proposed.kind !== target.kind))
      )
        throw new Error("resource_preview_target_mismatch");
      publish({ preview, validation, confirmed: validation === "unchanged" && wasConfirmed });
    } catch {
      if (!destroyed && token === sequence)
        publish({ failed: true, validation: revalidate ? "failed" : null, confirmed: false });
    } finally {
      if (!destroyed && token === sequence) publish({ busy: null });
    }
  }
  return {
    subscribe: store.subscribe,
    loadCatalog,
    setChange,
    load: () => request(false),
    revalidate: () => request(true),
    confirm: (value: boolean) => {
      if (!destroyed) publish({ confirmed: value && reviewable() });
    },
    destroy() {
      destroyed = true;
      invalidate();
    },
  };
}
