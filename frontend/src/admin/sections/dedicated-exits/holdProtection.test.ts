import { readFileSync } from "node:fs";
import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { DedicatedExit } from "$lib/admin/servicePlans";
import { consoleNodeServiceFixture } from "$lib/admin/consoleNodesFixtures";
import type { ApiClient } from "$lib/webapp/publicApi";
import {
  exitAvailable,
  exitEvidenceBlocked,
  exitHasHold,
  readEvidenceService,
} from "./availability";
import DedicatedExitOwnership from "./DedicatedExitOwnership.svelte";
import ExitEvidenceDialog from "../services/ExitEvidenceDialog.svelte";

const resource: DedicatedExit = {
  id: "exit1",
  label: "Test exit",
  ip_address: "192.0.2.10",
  resource_pool: "dedicated-test",
  revision: 4,
  service_id: null,
  hold_order_id: null,
  hold_service_id: null,
  squad_uuid: "squad1",
  verified_at: null,
  enabled: true,
};
const service = { id: "bound-service", replacement_order_id: null };
const at = (key: string) => key;
const currentUrl = "https://console.test/admin/dedicated-exits?exits_page=2&exit_id=exit1";
const held: DedicatedExit = {
  ...resource,
  hold_order_id: "replacement-order",
  hold_service_id: "actual-hold-service",
};

describe("dedicated exit allocation and evidence guards", () => {
  it.each([
    held,
    { ...held, hold_service_id: null },
    { ...held, hold_order_id: null },
    { ...held, enabled: false },
    { ...held, service_id: service.id },
  ])("never offers held or partially described holds as new allocations: %j", (exit) => {
    expect(exitHasHold(exit)).toBe(true);
    expect(exitAvailable(exit, resource.resource_pool)).toBe(false);
    expect(exitEvidenceBlocked(exit, service)).toBe(true);
  });

  it("preserves free resource selection but rejects disabled, bound or different pools", () => {
    expect(exitAvailable(resource, resource.resource_pool)).toBe(true);
    expect(exitAvailable({ ...resource, enabled: false }, resource.resource_pool)).toBe(false);
    expect(exitAvailable({ ...resource, service_id: service.id }, resource.resource_pool)).toBe(
      false
    );
    expect(exitAvailable(resource, "other-pool")).toBe(false);
    expect(exitAvailable(resource, null)).toBe(false);
  });

  it("blocks bound evidence until the exact service is known and no replacement is active", () => {
    const bound = { ...resource, service_id: service.id };
    expect(exitEvidenceBlocked(resource, null)).toBe(false);
    expect(exitEvidenceBlocked(bound, null)).toBe(true);
    expect(exitEvidenceBlocked(bound, { ...service, id: "another-service" })).toBe(true);
    expect(exitEvidenceBlocked(bound, { ...service, replacement_order_id: "order" })).toBe(true);
    expect(exitEvidenceBlocked(bound, service)).toBe(false);
  });

  it("reads only the exact bound service through the existing typed endpoint", async () => {
    const api = vi.fn<ApiClient["api"]>();
    const signal = new AbortController().signal;
    const detail = structuredClone(consoleNodeServiceFixture);
    detail.service.id = "service/a+b";
    detail.service.replacement_order_id = "order";
    api.mockResolvedValue({ ok: true, ...detail });
    const result = await readEvidenceService(api, detail.service.id, signal);
    expect(result.replacement_order_id).toBe("order");
    expect(api).toHaveBeenCalledExactlyOnceWith("/admin/console/services/service%2Fa%2Bb", {
      signal,
    });
  });

  it.each(["missing", "mismatched", "failed", "aborted"])(
    "does not turn %s service information into permission to write",
    async (failure) => {
      const api = vi.fn<ApiClient["api"]>();
      const controller = new AbortController();
      const detail = structuredClone(consoleNodeServiceFixture);
      const id = detail.service.id;
      if (failure === "missing") Reflect.deleteProperty(detail.service, "replacement_order_id");
      if (failure === "mismatched") detail.service.id = "another-service";
      if (failure === "failed") api.mockRejectedValue(new Error("read failed"));
      else if (failure === "aborted") {
        controller.abort();
        api.mockRejectedValue(new DOMException("Aborted", "AbortError"));
      } else api.mockResolvedValue({ ok: true, ...detail });
      await expect(readEvidenceService(api, id, controller.signal)).rejects.toThrow();
      expect(api).toHaveBeenCalledTimes(1);
    }
  );
});

describe("actual ownership and evidence consumers", () => {
  it("links the real hold service while keeping its order distinct from service identity", () => {
    const html = render(DedicatedExitOwnership, {
      props: { resource: held, at, currentUrl, onOpenService: vi.fn() },
    }).body;
    expect(html).toContain("services_exit_hold_service");
    expect(html).toContain("exit_service_id=actual-hold-service");
    expect(html).toContain("exits_page=2");
    expect(html).not.toContain("replacement-order");
    expect(html).not.toContain("services_available");
  });

  it("keeps missing hold ownership unknown without fabricating a service deep link", () => {
    const html = render(DedicatedExitOwnership, {
      props: {
        resource: { ...held, hold_service_id: null },
        at,
        currentUrl,
        onOpenService: vi.fn(),
      },
    }).body;
    expect(html).toContain("console_unknown");
    expect(html).not.toContain("href=");
  });

  it.each([held, { ...resource, service_id: service.id }])(
    "renders the real evidence dialog read-only for held or not-yet-checked bindings",
    (exit) => {
      const api = vi.fn<ApiClient["api"]>();
      const html = render(ExitEvidenceDialog, {
        props: {
          api,
          at,
          resource: exit,
          currentUrl,
          page: 0,
          onPageChange: vi.fn(),
          onOpenService: vi.fn(),
          onclose: vi.fn(),
          onsaved: vi.fn(),
        },
      }).body;
      expect(html).toMatch(/<button\b[^>]*type="submit"[^>]*disabled/);
      expect(html).toMatch(/<textarea\b[^>]*disabled/);
      expect(html).toContain("services_exit_audit");
      if (exitHasHold(exit)) {
        expect(html).toContain("services_exit_held");
        expect(html).not.toContain("console_exit_replacement_in_progress");
        expect(html).toContain("exit_service_id=actual-hold-service");
      }
      expect(api).not.toHaveBeenCalled();
    }
  );

  it("uses the guard in both the selectable options and preflight, preserving pending recovery", () => {
    const source = readFileSync(
      new URL("../services/ServiceActivationDialog.svelte", import.meta.url),
      "utf8"
    );
    expect(source).toContain(
      "exits.filter((item) => exitAvailable(item, plan?.terms.resource_pool))"
    );
    expect(source).toContain('plan.terms.resource_type !== "dedicated" || selectedExit');
    expect(source).toContain("items={availableExits.map");
    expect(source).toContain("pending ||");
    expect(source).toContain("submitServiceActivation(api, sessionStorage, body)");
  });

  it.each(["en", "ru", "zh-hans"])("has merged ownership and hold labels in %s", (language) => {
    const locale: Record<string, string> = JSON.parse(
      readFileSync(new URL(`../../../../../locales/${language}.json`, import.meta.url), "utf8")
    );
    for (const key of ["admin_services_exit_held", "admin_services_exit_hold_service"])
      expect(locale[key]?.trim(), key).toBeTruthy();
  });
});
