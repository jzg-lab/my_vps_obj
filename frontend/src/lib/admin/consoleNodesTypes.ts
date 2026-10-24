import type { components } from "$lib/api/openapi.generated";

export type ConsoleNodesTranslate = (
  key: string,
  params?: Record<string, unknown>,
  fallback?: string
) => string;

export type ConsoleNode = components["schemas"]["ConsoleNodeOut"];
export type ConsoleNodesPage = components["schemas"]["ConsoleNodesListOut"];
export type ConsoleNodeDetail = components["schemas"]["ConsoleNodeDetailOut"];
export type ConsoleServiceResources = components["schemas"]["ConsoleServiceResourcesOut"];
export type ConsoleNodeSource = components["schemas"]["ConsoleNodeSourceOut"];
export type ConsoleNodeTraffic = components["schemas"]["ConsoleNodeTrafficWindowOut"];
export type ConsoleNodeTrafficPreset = components["schemas"]["ConsoleNodeTrafficPreset"];
