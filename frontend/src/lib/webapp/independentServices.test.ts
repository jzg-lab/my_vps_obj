import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import {
  independentServiceScreen,
  serviceDate,
  serviceStatusKey,
  serviceUsage,
} from "./independentServices.js";

describe("independent service presentation", () => {
  it("shows real overage while bounding only the progress indicator", () => {
    expect(serviceUsage({ used_bytes: 117, quota_bytes: 100 })).toEqual({
      remaining: 0,
      overage: 17,
      percent: 100,
    });
    expect(serviceUsage({ used_bytes: 23, quota_bytes: 100 })).toEqual({
      remaining: 77,
      overage: 0,
      percent: 23,
    });
  });
  it("uses Beijing dates independently of the browser timezone", () => {
    expect(serviceDate("2026-10-31T16:30:00Z")).toBe("2026-11-01 00:30");
    expect(serviceDate(null)).toBe("—");
  });
  it("does not treat an unknown status as active", () => {
    expect(serviceStatusKey("new_state")).toBe("wa_services_status_unknown");
  });
  it.each(["trial", "install", "devices", "invite", "partner", "payment-history", "checkout"])(
    "redirects old %s pages to independent services",
    (screen) => {
      expect(independentServiceScreen(screen)).toBe("home");
    }
  );
  it.each(["settings", "security", "notifications", "support", "admin"])(
    "keeps %s usable",
    (screen) => {
      expect(independentServiceScreen(screen)).toBe(screen);
    }
  );
  it("ships the service copy in both base languages", () => {
    const en = JSON.parse(
      readFileSync(new URL("../../../../locales/en.json", import.meta.url), "utf8")
    );
    const ru = JSON.parse(
      readFileSync(new URL("../../../../locales/ru.json", import.meta.url), "utf8")
    );
    const source = readFileSync(
      new URL("../../webapp/screens/ServicesScreen.svelte", import.meta.url),
      "utf8"
    );
    for (const key of source.matchAll(/"(wa_services_\w+)"/g)) {
      expect(en[key[1]], key[1]).toBeTruthy();
      expect(ru[key[1]], key[1]).toBeTruthy();
    }
  });
});
