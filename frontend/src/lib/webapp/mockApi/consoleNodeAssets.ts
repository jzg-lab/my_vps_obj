import type {
  NodeAsset,
  NodeAssetBody,
  NodeAssetDeleted,
  NodeAssetsPage,
} from "../../admin/consoleNodeAssets";

export type ConsoleNodeAssetsDemoState = { records: NodeAsset[] };
type Reply =
  ((NodeAsset | NodeAssetDeleted | NodeAssetsPage) & { ok: true }) | { ok: false; error: string };

export function createConsoleNodeAssetsDemoState(): ConsoleNodeAssetsDemoState {
  return { records: [] };
}

function validAddress(value: string): boolean {
  if (value.includes(":")) {
    if (/[\s%/\\?#@[\]]/.test(value)) return false;
    try {
      return new URL(`http://[${value}]`).hostname.startsWith("[");
    } catch {
      return false;
    }
  }
  const labels = value.replace(/\.$/, "").split(".");
  if (labels.every((label) => /^\d+$/.test(label)))
    return (
      labels.length === 4 &&
      !value.endsWith(".") &&
      labels.every((label) => /^(0|[1-9]\d{0,2})$/.test(label) && Number(label) <= 255)
    );
  return labels.every((label) => /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$/.test(label));
}

function readBody(options: RequestInit): NodeAssetBody | null {
  if (typeof options.body !== "string") return null;
  let value: unknown;
  try {
    value = JSON.parse(options.body);
  } catch {
    return null;
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  if (Object.keys(value).some((key) => !["name", "address", "notes"].includes(key))) return null;
  if (
    !("name" in value) ||
    typeof value.name !== "string" ||
    !("address" in value) ||
    typeof value.address !== "string"
  )
    return null;
  const notes = "notes" in value ? value.notes : "";
  if (typeof notes !== "string") return null;
  const body = { name: value.name.trim(), address: value.address.trim(), notes: notes.trim() };
  const control = (text: string) =>
    Array.from(text).some(
      (char) => (char.charCodeAt(0) < 32 && !"\n\t".includes(char)) || char.charCodeAt(0) === 127
    );
  if (
    !body.name ||
    Array.from(body.name).length > 120 ||
    /[\n\t]/.test(body.name) ||
    !body.address ||
    body.address.length > 253 ||
    Array.from(body.notes).length > 2000 ||
    Object.values(body).some(control) ||
    !validAddress(body.address)
  )
    return null;
  return body;
}

export function consoleNodeAssetsDemoResponse(
  path: string,
  options: RequestInit,
  state: ConsoleNodeAssetsDemoState
): Reply | undefined {
  const url = new URL(path, "https://demo.invalid");
  const collection = "/admin/console/node-assets";
  if (url.pathname !== collection && !url.pathname.startsWith(`${collection}/`)) return undefined;
  const method = options.method ?? "GET";
  const id = url.pathname === collection ? null : url.pathname.slice(collection.length + 1);
  const invalid = (error: string): Reply => ({ ok: false, error });
  if (id !== null && !/^[a-f0-9]{32}$/.test(id)) return invalid("invalid_node_asset_id");
  if (id !== null || method !== "GET") {
    if (url.search) return invalid("invalid_node_asset_query");
  } else {
    for (const key of url.searchParams.keys())
      if (!["page", "page_size"].includes(key) || url.searchParams.getAll(key).length !== 1)
        return invalid("invalid_node_asset_query");
  }
  if (id === null && method === "GET") {
    const page = Number(url.searchParams.get("page") ?? 0);
    const size = Number(url.searchParams.get("page_size") ?? 20);
    if (
      ![page, size].every(Number.isSafeInteger) ||
      page < 0 ||
      page > 1000000 ||
      size < 1 ||
      size > 100 ||
      (url.searchParams.has("page") && !url.searchParams.get("page")) ||
      (url.searchParams.has("page_size") && !url.searchParams.get("page_size"))
    )
      return invalid("invalid_node_asset_query");
    const rows = [...state.records].sort(
      (a, b) => b.created_at.localeCompare(a.created_at) || b.id.localeCompare(a.id)
    );
    return {
      ok: true,
      items: structuredClone(rows.slice(page * size, (page + 1) * size)),
      total: rows.length,
      page,
      page_size: size,
    };
  }
  if (id === null && method === "POST") {
    const body = readBody(options);
    if (!body) return invalid("invalid_node_asset_request");
    const now = new Date().toISOString();
    const record: NodeAsset = {
      ...body,
      id: crypto.randomUUID().replaceAll("-", ""),
      management_state: "unmanaged",
      created_at: now,
      updated_at: now,
    };
    state.records.push(record);
    return { ok: true, ...structuredClone(record) };
  }
  if (id !== null && ["GET", "PUT", "DELETE"].includes(method)) {
    const body = method === "PUT" ? readBody(options) : null;
    if (method === "PUT" && !body) return invalid("invalid_node_asset_request");
    const index = state.records.findIndex((row) => row.id === id);
    const row = state.records[index];
    if (!row) return invalid("node_asset_not_found");
    if (method === "DELETE") {
      state.records.splice(index, 1);
      return { ok: true, id, deleted: true };
    }
    if (body) state.records[index] = { ...row, ...body, updated_at: new Date().toISOString() };
    return { ok: true, ...structuredClone(state.records[index]) };
  }
  return invalid("method_not_allowed");
}
