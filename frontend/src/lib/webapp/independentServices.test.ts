import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import {
  independentServiceScreen,
  serviceDate,
  serviceStatusKey,
  serviceNextStepKey,
  serviceUsage,
  serviceResetState,
} from "./independentServices.js";

describe("independent service presentation", () => {
  it("only offers import guidance for an active confirmed service", () => {
    expect(serviceNextStepKey({ status: "pending", sync_pending: false })).toBe(
      "wa_services_next_pending"
    );
    expect(serviceNextStepKey({ status: "active", sync_pending: true })).toBe(
      "wa_services_next_sync"
    );
    expect(serviceNextStepKey({ status: "active", sync_pending: false })).toBe(
      "wa_services_next_import"
    );
    expect(serviceNextStepKey({ status: "exhausted", sync_pending: false })).toBe(
      "wa_services_next_exhausted"
    );
    expect(serviceNextStepKey({ status: "expired", sync_pending: false })).toBe(
      "wa_services_next_expired"
    );
    expect(serviceNextStepKey({ status: "paused", sync_pending: false })).toBe(
      "wa_services_next_review"
    );
  });
  it("shows real overage while bounding only the progress indicator", () => {
    expect(
      serviceUsage({
        used_bytes: 117,
        quota_bytes: 100,
        last_usage_sync_at: "2026-10-24T00:00:00Z",
      })
    ).toEqual({
      remaining: 0,
      overage: 17,
      percent: 100,
    });
    expect(
      serviceUsage({ used_bytes: 23, quota_bytes: 100, last_usage_sync_at: "2026-10-24T00:00:00Z" })
    ).toEqual({
      remaining: 77,
      overage: 0,
      percent: 23,
    });
  });
  it("does not turn an initial counter or allowance into confirmed usage", () => {
    for (const used_bytes of [0, 25])
      expect(serviceUsage({ used_bytes, quota_bytes: 100, last_usage_sync_at: null })).toEqual({
        remaining: null,
        overage: null,
        percent: null,
      });
    expect(
      serviceUsage({ used_bytes: 0, quota_bytes: 100, last_usage_sync_at: "2026-10-24T00:00:00Z" })
    ).toEqual({
      remaining: 100,
      overage: 0,
      percent: 0,
    });
  });
  it("keeps independent balances and leaves an old confirmed sample intact", () => {
    const sample = { quota_bytes: 100, last_usage_sync_at: "2026-10-01T00:00:00Z" };
    expect(serviceUsage({ ...sample, used_bytes: 120 }).remaining).toBe(0);
    expect(serviceUsage({ ...sample, used_bytes: 20 }).remaining).toBe(80);
  });
  it.each(["2026-11-20T00:00:00Z", "2026-11-24T00:00:00Z"])(
    "does not promise another monthly allowance when expiry is %s",
    (expires_at) => {
      expect(
        serviceResetState({
          traffic_rule: "monthly",
          cycle_ends_at: "2026-11-24T00:00:00Z",
          expires_at,
          status: "active",
          desired_status: "active",
        })
      ).toBe("expires_first");
    }
  );
  it("distinguishes a future boundary, missing dates and a total allowance", () => {
    const period = {
      traffic_rule: "monthly" as const,
      cycle_ends_at: "2026-11-24T00:00:00Z",
      expires_at: "2026-12-24T00:00:00Z",
      status: "active" as const,
      desired_status: "active" as const,
    };
    expect(serviceResetState(period)).toBe("scheduled");
    expect(serviceResetState({ ...period, cycle_ends_at: null })).toBe("unknown");
    expect(serviceResetState({ ...period, cycle_ends_at: "bad" })).toBe("unknown");
    expect(serviceResetState({ ...period, traffic_rule: "total" })).toBe("not_monthly");
    expect(serviceResetState({ ...period, desired_status: "cancelled" })).toBe("ended");
    expect(
      serviceResetState({ ...period, status: "account_banned", desired_status: "cancelled" })
    ).toBe("ended");
    expect(serviceResetState({ ...period, status: "expired" })).toBe("ended");
    expect(serviceResetState({ ...period, status: "paused", desired_status: "paused" })).toBe(
      "scheduled"
    );
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
  it.each(["services", "settings", "security", "notifications", "support", "admin"])(
    "keeps %s usable",
    (screen) => {
      expect(independentServiceScreen(screen)).toBe(screen);
    }
  );
  it("ships service and home copy in all three languages", () => {
    const en = JSON.parse(
      readFileSync(new URL("../../../../locales/en.json", import.meta.url), "utf8")
    );
    const ru = JSON.parse(
      readFileSync(new URL("../../../../locales/ru.json", import.meta.url), "utf8")
    );
    const zh = JSON.parse(
      readFileSync(new URL("../../../../locales/zh-hans.json", import.meta.url), "utf8")
    );
    const source = ["ServicesScreen", "ServicesHomeScreen"]
      .map((name) =>
        readFileSync(new URL(`../../webapp/screens/${name}.svelte`, import.meta.url), "utf8")
      )
      .join("\n");
    for (const key of source.matchAll(/"(wa_services_\w+)"/g)) {
      expect(en[key[1]], key[1]).toBeTruthy();
      expect(ru[key[1]], key[1]).toBeTruthy();
      expect(zh[key[1]], key[1]).toBeTruthy();
    }
  });
});
