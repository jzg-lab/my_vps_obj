import { readFileSync } from "node:fs";
import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { DedicatedExit } from "$lib/admin/servicePlans";
import type { ApiClient } from "$lib/webapp/publicApi";
import DedicatedExitServiceLink from "./DedicatedExitServiceLink.svelte";
import ExitEvidenceDialog from "../services/ExitEvidenceDialog.svelte";
import DedicatedExitsSection from "../DedicatedExitsSection.svelte";
import { readDedicatedExitsRoute } from "./navigation";

const at = (key: string) => key;
const currentUrl =
  "https://console.test/app/admin/dedicated-exits?exits_page=2&exit_id=exit1&exit_audit_page=1&lang=zh";
const resource: DedicatedExit = {
  id: "exit1",
  label: "Dedicated exit fixture",
  ip_address: "192.0.2.10",
  resource_pool: "pool1",
  revision: 4,
  service_id: "service1",
  hold_order_id: null,
  hold_service_id: null,
  squad_uuid: "squad1",
  verified_at: null,
  enabled: true,
};

describe("dedicated exit service links", () => {
  it("renders a real deep link using the existing entity component and exact service ID", () => {
    const html = render(DedicatedExitServiceLink, {
      props: {
        serviceId: "service/a+b",
        currentUrl,
        routePrefix: "/app",
        at,
        onOpenService: vi.fn(),
      },
    }).body;
    const href = html.match(/href="([^"]+)"/)?.[1]?.replaceAll("&amp;", "&");
    expect(href).toBeDefined();
    const url = new URL(href!);
    expect(url.pathname).toBe("/app/admin/dedicated-exits");
    expect(readDedicatedExitsRoute(url.search)).toEqual({
      page: 2,
      exitId: "exit1",
      auditPage: 1,
      serviceId: "service/a+b",
    });
    expect(html).toContain("admin-entity-link");
    expect(html).toContain('title="console_service_detail"');
    expect(html).not.toContain("<button");
  });

  it.each([null, ""])(
    "does not invent a service or owner for an unbound exit (%s)",
    (serviceId) => {
      const html = render(DedicatedExitServiceLink, {
        props: { serviceId, currentUrl, at, onOpenService: vi.fn() },
      }).body;
      expect(html).not.toContain("href=");
      expect(html).not.toContain("<button");
    }
  );

  it("keeps the binding visible but prevents navigation during an evidence write", () => {
    const html = render(DedicatedExitServiceLink, {
      props: {
        serviceId: "service1",
        currentUrl,
        at,
        disabled: true,
        onOpenService: vi.fn(),
      },
    }).body;
    expect(html).toContain("service1");
    expect(html).not.toContain("href=");
    expect(html).not.toContain("<button");
  });

  it("renders ownership in the actual evidence dialog with the original confirmation fields", () => {
    const api = vi.fn<ApiClient["api"]>();
    const html = render(ExitEvidenceDialog, {
      props: {
        api,
        at,
        resource,
        currentUrl,
        routePrefix: "/app",
        page: 1,
        onPageChange: vi.fn(),
        onOpenService: vi.fn(),
        onclose: vi.fn(),
        onsaved: vi.fn(),
      },
    }).body;
    expect(html).toContain("exit_service_id=service1");
    expect(html).toContain("services_exit_observed_ip");
    expect(html).toContain("services_exit_checked_at");
    expect(html).toContain("services_exit_evidence_note");
    expect(html).toContain("services_exit_verify_confirm");
    expect(html).toContain("services_exit_audit");
    expect(html).toContain('role="status"');
    expect(html).not.toContain("services_exit_no_evidence");
    expect(html).not.toContain("admin-pagination-summary");
    expect(api).not.toHaveBeenCalled();
  });

  it("opens the existing service detail from an exit deep link without requiring the list", () => {
    const url = new URL(`${currentUrl}&exit_service_id=service1`);
    vi.stubGlobal("window", { location: { href: url.href, search: url.search } });
    try {
      const html = render(DedicatedExitsSection, {
        props: { api: vi.fn<ApiClient["api"]>(), at, routePrefix: "/app", onOpenUserCard: vi.fn() },
      }).body;
      expect(html).toContain('aria-label="console_service_detail"');
      expect(html).not.toContain("services_exit_unavailable");
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it.each(["en", "ru", "zh-hans"])("reuses translated ownership labels in %s", (language) => {
    const locale: Record<string, string> = JSON.parse(
      readFileSync(new URL(`../../../../../locales/${language}.json`, import.meta.url), "utf8")
    );
    for (const key of [
      "console_service_detail",
      "services_service_id",
      "services_exit_unavailable",
    ])
      expect(locale[`admin_${key}`], key).toBeTruthy();
  });
});
