import { describe, expect, it } from "vitest";
import {
  servicePlanBody,
  servicePlanDraft,
  serviceErrorKey,
  serviceBytes,
  GIB,
  type ServicePlan,
} from "./servicePlans";

const plan: ServicePlan = {
  id: "a".repeat(32),
  revision: 3,
  updated_at: "2026-10-22T00:00:00Z",
  enabled: true,
  terms: {
    name: "Custom plan",
    description: "",
    resource_type: "shared",
    traffic_rule: "monthly",
    quota_bytes: 100 * GIB + 17,
    validity_days: 365,
    price: "99.90",
    currency: "CNY",
    squad_uuids: ["squad-a"],
    resource_pool: null,
  },
};

describe("independent plan forms", () => {
  it("preserves exact byte quotas and the original snapshot while editing", () => {
    const draft = servicePlanDraft(plan);
    expect(servicePlanBody(draft).terms).toEqual(plan.terms);
    draft.squadUuids.push("squad-b");
    draft.name = "Next plan";
    expect(plan.terms.squad_uuids).toEqual(["squad-a"]);
    expect(plan.terms.name).toBe("Custom plan");
  });
  it("removes fields belonging to the other resource type", () => {
    const draft = servicePlanDraft(plan);
    draft.resourceType = "dedicated";
    draft.resourcePool = " exclusive ";
    expect(servicePlanBody(draft).terms).toMatchObject({
      squad_uuids: [],
      resource_pool: "exclusive",
    });
    draft.resourceType = "shared";
    expect(servicePlanBody(draft).terms).toMatchObject({
      squad_uuids: ["squad-a"],
      resource_pool: null,
    });
  });
  it.each([
    { quotaGiB: "0" },
    { quotaGiB: "1e20" },
    { quotaGiB: "0.00000000001" },
    { validityDays: "1.5" },
    { validityDays: "36501" },
    { price: "-1" },
    { price: "1e3" },
    { price: "1.234" },
    { currency: "CN" },
  ])("rejects invalid commercial terms %j", (value) => {
    expect(() => servicePlanBody({ ...servicePlanDraft(plan), ...value })).toThrow(
      "services_invalid_terms"
    );
  });
  it("requires resources and maps actual API conflicts to actionable labels", () => {
    expect(() => servicePlanBody({ ...servicePlanDraft(plan), squadUuids: [] })).toThrow(
      "services_resource_required"
    );
    expect(serviceErrorKey({ error: "plan_revision_changed" })).toBe("services_plan_changed");
    expect(serviceErrorKey({ error: "plan_disabled" })).toBe("services_plan_unavailable");
    expect(serviceErrorKey(new Error("network"))).toBe("services_request_failed");
  });
  it("does not cap usage at the quota or round tiny usage to zero GiB", () => {
    expect(serviceBytes(117 * GIB)).toBe("117 GiB");
    expect(serviceBytes(13)).toBe("13 B");
  });
});
