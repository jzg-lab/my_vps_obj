import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "$lib/webapp/publicApi";
import { accountOperationFixture } from "./consoleAccountOperationsFixtures";
import {
  accountBanKey,
  accountOperationCustomer,
  accountOperationErrorKey,
  accountOperationQuery,
  accountOperationsUrl,
  readAccountOperation,
  readAccountOperations,
  readAccountOperationsRoute,
  readOperationView,
  validAccountOperationsRoute,
} from "./consoleAccountOperations";

describe("account audit navigation and read contract", () => {
  it("retains independent service and resource filters alongside every account filter", () => {
    const route = readAccountOperationsRoute(
      `?account_status=unknown&account_source=administrator&account_archived=only&account_needs_attention=true&account_user_id=-42&account_actor_id=0&account_page=2&account_operation_id=${"a".repeat(32)}`
    );
    const current =
      "https://example.test/demo/runtime/admin/console-operations?mock=services&status=failed&phase=usage&user_id=910001&cursor=service-cursor&resource_operations_offset=25&resource_operation_id=" +
      "b".repeat(32);
    const url = accountOperationsUrl(current, route, "/demo/runtime");
    expect(url.pathname).toBe("/demo/runtime/admin/console-operations");
    expect(readAccountOperationsRoute(url.search)).toEqual(route);
    expect(readOperationView(url.search)).toBe("accounts");
    for (const [key, value] of new URL(current).searchParams)
      expect(url.searchParams.get(key)).toBe(value);
    expect(Object.fromEntries(accountOperationQuery(route))).toEqual({
      status: "unknown",
      source: "administrator",
      archived: "only",
      needs_attention: "true",
      user_id: "-42",
      actor_id: "0",
      page: "2",
      page_size: "25",
    });
    const closed = accountOperationsUrl(url.href, { ...route, operationId: "" }, "/demo/runtime");
    expect(closed.searchParams.has("account_operation_id")).toBe(false);
    expect(readAccountOperationsRoute(closed.search)).toEqual({ ...route, operationId: "" });
  });
  it.each(["services", "resources", "accounts"])(
    "restores the %s view without aliasing it",
    (view) => {
      expect(readOperationView(`?operations_view=${view}`)).toBe(view);
      expect(readOperationView("?operations_view=private-token")).toBe("services");
    }
  );
  it.each(["1.5", "1e3", "9007199254740992", "01", "private-token"])(
    "blocks malformed account/actor ID %s instead of broadening a query",
    (value) => {
      for (const key of ["user_id", "actor_id"]) {
        const route = readAccountOperationsRoute(`?account_${key}=${value}`);
        expect(validAccountOperationsRoute(route)).toBe(false);
        expect(accountOperationQuery(route).get(key)).toBe(value);
      }
    }
  );
  it("allows signed and zero IDs but rejects malformed or out-of-range pages", () => {
    for (const id of ["0", "-42", "9007199254740991", "-9007199254740991"])
      expect(
        validAccountOperationsRoute(
          readAccountOperationsRoute(`?account_user_id=${id}&account_actor_id=${id}`)
        )
      ).toBe(true);
    for (const page of ["-1", "1.5", "1e3", "01", "1000001"])
      expect(validAccountOperationsRoute(readAccountOperationsRoute(`?account_page=${page}`))).toBe(
        false
      );
  });
  it("reads generated paths with abort and unwraps list and detail envelopes", async () => {
    const row = accountOperationFixture();
    const call = vi.fn().mockResolvedValue({
      ok: true,
      operations: [row],
      total: 51,
      page: 2,
      page_size: 25,
      observed_at: row.created_at,
    });
    const api = call as ApiClient["api"];
    const controller = new AbortController();
    const result = await readAccountOperations(
      api,
      readAccountOperationsRoute(
        "?account_page=2&account_actor_id=-7&account_needs_attention=true"
      ),
      controller.signal
    );
    expect(result.total).toBe(51);
    const url = new URL(call.mock.calls[0][0], "https://test.invalid");
    expect(url.pathname).toBe("/admin/console/account-operations");
    expect(Object.fromEntries(url.searchParams)).toMatchObject({
      actor_id: "-7",
      needs_attention: "true",
      page: "2",
      page_size: "25",
    });
    expect(call.mock.calls[0][1]).toEqual({ signal: controller.signal });
    call.mockResolvedValue({ ok: true, operation: row });
    expect(await readAccountOperation(api, row.id, controller.signal)).toEqual(row);
    expect(call.mock.lastCall).toEqual([
      `/admin/console/account-operations/${row.id}`,
      { signal: controller.signal },
    ]);
    call.mockResolvedValue({ ok: false, error: "forbidden" });
    await expect(readAccountOperation(api, row.id)).rejects.toMatchObject({ error: "forbidden" });
  });
  it("never links archived targets, distinguishes unknown ban state, and masks unknown errors", () => {
    expect(accountOperationCustomer(accountOperationFixture({ archived: true }))).toBeNull();
    expect(accountOperationCustomer(accountOperationFixture({ user_id: null }))).toBeNull();
    expect(accountOperationCustomer(accountOperationFixture({ target_id: 1, user_id: -42 }))).toBe(
      -42
    );
    expect(accountBanKey(null)).toBe("console_unknown");
    expect(accountBanKey(false)).toBe("account_ops_unbanned");
    expect(accountBanKey(true)).toBe("account_ops_banned");
    expect(accountOperationErrorKey("panel_access_unconfirmed")).toBe("account_ops_error_access");
    for (const code of ["private-credential", "constructor", "__proto__"])
      expect(accountOperationErrorKey(code)).toBe("account_ops_error_unconfirmed");
  });
});
