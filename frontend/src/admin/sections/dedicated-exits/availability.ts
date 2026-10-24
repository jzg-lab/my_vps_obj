import type { DedicatedExit, UserService } from "$lib/admin/servicePlans";
import { builtApiPath, unwrap, type ApiClient } from "$lib/webapp/publicApi";

export function exitHasHold(resource: DedicatedExit): boolean {
  return resource.hold_order_id != null || resource.hold_service_id != null;
}

export function exitAvailable(resource: DedicatedExit, pool: string | null | undefined): boolean {
  return (
    resource.enabled &&
    resource.service_id === null &&
    !exitHasHold(resource) &&
    resource.resource_pool === pool
  );
}

export type EvidenceService = Pick<UserService, "id" | "replacement_order_id">;

export function exitEvidenceBlocked(
  resource: DedicatedExit,
  service: EvidenceService | null
): boolean {
  return (
    exitHasHold(resource) ||
    (resource.service_id !== null &&
      (service?.id !== resource.service_id || service.replacement_order_id !== null))
  );
}

export async function readEvidenceService(
  api: ApiClient["api"],
  serviceId: string,
  signal: AbortSignal
): Promise<EvidenceService> {
  const { service } = unwrap(
    await api(
      builtApiPath<"/api/admin/console/services/{service_id}">(
        `/admin/console/services/${encodeURIComponent(serviceId)}`
      ),
      { signal }
    )
  );
  if (
    service.id !== serviceId ||
    (service.replacement_order_id !== null && typeof service.replacement_order_id !== "string")
  )
    throw new Error("Unknown bound service replacement state");
  return service;
}
