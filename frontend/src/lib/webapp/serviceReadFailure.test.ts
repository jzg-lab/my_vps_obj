import { describe, expect, it, vi, afterEach } from "vitest";
import { isTemporaryServiceReadFailure } from "./serviceReadFailure";
import { builtApiPath, createApiClient, unwrap } from "./publicApi";
import { readFileSync } from "node:fs";

const services = builtApiPath<"/api/services">("/services");

afterEach(() => vi.unstubAllGlobals());

describe("service read snapshot retention", () => {
  it.each([429, 500, 502, 503, 504, 599])("retains a snapshot after HTTP %i", async (status) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status })));
    const { api } = createApiClient();
    const failure = await api(services).catch((error: unknown) => error);
    expect(isTemporaryServiceReadFailure(failure)).toBe(true);
  });

  it.each([401, 403, 404, 409, 422])("clears a snapshot after HTTP %i", async (status) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ ok: false, error: status === 403 ? "forbidden" : "denied" }),
          {
            status,
          }
        )
      )
    );
    const { api } = createApiClient();
    const failure = await api(services)
      .then(unwrap)
      .catch((error: unknown) => error);
    expect(isTemporaryServiceReadFailure(failure)).toBe(false);
  });

  it("recognizes fetch failures and the request layer's timeout forms", () => {
    expect(isTemporaryServiceReadFailure(new TypeError("Failed to fetch"))).toBe(true);
    expect(
      isTemporaryServiceReadFailure(
        Object.assign(new Error("api_request_timeout"), { name: "TimeoutError" })
      )
    ).toBe(true);
    expect(isTemporaryServiceReadFailure(new DOMException("request_cancelled", "AbortError"))).toBe(
      true
    );
    expect(
      isTemporaryServiceReadFailure(new DOMException("The session changed", "AbortError"))
    ).toBe(false);
  });

  it("uses the real request timeout rather than treating a permission cancellation as offline", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_input: RequestInfo | URL, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () => reject(init.signal?.reason), {
              once: true,
            });
          })
      )
    );
    const { api } = createApiClient({ requestTimeoutMs: 5 });
    const failure = await api(services).catch((error: unknown) => error);
    expect(failure).toMatchObject({ name: "TimeoutError", message: "api_request_timeout" });
    expect(isTemporaryServiceReadFailure(failure)).toBe(true);
    for (const message of ["admin_access_changed", "admin_access_revoked"])
      expect(isTemporaryServiceReadFailure(new DOMException(message, "AbortError"))).toBe(false);
  });

  it.each(["en", "ru", "zh-hans"])(
    "provides snapshot notices with matching time placeholders in %s",
    (language) => {
      const locale: Record<string, string> = JSON.parse(
        readFileSync(new URL(`../../../../locales/${language}.json`, import.meta.url), "utf8")
      );
      for (const prefix of ["wa", "admin"]) {
        expect(locale[`${prefix}_services_snapshot_stale`].match(/\{\w+\}/g)).toEqual(["{time}"]);
        expect(locale[`${prefix}_services_snapshot_unknown`]).toBeTruthy();
        expect(locale[`${prefix}_services_snapshot_unknown`]).not.toMatch(/\{\w+\}/);
      }
      expect(locale.admin_services_snapshot_observed_stale.match(/\{\w+\}/g)).toEqual(["{time}"]);
    }
  );

  it.each([
    null,
    undefined,
    "offline",
    {},
    { status: 600 },
    { status: Infinity },
    { status: 500.5 },
    { status: "503" },
    { error: "forbidden" },
    { error: "unauthorized" },
    new Error("unknown"),
  ])("does not preserve sensitive data for an unclassified failure %j", (failure) =>
    expect(isTemporaryServiceReadFailure(failure)).toBe(false)
  );
});
