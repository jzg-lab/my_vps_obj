import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { test, expect } from "@playwright/test";
import ts from "typescript";

const copy = JSON.parse(readFileSync(resolve(__dirname, "../../locales/zh-hans.json"), "utf8"));
const source = readFileSync(
  resolve(__dirname, "../../docs-site/src/scripts/swaggerChinese.ts"),
  "utf8"
)
  .replace(
    'import copy from "../../../locales/zh-hans.json";',
    `const copy = ${JSON.stringify(copy)};`
  )
  .replace("export function", "function");
const script = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None },
}).outputText;

test("Swagger translates controls while preserving identical protocol data", async ({ page }) => {
  await page.setContent(`<div id="swagger-ui">
    <div class="opblock-section-header"><div class="tab-item"><h4><span>Parameters</span></h4></div></div>
    <table class="parameters"><thead><tr><th>Name</th><th>Description</th></tr></thead>
      <tbody><tr><td><div class="parameter__name">Name</div>
      <div class="parameter__enum">default</div><select><option>Schema</option></select></td></tr></tbody></table>
    <table class="responses-table"><thead><tr><td>Code</td><td>Description</td></tr></thead><tbody><tr><td class="response-col_links"><i>No links</i></td></tr></tbody></table>
    <ul class="tab"><li><button>Schema</button></li></ul>
    <div class="model-title">Schema</div><span class="prop-name">Name</span>
    <div class="renderedMarkdown">Description</div><pre>default</pre><code>Name</code>
    <div class="example"><span title="Name">Schema</span></div>
    <button class="opblock-control-arrow" aria-label="Expand operation"></button>
  </div>`);
  const selectors = [
    ".parameter__name",
    ".parameter__enum",
    "option",
    ".model-title",
    ".prop-name",
    ".renderedMarkdown",
    "pre",
    "code",
    ".example",
  ];
  const before = await Promise.all(selectors.map((selector) => page.locator(selector).innerHTML()));
  await page.addScriptTag({ content: script });
  await expect(page.locator("h4")).toHaveText("参数");
  await expect(page.locator("th").first()).toHaveText("名称");
  await expect(page.locator(".responses-table thead td").first()).toHaveText("状态码");
  await expect(page.locator(".response-col_links > i")).toHaveText("无链接");
  await expect(page.locator(".tab button")).toHaveText("结构");
  await expect(page.locator(".opblock-control-arrow")).toHaveAttribute("aria-label", "展开接口");
  expect(
    await Promise.all(selectors.map((selector) => page.locator(selector).innerHTML()))
  ).toEqual(before);
  await page.locator("#swagger-ui").evaluate((root) => {
    const header = document.createElement("div");
    header.className = "opblock-section-header";
    header.innerHTML = "<h4>Responses</h4>";
    root.append(header);
  });
  await expect(page.locator("h4").last()).toHaveText("响应");
  expect(
    await Promise.all(selectors.map((selector) => page.locator(selector).innerHTML()))
  ).toEqual(before);
});
