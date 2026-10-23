<a id="создание-и-публикация-пользовательских-тем"></a>

# 制作与发布自定义主题

主题是包含 `theme.json`、可选 CSS 和本地资源的目录，可通过 ZIP 或公开 GitHub／GitLab 仓库分发。在“后台 → 外观 → 添加主题”安装和更新。

JavaScript 装饰效果见 [v2 包与效果 SDK](theme-effects.md)。效果随主题安装，只有管理员单独同意后才运行。

<a id="обновление-core-со-старыми-темами"></a>

## 带旧主题升级 Core

`WEBAPP_THEMES_DIR` 中已有目录继续使用原 `theme.json`、CSS，无需预先增加包元数据、版本、作者或截图。旧键（含大写）保留；描述中缺少键时仍使用目录名。所选主题、变体、颜色及后台使用设置保留。

主题库将旧主题标为服务器安装、无版本。没有截图时显示说明，仍可预览、启用，图片缺失或错误不阻止运行。

旧主题预览允许带缓存参数的本地链接；隔离预览跳过外部字体、图片、不可用资源和不支持规则，不修改实际个人中心 CSS。

主题明确交由管理器接管前，可通过 SFTP 编辑文件。即使已通过 ZIP 安装其他主题，旧描述文件变化仍被读取：文件已改值优先，其余所有者设置保留。删除原描述会从列表移除手工主题；删除当前主题前先切换。接管需在导入时单独明确确认。

<a id="начать-с-готового-примера"></a>

## 从示例开始

在“创建主题”选择 Default、ASCII 或 Windows 95，填写新键并下载 ZIP。导出同时修改键和对应 CSS 选择器，内置键不能替换。可单独勾选所有者调色板；默认导出作者文件。

仓库示例：`examples/themes/ocean`、`examples/themes/paper`、`examples/themes/minishop-themes.json`，使用与服务器校验相同的格式。

文档站下载：

- [Ocean 与 Paper 示例合集](/demo/theme-examples.zip)。
- [Default 模板](/demo/theme-starters/my-dark.zip)。
- [ASCII 模板](/demo/theme-starters/my-ascii.zip)。
- [Windows 95 模板](/demo/theme-starters/my-windows95.zip)。

<a id="структура-одной-темы"></a>

## 单主题结构

```text
my-theme/
  theme.json
  theme-package.json
  theme.css
  preview.webp
  fonts/
    interface.woff2
  icons/
    connect.png
  LICENSE
  README.md
```

`theme.json` 保留 Minishop 现有契约：

```json
{
  "key": "my-theme",
  "names": { "zh-hans": "我的主题", "en": "My theme" },
  "enabled": true,
  "default": false,
  "use_in_admin": false,
  "css_file": "theme.css",
  "assets_version": 1,
  "tokens": { "accent": "#39bce0" },
  "variants": {
    "dark": { "bg": "#0c1b2a", "text": "#edf9ff" },
    "light": { "bg": "#faf6ef", "text": "#29231b" }
  }
}
```

键长 1–64，只允许小写拉丁字母、数字、`-`、`_`，首位必须字母或数字。发布后保持不变，用于更新和设置关联。`dark`、`light`、`ascii`、`windows95` 为保留键。导入不创建隐藏主题或别名；目录名可与键不同，安装后以 `key` 识别。

CSS 可选，只有调色板时令牌已足够。完整令牌及选择器规则见[主题与外观](webapp-themes.md)。

<a id="метаданные-пакета"></a>

## 包元数据

`theme-package.json` 将作者信息与既有主题契约分开：

```json
{
  "schema_version": 1,
  "version": "1.0.0",
  "description": {
    "zh-hans": "平静的海洋色调主题",
    "en": "A calm ocean-inspired theme"
  },
  "author": { "name": "你的名字" },
  "license": "MIT",
  "homepage": "https://github.com/your-name/minishop-themes",
  "preview": "preview.webp",
  "compatibility": { "theme_api": 1 }
}
```

版本为 `major.minor.patch`，可带 `1.2.0-beta.1` 等后缀；更新时递增。安装同时保存内容 SHA-256，相同版本字符串不能隐藏文件变化。

目前支持 `theme_api: 1`，不兼容未来版会拒绝。旧 ZIP 可不含元数据；新主题发布至少添加版本、许可和说明，无元数据时服务器警告。

`preview` 为主题内 PNG／JPEG／WebP／GIF／ICO 路径。使用带演示数据的实际首页截图，移除个人资料、订阅令牌、收款信息和客户地址。建议 1280×800 WebP。没有截图仍可安装并使用隔离预览。

<a id="css-и-ресурсы"></a>

## CSS 与资源

选择器必须限定到本主题：

```css
html.theme-key-my-theme .app-shell {
  --accent: #39bce0;
}

@font-face {
  font-family: "My Interface";
  src: url("fonts/interface.woff2") format("woff2");
  font-display: swap;
}

html.theme-key-my-theme .card {
  border-color: #39bce044;
}
```

资源路径相对 CSS。CSS 位于 `styles/theme.css` 时可用 `../fonts/interface.woff2`，但不能超出主题目录。分发包不要写死 `/webapp-theme-assets/...`，服务器自动替换为已安装版本地址。

导入禁止：

- 未声明 JavaScript（v2 允许单个效果入口包）、HTML、可执行文件、符号链接和 ZIP 特殊条目。
- CSS `@import`、`@namespace`，以及外部、绝对、`data:` 地址。
- 动态 URL、不安全 CSS 函数、可注入声明的令牌值。
- 越出主题目录、歧义路径、不区分大小写的重名。

SVG 图标须经服务器校验，支持几何、渐变、蒙版、滤镜、图案、标记、文字和本地 `symbol`／`use`，以及 `vector-effect`、`paint-order`、字体、无障碍和静态 SVG 内联样式。`href`、`xlink:href`、`url(...)` 只能引用本地 `#id`，与连接教程图标共用规则。

脚本、事件处理、动画、内嵌 HTML、媒体、样式表、DTD／实体、处理指令、外部／`data:` 地址返回 `unsafe_svg`。CSS 转义、值中的注释和改变页面布局属性也拒绝。普通 XML 声明和注释允许。CSS 可像引用 PNG／WebP 一样引用已验证 SVG。

使用系统字体，或将已授权 WOFF／WOFF2／TTF／OTF 放入主题，附上所需许可。内置主题导出移除外部 `@import`；无本地字体时使用系统回退链。

允许 JSON、CSS、已验证 SVG、位图、字体、`README.md`、文本和许可文件。不要包含构建源码、`node_modules`、密钥或嵌套压缩包。由源码构建的主题应单独发布成品目录，并在合集索引指定。

<a id="архив-с-одной-темой-или-коллекцией"></a>

## 单主题或合集 ZIP

单主题可包含 `my-theme/`，也可将 `theme.json` 放 ZIP 根部。合集使用并列目录：

```text
minishop-themes.json
ocean/
  theme.json
  theme-package.json
  theme.css
paper/
  theme.json
  theme-package.json
  theme.css
```

`minishop-themes.json` 索引：

```json
{
  "schema_version": 1,
  "themes": [
    { "path": "ocean" },
    { "path": "paper" }
  ]
}
```

索引精确定义主题集合，路径相对索引目录。无索引时最多向下五级查找 `theme.json`。共同外层目录自动去除，包括 GitHub／GitLab 仓库快照外层。拒绝主题互相嵌套、重复键和重复合集路径。

每 ZIP 最多 **20 MiB** 压缩数据、解压 **100 MiB**、**2000 条目**、**20 主题**。单文件最多 **10 MiB**，CSS **1 MiB**，图片 **1600 万像素**，另限深度、压缩比及处理时间。高度重复压缩数据也可能拒绝，不要附带无关文件。

<a id="проверить-и-собрать-через-cli"></a>

## CLI 校验与打包

在安装后端依赖的 Core 源码中执行：

```bash
PYTHONPATH=backend python -m config.theme_packages validate examples/themes
PYTHONPATH=backend python -m config.theme_packages inspect examples/themes --json
PYTHONPATH=backend python -m config.theme_packages pack examples/themes --output my-themes.zip
PYTHONPATH=backend python -m config.theme_packages validate my-themes.zip
```

PowerShell 先执行 `$env:PYTHONPATH='backend'`，后续命令去掉 `PYTHONPATH=backend` 前缀。校验退出码 `0` 表示全部通过，`1` 表示错误。`inspect --json` 显示元数据、警告、尺寸和 SHA-256。

复制内置主题：

```bash
PYTHONPATH=backend python -m config.theme_packages fork backend/bot/app/web/themes ascii --new-key my-terminal --output my-terminal.zip
```

命令修改键及 CSS 选择器、校验成品，不改源主题。可用常规 ZIP 软件打包，但发布前仍应 CLI 校验。CLI 构建确定性：相同文件生成相同 ZIP。

<a id="публикация-в-git"></a>

## Git 发布

支持 **github.com**、**gitlab.com** 公开仓库，含 GitLab 多级群组；不支持私有仓库认证或自建 Git 服务。

1. 单主题放根目录，合集可放 `themes/`。
2. 仓库还含源码等其他文件时，添加精确路径索引。
3. 填写版本、兼容性、许可和截图。
4. 校验仓库快照 ZIP，创建版本标签，并将构建 ZIP 附到发布版本。
5. 向用户提供仓库或 ZIP 链接。

安装时可填仓库或 `tree` 页面；独立“分支、标签或提交”和“主题目录”字段消除歧义，例如 `release/next`、`dist/themes`。版本留空表示默认分支。服务器先解析具体提交再安装其快照，不运行 Git 钩子、构建脚本、子模块或仓库代码。

更新需手动“检查更新”，管理员选择要更新的主题。需要可重现安装时推荐标签或完整 SHA，不后台自动更新，也不执行安装脚本。

<a id="проверка-перед-выпуском"></a>

## 发布前检查

检查首页、购买、续费、设置、设备、客服、教程；两种变体、360–390 px 手机、1280 px 以上桌面、长名称、空状态、错误和打开的对话框。键盘焦点应可见，正文和按钮保持足够对比度。

预览使用真实首页结构和模拟数据，放在隔离文档中，不切换用户主题、不调用脚本或 API。完整交互验收须在独立测试 Core 安装。

文档演示在浏览器本地读取 ZIP，Git 链接使用示例合集。模拟安装、冲突、更新、导出、回滚和删除，刷新即重置。真正安全校验由实际安装时的服务器执行。

演示父页面启用导入主题后使用其调色板；上传 ZIP 的 CSS 仅在隔离预览展示，完整 CSS 交互仍需独立测试实例。

<a id="совместимость-версий-core"></a>

## Core 版本兼容

包管理器使用 Theme API 1，自本次更新的 Core dev 可用。前后端必须一起更新。旧 Core 可读手工 `theme.json` 目录，但不理解受管理目录；回滚前导出所需主题并备份。首个稳定版本号将在发布时注明。

<a id="ограничение-обратного-прокси"></a>

## 反向代理限制

Core 接受最高 20 MiB ZIP，multipart 包装使请求略大。标准 frontend 与示例 Nginx 允许 21 MiB。外层自建 Nginx 应为 Mini App 设置 `client_max_body_size 21m;`，其他代理设置等价限额。各后端处理器限制仍生效。
