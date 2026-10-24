import { defineConfig } from "@playwright/test";

const baseURL = process.env.QA_FRONTEND_URL || "http://127.0.0.1:18082";
if (!["127.0.0.1", "localhost", "[::1]"].includes(new URL(baseURL).hostname))
  throw new Error("Live console QA is restricted to the isolated loopback development stack.");

export default defineConfig({
  testDir: "./qa",
  testMatch: ["admin-console.spec.ts", "admin-console-audit.spec.ts"],
  outputDir: "../data/qa/admin-console-browser/results",
  workers: 1,
  retries: 0,
  timeout: 45_000,
  use: { baseURL, browserName: "chromium", locale: "zh-Hans", screenshot: "only-on-failure" },
});
