import { currentBootSignal } from "./bootBudget";
import { fetchApiJson } from "./apiJsonRequest";
import { createBlobRequester } from "./apiBlobRequest";
import { registerEmojiApiCacheScope } from "./emojiCatalogStorage";
import { readCookie } from "./session";
import { requestSignal } from "./requestSignal";
import { createAdminAccess, isAdminRequest } from "./adminAccess";
import { buildApiUrl, type ApiClient, type MockApi } from "./publicApi";
import type { ApiPathInput, ApiResponseFor, PostPayload, PostResponse } from "./publicApiContracts";

type MockContext = Record<string, unknown>;

type ApiClientOptions = {
  csrfCookieName?: string;
  getAuthToken?: () => string;
  getCsrfToken?: () => string;
  getEmojiCacheScope?: () => string;
  getTariffAccessCode?: () => string;
  onUnauthorized?: () => void;
  onAdminAccessRevoked?: () => void;
  onAdminAccessRestored?: () => void;
  mockApi?: MockApi | null;
  getMockContext?: () => MockContext;
  requestTimeoutMs?: number;
};

const DEFAULT_API_REQUEST_TIMEOUT_MS = 15000;
export function createApiClient({
  csrfCookieName = "rw_webapp_csrf",
  getAuthToken = () => "",
  getCsrfToken = () => "",
  getEmojiCacheScope = () => "",
  getTariffAccessCode = () => "",
  onUnauthorized = () => {},
  onAdminAccessRevoked = () => {},
  onAdminAccessRestored = () => {},
  mockApi = null,
  getMockContext = () => ({}),
  requestTimeoutMs = DEFAULT_API_REQUEST_TIMEOUT_MS,
}: ApiClientOptions = {}): ApiClient {
  const isFormDataBody = (body: BodyInit | null | undefined) =>
    typeof FormData !== "undefined" && body instanceof FormData;

  function authenticatedHeaders(options: RequestInit): Headers {
    const method = String(options.method || "GET").toUpperCase();
    const headers = new Headers(options.headers);
    headers.set("X-Billing-Period-Unit", "day");
    const csrf = getCsrfToken() || readCookie(csrfCookieName) || "";
    const authToken = getAuthToken();
    const tariffAccessCode = String(getTariffAccessCode() || "")
      .trim()
      .toLowerCase();
    if (authToken && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${authToken}`);
    }
    if (/^[a-f0-9]{32}$/.test(tariffAccessCode) && !headers.has("X-Tariff-Access-Code")) {
      headers.set("X-Tariff-Access-Code", tariffAccessCode);
    }
    if (csrf && ["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
      headers.set("X-CSRF-Token", csrf);
    }
    return headers;
  }

  const access = createAdminAccess({
    sessionScope: () =>
      JSON.stringify([getAuthToken(), getCsrfToken() || readCookie(csrfCookieName)]),
    readProfile: requestJsonRaw,
    onRevoked: () => {
      requestBlob = makeBlobRequester();
      onAdminAccessRevoked();
    },
    onRestored: onAdminAccessRestored,
  });

  async function requestJsonRaw(
    path: string,
    options: RequestInit = {},
    version?: number
  ): Promise<Record<string, unknown>> {
    if (mockApi) {
      const payload = (await mockApi(path, options, getMockContext())) as Record<string, unknown>;
      if (
        version !== undefined &&
        isAdminRequest(path) &&
        payload?.ok === false &&
        (payload.status === 403 || payload.error === "forbidden")
      )
        await access.forbidden(version);
      return payload;
    }

    const headers = authenticatedHeaders(options);
    if (options.body && !headers.has("Content-Type") && !isFormDataBody(options.body)) {
      headers.set("Content-Type", "application/json");
    }

    return fetchApiJson(
      buildApiUrl(path),
      path,
      { ...options, headers },
      requestTimeoutMs,
      onUnauthorized,
      version !== undefined && isAdminRequest(path) ? () => access.forbidden(version) : undefined
    );
  }

  function requestJson(path: string, options: RequestInit = {}): Promise<Record<string, unknown>> {
    return access.request(path, (version) => requestJsonRaw(path, options, version));
  }

  async function api<
    Path extends ApiPathInput,
    Options extends RequestInit | undefined = undefined,
  >(path: Path, options: Options = {} as Options): Promise<ApiResponseFor<Path, Options>> {
    return (await requestJson(path, options)) as ApiResponseFor<Path, Options>;
  }

  async function apiUnchecked(
    path: string,
    options: RequestInit = {}
  ): Promise<Record<string, unknown>> {
    return requestJson(path, options);
  }

  function makeBlobRequester() {
    return createBlobRequester({
      authenticatedHeaders,
      sessionScope: () => getCsrfToken() || readCookie(csrfCookieName) || "",
      persistentScope: getEmojiCacheScope,
      buildApiUrl,
      mockApi,
      getMockContext,
      onUnauthorized,
      onForbidden: (version) => access.forbidden(version),
      requestTimeoutMs,
    });
  }
  let requestBlob = makeBlobRequester();

  const apiBlob: ApiClient["apiBlob"] = (path, options) =>
    access.request(path, (version) => requestBlob(path, options, version));

  async function publicApiUnchecked(
    path: string,
    payload: Record<string, unknown> = {},
    options: Pick<RequestInit, "signal"> = {}
  ): Promise<Record<string, unknown>> {
    if (mockApi) {
      return (await mockApi(
        path,
        { method: "POST", body: JSON.stringify(payload) },
        getMockContext()
      )) as Record<string, unknown>;
    }
    const { signal, cleanup } = requestSignal(
      options.signal || currentBootSignal(),
      requestTimeoutMs
    );
    try {
      const response = await fetch(buildApiUrl(path), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal,
        credentials: "same-origin",
      });
      return (await response.json()) as Record<string, unknown>;
    } finally {
      cleanup();
    }
  }

  async function publicApi<Path extends ApiPathInput>(
    path: Path,
    payload: PostPayload<Path> = {} as PostPayload<Path>,
    options: Pick<RequestInit, "signal"> = {}
  ): Promise<PostResponse<Path>> {
    return (await publicApiUnchecked(path, payload, options)) as PostResponse<Path>;
  }

  registerEmojiApiCacheScope(api, () =>
    !mockApi && (getAuthToken() || getCsrfToken() || readCookie(csrfCookieName))
      ? getEmojiCacheScope()
      : ""
  );
  return { api, apiUnchecked, apiBlob, publicApi, publicApiUnchecked } as ApiClient;
}
