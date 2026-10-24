import { describe, expect, it, vi } from "vitest";
import {
  operationHistoryState,
  operationQuery,
  operationsRouteUrl,
  readGlobalOperations,
  readOperationTrail,
  readOperationsRoute,
  validOperationIds,
} from "./consoleGlobalOperations";
import type { ApiClient } from "$lib/webapp/publicApi";

describe("global operation navigation and contract", () => {
  it.each(["usage", "exit_replace"])(
    "retains %s and every other filter through navigation",
    (phase) => {
      const route = readOperationsRoute(
        `?status=unknown&phase=${phase}&archived=only&user_id=-42&service_id=${"a".repeat(32)}&needs_attention=true&cursor=opaque&detail_service_id=${"b".repeat(32)}`
      );
      expect(route.phase).toBe(phase);
      const url = operationsRouteUrl(
        "https://example.test/demo/runtime/admin/nodes?mock=services&lang=ru&node_id=old&page=9&q=old",
        route,
        "/demo/runtime"
      );
      expect(url.pathname).toBe("/demo/runtime/admin/console-operations");
      expect(readOperationsRoute(url.search)).toEqual(route);
      expect(url.searchParams.get("mock")).toBe("services");
      for (const key of ["node_id", "q", "page"]) expect(url.searchParams.has(key)).toBe(false);
      expect(operationQuery(route).has("detail_service_id")).toBe(false);
      expect(operationQuery({ ...route, detailServiceId: "" }).toString()).toBe(
        operationQuery(route).toString()
      );
    }
  );
  it.each(["1.5", "1e3", "9007199254740992", "01", "secret"])(
    "rejects invalid customer identifier %s instead of broadening the query",
    (value) => {
      expect(validOperationIds(value, "")).toBe(false);
      expect(readOperationsRoute(`?user_id=${value}`).userId).toBe(value);
    }
  );
  it("accepts zero and negative current-owner IDs and validates service IDs", () => {
    for (const id of ["", "0", "-5", "9007199254740991"])
      expect(validOperationIds(id, "a".repeat(32))).toBe(true);
    expect(validOperationIds("", "not-a-service")).toBe(false);
  });
  it("restores only the cursor trail belonging to this exact query", () => {
    const route = readOperationsRoute("?cursor=second&status=failed");
    const state = operationHistoryState(route, ["", "first"]);
    expect(readOperationTrail(state, route)).toEqual(["", "first"]);
    expect(readOperationTrail(state, { ...route, phase: "usage" })).toEqual([]);
    expect(
      readOperationTrail(
        { consoleOperationTrail: { query: operationQuery(route).toString(), cursors: [3] } },
        route
      )
    ).toEqual([]);
    expect(readOperationTrail(null, route)).toEqual([]);
  });
  it("makes a proxy-backed cursor trail cloneable for detail open, close and customer return", () => {
    const list = readOperationsRoute("?cursor=second&status=unknown&needs_attention=true");
    const trail = new Proxy(["", "first"], {});
    // History uses structured cloning, which rejects proxies including Svelte state arrays.
    expect(() => structuredClone(trail)).toThrow();
    const detail = { ...list, detailServiceId: "a".repeat(32) };
    const opened = structuredClone(operationHistoryState(detail, trail));
    expect(readOperationTrail(opened, detail)).toEqual(["", "first"]);
    const restoredTrail = new Proxy(readOperationTrail(opened, detail), {});
    const closed = structuredClone(operationHistoryState(list, restoredTrail));
    const customerHistory = structuredClone({ adminUserReturnState: closed });
    const returned = structuredClone(customerHistory.adminUserReturnState);
    expect(readOperationTrail(returned, list)).toEqual(["", "first"]);
    expect(returned.consoleOperationTrail.query).toBe(operationQuery(list).toString());
  });
  it("captures cursor values without retaining a mutable array reference", () => {
    const route = readOperationsRoute("?cursor=second");
    const cursors = ["", "first"];
    const state = operationHistoryState(route, cursors);
    cursors[1] = "changed";
    cursors.push("later");
    expect(readOperationTrail(state, route)).toEqual(["", "first"]);
  });
  it("calls the generated API path, forwards abort and unwraps the authoritative total", async () => {
    const response = {
      ok: true,
      operations: [],
      total: 51,
      next_cursor: "next",
      limit: 25,
      observed_at: "2026-10-24T00:00:00Z",
    };
    const call = vi.fn().mockResolvedValue(response);
    const api = call as ApiClient["api"];
    const controller = new AbortController();
    const result = await readGlobalOperations(
      api,
      readOperationsRoute("?needs_attention=true&cursor=abc"),
      controller.signal
    );
    expect(result.total).toBe(51);
    expect(call.mock.calls[0][0]).toContain("/admin/console/operations?");
    const query = new URL(call.mock.calls[0][0], "https://test.invalid").searchParams;
    expect(Object.fromEntries(query)).toMatchObject({
      needs_attention: "true",
      cursor: "abc",
      limit: "25",
    });
    expect(call.mock.calls[0][1].signal).toBe(controller.signal);
    call.mockResolvedValue({ ok: false, error: "forbidden" });
    await expect(readGlobalOperations(api, readOperationsRoute(""))).rejects.toMatchObject({
      error: "forbidden",
    });
  });
});
