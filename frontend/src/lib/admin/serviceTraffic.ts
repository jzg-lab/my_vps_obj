import type { components } from "$lib/api/openapi.generated";

export type ServiceTraffic = components["schemas"]["ConsoleServiceTrafficOut"];

export function serviceTrafficMessage(history: ServiceTraffic | null | undefined) {
  if (!history || history.availability === "unavailable") return "console_visual_history_failed";
  if (history.availability === "unconfigured") return "console_visual_history_unconfigured";
  if (!history.days?.some((day) => day.bytes !== null)) return "console_visual_history_no_samples";
  return history.availability === "partial" ? "console_availability_partial" : null;
}
