import { writable } from "svelte/store";
import type { ApiClient } from "$lib/webapp/publicApi";
import { unwrap } from "$lib/webapp/publicApi";
import {
  canReviewPreview,
  canonicalResource,
  resourceRequestChange,
  type ResourceChange,
  type ResourcePreview,
} from "../../admin/sections/nodes/resourcePreview";
import {
  resourceErrorKey,
  resourceRejected,
  type ResourceOperation,
  type ResourceStart,
} from "./resourceOperations";

const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);
const uuid = (value: unknown): value is string =>
  typeof value === "string" && /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/i.test(value);
const ids = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every(uuid) && new Set(value).size === value.length;
const string = (value: unknown, min: number, max: number): value is string =>
  typeof value === "string" && value.length >= min && value.length <= max;
export function resourcePort(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 1 && value <= 65535;
}
export function resourceEndpoint(value: unknown): value is string {
  if (!string(value, 1, 253)) return false;
  if (/^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/i.test(value)) return true;
  if (!value.includes(":")) return false;
  try {
    return new URL(`http://[${value}]`).hostname !== "";
  } catch {
    return false;
  }
}
const exact = (value: Record<string, unknown>, fields: string[]) =>
  Object.keys(value).every((key) => fields.includes(key));
export function validResourceChange(value: unknown): value is ResourceChange {
  if (!record(value)) return false;
  switch (value.operation) {
    case "node_enable":
    case "node_disable":
    case "node_restart":
      return (
        exact(value, ["operation", "target_id", "force_restart"]) &&
        uuid(value.target_id) &&
        (value.force_restart === undefined || typeof value.force_restart === "boolean") &&
        (value.operation === "node_restart" || !value.force_restart)
      );
    case "group_inbounds":
      return (
        exact(value, ["operation", "target_id", "inbound_ids"]) &&
        uuid(value.target_id) &&
        ids(value.inbound_ids)
      );
    case "group_create":
      return (
        exact(value, ["operation", "name", "inbound_ids"]) &&
        string(value.name, 2, 30) &&
        /^[A-Za-z0-9_\s-]+$/.test(value.name) &&
        value.name !== "Default-Squad" &&
        ids(value.inbound_ids)
      );
    case "node_create":
      return (
        exact(value, ["operation", "name", "address", "port", "profile_id", "inbound_ids"]) &&
        string(value.name, 3, 30) &&
        string(value.address, 2, 253) &&
        resourceEndpoint(value.address) &&
        resourcePort(value.port) &&
        uuid(value.profile_id) &&
        ids(value.inbound_ids) &&
        value.inbound_ids.length > 0
      );
    case "host_create":
      return (
        exact(value, [
          "operation",
          "name",
          "address",
          "port",
          "profile_id",
          "inbound_id",
          "node_ids",
          "group_mode",
          "group_ids",
          "is_disabled",
          "is_hidden",
        ]) &&
        string(value.name, 1, 100) &&
        resourceEndpoint(value.address) &&
        resourcePort(value.port) &&
        uuid(value.profile_id) &&
        uuid(value.inbound_id) &&
        ids(value.node_ids) &&
        ids(value.group_ids) &&
        ["EXCLUDE", "ALLOW_ONLY"].includes(String(value.group_mode)) &&
        (value.group_mode !== "ALLOW_ONLY" || value.group_ids.length > 0) &&
        typeof value.is_disabled === "boolean" &&
        typeof value.is_hidden === "boolean"
      );
    case "host_update": {
      if (
        !exact(value, ["operation", "target_id", "patch"]) ||
        !uuid(value.target_id) ||
        !record(value.patch)
      )
        return false;
      const patch = value.patch;
      const rules: Record<string, (value: unknown) => boolean> = {
        profile_id: uuid,
        inbound_id: uuid,
        node_ids: ids,
        group_ids: ids,
        group_mode: (v) => v === "EXCLUDE" || v === "ALLOW_ONLY",
        is_disabled: (v) => typeof v === "boolean",
        is_hidden: (v) => typeof v === "boolean",
        address: resourceEndpoint,
        port: resourcePort,
      };
      const values = Object.entries(patch);
      return (
        values.length > 0 &&
        Object.keys(patch).every((key) => Object.hasOwn(rules, key)) &&
        values.every(([key, item]) => rules[key](item)) &&
        (patch.profile_id != null) === (patch.inbound_id != null) &&
        (patch.group_mode != null) === (patch.group_ids != null) &&
        (patch.group_mode !== "ALLOW_ONLY" || (ids(patch.group_ids) && patch.group_ids.length > 0))
      );
    }
    default:
      return false;
  }
}
const storageKey = (actorId: number) => `my-vps-resource-intent:${actorId}`;
export function readResourceIntent(storage: Storage, actorId: number): ResourceStart | null {
  const raw = storage.getItem(storageKey(actorId));
  if (raw === null) return null;
  const body: unknown = JSON.parse(raw);
  if (
    !record(body) ||
    !exact(body, ["change", "expected_fingerprint", "idempotency_key", "recovery_of"]) ||
    !validResourceChange(body.change) ||
    !string(body.expected_fingerprint, 64, 64) ||
    !/^[a-f0-9]+$/.test(body.expected_fingerprint) ||
    !string(body.idempotency_key, 1, 128) ||
    (body.recovery_of != null &&
      !(string(body.recovery_of, 32, 32) && /^[a-f0-9]+$/.test(body.recovery_of)))
  )
    throw new Error("invalid_resource_intent_storage");
  return {
    change: body.change,
    expected_fingerprint: body.expected_fingerprint,
    idempotency_key: body.idempotency_key,
    recovery_of: typeof body.recovery_of === "string" ? body.recovery_of : null,
  };
}
type IntentState = {
  busy: boolean;
  ready: boolean;
  pending: ResourceStart | null;
  operation: ResourceOperation | null;
  error: string;
  needsPreview: boolean;
};
export function createResourceIntent(api: ApiClient["api"], storage: Storage) {
  let state: IntentState = {
    busy: false,
    ready: false,
    pending: null,
    operation: null,
    error: "",
    needsPreview: false,
  };
  const store = writable(state);
  let actorId: number | null = null;
  let destroyed = false;
  const publish = (patch: Partial<IntentState>) => {
    state = { ...state, ...patch };
    if (!destroyed) store.set(state);
  };
  async function identity() {
    const result = unwrap(await api("/admin/me"));
    if (!Number.isSafeInteger(result.user_id)) throw new Error("invalid_actor");
    actorId = result.user_id;
    return actorId;
  }
  async function initialize() {
    if (state.busy) return;
    publish({ busy: true, error: "" });
    try {
      const actor = await identity();
      publish({ pending: readResourceIntent(storage, actor), ready: true });
    } catch {
      publish({ ready: false, error: "resource_ops_storage_failed" });
    } finally {
      publish({ busy: false });
    }
  }
  async function send(body: ResourceStart, actor: number) {
    try {
      const result = unwrap(
        await api("/admin/console/resources/operations", {
          method: "POST" as const,
          body: JSON.stringify(body),
        })
      );
      storage.removeItem(storageKey(actor));
      publish({ operation: result.operation, pending: null, needsPreview: false });
    } catch (failure) {
      if (resourceRejected(failure)) {
        storage.removeItem(storageKey(actor));
        publish({ pending: null, needsPreview: true });
      }
      publish({ error: resourceErrorKey(failure) });
    }
  }
  return {
    subscribe: store.subscribe,
    initialize,
    resetPreview() {
      if (!state.pending && !state.busy) publish({ needsPreview: false, error: "" });
    },
    async submit(preview: ResourcePreview, confirmed: boolean, recoveryOf: string | null = null) {
      if (
        !state.ready ||
        state.busy ||
        state.operation ||
        state.pending ||
        state.needsPreview ||
        !confirmed ||
        !canReviewPreview(preview) ||
        !preview.execution_available ||
        !preview.fingerprint
      )
        return;
      publish({ busy: true, error: "" });
      try {
        const actor = await identity();
        if (destroyed) return;
        const existing = readResourceIntent(storage, actor);
        if (existing) {
          publish({ pending: existing });
          return;
        }
        const fresh = unwrap(
          await api("/admin/console/resources/revalidate", {
            method: "POST",
            body: JSON.stringify({
              change: resourceRequestChange(preview.change),
              expected_fingerprint: preview.fingerprint,
            }),
          })
        );
        if (destroyed) return;
        if (
          !fresh.valid ||
          fresh.reason !== "unchanged" ||
          fresh.preview.fingerprint !== preview.fingerprint ||
          canonicalResource(fresh.preview.change) !== canonicalResource(preview.change) ||
          !canReviewPreview(fresh.preview) ||
          !fresh.preview.execution_available
        ) {
          publish({ needsPreview: true, error: "resource_ops_error_changed" });
          return;
        }
        const body: ResourceStart = {
          change: resourceRequestChange(preview.change),
          expected_fingerprint: preview.fingerprint,
          idempotency_key: crypto.randomUUID(),
          recovery_of: recoveryOf,
        };
        storage.setItem(storageKey(actor), JSON.stringify(body));
        publish({ pending: body });
        await send(body, actor);
      } catch (failure) {
        publish({ error: resourceErrorKey(failure) });
      } finally {
        publish({ busy: false });
      }
    },
    async resume() {
      if (state.busy || !state.pending || actorId === null) return;
      const originalActor = actorId;
      publish({ busy: true, error: "" });
      try {
        const actor = await identity();
        if (destroyed) return;
        if (actor !== originalActor) {
          publish({ ready: false, pending: null, error: "resource_ops_storage_failed" });
          return;
        }
        const body = readResourceIntent(storage, actor);
        if (!body) {
          publish({ pending: null });
          return;
        }
        // The same idempotency key resolves the original command; no worker dispatch occurs here.
        await send(body, actor);
      } catch {
        publish({ error: "resource_ops_error_unknown" });
      } finally {
        publish({ busy: false });
      }
    },
    destroy() {
      destroyed = true;
    },
  };
}
