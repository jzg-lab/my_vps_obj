import { render } from "svelte/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import AdvancedMaintenanceSection from "./AdvancedMaintenanceSection.svelte";
import { ADMIN_SECTIONS, resolveAdminSectionId } from "./registry";
import { RETIRED_ADMIN_SECTIONS } from "$lib/admin/independentServices";
import * as maintenance from "$lib/admin/stores/maintenanceStore.svelte";
import { createApiClient } from "$lib/webapp/publicApi";

const at = (key: string, _params?: Record<string, unknown>, fallback = key) => fallback;
const destination = "https://panel.example.com/maintenance";
const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function setup() {
  const fetcher = vi.fn<typeof fetch>();
  vi.stubGlobal("fetch", fetcher);
  const { api } = createApiClient();
  const store = maintenance.createMaintenanceStore(api);
  vi.spyOn(maintenance, "createMaintenanceStore").mockReturnValue(store);
  return {
    fetcher,
    store,
    html: () => render(AdvancedMaintenanceSection, { props: { at, api } }).body,
  };
}
function deferredResponse() {
  let resolve!: (response: Response) => void;
  const promise = new Promise<Response>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("advanced maintenance", () => {
  it("registers an independent-service-compatible destination under System", () => {
    const section = ADMIN_SECTIONS.find((item) => item.id === "advanced-maintenance");
    expect(section?.group).toBe("system");
    expect(resolveAdminSectionId("advanced-maintenance")).toBe(section?.id);
    expect(RETIRED_ADMIN_SECTIONS.has("advanced-maintenance")).toBe(false);
  });

  it("starts loading without claiming that configuration is absent", () => {
    const { html, fetcher } = setup();
    expect(html()).toContain('aria-busy="true"');
    expect(html()).toContain("Loading…");
    expect(html()).not.toContain("public maintenance address is not configured");
    expect(html()).not.toContain("href=");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("uses only the typed maintenance endpoint and renders its safe external destination", async () => {
    const { store, fetcher, html: renderHtml } = setup();
    fetcher.mockResolvedValue(reply({ ok: true, destination }));
    await store.load();
    expect(fetcher).toHaveBeenCalledExactlyOnceWith(
      "/api/admin/console/maintenance",
      expect.objectContaining({ cache: "no-store", credentials: "same-origin" })
    );
    expect(store.state).toEqual({ status: "ready", destination });
    const html = renderHtml();
    expect(html).toContain(`href="${destination}"`);
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toContain('referrerpolicy="no-referrer"');
    expect(html).toContain("Its existing sign-in is required");
    expect(html).toContain("External destination");
    expect(html).not.toContain("public maintenance address is not configured");
    expect(html).not.toContain("Loading…");
  });

  it("shows unconfigured only for a successful explicit null destination", async () => {
    const { store, fetcher, html } = setup();
    fetcher.mockResolvedValue(reply({ ok: true, destination: null }));
    await store.load();
    expect(store.state).toEqual({ status: "unconfigured" });
    expect(html()).toContain("public maintenance address is not configured");
    expect(html()).not.toContain("href=");
    expect(html()).not.toContain('role="alert"');
  });

  it.each([
    undefined,
    42,
    "",
    "javascript:alert(1)",
    "//panel.example.test",
    "https://user:secret@panel.example.test",
    "https://panel.example.test/?token=secret",
    "https://panel.example.test/#token",
    "https://panel.example.test\\evil",
  ])("treats malformed or unsafe backend data as an error (%s)", async (destination) => {
    const { store, fetcher, html } = setup();
    fetcher.mockResolvedValue(reply({ ok: true, destination }));
    await store.load();
    expect(store.state).toEqual({ status: "error" });
    expect(html()).toContain('role="alert"');
    expect(html()).not.toContain("public maintenance address is not configured");
    expect(html()).not.toContain("href=");
    expect(html()).not.toContain("secret");
  });

  it.each([200, 400, 503])(
    "unwraps failures without exposing response details (%s)",
    async (status) => {
      const { store, fetcher, html } = setup();
      fetcher.mockResolvedValue(
        reply({ ok: false, error: "private-api-secret", destination }, status)
      );
      await store.load();
      expect(store.state).toEqual({ status: "error" });
      expect(html()).toContain("could not be loaded");
      expect(html()).toContain("Retry");
      expect(html()).not.toContain("public maintenance address is not configured");
      expect(html()).not.toContain("private-api-secret");
      expect(html()).not.toContain(destination);
    }
  );

  it("distinguishes network errors, pending retry and a successful retry", async () => {
    const { store, fetcher, html } = setup();
    fetcher.mockRejectedValueOnce(new TypeError("offline"));
    await store.load();
    expect(html()).toContain('role="alert"');
    const pending = deferredResponse();
    fetcher.mockReturnValueOnce(pending.promise);
    const retry = store.load();
    expect(html()).toContain('aria-busy="true"');
    expect(html()).not.toContain('role="alert"');
    expect(html()).not.toContain("public maintenance address is not configured");
    pending.resolve(reply({ ok: true, destination }));
    await retry;
    expect(html()).toContain(`href="${destination}"`);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("clears the previous destination before another load and after failure", async () => {
    const { store, fetcher, html } = setup();
    fetcher.mockResolvedValueOnce(reply({ ok: true, destination }));
    await store.load();
    const pending = deferredResponse();
    fetcher.mockReturnValueOnce(pending.promise);
    const refresh = store.load();
    expect(html()).not.toContain(destination);
    pending.resolve(reply({ ok: false }, 503));
    await refresh;
    expect(html()).not.toContain(destination);
    expect(store.state).toEqual({ status: "error" });
  });

  it("cannot restore an address from a late response after disposal", async () => {
    const { store, fetcher } = setup();
    const pending = deferredResponse();
    fetcher.mockReturnValueOnce(pending.promise);
    const loading = store.load();
    store.dispose();
    expect(fetcher.mock.calls[0][1]?.signal?.aborted).toBe(true);
    pending.resolve(reply({ ok: true, destination }));
    await loading;
    expect(store.state).toEqual({ status: "loading" });
  });

  it("keeps the newer null result when an older successful request arrives late", async () => {
    const { store, fetcher } = setup();
    const pending = deferredResponse();
    fetcher.mockReturnValueOnce(pending.promise);
    const first = store.load();
    fetcher.mockResolvedValueOnce(reply({ ok: true, destination: null }));
    await store.load();
    pending.resolve(reply({ ok: true, destination }));
    await first;
    expect(store.state).toEqual({ status: "unconfigured" });
  });
});
