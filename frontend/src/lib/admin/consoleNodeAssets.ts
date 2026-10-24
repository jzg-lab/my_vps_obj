import type { components } from "$lib/api/openapi.generated";
import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi";

export type NodeAsset = components["schemas"]["ConsoleNodeAssetOut"];
export type NodeAssetBody = components["schemas"]["ConsoleNodeAssetBody"];
export type NodeAssetsPage = components["schemas"]["ConsoleNodeAssetsListOut"];
export type NodeAssetDeleted = components["schemas"]["ConsoleNodeAssetDeletedOut"];
export type NodeAssetView = "managed" | "unmanaged";
export type NodeAssetAction = { kind: "create" } | { kind: "edit" | "delete"; asset: NodeAsset };

export function readNodeAssetsRoute(search: string): { view: NodeAssetView; page: number } {
  const params = new URLSearchParams(search);
  const page = Number(params.get("node_assets_page") ?? 0);
  return {
    view:
      !params.get("node_id") && params.get("nodes_view") === "unmanaged" ? "unmanaged" : "managed",
    page: Number.isSafeInteger(page) && page >= 0 && page <= 1000000 ? page : 0,
  };
}

export function nodeAssetsViewUrl(current: string, view: NodeAssetView, page?: number): URL {
  const url = new URL(current);
  url.searchParams.set("section", "nodes");
  if (view === "unmanaged") url.searchParams.set("nodes_view", view);
  else url.searchParams.delete("nodes_view");
  url.searchParams.delete("node_id");
  url.searchParams.delete("nodes_related_page");
  if (page !== undefined) {
    if (page > 0) url.searchParams.set("node_assets_page", String(page));
    else url.searchParams.delete("node_assets_page");
  }
  return url;
}

export function nodeAssetPath(id: string) {
  return builtApiPath<"/api/admin/console/node-assets/{asset_id}">(
    `/admin/console/node-assets/${encodeURIComponent(id)}`
  );
}

export async function loadNodeAssets(
  api: ApiClient["api"],
  page: number,
  signal?: AbortSignal
): Promise<NodeAssetsPage> {
  return unwrap(
    await api(
      builtApiPath<"/api/admin/console/node-assets">(
        `/admin/console/node-assets?${new URLSearchParams({ page: String(page), page_size: "20" })}`
      ),
      { signal }
    )
  );
}

export async function saveNodeAsset(
  api: ApiClient["api"],
  id: string | null,
  draft: NodeAssetBody
): Promise<NodeAsset> {
  const body: NodeAssetBody = {
    name: draft.name.trim(),
    address: draft.address.trim(),
    notes: draft.notes.trim(),
  };
  return id === null
    ? unwrap(
        await api("/admin/console/node-assets", {
          method: "POST" as const,
          body: JSON.stringify(body),
        })
      )
    : unwrap(await api(nodeAssetPath(id), { method: "PUT" as const, body: JSON.stringify(body) }));
}

export async function deleteNodeAsset(
  api: ApiClient["api"],
  id: string
): Promise<NodeAssetDeleted> {
  return unwrap(await api(nodeAssetPath(id), { method: "DELETE" as const }));
}

export function nodeAssetErrorKey(error: unknown): string {
  const code =
    error && typeof error === "object" && "error" in error && typeof error.error === "string"
      ? error.error
      : "";
  if (["unauthorized", "forbidden", "csrf_failed"].includes(code))
    return "console_node_assets_forbidden";
  if (["invalid_payload", "invalid_node_asset_request", "payload_too_large"].includes(code))
    return "console_node_assets_invalid";
  if (code === "node_asset_not_found") return "console_node_assets_not_found";
  return "console_node_assets_write_failed";
}

export function nodeAssetDraftReady(body: NodeAssetBody): boolean {
  return (
    body.name.trim().length > 0 &&
    Array.from(body.name.trim()).length <= 120 &&
    body.address.trim().length > 0 &&
    Array.from(body.address.trim()).length <= 253 &&
    Array.from(body.notes.trim()).length <= 2000
  );
}
