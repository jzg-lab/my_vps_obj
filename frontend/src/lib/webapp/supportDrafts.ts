import { escapeHtml } from "$lib/richtext/escape.js";

const SUPPORT_DRAFT_STORAGE_PREFIX = "rw_webapp_support_draft_v1";
const SUPPORT_DRAFT_TTL_MS = 14 * 24 * 60 * 60 * 1000;
const DEFAULT_SCOPE = "anonymous";

export type SupportDraft = Record<string, unknown>;

type SupportDraftUserLike = {
  user_id?: unknown;
  id?: unknown;
  telegram_id?: unknown;
} | null;

function safeStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage || null;
  } catch (_error) {
    return null;
  }
}

function draftKey(kind: unknown, scope: unknown, id: unknown = "new"): string {
  return [
    SUPPORT_DRAFT_STORAGE_PREFIX,
    encodeURIComponent(String(kind || "draft")),
    encodeURIComponent(String(scope || DEFAULT_SCOPE)),
    encodeURIComponent(String(id || "new")),
  ].join(":");
}

function normalizeDraftEnvelope(value: unknown): SupportDraft | null {
  if (!value || typeof value !== "object") return null;
  const envelope = value as { updatedAt?: unknown; draft?: unknown };
  const updatedAt = Number(envelope.updatedAt || 0);
  if (!updatedAt || Date.now() - updatedAt > SUPPORT_DRAFT_TTL_MS) return null;
  return envelope.draft && typeof envelope.draft === "object"
    ? (envelope.draft as SupportDraft)
    : null;
}

export function supportDraftScope(user: SupportDraftUserLike = {}): string {
  const id = String(user?.user_id ?? user?.id ?? user?.telegram_id ?? "").trim();
  return id || DEFAULT_SCOPE;
}

export function readSupportDraft(
  kind: unknown,
  scope: unknown,
  id: unknown = "new"
): SupportDraft | null {
  const storage = safeStorage();
  if (!storage) return null;
  const key = draftKey(kind, scope, id);

  try {
    const raw = storage.getItem(key);
    if (!raw) return null;

    const draft = normalizeDraftEnvelope(JSON.parse(raw));
    if (!draft) storage.removeItem(key);
    return draft;
  } catch (_error) {
    try {
      storage.removeItem(key);
    } catch (_removeError) {
      void _removeError;
    }
    return null;
  }
}

export function writeSupportDraft(
  kind: unknown,
  scope: unknown,
  id: unknown = "new",
  draft: SupportDraft = {}
): void {
  const storage = safeStorage();
  if (!storage) return;

  try {
    storage.setItem(
      draftKey(kind, scope, id),
      JSON.stringify({
        updatedAt: Date.now(),
        draft: draft && typeof draft === "object" ? draft : {},
      })
    );
  } catch (_error) {
    void _error;
  }
}

export function clearSupportDraft(kind: unknown, scope: unknown, id: unknown = "new"): void {
  const storage = safeStorage();
  if (!storage) return;

  try {
    storage.removeItem(draftKey(kind, scope, id));
  } catch (_error) {
    void _error;
  }
}

export function prepareServiceSupportDraft(scope: string, serviceId: string, label: string): void {
  if (!/^[0-9a-f]{32}$/.test(serviceId)) return;
  const previous = readSupportDraft("new", scope) ?? {};
  const body = typeof previous.body === "string" ? previous.body : "";
  const reference = escapeHtml(label + ": " + serviceId);
  writeSupportDraft("new", scope, "new", {
    ...previous,
    subject:
      typeof previous.subject === "string" && previous.subject.trim()
        ? previous.subject
        : label + ": " + serviceId,
    body: body.includes(serviceId) ? body : [body, reference].filter(Boolean).join("\n\n"),
    open: true,
  });
}
