import { describe, expect, it } from "vitest";
import {
  consoleNodeAssetsDemoResponse as respond,
  createConsoleNodeAssetsDemoState,
} from "./consoleNodeAssets";

const base = "/admin/console/node-assets";
const body = { name: "Manual record", address: "192.0.2.1", notes: "" };

describe("isolated pending-node demo inventory", () => {
  it("starts empty, leaves managed routes alone and does not share state between instances", () => {
    const state = createConsoleNodeAssetsDemoState();
    expect(respond(base, {}, state)).toEqual({
      ok: true,
      items: [],
      total: 0,
      page: 0,
      page_size: 20,
    });
    for (const path of [
      "/admin/console/nodes",
      "/admin/console/services",
      "/admin/console/node-assets-other",
    ])
      expect(respond(path, {}, state)).toBeUndefined();
    respond(base, { method: "POST", body: JSON.stringify(body) }, state);
    expect(createConsoleNodeAssetsDemoState().records).toHaveLength(0);
  });
  it("uses local IDs, allows duplicate addresses, and returns snapshots rather than mutable storage", () => {
    const state = createConsoleNodeAssetsDemoState();
    respond(base, { method: "POST", body: JSON.stringify(body) }, state);
    respond(base, { method: "POST", body: JSON.stringify(body) }, state);
    expect(state.records).toHaveLength(2);
    expect(new Set(state.records.map((row) => row.id)).size).toBe(2);
    const list = respond(`${base}?page_size=1`, {}, state);
    expect(list).toMatchObject({ total: 2 });
    if (!list?.ok || !("items" in list)) throw new Error("Expected list");
    expect(list.items).toHaveLength(1);
    list.items[0].name = "Mutated response";
    expect(state.records.every((row) => row.name === body.name)).toBe(true);
    expect(Object.keys(state.records[0]).sort()).toEqual([
      "address",
      "created_at",
      "id",
      "management_state",
      "name",
      "notes",
      "updated_at",
    ]);
  });
  it("edits and deletes only the named record, clearing notes without upsert or remote fallback", () => {
    const state = createConsoleNodeAssetsDemoState();
    respond(base, { method: "POST", body: JSON.stringify(body) }, state);
    const row = state.records[0];
    expect(
      respond(
        `${base}/${row.id}`,
        { method: "PUT", body: JSON.stringify({ ...body, name: " Changed ", notes: " note " }) },
        state
      )
    ).toMatchObject({ ok: true, name: "Changed", notes: "note", created_at: row.created_at });
    expect(respond(`${base}/${row.id}`, {}, state)).toMatchObject({ name: "Changed" });
    respond(
      `${base}/${row.id}`,
      { method: "PUT", body: JSON.stringify({ name: body.name, address: body.address }) },
      state
    );
    expect(state.records[0].notes).toBe("");
    expect(respond(`${base}/${row.id}`, { method: "DELETE" }, state)).toEqual({
      ok: true,
      id: row.id,
      deleted: true,
    });
    for (const method of ["GET", "PUT", "DELETE"])
      expect(respond(`${base}/${row.id}`, { method, body: JSON.stringify(body) }, state)).toEqual({
        ok: false,
        error: "node_asset_not_found",
      });
    expect(state.records).toHaveLength(0);
  });
  it.each([
    "?page=-1",
    "?page_size=101",
    "?page_size=0",
    "?page=1.5",
    "?page=",
    "?page=1&page=2",
    "?q=x",
  ])("rejects invalid pagination %s", (query) => {
    expect(respond(`${base}${query}`, {}, createConsoleNodeAssetsDemoState())).toMatchObject({
      ok: false,
      error: "invalid_node_asset_query",
    });
  });
  it.each([
    "",
    "999.1.2.3",
    "127.1",
    "a..b",
    "-host.example",
    "a_underscore",
    "https://host.example",
    "host:443",
    "user@host",
    "[::1]",
    "fe80::1%eth0",
  ])("rejects invalid address %s without recording it", (address) => {
    const state = createConsoleNodeAssetsDemoState();
    expect(
      respond(base, { method: "POST", body: JSON.stringify({ ...body, address }) }, state)
    ).toMatchObject({ ok: false, error: "invalid_node_asset_request" });
    expect(state.records).toHaveLength(0);
  });
  it.each(["::1", "2001:db8::1", "10.0.0.1", "node-1", "a.example."])(
    "accepts syntax-only inventory address %s",
    (address) => {
      const state = createConsoleNodeAssetsDemoState();
      expect(
        respond(base, { method: "POST", body: JSON.stringify({ ...body, address }) }, state)
      ).toMatchObject({ ok: true, management_state: "unmanaged", address });
    }
  );
  it("rejects extra fields, nulls, oversized input and unknown methods without mutations", () => {
    const state = createConsoleNodeAssetsDemoState();
    for (const value of [
      null,
      [],
      {},
      { ...body, node_id: "remote" },
      { ...body, notes: null },
      { ...body, name: " " },
      { ...body, name: "x".repeat(121) },
      { ...body, notes: "x".repeat(2001) },
      { ...body, name: "a\nb" },
    ])
      expect(respond(base, { method: "POST", body: JSON.stringify(value) }, state)).toMatchObject({
        ok: false,
      });
    expect(respond(base, { method: "PATCH", body: JSON.stringify(body) }, state)).toMatchObject({
      ok: false,
    });
    expect(respond(`${base}/bad`, {}, state)).toMatchObject({
      ok: false,
      error: "invalid_node_asset_id",
    });
    expect(state.records).toHaveLength(0);
  });
});
