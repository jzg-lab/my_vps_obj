import type { ConsoleNode, ConsoleNodeTraffic, ConsoleNodesTranslate } from "./consoleNodesTypes";

export function nodeTrafficDate(value: string | null, at: ConsoleNodesTranslate): string {
  if (!value) return at("console_unknown");
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? at("console_unknown")
    : date.toISOString().replace("T", " ").replace("Z", " UTC");
}

export function nodeWindowTrafficQuality(
  node: ConsoleNode,
  traffic: ConsoleNodeTraffic | null | undefined
): ConsoleNode["window_traffic_quality"] {
  if (!traffic || traffic.availability === "unavailable" || traffic.availability === "unconfigured")
    return "missing";
  if (node.window_traffic_quality === "invalid") return "invalid";
  if (node.window_traffic_quality !== "reported" || node.window_traffic_bytes == null)
    return "missing";
  return Number.isSafeInteger(node.window_traffic_bytes) && node.window_traffic_bytes >= 0
    ? "reported"
    : "invalid";
}
