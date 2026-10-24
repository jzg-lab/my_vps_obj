import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import {
  consoleServiceErrorKey,
  consoleServiceLabel,
  consoleServiceLabels,
  consoleServiceMessageKeys,
  pendingOperationRetry,
  preflightSelectionKey,
  readServiceDiagnostics,
  readServiceOperations,
  retryBodyForSnapshot,
  submitOperationRetry,
  type ServiceRetryBody,
} from "./consoleServiceOperations";
import {
  diagnosticsFixture,
  operationFixture,
  operationsFixture,
} from "./consoleServiceOperationsFixtures";
import { resolveLocaleKey } from "$lib/webapp/constants";

function storage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => {
      values.set(key, value);
    },
    removeItem: (key) => {
      values.delete(key);
    },
    key: (index) => [...values.keys()][index] ?? null,
  };
}
const serviceId = diagnosticsFixture.service_id;
const operationId = operationFixture.id;
const body: ServiceRetryBody = {
  user_id: 910001,
  expected_revision: 3,
  idempotency_key: "same-intent",
};

describe("operation retry uses authoritative contracts", () => {
  it("explains the resource gate from both diagnostics and rejected service writes", () => {
    expect(consoleServiceErrorKey("resource_operation_in_progress")).toBe(
      "resource_ops_error_busy"
    );
    expect(consoleServiceErrorKey({ error: "resource_operation_in_progress" })).toBe(
      "resource_ops_error_busy"
    );
  });
  it("reads literal typed paths with real pagination", async () => {
    const api = vi.fn().mockResolvedValue({ ok: true, ...operationsFixture });
    await readServiceOperations(api, serviceId, 2);
    expect(api.mock.calls[0][0]).toBe(
      `/admin/console/services/${serviceId}/operations?limit=25&offset=50`
    );
    await readServiceDiagnostics(api, serviceId);
    expect(api.mock.calls[1][0]).toBe(`/admin/console/services/${serviceId}/diagnostics`);
  });
  it("takes the newest owner/revision and only a server-retryable operation", () => {
    expect(
      retryBodyForSnapshot(
        diagnosticsFixture,
        operationsFixture,
        operationId,
        diagnosticsFixture,
        null
      )
    ).toMatchObject({ user_id: 910001, expected_revision: 3 });
    expect(() =>
      retryBodyForSnapshot(
        diagnosticsFixture,
        { ...operationsFixture, operations: [{ ...operationFixture, retryable: false }] },
        operationId,
        diagnosticsFixture,
        null
      )
    ).toThrow();
  });
  it.each([null, 0, 910002])(
    "rejects a changed/archived owner %s without substituting zero",
    (owner) => {
      expect(() =>
        retryBodyForSnapshot(
          { ...diagnosticsFixture, user_id: owner },
          operationsFixture,
          operationId,
          diagnosticsFixture,
          null
        )
      ).toThrow();
    }
  );
  it("rejects inconsistent snapshots and pending receipts belonging to another owner", () => {
    expect(() =>
      retryBodyForSnapshot(
        diagnosticsFixture,
        { ...operationsFixture, service_revision: 4 },
        operationId,
        diagnosticsFixture,
        null
      )
    ).toThrow();
    expect(() =>
      retryBodyForSnapshot(diagnosticsFixture, operationsFixture, operationId, diagnosticsFixture, {
        ...body,
        user_id: 910002,
      })
    ).toThrow();
  });
  it("reconciles a stored receipt without rewriting its revision or requiring a new intent", () => {
    const receipt = { ...body, expected_revision: 2 };
    expect(
      retryBodyForSnapshot(
        diagnosticsFixture,
        {
          ...operationsFixture,
          operations: [{ ...operationFixture, retryable: false, status: "succeeded" }],
        },
        operationId,
        diagnosticsFixture,
        receipt
      )
    ).toBe(receipt);
  });
  it("retains the exact POST across response loss and clears it only after acknowledgement", async () => {
    const cache = storage();
    const api = vi.fn().mockRejectedValueOnce(new Error("lost reply")).mockResolvedValueOnce({
      ok: true,
      accepted: true,
      operation: operationFixture,
      retry_order_id: "receipt",
      duplicate: true,
    });
    await expect(submitOperationRetry(api, cache, serviceId, operationId, body)).rejects.toThrow(
      "lost reply"
    );
    expect(pendingOperationRetry(cache, serviceId, operationId)).toEqual(body);
    expect(pendingOperationRetry(cache, serviceId, "different")).toBeNull();
    await submitOperationRetry(
      api,
      cache,
      serviceId,
      operationId,
      pendingOperationRetry(cache, serviceId, operationId)!
    );
    expect(api.mock.calls[0]).toEqual(api.mock.calls[1]);
    expect(pendingOperationRetry(cache, serviceId, operationId)).toBeNull();
  });
  it("blocks a new retry when the displayed revision changed before submission", () => {
    expect(() =>
      retryBodyForSnapshot(
        { ...diagnosticsFixture, service_revision: 4 },
        { ...operationsFixture, service_revision: 4 },
        operationId,
        diagnosticsFixture,
        null
      )
    ).toThrow();
  });
  it.each([
    "account_banned",
    "service_revision_changed",
    "operation_not_retryable",
    "idempotency_owner_changed",
  ])("clears a definitive rejection: %s", async (error) => {
    const cache = storage();
    await expect(
      submitOperationRetry(
        vi.fn().mockResolvedValue({ ok: false, error }),
        cache,
        serviceId,
        operationId,
        body
      )
    ).rejects.toEqual({ ok: false, error });
    expect(pendingOperationRetry(cache, serviceId, operationId)).toBeNull();
  });
  it("retains unknown failures, rejects malformed storage, and does not POST without storage", async () => {
    const cache = storage();
    const api = vi.fn().mockResolvedValue({ ok: false, error: "internal_error" });
    await expect(
      submitOperationRetry(api, cache, serviceId, operationId, body)
    ).rejects.toBeDefined();
    const key = cache.key(0)!;
    cache.setItem(key, JSON.stringify({ ...body, user_id: null }));
    expect(() => pendingOperationRetry(cache, serviceId, operationId)).toThrow();
    cache.setItem = () => {
      throw new Error("storage blocked");
    };
    api.mockClear();
    await expect(submitOperationRetry(api, cache, serviceId, operationId, body)).rejects.toThrow(
      "storage blocked"
    );
    expect(api).not.toHaveBeenCalled();
  });
});

describe("preflight selection and safe localizations", () => {
  it("invalidates a check for every account, plan, exit and version change", () => {
    const request = { user_id: 1, plan_id: "a", expected_revision: 1, exit_id: "b" };
    const keys = [
      preflightSelectionKey(request, 1),
      preflightSelectionKey({ ...request, user_id: 2 }, 1),
      preflightSelectionKey({ ...request, plan_id: "c" }, 1),
      preflightSelectionKey({ ...request, expected_revision: 2 }, 1),
      preflightSelectionKey({ ...request, exit_id: "c" }, 1),
      preflightSelectionKey(request, 2),
    ];
    expect(new Set(keys).size).toBe(keys.length);
  });
  it.each(["token=secret", "__proto__", "constructor", "future_error_code"])(
    "does not expose an unknown code: %s",
    (code) => {
      expect(consoleServiceErrorKey(code)).toBe("console_ops_unclassified_error");
      expect(consoleServiceLabel("next", code)).toBe("console_unknown");
    }
  );
  it.each(["en", "ru", "zh-hans"])(
    "ships all operation mappings and D resource strings in %s",
    (language) => {
      const locale: Record<string, string> = JSON.parse(
        readFileSync(new URL(`../../../../locales/${language}.json`, import.meta.url), "utf8")
      );
      for (const key of [
        ...Object.values(consoleServiceLabels).flatMap(Object.values),
        ...consoleServiceMessageKeys,
      ])
        expect(locale[resolveLocaleKey(`admin_${key}`)], key).toBeTruthy();
      const en: Record<string, string> = JSON.parse(
        readFileSync(new URL("../../../../locales/en.json", import.meta.url), "utf8")
      );
      for (const key of Object.keys(en).filter(
        (key) =>
          key.startsWith("admin_console_resource_") ||
          key.startsWith("admin_console_ops_") ||
          key.startsWith("admin_console_preflight_")
      ))
        expect(locale[key], key).toBeTruthy();
    }
  );
});
