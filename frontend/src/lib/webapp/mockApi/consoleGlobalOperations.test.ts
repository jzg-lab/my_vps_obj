import { describe, expect, it } from "vitest";
import { consoleGlobalOperationsDemoResponse } from "./consoleGlobalOperations";
import type { ConsoleServiceOperationsDemoState } from "./consoleServiceOperations";
import { consoleNodeServiceFixture } from "$lib/admin/consoleNodesFixtures";
import { operationFixture } from "$lib/admin/consoleServiceOperationsFixtures";
import type { ServiceOrder } from "$lib/admin/serviceHistory";
import { demoAdminUserById } from "./users";

const legacy: ServiceOrder = {
  id: "b".repeat(32),
  service_id: operationFixture.service_id,
  user_id: 910001,
  kind: "activate",
  actor_id: 7,
  created_at: operationFixture.created_at,
  snapshot: {},
};
function fixture() {
  const state: ConsoleServiceOperationsDemoState = {
    owner: 0,
    services: [{ ...consoleNodeServiceFixture.service, user_id: 910002 }],
    archived: [],
    plans: [],
    exits: [],
    orders: [legacy],
    operations: [],
  };
  const read = (query = "") => {
    const response = consoleGlobalOperationsDemoResponse(
      `/admin/console/operations${query ? `?${query}` : ""}`,
      {},
      state
    );
    if (!response?.ok) throw new Error(response?.error);
    return response;
  };
  return { state, read };
}

describe("global operations reads the existing demo ledger", () => {
  it("leaves unrelated paths alone, never writes, and rejects malformed filters/cursors", () => {
    const { state } = fixture();
    expect(
      consoleGlobalOperationsDemoResponse("/admin/console/summary", {}, state)
    ).toBeUndefined();
    expect(
      consoleGlobalOperationsDemoResponse("/admin/console/operations", { method: "POST" }, state)
    ).toMatchObject({ ok: false });
    for (const query of [
      "unknown=1",
      "limit=0",
      "limit=201",
      "status=secret",
      "status=failed&status=unknown",
      "phase=bad",
      "needs_attention=1",
      "archived=bad",
      "user_id=",
      "user_id=1.5",
      "service_id=bad",
      "cursor=",
      "cursor=bad",
    ]) {
      expect(
        consoleGlobalOperationsDemoResponse(`/admin/console/operations?${query}`, {}, state)
      ).toMatchObject({ ok: false, error: "invalid_global_operations_query" });
    }
  });
  it("keeps historical unknown orders out of attention without inventing execution evidence", () => {
    const { state, read } = fixture();
    const before = structuredClone(state);
    expect(read().operations[0]).toMatchObject({
      record_type: "order",
      status: "unknown",
      needs_attention: false,
      phase: null,
      attempt_count: null,
      attempted_at: null,
      first_failed_at: null,
      last_success_at: null,
      completed_at: null,
    });
    expect(read("needs_attention=true").total).toBe(0);
    expect(state).toEqual(before);
  });
  it("uses the service's current owner instead of the order owner or GET state.owner=0", () => {
    const { state, read } = fixture();
    const user = demoAdminUserById(910002)!;
    expect(read().operations[0].customer).toMatchObject({
      user_id: user.user_id,
      minishop_id: user.minishop_id,
    });
    expect(read("user_id=910001").total).toBe(0);
    expect(read("user_id=910002").total).toBe(1);
    state.services[0].user_id = 910001;
    expect(read("user_id=910002").total).toBe(0);
    expect(read("user_id=910001").operations[0].customer.user_id).toBe(910001);
  });
  it("clears archived identity and never exposes order snapshots or service credentials", () => {
    const { state, read } = fixture();
    state.archived.push({ ...state.services.pop()!, user_id: null });
    state.orders![0].snapshot = { secret: "private-token" };
    expect(read("archived=only").operations[0]).toMatchObject({
      archived: true,
      customer: {
        user_id: null,
        minishop_id: null,
        email: null,
        username: null,
        first_name: null,
        last_name: null,
        is_banned: null,
      },
    });
    expect(read("archived=exclude").total).toBe(0);
    expect(read("user_id=910001").total).toBe(0);
    expect(JSON.stringify(read())).not.toContain("private-token");
    expect(read().operations[0]).not.toHaveProperty("subscription_url");
  });
  it("uses execution evidence for attention and same-service same-phase last success", () => {
    const { state, read } = fixture();
    state.operations = [
      { ...operationFixture, status: "unknown" },
      { ...operationFixture, id: "1".repeat(32), status: "pending", error_code: null },
      { ...operationFixture, id: "2".repeat(32), status: "pending" },
      {
        ...operationFixture,
        id: "3".repeat(32),
        status: "succeeded",
        completed_at: "2026-10-24T01:02:00Z",
        error_code: null,
      },
      {
        ...operationFixture,
        id: "4".repeat(32),
        phase: "usage",
        status: "succeeded",
        completed_at: "2026-10-24T02:00:00Z",
      },
      {
        ...operationFixture,
        id: "5".repeat(32),
        service_id: "f".repeat(32),
        status: "succeeded",
        completed_at: "2026-10-24T03:00:00Z",
      },
    ];
    expect(read("needs_attention=true").total).toBe(2);
    expect(read("status=unknown&needs_attention=true").operations[0]).toMatchObject({
      status: "unknown",
      completed_at: null,
      last_success_at: "2026-10-24T01:02:00Z",
    });
    expect(read("phase=usage").total).toBe(1);
    expect(read(`service_id=${operationFixture.service_id}`).total).toBe(6);
    expect(
      read().operations.find((row) => row.record_type === "order")?.last_success_at
    ).toBeNull();
  });
  it("keeps colliding order/execution IDs, true totals, stable ties and cursor binding", () => {
    const { state, read } = fixture();
    state.operations = Array.from({ length: 27 }, (_, index) => ({
      ...operationFixture,
      id: index === 26 ? legacy.id : index.toString(16).padStart(32, "0"),
    }));
    const first = read();
    expect(first.total).toBe(28);
    expect(first.operations).toHaveLength(25);
    expect(first.next_cursor).not.toBeNull();
    const second = read(`cursor=${first.next_cursor}`);
    expect(second.total).toBe(28);
    expect(second.operations).toHaveLength(3);
    expect(second.next_cursor).toBeNull();
    const keys = [...first.operations, ...second.operations].map(
      (row) => `${row.record_type}:${row.id}`
    );
    expect(new Set(keys).size).toBe(28);
    expect(keys).toContain(`order:${legacy.id}`);
    expect(keys).toContain(`execution:${legacy.id}`);
    expect(
      consoleGlobalOperationsDemoResponse(
        `/admin/console/operations?status=failed&cursor=${first.next_cursor}`,
        {},
        state
      )
    ).toMatchObject({ ok: false });
    state.operations.unshift({
      ...operationFixture,
      id: "e".repeat(32),
      created_at: "2026-10-25T00:00:00Z",
    });
    expect(read(`cursor=${first.next_cursor}`).operations).toEqual(second.operations);
    expect(read(`cursor=${first.next_cursor}`).total).toBe(29);
    state.operations = [];
    state.orders = [];
    expect(read(`cursor=${first.next_cursor}`)).toMatchObject({
      total: 0,
      operations: [],
      next_cursor: null,
    });
  });
  it("does not duplicate an order that already has execution evidence or list retry receipts", () => {
    const { state, read } = fixture();
    state.operations = [{ ...operationFixture, order_id: legacy.id }];
    state.orders!.push({ ...legacy, id: "d".repeat(32), kind: "retry" });
    expect(read().total).toBe(1);
    expect(read().operations[0].record_type).toBe("execution");
  });
});
