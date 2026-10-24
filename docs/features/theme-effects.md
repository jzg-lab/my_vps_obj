<a id="javascript-в-пакетах-тем"></a>

# 主题包中的 JavaScript

本文属于[主题与公开扩展参考](../upstream/index.md#主题与公开扩展)，描述需要单独授权的可选装饰效果。[基础主题](webapp-themes.md)不依赖 JavaScript；独立服务模式继续使用其配色、品牌和字体能力，不因未启用效果而不可用。

主题可包含预构建 JavaScript 装饰模块，随主题安装、更新、导出、删除，无需独立插件。v1 普通主题继续兼容。

<a id="установка-и-доверие"></a>

## 安装与信任

在主题库上传 ZIP 或导入公开仓库，选择主题，按需明确允许 JavaScript。默认不勾选，只安装颜色与 CSS；每次更新都重新确认。已安装主题卡片的 JavaScript 按钮可授权或撤销，只有当前用户站点主题能运行效果。

**`trusted-dom` 是受信任页面代码，不是沙箱。** 它可读取 DOM、调用访客可访问 API、以访客身份操作。SDK 仅帮助管理资源，不阻止访问 `window`、`document`、网络或存储。只允许已核查且作者可信的代码；文件与 SHA-256 校验不能证明作者安全。许可绑定效果内容、资源、清单、作者、来源和策略版本，不随导出转移；恢复备份也会关闭效果。

管理员在普通 Mini App 中默认不运行效果。“外观 → 管理员主题 JavaScript”（`WEBAPP_ADMIN_THEME_EFFECTS_ENABLED`）只允许当前主题且授权有效时运行，撤销和本地关闭仍生效。受信任代码会获得管理员页面及 API 权限。管理后台与未登录访客不运行效果。管理员显式 `theme_preview` 不受此开关限制，但仍需授权。

主题库动态预览须单独点击，在 `iframe sandbox="allow-scripts"` 内运行，源不透明、禁止网络、只提供无账号数据的测试卡片；关闭或 60 秒后销毁。预览是外观检查，不是安全审计或兼容保证。公开文档演示只展示授权管理，不执行上传 JavaScript；动态效果预览需已安装 Core。

<a id="формат-пакета"></a>

## 包格式

```text
my-theme/
  theme.json
  theme.css
  theme-package.json
  effects/main.js
  LICENSE
```

`theme-package.json`：

```json
{
  "schema_version": 2,
  "version": "1.0.0",
  "license": "MIT",
  "effects": {
    "api_version": 1,
    "runtime": "trusted-dom",
    "entry": "effects/main.js",
    "styles": [],
    "assets": [],
    "targets": ["home.header.surface", "home.card.surface"],
    "description": {"zh-hans": "装饰玻璃效果"}
  }
}
```

`entry` 是最多 2 MiB、UTF-8 的单个 ESM 成品包，依赖必须内嵌。不接受额外 JS、HTML、服务器钩子或安装命令，不依赖 CDN、`npm install`、动态分块或相对 `import`。`styles` 最多 8 个 CSS，`assets` 最多 32 个图片／字体、总计 5 MiB，沿用 CSS／SVG／ZIP 校验。路径必须本地，不含 `..` 或链接。无需修改全局 `script-src` 或增加 `unsafe-eval`。

主题在无 JavaScript 时仍必须可用且外观完整。WebGL 不支持、模块错误、用户关闭、减少动态效果偏好都应保留 CSS 主题。

<a id="контракт-адаптера"></a>

## 适配器契约

SDK 类型见 [themeEffectsSdk.ts](../../frontend/src/lib/webapp/themeEffectsSdk.ts)。模块导出 `mount(host, context)`，返回 `{ update(context), dispose() }`，两项可异步。初始化必须放在 `mount` 内，不放模块顶层，因为浏览器缓存导入，而页面隐藏后可能再次挂载。

```ts
export function mount(host, context) {
  const layers = host.targets("home.header.surface");
  const stop = host.animation((time) => {
    // 只在装饰层内更新自己创建的节点。
  });
  return {
    update(next) { context = next; },
    dispose() { stop(); }
  };
}
```

装饰区域为 `shell.background`、`home.header.surface`、`home.card.surface`，带 `aria-hidden` 和 `pointer-events: none`，不替换业务按钮或 Svelte DOM。卡片区域指上游常规首页主要订阅卡片，不保证在独立服务首页、服务列表或紧凑布局中存在；区域缺失时回退至背景／标题，不自行注入或替换服务卡片。不要依赖内部 CSS 类或结构，通过 `watchTargets` 监听导航中的区域变化。`context` 只包含变体、颜色、语言、减少动态效果，不含账号数据；这不限制 `trusted-dom` 模块自行读取页面。`host.asset(name)` 返回已声明资源 URL。

SDK 通过 `host.signal` 和清理流程释放自己的监听、计时器、RAF、ResizeObserver；适配器须释放 WebGL 缓冲、纹理、程序、第三方对象及未完成操作。异步初始化的迟到结果必须检查 `host.signal.aborted`。文档隐藏停止效果，返回可重新挂载相同版本。初始化／更新错误保留 CSS；JS 启动后错误会带 `theme_effects=off` 重载。SDK 不能终止无限同步循环或故意恶意代码。

<a id="отключение-и-восстановление"></a>

## 关闭与恢复

- 访客：点击“关闭主题效果”，设备本地保存，切换会重载。紧急入口在 URL 添加 `?theme_effects=off`。
- 管理员：在卡片关闭 JavaScript，同时撤销旧版本回滚许可；更新时不勾选同意有相同效果。
- 运营者：创建空文件 `<WEBAPP_THEMES_DIR>/_registry/effects-disabled`，删除后，仍有授权的效果重新可用。
- 已打开站点每 30 秒检查许可，请求超时 10 秒。主题删除、版本／主题切换或撤销时清理并关闭 JS 重载。这是标准客户端行为，不能强制终止已运行的恶意脚本。服务器立即停止提供资源，历史／已退役包不能访问 JS。
- v1 注册表首次写入迁移至 v2，并备份 `_registry/before-effects-v2.json`。旧 Core 不能读取 v2；回滚前完整备份并恢复兼容状态，同时考虑备份后新增修改。

<a id="готовые-примеры"></a>

## 示例

- [tilt.zip](../../examples/theme-effects/tilt.zip)：无依赖的轻量指针效果。VanillaTilt、Vanta／Three.js 或粒子也可预构建后打包，但必须绑定装饰区域并完整释放资源。

[dashersw/liquid-glass-js](https://github.com/dashersw/liquid-glass-js/tree/78cb6ccb0b9987bb60a88b14ccbd13a9e6e8ab2a) 需要适配：原 `Container`／`Button` 操作全局 DOM、使用 `html2canvas(document.body)`、没有完整 `dispose`，演示还需外部脚本。应预构建依赖，只截取作者装饰背景，限制 WebGL 上下文数与画布大小，清理监听和 GPU 资源。这样会改变真实页面折射效果，但不截取账号数据。原仓库不能直接作为 Minishop 安装包。

适配器源码位于 `examples/theme-effects-src/`，构建：

```bash
npm --prefix frontend ci
node scripts/build_theme_effect_examples.mjs
node scripts/build_theme_effect_examples.mjs --check
```

正式发布须检查桌面／手机、Chrome／Safari／Firefox、使用的 Telegram WebView、无 WebGL、减少动态效果、后台切换、重复导航、更新和撤销许可。预览只有模拟布局，不能替代这些检查。
