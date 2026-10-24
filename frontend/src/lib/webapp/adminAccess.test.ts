import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient } from "@tanstack/svelte-query";
import { createApiClient } from "./publicApi";
import { createWebappDataClient } from "./dataClient";
import { createUsersStore } from "../admin/stores/usersStore";
import type { AdminApi } from "../admin/stores/usersStoreState";
import { revokeAdminAccess } from "./adminAccessSession";
import { resetShellState, shellState } from "./shellState.svelte";

const reply = (payload: unknown, status = 200) => new Response(JSON.stringify(payload), { status });
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

afterEach(() => vi.unstubAllGlobals());

function setup() {
  resetShellState({
    mode: "app",
    screen: "admin",
    token: "ordinary-session",
    csrfToken: "csrf",
    data: { ok: true, user: { id: 7, is_admin: true }, subscription: { active: true } },
  });
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const destroyAdminMount = vi.fn(() => cache.clear());
  const syncAppSectionPath = vi.fn();
  const onUnauthorized = vi.fn();
  const onRevoked = vi.fn(() =>
    revokeAdminAccess({
      destroyAdminMount,
      cancelAdminAssetsPrefetch: vi.fn(),
      syncAppSectionPath,
    })
  );
  const client = createApiClient({
    getAuthToken: () => shellState.token,
    getCsrfToken: () => shellState.csrfToken,
    onUnauthorized,
    onAdminAccessRevoked: onRevoked,
    onAdminAccessRestored: () => {
      shellState.adminAccessRevoked = false;
    },
  });
  const store = createUsersStore({
    api: client.api as AdminApi,
    queryClient: cache,
    at: (key) => key,
    onToast: vi.fn(),
  });
  return { client, store, cache, destroyAdminMount, syncAppSectionPath, onRevoked, onUnauthorized };
}

describe("shared administrator access", () => {
  it.each(["sort", "refresh"])(
    "removes the loaded customer shell and cache after revoked %s",
    async (action) => {
      let denied = false;
      const fetcher = vi.fn(async (url: string) =>
        url === "/api/me?fresh=1"
          ? reply({ ok: true, user: { id: 7, is_admin: false } })
          : denied
            ? reply({ ok: false, error: "forbidden" }, 403)
            : reply({ ok: true, users: [{ user_id: 42, email: "private@example.test" }], total: 1 })
      );
      vi.stubGlobal("fetch", fetcher);
      const { store, cache, onRevoked, onUnauthorized, destroyAdminMount, syncAppSectionPath } =
        setup();
      await store.loadUsers();
      expect(store.users).toHaveLength(1);
      expect(cache.getQueryCache().getAll()).toHaveLength(1);
      denied = true;
      if (action === "sort") store.updateState({ usersSort: "created_asc" });
      await store.loadUsers({ refresh: action === "refresh" });
      expect(onRevoked).toHaveBeenCalledOnce();
      expect(destroyAdminMount).toHaveBeenCalledOnce();
      expect(cache.getQueryCache().getAll()).toHaveLength(0);
      expect(shellState.data?.user).toMatchObject({ id: 7, is_admin: false });
      expect(shellState).toMatchObject({
        screen: "settings",
        token: "ordinary-session",
        csrfToken: "csrf",
        adminAccessRevoked: true,
      });
      expect(shellState.data?.subscription).toEqual({ active: true });
      expect(syncAppSectionPath).toHaveBeenCalledWith("settings", true);
      expect(onUnauthorized).not.toHaveBeenCalled();
    }
  );

  it.each(["forbidden", "cannot_ban_self", "csrf_invalid"])(
    "preserves an administrator's business 403 (%s) and payload",
    async (error) => {
      const body = { ok: false, error, detail: "unchanged" };
      const fetcher = vi.fn(async (url: string) =>
        url === "/api/me?fresh=1" ? reply({ ok: true, user: { is_admin: true } }) : reply(body, 403)
      );
      vi.stubGlobal("fetch", fetcher);
      const { client, onRevoked, onUnauthorized } = setup();
      await expect(client.apiUnchecked("/admin/users/7/ban", { method: "POST" })).resolves.toEqual(
        body
      );
      expect(onRevoked).not.toHaveBeenCalled();
      expect(onUnauthorized).not.toHaveBeenCalled();
      expect(shellState.screen).toBe("admin");
    }
  );

  it("does not infer revocation from an unavailable or malformed role check", async () => {
    const { client, onRevoked, onUnauthorized } = setup();
    for (const response of [reply({}, 200), reply({ ok: false }, 403), reply({}, 503)]) {
      vi.stubGlobal(
        "fetch",
        vi.fn(async (url: string) =>
          url === "/api/me?fresh=1" ? response : reply({ ok: false, error: "forbidden" }, 403)
        )
      );
      await expect(client.api("/admin/users")).resolves.toMatchObject({ ok: false });
    }
    expect(onRevoked).not.toHaveBeenCalled();
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("discards late customer and profile responses and shares concurrent role checks", async () => {
    const late = deferred<Response>();
    const profile = deferred<Response>();
    const check = deferred<Response>();
    const fetcher = vi.fn(async (url: string) => {
      if (url === "/api/me") return profile.promise;
      if (url === "/api/me?fresh=1") return check.promise;
      if (url.includes("created_asc")) return late.promise;
      return reply({ ok: false, error: "forbidden" }, 403);
    });
    vi.stubGlobal("fetch", fetcher);
    const { client, store, cache, onRevoked } = setup();
    store.updateState({ usersSort: "created_asc" });
    const list = store.loadUsers();
    const oldProfile = expect(client.api("/me")).rejects.toMatchObject({ name: "AbortError" });
    const denied = expect(client.api("/admin/stats")).rejects.toMatchObject({ name: "AbortError" });
    const deniedAgain = expect(client.api("/admin/health")).rejects.toMatchObject({
      name: "AbortError",
    });
    await vi.waitFor(() =>
      expect(fetcher.mock.calls.filter(([url]) => url === "/api/me?fresh=1")).toHaveLength(1)
    );
    check.resolve(reply({ ok: true, user: { is_admin: false } }));
    await Promise.all([denied, deniedAgain]);
    late.resolve(reply({ ok: true, users: [{ user_id: 42 }], total: 1 }));
    profile.resolve(reply({ ok: true, user: { is_admin: true } }));
    await Promise.all([list, oldProfile]);
    expect(store.users).toEqual([]);
    expect(cache.getQueryCache().getAll()).toHaveLength(0);
    expect(onRevoked).toHaveBeenCalledOnce();
    expect(shellState.adminAccessRevoked).toBe(true);
    await expect(client.api("/admin/users")).rejects.toMatchObject({ name: "AbortError" });
  });

  it("ignores a role check belonging to a replaced session", async () => {
    const check = deferred<Response>();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url === "/api/me?fresh=1" ? check.promise : reply({ ok: false, error: "forbidden" }, 403)
      )
    );
    const { client, onRevoked } = setup();
    const pending = expect(client.api("/admin/users")).rejects.toMatchObject({
      name: "AbortError",
    });
    await vi.waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledTimes(2));
    shellState.token = "new-session";
    check.resolve(reply({ ok: true, user: { is_admin: false } }));
    await pending;
    expect(onRevoked).not.toHaveBeenCalled();
  });

  it("does not let an older role check replace a newer authoritative profile", async () => {
    const check = deferred<Response>();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url === "/api/me?fresh=1"
          ? check.promise
          : url === "/api/me"
            ? reply({ ok: true, user: { is_admin: true } })
            : reply({ ok: false, error: "forbidden" }, 403)
      )
    );
    const { client, onRevoked } = setup();
    const denied = client.api("/admin/users");
    await vi.waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledTimes(2));
    await client.api("/me");
    check.resolve(reply({ ok: true, user: { is_admin: false } }));
    await expect(denied).resolves.toMatchObject({ ok: false, error: "forbidden" });
    expect(onRevoked).not.toHaveBeenCalled();
    expect(shellState.adminAccessRevoked).toBe(false);
  });

  it("retains the existing 401 handling on the shared request path", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => reply({ ok: false, error: "unauthorized" }, 401))
    );
    const { client, onRevoked, onUnauthorized } = setup();
    await expect(client.api("/admin/users")).resolves.toMatchObject({
      ok: false,
      error: "unauthorized",
    });
    expect(onUnauthorized).toHaveBeenCalledOnce();
    expect(onRevoked).not.toHaveBeenCalled();
  });

  it("allows a new authoritative profile to restore access without logging in again", async () => {
    let role = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.includes("/me")
          ? reply({ ok: true, user: { is_admin: role } })
          : role
            ? reply({ ok: true })
            : reply({ ok: false }, 403)
      )
    );
    const { client } = setup();
    await expect(client.api("/admin/users")).rejects.toMatchObject({ name: "AbortError" });
    role = true;
    await client.api("/me?fresh=1");
    await expect(client.api("/admin/users")).resolves.toMatchObject({ ok: true });
    expect(shellState.adminAccessRevoked).toBe(false);
    expect(shellState.token).toBe("ordinary-session");
  });

  it("protects binary exports and leaves non-admin 403 responses alone", async () => {
    const fetcher = vi.fn(async (url: string) =>
      url === "/api/me?fresh=1"
        ? reply({ ok: true, user: { is_admin: false } })
        : reply({ ok: false }, 403)
    );
    vi.stubGlobal("fetch", fetcher);
    const { client, onRevoked } = setup();
    await client.api("/devices");
    expect(fetcher).toHaveBeenCalledTimes(1);
    await expect(client.apiBlob("/admin/payments/export.csv")).rejects.toMatchObject({
      status: 403,
    });
    expect(onRevoked).toHaveBeenCalledOnce();
  });

  it("does not restore an old profile through the actual data-client cache", async () => {
    const stale = deferred<Response>();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url === "/api/me"
          ? stale.promise
          : url === "/api/me?fresh=1"
            ? reply({ ok: true, user: { is_admin: false } })
            : reply({ ok: false }, 403)
      )
    );
    const client = createWebappDataClient();
    const pending = expect(client.loadData()).rejects.toMatchObject({ name: "AbortError" });
    await expect(client.api("/admin/users")).rejects.toMatchObject({ name: "AbortError" });
    stale.resolve(reply({ ok: true, user: { is_admin: true } }));
    await pending;
  });
});
