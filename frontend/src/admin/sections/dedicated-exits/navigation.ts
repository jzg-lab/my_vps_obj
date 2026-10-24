import { withRoutePrefix } from "$lib/webapp/routes";

export type DedicatedExitsRoute = {
  page: number;
  exitId: string;
  auditPage: number;
  serviceId: string;
};

export function readDedicatedExitsRoute(search: string): DedicatedExitsRoute {
  const params = new URLSearchParams(search);
  function page(key: string): number {
    const value = Number(params.get(key) ?? 0);
    return Number.isSafeInteger(value) && value >= 0 && value <= 1_000_000 ? value : 0;
  }
  return {
    page: page("exits_page"),
    exitId: params.get("exit_id") ?? "",
    auditPage: page("exit_audit_page"),
    serviceId: params.get("exit_service_id") ?? "",
  };
}

export function dedicatedExitsUrl(
  current: string,
  route: DedicatedExitsRoute,
  routePrefix = ""
): URL {
  const url = new URL(current);
  url.pathname = withRoutePrefix("/admin/dedicated-exits", routePrefix);
  url.searchParams.set("section", "dedicated-exits");
  for (const [key, value] of Object.entries({
    exits_page: route.page ? String(route.page) : "",
    exit_id: route.exitId,
    exit_audit_page: route.auditPage ? String(route.auditPage) : "",
    exit_service_id: route.serviceId,
  })) {
    if (value) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
  }
  return url;
}
