type Payload = Record<string, unknown>;
type Request = (path: string, options?: RequestInit) => Promise<Payload>;

export function isAdminRequest(path: string): boolean {
  return /^\/(?:api\/)?admin(?:\/|\?|$)/.test(path);
}

export function createAdminAccess({
  sessionScope,
  readProfile,
  onRevoked,
  onRestored,
}: {
  sessionScope: () => string;
  readProfile: Request;
  onRevoked: () => void;
  onRestored: () => void;
}) {
  let scope = sessionScope();
  let generation = 0;
  let profileRevision = 0;
  let observedProfileRevision = 0;
  let revoked = false;
  let checking: Promise<void> | null = null;

  function current(): number {
    const next = sessionScope();
    if (scope !== next) {
      scope = next;
      generation += 1;
      revoked = false;
      checking = null;
    }
    return generation;
  }

  function assertCurrent(version: number): void {
    if (current() !== version) throw new DOMException("admin_access_changed", "AbortError");
  }

  function observeProfile(payload: Payload, revision: number): void {
    if (payload.ok !== true || !payload.user || typeof payload.user !== "object") return;
    const role = (payload.user as Payload).is_admin;
    if (typeof role !== "boolean" || revision < observedProfileRevision) return;
    observedProfileRevision = revision;
    if (role === false && !revoked) {
      revoked = true;
      generation += 1;
      onRevoked();
    } else if (role === true) {
      revoked = false;
      onRestored();
    }
  }

  async function forbidden(version: number): Promise<void> {
    assertCurrent(version);
    if (!checking) {
      const revision = ++profileRevision;
      const promise = (async () => {
        try {
          // A business/CSRF 403 does not prove that the session lost its role.
          const profile = await readProfile("/me?fresh=1");
          assertCurrent(version);
          observeProfile(profile, revision);
        } catch {
          // An unavailable role check must not turn a business denial into logout.
        }
      })();
      checking = promise;
      void promise.finally(() => {
        if (checking === promise) checking = null;
      });
    }
    await checking;
  }

  async function request<T>(path: string, send: (version: number) => Promise<T>): Promise<T> {
    const version = current();
    const admin = isAdminRequest(path);
    const profile = /^\/(?:api\/)?me(?:\?|$)/.test(path);
    const revision = profile ? ++profileRevision : 0;
    if (admin && revoked) throw new DOMException("admin_access_revoked", "AbortError");
    const payload = await send(version);
    if (admin || profile) {
      assertCurrent(version);
      if (profile) observeProfile(payload as Payload, revision);
    }
    return payload;
  }

  return { request, forbidden };
}
