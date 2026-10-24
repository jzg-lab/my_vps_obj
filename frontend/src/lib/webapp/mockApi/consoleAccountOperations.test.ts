import { describe, expect, it } from "vitest";
import { createApiClient } from "$lib/webapp/publicApi";
import { accountOperationFixture } from "$lib/admin/consoleAccountOperationsFixtures";
import {
  readAccountOperation,
  readAccountOperations,
  readAccountOperationsRoute,
} from "$lib/admin/consoleAccountOperations";
import { consoleAccountOperationsDemoResponse } from "./consoleAccountOperations";

const root = "/admin/console/account-operations";
describe("read-only account audit demo", () => {
  it("does not invent records and leaves other domains to their handlers", () => {
    expect(consoleAccountOperationsDemoResponse("/admin/console/operations", {})).toBeUndefined();
    expect(consoleAccountOperationsDemoResponse(root, {})).toMatchObject({
      ok: true,
      operations: [],
      total: 0,
    });
    expect(consoleAccountOperationsDemoResponse(root, { method: "POST" })).toMatchObject({
      ok: false,
      status: 405,
    });
  });
  it.each([
    "unknown=1",
    "status=secret",
    "source=secret",
    "archived=bad",
    "status=failed&status=unknown",
    "needs_attention=1",
    "user_id=",
    "actor_id=1.5",
    "actor_id=9007199254740992",
    "page=-1",
    "page=01",
    "page=1000001",
    "page_size=0",
    "page_size=201",
  ])("rejects malformed query %s", (query) => {
    expect(consoleAccountOperationsDemoResponse(`${root}?${query}`, {})).toMatchObject({
      ok: false,
      error: "invalid_account_operations_query",
    });
  });
  it("filters by original target, not merged owner, and respects archived/actor/source/attention", () => {
    const records = [
      accountOperationFixture({ target_id: -7, user_id: 42, actor_id: 0 }),
      accountOperationFixture({
        id: "b".repeat(32),
        target_id: -7,
        user_id: null,
        archived: true,
        needs_attention: false,
        status: "superseded",
      }),
      accountOperationFixture({
        id: "c".repeat(32),
        source: "worker",
        actor_id: null,
        before_banned: null,
        needs_attention: false,
      }),
    ];
    const before = structuredClone(records);
    expect(consoleAccountOperationsDemoResponse(`${root}?user_id=-7`, {}, records)).toMatchObject({
      total: 2,
    });
    expect(consoleAccountOperationsDemoResponse(`${root}?user_id=42`, {}, records)).toMatchObject({
      total: 0,
    });
    expect(
      consoleAccountOperationsDemoResponse(
        `${root}?actor_id=0&source=administrator&status=unknown&archived=exclude&needs_attention=true`,
        {},
        records
      )
    ).toMatchObject({ total: 1, operations: [records[0]] });
    expect(
      consoleAccountOperationsDemoResponse(`${root}?archived=only`, {}, records)
    ).toMatchObject({ total: 1, operations: [records[1]] });
    expect(
      consoleAccountOperationsDemoResponse(`${root}?source=worker&actor_id=0`, {}, records)
    ).toMatchObject({ total: 0 });
    expect(records).toEqual(before);
  });
  it("returns true totals and stable server-side pages without changing the ledger", async () => {
    const records = Array.from({ length: 28 }, (_, index) =>
      accountOperationFixture({ id: index.toString(16).padStart(32, "0") })
    );
    const before = structuredClone(records);
    const { api } = createApiClient({
      mockApi: (path, options) => consoleAccountOperationsDemoResponse(path, options, records),
    });
    const first = await readAccountOperations(api, readAccountOperationsRoute(""));
    const second = await readAccountOperations(api, readAccountOperationsRoute("?account_page=1"));
    expect(first.total).toBe(28);
    expect(first.operations).toHaveLength(25);
    expect(first.operations[0].id).toBe(records.at(-1)!.id);
    expect(second.total).toBe(28);
    expect(second.operations).toHaveLength(3);
    expect(new Set([...first.operations, ...second.operations].map((row) => row.id)).size).toBe(28);
    expect(await readAccountOperation(api, first.operations[0].id)).toEqual(first.operations[0]);
    expect(records).toEqual(before);
  });
  it("projects safe fields in list and detail without exposing arbitrary error payloads", () => {
    const row = accountOperationFixture({ error_code: "private-upstream-token" });
    Object.assign(row, { secret: "private-config-body" });
    for (const path of [root, `${root}/${row.id}`]) {
      const result = consoleAccountOperationsDemoResponse(path, {}, [row]);
      expect(JSON.stringify(result)).toContain("account_sync_unconfirmed");
      expect(JSON.stringify(result)).not.toContain("private-");
    }
    expect(consoleAccountOperationsDemoResponse(`${root}/bad`, {}, [row])).toMatchObject({
      error: "invalid_account_operation_id",
      status: 400,
    });
    expect(
      consoleAccountOperationsDemoResponse(`${root}/${"f".repeat(32)}`, {}, [row])
    ).toMatchObject({ error: "account_operation_not_found", status: 404 });
  });
});
