import {
  independentServicesCustomerSummaries,
  independentServicesDemoResponse,
} from "./mockApi/independentServices";
import { buildAdminDemoFixtures } from "./mockApi/adminFixtures";
import { adminFallbackResponse } from "./mockApi/adminFallback";
import { defaultClone, type MockApiContext } from "./mockApi/dataset";
import { demoApiResponse } from "./mockApi/datasetApi";
import { partnerProgramDemoResponse } from "./mockApi/partnerProgramResponse";
import { webappFallbackResponse } from "./mockApi/webappFallback";
import { giftsDemoResponse } from "./mockApi/giftsDemo";
import { advertisingDemoResponse } from "./mockApi/advertisingDemo";
import { telegramMenuDemoResponse } from "./mockApi/telegramMenuDemo";
import { accountMergeDemoResponse } from "./mockApi/accountMerge";
import { issueReviewDemoResponse } from "./mockApi/issueReview";
import { paymentHistoryDemoResponse } from "./mockApi/paymentHistory";
import { chineseDemoContent } from "./mockApi/chineseDemo";
import { consoleResourcePreviewDemoResponse } from "./mockApi/consoleResourcePreview";
import { consoleResourceOperationsDemoResponse } from "./mockApi/consoleResourceOperations";
import { consoleAccountOperationsDemoResponse } from "./mockApi/consoleAccountOperations";
import {
  consoleNodeAssetsDemoResponse,
  createConsoleNodeAssetsDemoState,
} from "./mockApi/consoleNodeAssets";

const nodeAssetsState = createConsoleNodeAssetsDemoState();

export async function mockApi(
  path: string,
  options: RequestInit = {},
  context: MockApiContext = {}
): Promise<unknown> {
  const raw = await mockApiResponse(path, options, context);
  const response =
    path.split("?")[0] === "/admin/users" && (options.method || "GET") === "GET"
      ? independentServicesCustomerSummaries(raw)
      : raw;
  return context.currentLang === "zh-hans" && !path.startsWith("/admin/translations")
    ? chineseDemoContent(response)
    : response;
}

async function mockApiResponse(
  path: string,
  options: RequestInit,
  context: MockApiContext
): Promise<unknown> {
  const {
    currentLang = "ru",
    normalizeLangCode = (value: unknown) => String(value || "ru"),
    clone = defaultClone,
  } = context;
  await new Promise((resolve) => window.setTimeout(resolve, 120));
  const accountOperations = consoleAccountOperationsDemoResponse(path, options);
  if (accountOperations !== undefined) return accountOperations;
  const nodeAssets = consoleNodeAssetsDemoResponse(path, options, nodeAssetsState);
  if (nodeAssets !== undefined) return nodeAssets;
  const resourceOperation = consoleResourceOperationsDemoResponse(path, options);
  if (resourceOperation !== undefined) return resourceOperation;
  const resourcePreview = consoleResourcePreviewDemoResponse(path, options);
  if (resourcePreview !== undefined) return resourcePreview;
  const independentServices = independentServicesDemoResponse(path, options);
  if (independentServices !== undefined) return independentServices;
  const cleanPath = String(path || "").split("?")[0];
  if (cleanPath === "/admin/console/maintenance") {
    if (String(options.method || "GET").toUpperCase() !== "GET")
      return { ok: false, error: "method_not_allowed", status: 405 };
    if (new URL(path, "https://demo.invalid").searchParams.size)
      return { ok: false, error: "invalid_maintenance_query", status: 400 };
    return { ok: true, destination: null };
  }
  if (cleanPath.startsWith("/admin/console/")) return { ok: false, error: "route_not_found" };
  const paymentHistory = paymentHistoryDemoResponse(path);
  if (paymentHistory !== undefined) return paymentHistory;
  const issueReview = issueReviewDemoResponse(path, options, currentLang);
  if (issueReview !== undefined) return issueReview;
  const mergeResponse = accountMergeDemoResponse(cleanPath, options);
  if (mergeResponse !== undefined) return mergeResponse;
  const telegramMenu = telegramMenuDemoResponse(path, options, currentLang);
  if (telegramMenu !== undefined) return telegramMenu;
  const advertising = advertisingDemoResponse(path, options);
  if (advertising !== undefined) return advertising;
  if (cleanPath === "/theme-effects") return { ok: true, effect: null };
  const giftsResponse = giftsDemoResponse(cleanPath, options, path);
  if (giftsResponse !== undefined) return giftsResponse;
  const resolvedContext: MockApiContext = { clone, currentLang, normalizeLangCode };
  const demoResponse = demoApiResponse(path, cleanPath, options, resolvedContext);
  if (demoResponse !== undefined) return demoResponse;
  const partnerResponse = partnerProgramDemoResponse(path, cleanPath, options, resolvedContext);
  if (partnerResponse !== undefined) return partnerResponse;
  const fixtures = buildAdminDemoFixtures();
  const adminResponse = adminFallbackResponse(path, cleanPath, options, resolvedContext, fixtures);
  if (adminResponse !== undefined) return adminResponse;
  return webappFallbackResponse(path, cleanPath, options, resolvedContext, fixtures);
}
