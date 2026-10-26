import { describe, expect, it } from "vitest";
import { serviceTrafficMessage, type ServiceTraffic } from "./serviceTraffic";

const history: ServiceTraffic = {
  service_id: "a".repeat(32),
  start_date: "2026-10-21",
  end_date: "2026-10-27",
  availability: "available",
  timezone: "UTC",
  observed_at: null,
  source: "panel_service_identity_raw_traffic_not_billing",
  history_completeness: "unknown",
  days: [],
  nodes: [],
};
describe("service history states", () => {
  it("separates an unconfigured source, failed read and absent samples", () => {
    expect(serviceTrafficMessage(null)).toBe("console_visual_history_failed");
    expect(serviceTrafficMessage({ ...history, availability: "unavailable" })).toBe(
      "console_visual_history_failed"
    );
    expect(serviceTrafficMessage({ ...history, availability: "unconfigured" })).toBe(
      "console_visual_history_unconfigured"
    );
    expect(serviceTrafficMessage(history)).toBe("console_visual_history_no_samples");
    expect(serviceTrafficMessage({ ...history, days: [{ date: "2026-10-27", bytes: null }] })).toBe(
      "console_visual_history_no_samples"
    );
  });
  it("preserves real zero and partial observations", () => {
    const zero = { ...history, days: [{ date: "2026-10-27", bytes: 0 }] };
    expect(serviceTrafficMessage(zero)).toBeNull();
    expect(serviceTrafficMessage({ ...zero, availability: "partial" })).toBe(
      "console_availability_partial"
    );
  });
});
