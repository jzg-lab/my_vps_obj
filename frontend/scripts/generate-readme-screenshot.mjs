/* global document, HTMLElement, window */

import { spawn } from "node:child_process";
import { createReadStream } from "node:fs";
import { access, mkdir, readFile, stat } from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)));
const repoRoot = path.resolve(frontendRoot, "..");
const docsSiteRoot = path.join(repoRoot, "docs-site");
const publicRoot = path.join(docsSiteRoot, "public");
const runtimeRoot = path.join(publicRoot, "demo", "runtime");
const appShell = path.join(runtimeRoot, "app", "index.html");
const outputPath = path.join(repoRoot, "docs", "remnawave-minishop.webp");
const logoPath = path.join(runtimeRoot, "default-brand", "default-logo.webp");

const skipBuild = process.argv.includes("--skip-build");
const isWindows = process.platform === "win32";
const homeLogoScalePercent = 150;

const canvas = { width: 1920, height: 1080 };
const panel = { y: 70, height: 940, radius: 16 };
const placements = {
  home: { x: 40, width: 360 },
  settings: { x: 440, width: 360 },
  admin: { x: 840, width: 1040 },
};

const contentTypes = new Map([
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".mjs", "text/javascript; charset=utf-8"],
  [".css", "text/css; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".svg", "image/svg+xml"],
  [".png", "image/png"],
  [".webp", "image/webp"],
  [".ico", "image/x-icon"],
  [".woff", "font/woff"],
  [".woff2", "font/woff2"],
]);

const screenshotCss = `
  *, *::before, *::after {
    animation-duration: 0s !important;
    animation-delay: 0s !important;
    transition: none !important;
    caret-color: transparent !important;
  }
  *:focus-visible {
    outline: none !important;
    box-shadow: none !important;
  }
  .admin-config-alerts {
    display: none !important;
  }
`;

function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: repoRoot,
      stdio: "inherit",
      shell: false,
      ...options,
    });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(`${command} ${args.join(" ")} exited with code ${code}`));
    });
  });
}

async function pathExists(targetPath) {
  try {
    await access(targetPath);
    return true;
  } catch {
    return false;
  }
}

async function ensureFrontendDependencies() {
  const requiredPackages = ["@playwright/test", "sharp"];
  const missing = [];
  for (const packageName of requiredPackages) {
    const packagePath = path.join(frontendRoot, "node_modules", ...packageName.split("/"));
    if (!(await pathExists(packagePath))) missing.push(packageName);
  }
  if (!missing.length) return;

  const npmCommand = isWindows ? "npm.cmd" : "npm";
  console.log(`Installing frontend dependencies (${missing.join(", ")})...`);
  await run(npmCommand, ["ci"], {
    cwd: frontendRoot,
    shell: isWindows,
  });
}

async function buildDemoRuntime() {
  if (skipBuild) {
    await access(appShell);
    console.log("Using the existing docs demo runtime (--skip-build).");
    return;
  }
  await run(process.execPath, [path.join(docsSiteRoot, "scripts", "build-demo-runtime.mjs")]);
}

async function installScreenshotLogo(sharp) {
  const source = await readFile(logoPath);
  await sharp(source, { animated: false })
    .resize(512, 512, { fit: "contain" })
    .webp({ quality: 96 })
    .toFile(logoPath);
}

function resolveRequestPath(urlPath) {
  let pathname = decodeURIComponent(urlPath.split("?")[0]);
  if (pathname.endsWith("/")) pathname += "index.html";
  const resolved = path.normalize(path.join(publicRoot, pathname));
  return resolved.startsWith(publicRoot) ? resolved : null;
}

async function isFile(candidate) {
  try {
    return (await stat(candidate)).isFile();
  } catch {
    return false;
  }
}

function sendFile(response, filePath, statusCode = 200) {
  const contentType =
    contentTypes.get(path.extname(filePath).toLowerCase()) || "application/octet-stream";
  response.writeHead(statusCode, {
    "Cache-Control": "no-store",
    "Content-Type": contentType,
  });
  createReadStream(filePath).pipe(response);
}

async function startServer() {
  const server = http.createServer(async (request, response) => {
    const target = resolveRequestPath(request.url || "/");
    if (target && (await isFile(target))) {
      sendFile(response, target);
      return;
    }
    if (target && path.extname(target)) {
      response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      response.end(`not found: ${request.url}`);
      return;
    }
    sendFile(response, appShell);
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (!address || typeof address === "string") {
    server.close();
    throw new Error("Unable to determine the local screenshot server address.");
  }
  return {
    baseUrl: `http://127.0.0.1:${address.port}/demo/runtime/app/`,
    close: () =>
      new Promise((resolve, reject) =>
        server.close((error) => (error ? reject(error) : resolve()))
      ),
  };
}

function routeUrl(baseUrl, route) {
  const url = new URL(baseUrl);
  url.searchParams.set("path", route);
  url.searchParams.set("mock", "services");
  url.searchParams.set("theme_preview", "dark");
  return url.href;
}

async function preparePage(page, url) {
  await page.addInitScript(() => localStorage.setItem("rw_minishop_demo_language", "zh-hans"));
  await page.goto(url, { waitUntil: "networkidle" });
  await page.addStyleTag({ content: screenshotCss });
  await page.evaluate(async () => {
    await document.fonts.ready;
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    window.getSelection()?.removeAllRanges();
  });
}

async function captureScreens(chromium, baseUrl) {
  const browser = await chromium.launch({ headless: true });
  try {
    const mobileContext = await browser.newContext({
      colorScheme: "dark",
      deviceScaleFactor: 1,
      locale: "zh-CN",
      reducedMotion: "reduce",
      viewport: { width: placements.home.width, height: panel.height },
    });
    const mobilePage = await mobileContext.newPage();

    await preparePage(mobilePage, routeUrl(baseUrl, "/services"));
    await mobilePage.getByRole("heading", { name: "我的服务", exact: true }).waitFor();
    // Mirror Appearance → Home and login logo → Mobile logo scale without
    // changing the shared docs-demo catalog used by the other screenshots.
    await mobilePage.locator(".app-shell").evaluate((element, percent) => {
      element.style.setProperty("--home-logo-scale-mobile", String(percent / 100));
    }, homeLogoScalePercent);
    const home = await mobilePage.screenshot({ animations: "disabled", caret: "hide" });

    await preparePage(mobilePage, routeUrl(baseUrl, "/settings"));
    await mobilePage.getByText("@u3252a8", { exact: true }).waitFor();
    const settings = await mobilePage.screenshot({ animations: "disabled", caret: "hide" });
    await mobileContext.close();

    const adminContext = await browser.newContext({
      colorScheme: "dark",
      deviceScaleFactor: 1,
      locale: "zh-CN",
      reducedMotion: "reduce",
      viewport: { width: placements.admin.width, height: panel.height },
    });
    const adminPage = await adminContext.newPage();
    await preparePage(adminPage, routeUrl(baseUrl, "/admin/service-plans"));
    await adminPage.getByRole("button", { name: "新建套餐", exact: true }).waitFor();
    const admin = await adminPage.screenshot({ animations: "disabled", caret: "hide" });
    await adminContext.close();

    return { admin, home, settings };
  } finally {
    await browser.close();
  }
}

function roundedMask(width, height) {
  return Buffer.from(
    `<svg width="${width}" height="${height}" xmlns="http://www.w3.org/2000/svg">` +
      `<rect width="${width}" height="${height}" rx="${panel.radius}" fill="#fff"/>` +
      `</svg>`
  );
}

async function roundedScreenshot(sharp, source, width) {
  const resized = await sharp(source).resize(width, panel.height, { fit: "fill" }).png().toBuffer();
  return sharp(resized)
    .composite([{ input: roundedMask(width, panel.height), blend: "dest-in" }])
    .png()
    .toBuffer();
}

function backgroundSvg() {
  const shadows = Object.values(placements)
    .map(
      ({ x, width }) =>
        `<rect x="${x}" y="${panel.y}" width="${width}" height="${panel.height}" ` +
        `rx="${panel.radius}" fill="#000" fill-opacity="0.7" filter="url(#shadow)"/>`
    )
    .join("");
  return Buffer.from(`<svg width="${canvas.width}" height="${canvas.height}" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="base" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#07110b"/>
        <stop offset="0.46" stop-color="#0b0d0e"/>
        <stop offset="1" stop-color="#12101a"/>
      </linearGradient>
      <radialGradient id="green" cx="0" cy="0" r="1" gradientTransform="translate(250 80) rotate(35) scale(900 700)">
        <stop offset="0" stop-color="#16321f" stop-opacity="0.28"/>
        <stop offset="1" stop-color="#16321f" stop-opacity="0"/>
      </radialGradient>
      <radialGradient id="purple" cx="0" cy="0" r="1" gradientTransform="translate(1700 950) rotate(-135) scale(800 600)">
        <stop offset="0" stop-color="#2b1738" stop-opacity="0.24"/>
        <stop offset="1" stop-color="#2b1738" stop-opacity="0"/>
      </radialGradient>
      <filter id="shadow" x="-20%" y="-20%" width="140%" height="150%">
        <feDropShadow dx="0" dy="18" stdDeviation="20" flood-color="#000" flood-opacity="0.68"/>
      </filter>
    </defs>
    <rect width="100%" height="100%" fill="url(#base)"/>
    <rect width="100%" height="100%" fill="url(#green)"/>
    <rect width="100%" height="100%" fill="url(#purple)"/>
    ${shadows}
  </svg>`);
}

async function compose(sharp, screenshots) {
  const [home, settings, admin] = await Promise.all([
    roundedScreenshot(sharp, screenshots.home, placements.home.width),
    roundedScreenshot(sharp, screenshots.settings, placements.settings.width),
    roundedScreenshot(sharp, screenshots.admin, placements.admin.width),
  ]);

  await mkdir(path.dirname(outputPath), { recursive: true });
  await sharp(backgroundSvg())
    .resize(canvas.width, canvas.height)
    .composite([
      { input: home, left: placements.home.x, top: panel.y },
      { input: settings, left: placements.settings.x, top: panel.y },
      { input: admin, left: placements.admin.x, top: panel.y },
    ])
    .webp({ quality: 92, smartSubsample: true })
    .toFile(outputPath);
}

await ensureFrontendDependencies();
const [{ chromium }, { default: sharp }] = await Promise.all([
  import("@playwright/test"),
  import("sharp"),
]);

await buildDemoRuntime();
await installScreenshotLogo(sharp);

const server = await startServer();
try {
  const screenshots = await captureScreens(chromium, server.baseUrl);
  await compose(sharp, screenshots);
} finally {
  await server.close();
}

const metadata = await sharp(outputPath).metadata();
console.log(
  `Generated ${path.relative(repoRoot, outputPath)} (${metadata.width}x${metadata.height}, ${metadata.format}).`
);
