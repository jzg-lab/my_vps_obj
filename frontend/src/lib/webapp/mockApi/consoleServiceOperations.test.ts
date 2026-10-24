import { describe, expect, it } from "vitest";
import {
  createConsoleServiceOperationsDemo,
  type ConsoleServiceOperationsDemoState,
} from "./consoleServiceOperations";
import { consoleNodeServiceFixture } from "$lib/admin/consoleNodesFixtures";
import { operationFixture } from "$lib/admin/consoleServiceOperationsFixtures";
import type { UserService } from "$lib/admin/servicePlans";

function fixture() {
  const service: UserService = {
    ...consoleNodeServiceFixture.service,
    user_id: 910001,
    revision: 3,
  };
  const state: ConsoleServiceOperationsDemoState = {
    owner: 910001,
    services: [service],
    archived: [],
    plans: [],
    exits: [],
    operations: [{ ...operationFixture, service_id: service.id }],
  };
  const respond = createConsoleServiceOperationsDemo();
  return {
    state,
    service,
    read: (suffix: string) => respond(`/admin/console/services/${service.id}/${suffix}`, {}, state),
    post: (path: string, body: unknown) =>
      respond(path, { method: "POST", body: JSON.stringify(body) }, state),
  };
}
describe("isolated console service operations demo adapter", () => {
  it("leaves unrelated routes to the shared router", () => {
    const { state } = fixture();
    expect(
      createConsoleServiceOperationsDemo()("/admin/console/summary", {}, state)
    ).toBeUndefined();
  });
  it("returns a read-only unconfigured observation, never fake zero usage or remote success", () => {
    const { read, service } = fixture();
    const before = structuredClone(service);
    expect(read("diagnostics")).toMatchObject({
      ok: true,
      user_id: 910001,
      remote: { availability: "unconfigured", raw_used_bytes: null, observed_at: null },
      data_plane_verified: false,
    });
    expect(service).toEqual(before);
  });
  it("allows pending creation with unknown resources but never reports delivery ready", () => {
    const { state, post } = fixture();
    state.plans = [
      {
        id: "1".repeat(32),
        revision: 1,
        enabled: true,
        updated_at: "2026-10-24T01:00:00Z",
        terms: consoleNodeServiceFixture.terms,
      },
    ];
    const request = {
      user_id: state.owner,
      plan_id: state.plans[0].id,
      expected_revision: 1,
      exit_id: null,
    };
    expect(post("/admin/console/service-preflight", request)).toMatchObject({
      ok: true,
      allow_pending_creation: true,
      resource_readiness: "unknown",
      ready_for_delivery: false,
    });
    expect(
      post("/admin/console/service-preflight", { ...request, expected_revision: 2 })
    ).toMatchObject({ allow_pending_creation: false });
  });
  it("returns the full total and pages, not a page-sized total", () => {
    const { state, read } = fixture();
    state.operations = Array.from({ length: 27 }, (_, index) => ({
      ...operationFixture,
      id: index.toString(16).padStart(32, "0"),
    }));
    const response = read("operations?offset=25&limit=25");
    expect(response).toMatchObject({ total: 27, offset: 25, limit: 25 });
    expect(response).toHaveProperty("operations.length", 2);
  });
  it("blocks a held dedicated exit even when it is enabled and has no current binding", () => {
    const { state, post } = fixture();
    state.plans = [
      {
        id: "1".repeat(32),
        revision: 1,
        enabled: true,
        updated_at: "2026-10-24T01:00:00Z",
        terms: {
          ...consoleNodeServiceFixture.terms,
          resource_type: "dedicated",
          resource_pool: "private",
          squad_uuids: [],
        },
      },
    ];
    state.exits = [
      {
        id: "2".repeat(32),
        label: "Held exit",
        revision: 1,
        ip_address: "192.0.2.10",
        resource_pool: "private",
        squad_uuid: "3".repeat(32),
        service_id: null,
        hold_order_id: "4".repeat(32),
        hold_service_id: "5".repeat(32),
        verified_at: null,
        enabled: true,
      },
    ];
    const body = {
      user_id: state.owner,
      plan_id: state.plans[0].id,
      expected_revision: 1,
      exit_id: state.exits[0].id,
    };
    expect(post("/admin/console/service-preflight", body)).toMatchObject({
      allow_pending_creation: false,
      checks: expect.arrayContaining([
        { code: "exit", status: "blocked", reason: "exit_unavailable" },
      ]),
    });
    state.exits[0].hold_order_id = null;
    state.exits[0].hold_service_id = null;
    expect(post("/admin/console/service-preflight", body)).toMatchObject({
      allow_pending_creation: true,
    });
  });
  it("retains nullable archives and rejects business retries", () => {
    const { service, read, post } = fixture();
    service.user_id = null;
    expect(read("diagnostics")).toMatchObject({ user_id: null });
    expect(
      post(`/admin/console/services/${service.id}/operations/${operationFixture.id}/retry`, {
        user_id: 0,
        expected_revision: 3,
        idempotency_key: "same",
      })
    ).toMatchObject({ ok: false, error: "service_not_found" });
  });
  it("acknowledges one intent twice without modifying entitlement, usage or historical times", () => {
    const { state, service, post } = fixture();
    const before = structuredClone(service);
    const path = `/admin/console/services/${service.id}/operations/${operationFixture.id}/retry`;
    const body = { user_id: 910001, expected_revision: 3, idempotency_key: "same" };
    const accepted = post(path, body);
    expect(accepted).toMatchObject({
      accepted: true,
      duplicate: false,
      operation: {
        status: "pending",
        first_failed_at: operationFixture.first_failed_at,
        completed_at: null,
      },
    });
    expect(post(path, body)).toMatchObject({ accepted: true, duplicate: true });
    expect(service).toEqual(before);
    expect(state.operations?.[0].attempt_count).toBe(1);
    expect(state.operations?.[0]).toEqual({
      ...operationFixture,
      service_id: service.id,
      status: "pending",
    });
    expect(post(path, { ...body, expected_revision: 4 })).toMatchObject({
      ok: false,
      error: "idempotency_conflict",
    });
  });
  it("keeps an already unknown result and every historical observation on acceptance", () => {
    const { state, service, post } = fixture();
    const operation = { ...operationFixture, service_id: service.id, status: "unknown" as const };
    state.operations = [structuredClone(operation)];
    expect(
      post(`/admin/console/services/${service.id}/operations/${operation.id}/retry`, {
        user_id: 910001,
        expected_revision: 3,
        idempotency_key: "unknown-retry",
      })
    ).toMatchObject({ accepted: true, operation });
    expect(state.operations[0]).toEqual(operation);
  });
});
