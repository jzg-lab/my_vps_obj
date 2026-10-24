import { writable } from "svelte/store";
import type { components } from "$lib/api/openapi.generated";
import { unwrap, type ApiClient } from "$lib/webapp/publicApi";

export type NodeChange = components["schemas"]["ResourceNodeChange"];
export type ResourcePreview = components["schemas"]["ConsoleResourcePreviewOut"];
// HTTP patches omit unspecified fields; the generated response includes nullable defaults.
export type ResourceChange =
  | Exclude<ResourcePreview["change"], components["schemas"]["ResourceHostChange"]>
  | (Omit<components["schemas"]["ResourceHostChange"], "patch"> & {
      patch: Partial<components["schemas"]["ResourceHostPatch"]>;
    });
export function resourceRequestChange(change: ResourceChange): ResourceChange {
  const copy: ResourceChange = JSON.parse(JSON.stringify(change));
  if (copy.operation === "host_update")
    copy.patch = Object.fromEntries(
      Object.entries(copy.patch).filter(([, value]) => value !== null && value !== undefined)
    );
  return copy;
}
type Revalidation = components["schemas"]["ConsoleResourceRevalidateOut"];
export type PreviewState = {
  change: ResourceChange | null;
  preview: ResourcePreview | null;
  busy: "preview" | "revalidate" | null;
  confirmed: boolean;
  failed: boolean;
  validation: Revalidation["reason"] | "failed" | null;
};

export const nodeOperations = ["node_enable", "node_disable", "node_restart"] as const;

export function canReviewPreview(preview: ResourcePreview | null): boolean {
  return Boolean(
    preview &&
    preview.coverage === "complete" &&
    preview.blockers.length === 0 &&
    preview.fingerprint &&
    (preview.current || preview.change.operation.endsWith("_create")) &&
    preview.proposed &&
    preview.remote_authorization_verified
  );
}

export function canonicalResource(value: unknown): string {
  if (Array.isArray(value)) return JSON.stringify([...value].sort());
  if (value && typeof value === "object")
    return JSON.stringify(
      Object.entries(value)
        .filter(([, item]) => item !== null && item !== undefined)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([key, item]) => [key, canonicalResource(item)])
    );
  return JSON.stringify(value);
}
function sameChange(left: ResourceChange | null, right: ResourceChange | null): boolean {
  return canonicalResource(left) === canonicalResource(right);
}

export function createResourcePreview(api: ApiClient["api"]) {
  let state: PreviewState = {
    change: null,
    preview: null,
    busy: null,
    confirmed: false,
    failed: false,
    validation: null,
  };
  const store = writable(state);
  let sequence = 0;
  let controller: AbortController | null = null;
  let destroyed = false;
  const publish = (patch: Partial<PreviewState>) => {
    state = { ...state, ...patch };
    store.set(state);
  };
  function invalidate() {
    sequence++;
    controller?.abort();
    controller = null;
  }
  function setChange(change: ResourceChange | null) {
    if (destroyed || sameChange(state.change, change)) return;
    invalidate();
    publish({
      change: change ? resourceRequestChange(change) : null,
      preview: null,
      busy: null,
      confirmed: false,
      failed: false,
      validation: null,
    });
  }
  async function request(revalidate: boolean) {
    if (destroyed || !state.change || state.busy) return;
    const expected = state.preview?.fingerprint;
    if (revalidate && (!expected || !canReviewPreview(state.preview))) return;
    const change = { ...state.change };
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
      let validation: PreviewState["validation"] = null;
      let confirmed = false;
      if (revalidate && expected) {
        const body = {
          change,
          expected_fingerprint: expected,
        };
        const result = unwrap(
          await api("/admin/console/resources/revalidate", {
            method: "POST",
            body: JSON.stringify(body),
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
        confirmed = validation === "unchanged" && wasConfirmed;
      } else {
        const body = { change };
        preview = unwrap(
          await api("/admin/console/resources/preview", {
            method: "POST",
            body: JSON.stringify(body),
            signal,
          })
        );
      }
      if (destroyed || token !== sequence) return;
      if (
        !sameChange(change, preview.change) ||
        ("target_id" in change &&
          ((preview.current && preview.current.id !== change.target_id) ||
            (preview.proposed && preview.proposed.id !== change.target_id)))
      )
        throw new Error("resource_preview_target_mismatch");
      publish({ preview, validation, confirmed });
    } catch {
      if (!destroyed && token === sequence)
        publish({ failed: true, validation: revalidate ? "failed" : null, confirmed: false });
    } finally {
      if (!destroyed && token === sequence) publish({ busy: null });
    }
  }
  return {
    subscribe: store.subscribe,
    setChange,
    load: () => request(false),
    revalidate: () => request(true),
    confirm(value: boolean) {
      if (!destroyed)
        publish({
          confirmed:
            value &&
            !state.busy &&
            state.validation !== "incomplete" &&
            canReviewPreview(state.preview),
        });
    },
    destroy() {
      destroyed = true;
      invalidate();
    },
  };
}
