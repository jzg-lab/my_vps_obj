import { nodesRouteUrl, readNodesRoute } from "$lib/admin/consoleNodesNavigation";
import { nodeOperations, type NodeChange } from "./resourcePreview";

export type NodePreviewRoute = {
  open: boolean;
  operation: NodeChange["operation"] | "";
  forceRestart: boolean;
  serviceId: string;
};

export function readNodePreviewRoute(search: string): NodePreviewRoute {
  const params = new URLSearchParams(search);
  const open = params.get("resource_preview") === "node";
  const operation = open
    ? (nodeOperations.find((item) => item === params.get("resource_action")) ?? "")
    : "";
  return {
    open,
    operation,
    forceRestart: operation === "node_restart" && params.get("resource_force") === "1",
    serviceId: open ? (params.get("resource_service_id") ?? "") : "",
  };
}

export function nodePreviewChange(nodeId: string, route: NodePreviewRoute): NodeChange | null {
  return route.open && route.operation
    ? {
        operation: route.operation,
        target_id: nodeId,
        force_restart: route.operation === "node_restart" && route.forceRestart,
      }
    : null;
}

export function nodePreviewUrl(current: string, route: NodePreviewRoute, routePrefix = ""): URL {
  const url = nodesRouteUrl(current, readNodesRoute(new URL(current).search), routePrefix);
  for (const key of [
    "resource_preview",
    "resource_action",
    "resource_force",
    "resource_service_id",
  ])
    url.searchParams.delete(key);
  if (route.open) {
    url.searchParams.set("resource_preview", "node");
    if (route.operation) url.searchParams.set("resource_action", route.operation);
    if (route.operation === "node_restart" && route.forceRestart)
      url.searchParams.set("resource_force", "1");
    if (route.serviceId) url.searchParams.set("resource_service_id", route.serviceId);
  }
  return url;
}
