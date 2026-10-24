import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  independentServicesCustomerSummaries,
  independentServicesDemoResponse,
  seedIndependentServicesDemo,
} from "./independentServices";
import { withCustomerServiceSummaries } from "./adminConsole";
import { mockApi } from "../mockApi";
import { demoApiResponse } from "./datasetApi";
import { issueReviewDemoResponse } from "./issueReview";
import { adminFallbackResponse } from "./adminFallback";
import { buildAdminDemoFixtures } from "./adminFixtures";
import { DATASET } from "./dataset";
import type { paths } from "$lib/api/openapi.generated";
import { resetResourceOperationsDemo } from "./consoleResourceOperations";

const read = (path: string) => independentServicesDemoResponse(`/admin/console/${path}`, {});

describe("console demo shares the existing service fixture", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.stubGlobal("window", { location: { search: "" }, setTimeout });
    seedIndependentServicesDemo(42);
    resetResourceOperationsDemo();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("keeps totals, filtering and pagination consistent", () => {
    expect(read("summary")).toMatchObject({
      ok: true,
      customers: { total: 1, with_services: 1 },
      services: { total: 12, by_status: { pending: 11, exhausted: 1 } },
      usage: { services_sampled: 2, availability: "partial" },
      health: { scope: "including_archived_services", usage_failed: 2 },
    });
    expect(read("services?status=exhausted&page_size=1")).toMatchObject({
      total: 1,
      services: [{ service: { status: "exhausted" }, customer: { user_id: 42 } }],
    });
    expect(read("services?status=exhausted&page_size=1&page=1")).toMatchObject({
      total: 1,
      services: [],
    });
    expect(read("services?user_id=43")).toMatchObject({ total: 0, services: [] });
    expect(read("services?q=dedicated")).toMatchObject({ total: 1 });
    expect(read("services?status=usage_unconfirmed")).toMatchObject({ total: 11 });
  });

  it("provides the complete detail and does not pretend the panel is configured", () => {
    const id = "10".padStart(32, "0");
    expect(read(`services/${id}`)).toMatchObject({
      service: { id },
      terms: { price: "29.90", currency: "CNY" },
      connection: null,
    });
    expect(read(`services/${id}/resources`)).toMatchObject({
      service_id: id,
      coverage: "unavailable",
      remote_authorization_verified: false,
    });
    expect(read("nodes")).toMatchObject({ total: null, nodes: [], coverage: "unavailable" });
    expect(read("nodes/missing")).toEqual({ ok: false, error: "node_not_found" });
    expect(read("services/missing")).toEqual({ ok: false, error: "service_not_found" });
  });

  it("matches the known zero of an empty service inventory", () => {
    seedIndependentServicesDemo(42, true);
    expect(read("summary")).toMatchObject({
      services: { total: 0 },
      usage: { confirmed_used_bytes: 0, availability: "available" },
    });
  });

  it("does not disguise unknown console routes as a successful service detail", async () => {
    const id = "10".padStart(32, "0");
    expect(read(`services/${id}/unknown`)).toBeUndefined();
    for (const path of [`/admin/console/services/${id}/unknown`, "/admin/console/unknown"])
      expect(await mockApi(path, {}, { currentLang: "en" })).toEqual({
        ok: false,
        error: "route_not_found",
      });
  });

  it("dispatches resource preview before the general console fallback", async () => {
    const path = "/admin/console/resources/preview";
    expect(await mockApi(path, {}, { currentLang: "en" })).toEqual({
      ok: false,
      error: "method_not_allowed",
    });
    expect(await mockApi(path, { method: "POST", body: "{}" }, { currentLang: "en" })).toEqual({
      ok: false,
      error: "invalid_resource_change",
      status: 400,
    });
  });

  it("dispatches resource catalog, history and deployment before older fallbacks", async () => {
    const context = { currentLang: "en" };
    expect(await mockApi("/admin/console/resources/catalog", {}, context)).toMatchObject({
      ok: true,
      execution_available: true,
    });
    expect(await mockApi("/admin/console/resources/operations", {}, context)).toEqual({
      ok: true,
      items: [],
      total: 0,
    });
    expect(
      await mockApi(
        "/admin/console/nodes/onboarding/deployment",
        { method: "POST", body: JSON.stringify({ management_port: 2222 }) },
        context
      )
    ).toMatchObject({ ok: true, management_port: 2222, installation_performed: false });
  });

  it("routes preflight and diagnostics through the existing mutable inventory", async () => {
    const userId = Number(DATASET.currentUser?.user_id);
    seedIndependentServicesDemo(userId);
    expect(
      await mockApi(
        "/admin/console/service-preflight",
        {
          method: "POST",
          body: JSON.stringify({
            user_id: userId,
            plan_id: "1".repeat(32),
            expected_revision: 1,
            exit_id: null,
          }),
        },
        { currentLang: "en" }
      )
    ).toMatchObject({
      ok: true,
      allow_pending_creation: true,
      resource_readiness: "unknown",
      ready_for_delivery: false,
    });
    const id = "12".padStart(32, "0");
    expect(read(`services/${id}/diagnostics`)).toMatchObject({
      service_id: id,
      user_id: userId,
      remote: { availability: "unconfigured", observed_at: null },
      data_plane_verified: false,
    });
    independentServicesDemoResponse(`/admin/services/${id}/changes`, {
      method: "POST",
      body: JSON.stringify({
        user_id: userId,
        expected_revision: 1,
        idempotency_key: "operations-pause",
        change: { action: "pause" },
      }),
    });
    expect(read(`services/${id}/diagnostics`)).toMatchObject({
      service_revision: 2,
      desired_status: "paused",
      target_access: "disabled",
    });
    expect(read(`services/${id}/operations?limit=1`)).toMatchObject({
      service_revision: 2,
      operations: [{ kind: "pause", status: "unknown", retryable: false }],
    });
    expect(
      await mockApi(`/admin/console/operations?service_id=${id}`, {}, { currentLang: "en" })
    ).toMatchObject({
      ok: true,
      total: 1,
      operations: [
        {
          service_id: id,
          service_revision: 2,
          customer: { user_id: userId },
          kind: "pause",
          record_type: "order",
          status: "unknown",
          needs_attention: false,
        },
      ],
    });
    expect(read(`operations?service_id=${id}&needs_attention=true`)).toMatchObject({
      total: 0,
      operations: [],
    });
  });

  it("keeps archived diagnostics and unknown history read-only", () => {
    const id = (200).toString(16).padStart(32, "0");
    expect(read(`services/${id}/diagnostics`)).toMatchObject({
      user_id: null,
      status: "cancelled",
      remote: { availability: "unconfigured" },
    });
    expect(read(`services/${id}/operations`)).toMatchObject({
      total: 1,
      operations: [{ status: "unknown", retryable: false, attempted_at: null }],
    });
    expect(read(`operations?service_id=${id}&archived=only`)).toMatchObject({
      total: 1,
      operations: [{ archived: true, customer: { user_id: null }, status: "unknown" }],
    });
  });

  it("aggregates the same-plan inventory once per owner, excludes archives and preserves fields", () => {
    const response = {
      ok: true,
      users: [{ user_id: 42, email: "owner@test", balance: { amount: "9" } }, { user_id: 43 }],
      total: 100,
      page: 3,
      page_size: 2,
    };
    const result = independentServicesCustomerSummaries(response);
    expect(result).toMatchObject({
      ...response,
      users: [
        {
          ...response.users[0],
          independent_services: {
            total: 12,
            by_status: { pending: 11, exhausted: 1 },
            sync_error: 1,
            sync_unobserved: 12,
            usage_unobserved: 10,
            oldest_sync_confirmed_at: null,
            latest_sync_confirmed_at: null,
            oldest_usage_sync_at: "2026-10-22T04:00:00Z",
            latest_usage_sync_at: "2026-10-22T04:00:00Z",
            activity: "not_collected",
          },
        },
        {
          user_id: 43,
          independent_services: { total: 0, sync_error: 0, latest_usage_sync_at: null },
        },
      ],
    });
    expect(response.users[0]).not.toHaveProperty("independent_services");
  });

  it("does not turn an account ban into a service error", () => {
    expect(
      independentServicesCustomerSummaries({ ok: true, users: [{ user_id: 42, is_banned: true }] })
    ).toMatchObject({
      users: [
        {
          is_banned: true,
          independent_services: {
            total: 12,
            by_status: { account_banned: 12, pending: 0, exhausted: 0 },
            sync_error: 1,
          },
        },
      ],
    });
  });

  it("counts overlapping states independently and keeps oldest/latest successful evidence", () => {
    const response = independentServicesDemoResponse(
      "/admin/services?user_id=42",
      {}
    ) as paths["/api/admin/services"]["get"]["responses"][200]["content"]["application/json"];
    const first = response.services[0];
    const services = [
      {
        ...first,
        status: "cancelled" as const,
        sync_error: "failed",
        sync_pending: true,
        cycle_pending: true,
        sync_confirmed_at: "2026-10-24T01:00:00Z",
      },
      {
        ...first,
        id: "second",
        status: "paused" as const,
        sync_confirmed_at: "2026-10-22T01:00:00Z",
        last_usage_sync_at: null,
      },
      { ...first, id: "archive", user_id: null },
      { ...first, id: "outside", user_id: 99 },
    ];
    expect(
      withCustomerServiceSummaries({ ok: true, users: [{ user_id: 42 }] }, services)
    ).toMatchObject({
      users: [
        {
          independent_services: {
            total: 2,
            by_status: { cancelled: 1, paused: 1 },
            sync_error: 1,
            sync_pending: 1,
            cycle_pending: 1,
            sync_unobserved: 0,
            usage_unobserved: 1,
            oldest_sync_confirmed_at: "2026-10-22T01:00:00Z",
            latest_sync_confirmed_at: "2026-10-24T01:00:00Z",
          },
        },
      ],
    });
  });

  it("does not fabricate a known zero from failure or an unidentified user", () => {
    for (const response of [null, { ok: false, error: "offline" }, { ok: true, users: null }])
      expect(independentServicesCustomerSummaries(response)).toBe(response);
    const response = { ok: true, users: [null, {}, { user_id: "" }, { user_id: "bad" }] };
    expect(independentServicesCustomerSummaries(response)).toEqual(response);
  });

  it.each(["", "?issues_demo=1"])(
    "enriches final output %s without altering searches or pagination",
    async (search) => {
      window.location.search = search;
      seedIndependentServicesDemo(Number(DATASET.currentUser?.user_id));
      for (const path of [
        "/admin/users?page=0&page_size=25",
        "/admin/users?page=1&page_size=25",
        "/admin/users?q=not-found-customer",
        "/admin/users?filter=banned&page_size=5",
        "/admin/users?q=Alex",
      ]) {
        const expected =
          issueReviewDemoResponse(path, {}, "en") ?? demoApiResponse(path, "/admin/users", {}, {});
        const actual = await mockApi(path, {}, { currentLang: "en" });
        expect(actual).toEqual(independentServicesCustomerSummaries(expected));
      }
    }
  );

  it("reflects changes to the existing mutable service inventory", () => {
    const result = independentServicesDemoResponse(
      `/admin/services/${"12".padStart(32, "0")}/changes`,
      {
        method: "POST",
        body: JSON.stringify({
          user_id: 42,
          expected_revision: 1,
          idempotency_key: "customer-summary-pause",
          change: { action: "pause" },
        }),
      }
    );
    expect(result).toMatchObject({ ok: true });
    expect(
      independentServicesCustomerSummaries({ ok: true, users: [{ user_id: 42 }] })
    ).toMatchObject({
      users: [
        {
          independent_services: {
            total: 12,
            by_status: { paused: 1, pending: 10 },
            sync_pending: 1,
          },
        },
      ],
    });
  });

  it("enriches the fallback list through the same wrapper", () => {
    const response = adminFallbackResponse(
      "/admin/users",
      "/admin/users",
      {},
      {},
      buildAdminDemoFixtures()
    );
    expect(independentServicesCustomerSummaries(response)).toMatchObject({
      ok: true,
      users: expect.arrayContaining([
        expect.objectContaining({
          independent_services: expect.objectContaining({
            source: "local_independent_service_records",
          }),
        }),
      ]),
    });
  });
});
