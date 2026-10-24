import { buildAdminUserPath, builtApiPath } from "$lib/webapp/publicApi";
import { withRoutePrefix } from "$lib/webapp/routes";
import type { ConsoleNodeTrafficPreset } from "./consoleNodesTypes";

export const nodeTrafficWindows = [
  "today",
  "7d",
  "30d",
] as const satisfies readonly ConsoleNodeTrafficPreset[];
export type NodeTrafficWindow = ConsoleNodeTrafficPreset;

export type NodesRoute = {
  nodeId: string;
  serviceId: string;
  query: string;
  status: "all" | "online" | "offline" | "unknown";
  page: number;
  relatedPage: number;
  trafficWindow: NodeTrafficWindow;
};

export function readNodesRoute(search: string): NodesRoute {
  const params = new URLSearchParams(search);
  const page = Number(params.get("nodes_page") ?? 0);
  const relatedPage = Number(params.get("nodes_related_page") ?? 0);
  const status = params.get("nodes_status");
  const trafficWindow = params.get("nodes_traffic_window");
  return {
    nodeId: params.get("node_id") ?? "",
    serviceId: params.get("service_id") ?? "",
    query: params.get("nodes_q") ?? "",
    status: status === "online" || status === "offline" || status === "unknown" ? status : "all",
    trafficWindow: trafficWindow === "7d" || trafficWindow === "30d" ? trafficWindow : "today",
    page: Number.isSafeInteger(page) && page >= 0 && page <= 1000000 ? page : 0,
    relatedPage:
      Number.isSafeInteger(relatedPage) && relatedPage >= 0 && relatedPage <= 1000000
        ? relatedPage
        : 0,
  };
}

export function consoleNodesListPath(route: NodesRoute) {
  const params = new URLSearchParams({
    q: route.query,
    status: route.status,
    page: String(route.page),
    page_size: "25",
    traffic_window: route.trafficWindow,
  });
  return builtApiPath<"/api/admin/console/nodes">(`/admin/console/nodes?${params}`);
}

export function consoleNodeDetailPath(route: NodesRoute) {
  const params = new URLSearchParams({
    page: String(route.relatedPage),
    page_size: "25",
    traffic_window: route.trafficWindow,
  });
  return builtApiPath<"/api/admin/console/nodes/{node_id}">(
    `/admin/console/nodes/${encodeURIComponent(route.nodeId)}?${params}`
  );
}

export function nodesRouteUrl(current: string, route: NodesRoute, routePrefix = ""): URL {
  const url = new URL(current);
  url.pathname = withRoutePrefix("/admin/nodes", routePrefix);
  url.searchParams.set("section", "nodes");
  for (const key of ["user_id", "q", "status", "sort", "page"]) {
    url.searchParams.delete(key);
  }
  const values: Array<[string, string]> = [
    ["node_id", route.nodeId],
    ["service_id", route.serviceId],
    ["nodes_q", route.query],
    ["nodes_status", route.status === "all" ? "" : route.status],
    ["nodes_page", route.page ? String(route.page) : ""],
    ["nodes_related_page", route.relatedPage ? String(route.relatedPage) : ""],
    ["nodes_traffic_window", route.trafficWindow === "today" ? "" : route.trafficWindow],
  ];
  for (const [key, value] of values) {
    if (value) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
  }
  return url;
}

export function nodeRelatedUrl(
  current: string,
  target: { serviceId: string } | { userId: string | number },
  routePrefix = ""
): URL {
  const url = new URL(current);
  // Keep the node filters in history, but don't apply another section's filters.
  for (const key of ["node_id", "service_id", "user_id", "q", "status", "sort", "page"]) {
    url.searchParams.delete(key);
  }
  if ("serviceId" in target) {
    url.pathname = withRoutePrefix("/admin/services", routePrefix);
    url.searchParams.set("section", "services");
    url.searchParams.set("service_id", target.serviceId);
  } else {
    url.pathname = withRoutePrefix(buildAdminUserPath(target.userId), routePrefix);
    url.searchParams.set("section", "users");
  }
  return url;
}
