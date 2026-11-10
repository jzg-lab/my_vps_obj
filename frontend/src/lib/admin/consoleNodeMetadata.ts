import type { components } from "$lib/api/openapi.generated";
import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi";

export type ConsoleNodeMetadata = components["schemas"]["ConsoleNodeMetadataOut"];
export type ConsoleNodeMetadataBody = components["schemas"]["ConsoleNodeMetadataBody"];
export type ConsoleNodeMetadataDraft = {
  display_name: string;
  region: string;
  provider: string;
  country_code?: string;
  country_lookup_ip?: string;
};

function metadataPath(nodeId: string) {
  return builtApiPath<"/api/admin/console/nodes/{node_id}/metadata">(
    `/admin/console/nodes/${encodeURIComponent(nodeId)}/metadata`
  );
}

export async function saveConsoleNodeMetadata(
  api: ApiClient["api"],
  nodeId: string,
  draft: ConsoleNodeMetadataDraft
): Promise<ConsoleNodeMetadata> {
  const body: ConsoleNodeMetadataBody = {
    display_name: draft.display_name.trim() || null,
    region: draft.region.trim() || null,
    provider: draft.provider.trim() || null,
    country_code: draft.country_code?.trim().toUpperCase() || null,
    country_lookup_ip: draft.country_lookup_ip?.trim() || null,
  };
  return unwrap(
    await api(metadataPath(nodeId), { method: "PUT" as const, body: JSON.stringify(body) })
  );
}

export async function clearConsoleNodeMetadata(
  api: ApiClient["api"],
  nodeId: string
): Promise<void> {
  unwrap(await api(metadataPath(nodeId), { method: "DELETE" as const }));
}

export function consoleNodeMetadataDraftReady(draft: ConsoleNodeMetadataDraft): boolean {
  const code = draft.country_code?.trim().toUpperCase();
  return (
    (!code || consoleNodeCountryLabel(code, "en") !== null) &&
    (draft.country_lookup_ip?.trim().length ?? 0) <= 45 &&
    [draft.display_name, draft.region, draft.provider].every(
      (value) => Array.from(value.trim()).length <= 120
    )
  );
}

export function consoleNodeMetadataErrorKey(error: unknown): string {
  const code =
    error && typeof error === "object" && "error" in error && typeof error.error === "string"
      ? error.error
      : "";
  if (["unauthorized", "forbidden", "csrf_failed"].includes(code))
    return "console_node_metadata_forbidden";
  if (
    ["invalid_payload", "invalid_console_node_metadata_request", "payload_too_large"].includes(code)
  )
    return "console_node_metadata_invalid";
  if (code === "node_not_found") return "console_node_metadata_not_found";
  return "console_node_metadata_write_failed";
}

export function consoleNodeCountryLabel(
  countryCode: string | null,
  locale?: string
): string | null {
  const code = countryCode?.trim().toUpperCase();
  if (
    !code ||
    !/^[A-Z]{2}$/.test(code) ||
    ["XX", "ZZ", "EU", "UN", "QO", "XA", "XB"].includes(code)
  )
    return null;
  try {
    const selectedLocale =
      locale ??
      (typeof document === "undefined"
        ? "en"
        : document.documentElement.lang || navigator.language || "en");
    const name = new Intl.DisplayNames([selectedLocale], { type: "region" }).of(code);
    if (!name || name === code) return null;
    const flag = String.fromCodePoint(
      ...Array.from(code, (char) => 0x1f1e6 + char.charCodeAt(0) - 65)
    );
    return `${flag} ${name} (${code})`;
  } catch {
    return null;
  }
}
