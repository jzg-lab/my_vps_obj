<a id="контрибьютинг"></a>

# 贡献指南

本文规定项目架构、开发约定和**可自动验证**的质量门禁，适用于开发者和 AI 智能体。核心原则：

> **契约是唯一事实来源，依靠工具强制执行，而不是口头约定。**
> 类型、结构和生成产物不一致时必须使构建失败，让问题在本地或 CI 暴露，而不是进入生产环境。有疑问时，让工具验证。

修改代码前完整阅读一次。下列大多数规则由 CI 保护（第 1 节）；运行门禁即可发现违规。

---

<a id="1-гейты-качества--выбирай-по-зоне-изменений-перед-пушем"></a>

## 1. 质量门禁：推送前按修改范围选择

CI（`.github/workflows/ci.yml`）运行全部检查；检查失败不得合并。

本地先分类**全部**差异，包括暂存和未暂存文件，再运行足以发现相关回归的最小检查集。产品或共享代码、根依赖与配置、CI／部署、跨多个区域的修改，或无法证明相互隔离的修改，必须完整检查。用户明确要求的命令须原样执行。

在仓库根目录运行完整检查：

```bash
make check
```

不依赖 GNU `make` 的等价命令：

```bash
npm run check
```

开发期间可快速冒烟检查，跳过 `ruff format --check`、`mypy` 和完整前端构建：

```bash
npm run check:quick
```

文档采用独立检查矩阵，无需仅为形式运行全部后端和前端检查：

| 修改范围 | 必须执行的本地检查 |
| --- | --- |
| 仅普通 Markdown／规则文档（`README*`、`AGENTS.md`、`CONTRIBUTING.md`、`docs/**/*.md`）和静态文档资源，不含生成文件 | `git diff --check`、变动链接／路径检查及相关内容的视觉检查；发布到文档站的内容还须运行 `npm run check:docs` 和 `npm run build:docs` |
| 仅 `docs-site/**` | `npm run check:docs` 和 `npm run build:docs`；修改演示运行时、客户端行为或导航时，增加 `npm run check:e2e` |
| `docs-site/package-lock.json` 或文档站依赖 | `npm run check:lockfiles`，然后 `npm run build:docs` |
| 生成文档／契约 | 运行下表对应生成器和漂移／契约测试，再运行 `npm run check:docs`；修改生成器代码属于代码修改 |

修改 `docs-site/scripts/sync-docs.mjs` 时，另运行 `npm --prefix docs-site run test:docs`，验证仓库文件引用、旧锚点和 OpenAPI 链接兼容。该测试会同步生成副本，不与文档构建并行；文档分工及来源规则见[文档维护规范](docs/documentation.md)。

完成限定范围的检查后，列明已执行检查，并明确说明：由于已证明差异仅涉及文档或文档站，跳过了完整 `pytest`／`ruff`／`mypy`／前端矩阵。CI 仍是合并前的最终完整门禁。

mypy 没有范围边界之外的豁免：整个仓库都在检查范围内，包括全部后端包、两个脚本根目录（`backend/scripts`、`scripts`）和完整 `tests/`。`type_ignore` 允许清单仅保留一项经边界证明的例外：`config/settings.py` 的 pydantic-settings 从环境填入必填字段，静态分析不可见；调用处的行内注释记录了原因。

以下显式命令仍是 CI 和人工诊断的事实来源。

**后端**（仓库根目录；`pytest.ini` 设置 `pythonpath = backend .`）：

```bash
python -m pytest -q                 # 完整测试；CI 启动 Postgres + Redis；警告视为错误；分支覆盖率下限 fail_under=53
python -m ruff check .              # 静态检查
python -m ruff format --check .     # 格式检查
python -m mypy --explicit-package-bases backend/config backend/db backend/bot/infra \
  backend/bot/middlewares backend/bot/utils \
  backend/bot/plugins backend/bot/keyboards backend/bot/payment_providers backend/bot/services \
  backend/bot/handlers backend/bot/app/factories backend/bot/app/controllers backend/bot/app/web \
  backend/main_backend.py backend/main_worker.py backend/scripts scripts tests
```

ruff 规则组为 `E, W, F, I, UP, B, ASYNC, DTZ, C4, SIM, PIE, PERF, RUF, LOG, G, PLE, T10`，定义于 `pyproject.toml` 的 `[tool.ruff.lint]`。不使用 `per-file-ignores`，不得新增按文件忽略规则。`pytest.ini` 设置 `filterwarnings = error`，未预期的警告会使测试失败。

<a id="локальные-backend-тесты-на-windows"></a>

### Windows 本地后端测试

Windows 非 CI 环境下，`npm test` 将当前 Git 源码的新快照（含未忽略的新文件）放到 Linux Docker 中运行。快照不包含 `.env` 或知识图谱。`qa-deps` 目标仅包含 Python／Node／Docker CLI 和依赖，准备环境时不构建前端或产品代码。保留 asyncio 调试、警告视为错误及 pytest 参数。

```bash
npm run check:local    # 按指纹准备依赖，再完整执行 npm run check
npm run qa:local       # 完整隔离环境、升级验证及零跳过测试
npm run test:env        # 首次准备 Linux 依赖
npm run test:env:refresh # 显式更新系统和依赖，需要网络
npm run test:env:gc     # 清理旧的镜像保留容器
```

`check:local` 需要 Node 24、uv 和 Python 3.12（uv 可下载 Python）。原生 Python 和前端 node_modules 存在检出目录之外：`%LOCALAPPDATA%/minishop/test-envs` 或 `$XDG_CACHE_HOME/minishop/test-envs`（默认 `~/.cache/minishop/test-envs`）。`MINISHOP_TEST_CACHE_DIR` 可更改根目录。node_modules 通过符号链接接入；清理检出目录后会恢复链接，manifest／lock 不变时不会重复安装。不同系统、架构和 Node 版本的路径相互隔离。

Linux 镜像以摘要和依赖指纹固定在 `deploy/docker/test-runtime.lock.json`。GitLab 仅把依赖阶段发布到 `3252a8/remnawave-minishop-test-runtime`；包含新 lock 的产物须审查后加入 dev。输入文件变化时不复用旧 lock；镜像仓库不可用时可本地构建。可变标签不得替代已验证 lock 的摘要。更新步骤：执行 `test:env:refresh`，再以 Docker Hub 用户 `3252a8` 登录并运行 `node scripts/test_runtime.mjs publish`。不同测试运行不得共用测试数据库。

带 `minishop.local.keep=true` 标签的已停止保留容器仅保留镜像，不运行进程。清理容器时必须排除此标签：`docker container prune -f --filter "label!=minishop.local.keep=true"`。不得对该引擎执行无范围限制的 `docker system prune`。运行中的 pytest 默认限制为 4 CPU／4 GiB，可通过 `MINISHOP_TEST_CPUS` 和 `MINISHOP_TEST_MEMORY` 覆盖；未运行时不预留资源。详细保留和更新规则见 [test-environments.md](docs/test-environments.md)。

没有 Docker 时使用 `.venv/Scripts/python.exe` 或 PATH 中的 pytest。`MINISHOP_LOCAL_TEST_RUNTIME=native` 显式使用原生运行时；`MINISHOP_LOCAL_TEST_RUNTIME=container` 允许在 Linux／CI 中使用容器。不得把工作密钥存入镜像、lock 或快照。

**前端**（`frontend/`）：

```bash
npm run check        # eslint + svelte-check + prettier --check
npm run test         # Vitest：辅助函数和状态存储单元测试
npm run build        # 仅改类型后也必须通过 vite build
npm run test:e2e     # Playwright 文档演示冒烟：应用与后台、窗口、标签页、无控制台错误
```

**生成产物都有漂移保护，必须重新生成，不得手改：**

| 产物 | 生成命令 | 保护检查 |
| --- | --- | --- |
| `docs/openapi.json` | `PYTHONPATH=backend python -m bot.app.web.openapi` | `tests/contracts/test_openapi_artifact.py` |
| `docs-site/public/openapi.json` | `npm --prefix docs-site run sync:docs` | `npm run check:docs`、提交前检查、CI |
| `docs/architecture/events.md` | `PYTHONPATH=backend python -m bot.infra.event_catalog` | `tests/contracts/test_contract_docs_accuracy.py` |
| `docs/architecture/remnawave-api-compatibility.md` | `PYTHONPATH=backend python -m bot.services.panel_api_catalog` | `tests/contracts/test_remnawave_api_contract.py` |
| `frontend/src/lib/api/openapi.generated.ts` | `npm --prefix frontend run generate:api-types` | CI `git diff --exit-code` |
| 演示设置清单 | `python scripts/export_settings_manifest.py`（加 prettier） | `tests/contracts/test_settings_manifest_demo_sync.py` |
| `docs/remnawave-minishop.webp` | `npm run generate:readme-screenshot` | README 视觉检查 |
| `backend/requirements.txt` | `python -m piptools compile --resolver=backtracking --no-emit-index-url --no-emit-trusted-host -o backend/requirements.txt backend/requirements.in`（Python 3.12） | CI 安装 + `pip-audit` |
| `frontend/package-lock.json`、`docs-site/package-lock.json` | `cd <目录> && npx --yes npm@10.9.9 install --package-lock-only --ignore-scripts --no-audit --no-fund` | `npm run check:lockfiles`、提交前检查、Docker 矩阵前的 CI 检查 |

`docs-site/package.json` 固定 `postcss-selector-parser 7.1.6`，修复 [GHSA-rj75-hqrm-r3gf](https://github.com/advisories/GHSA-rj75-hqrm-r3gf)：`@expressive-code/core` 经 `postcss-nested@6` 暂时依赖存在漏洞的 parser 6.x。上游依赖可自行解析到不低于 `7.1.6`，且审计和文档构建不再需要覆盖时，才能删除该 override。

API 契约变化时，同时重新生成 `openapi.json` 和 `openapi.generated.ts`。新增接口需在 `backend/bot/app/web/openapi.zh-hans.json` 补充中文标题及分类；路径、字段和 `operationId` 保持协议标识。

---

<a id="2-золотые-правила-без-исключений"></a>

## 2. 不可违反的规则

- **不得手改生成产物。** 运行其生成器（第 1 节）。
- **不得修改、重排或重新编号已有数据库迁移。** 迁移只能追加，且必须幂等（第 5 节）。
- **不得压制自有代码的类型检查。** 不得用 `# type: ignore`／`any` 凑合编译，应修正类型。整个后端的 `mypy` 必须通过。
- **不得破坏线上传输契约：** HTTP `{"ok": …}` 包装、事件的扁平字典载荷、插件订阅签名 `(event_name, dict)`。
- **门面模块（`admin_api`、`subscription_webapp`、`subscription_service`）仅用于兼容。** 新代码使用具体内部模块（`*_impl`、领域模块、服务／路由模块），不得默认依赖门面作为内部 API；例外须记录在契约测试中。
- **自有前端代码全部使用 TypeScript**（`.ts`／`<script lang="ts">`）。架构门禁禁止在 `frontend/src` 新增 `.js` 或无 `lang="ts"` 的 `<script>`（`scripts/architecture_gates.json` 的 `first_party_js`、`svelte_lang_ts`）；仅允许清单中的生成产物例外。不得启用全局 `checkJs`。
- **不得硬编码用户或管理员可见文案。** 新增或修改的可见文本（机器人、应用、后台、邮件／通知、aria／placeholder／title）必须本地化，至少提供 `locales/ru.json` 和 `locales/en.json` 基础条目。中文阅读路径同时提供 `locales/zh-hans.json` 条目。组件或辅助函数的英文回退只用于开发兜底，不能替代基础语言键；西里尔文只放在语言文件中。`cyrillic_fallbacks` 架构门禁禁止增加历史违规。**后台键必须以 `admin_` 开头**：`at("foo")` 查找 `admin_foo`，缺少条目会向俄语管理员静默显示英文回退，类型和构建检查无法发现。`tests/contracts/test_admin_locale_keys.py` 检查所有字面量 `at("...")` 是否存在于两种基础语言中。
- **先拆分，再完善类型**，见第 5 节。不得直接给巨型文件原地补类型。
- **区分“兼容其他机器人”（保留的功能）与“重构残留”（应删除）**，见第 6 节。
- **保持核心与单独交付的 minishop PRO 隔离。** 核心公开文档和导航可以提及 PRO、概述公开能力并链接官网，但不得复制 PRO 代码、私有契约、资源或运行时依赖到核心。

---

<a id="3-соглашения-бэкенда"></a>

## 3. 后端约定

后端使用手写 `aiohttp` + `aiogram` + SQLAlchemy（异步）+ pydantic v2。**没有 FastAPI，不得引入。** 架构见 [docs/architecture.md](docs/architecture.md)。

常见任务（添加支付提供商、领域事件或 HTTP 端点）的步骤见[开发操作指南](docs/development/how-to.md)，每项均以第 1 节门禁结束。

<a id="31-http-api-типизированные-контракты"></a>

### 3.1 HTTP API（类型化契约）

- 在 `setup_subscription_webapp_routes`（`bot/app/web/webapp/routes.py`）及 `setup_admin_routes`（`bot/app/web/admin_api_impl/routes.py`）显式注册路由；插件通过 `Plugin.setup_web` 在运行时添加路由。
- **请求体：** 用 `parse_body`／`parse_body_or_400`（`bot/app/web/request_parsing.py`）按 `HttpBodyModel` 解析；新端点不得直接返回原始 `_read_json`。`parse_body_or_400` 可正确缩窄 mypy 类型。
- **响应：** 通过显式类方法 `from_orm_*` 构造 `HttpResponseModel`，**只读取已加载的标量属性**，如 `obj.__dict__.get("user")`。**不得开启 ORM 自动扫描 `from_attributes`**，它会在会话关闭后触发延迟加载。用 `_ok`／`_error` 包装响应，不改字段名和类型。
- **每条路由都在 `bot/app/web/route_contracts.py` 注册契约**，以生成 `openapi.json`。非 JSON 路由（CSV／二进制／multipart）声明内容类型，而非 JSON 模型。
- HTTP 参考：[docs/architecture/http-api.md](docs/architecture/http-api.md)。

<a id="32-доменные-события-типизированные-payloadы"></a>

### 3.2 领域事件（类型化载荷）

- 每个事件在 `bot/infra/event_payloads.py` 中对应一个 pydantic 模型（`extra="forbid"`）。通过 `events.emit_model(Model(...))` 发布；事件总线仍基于字典，`emit` **绝不抛出异常**。
- 载荷必须是**基本类型与 ISO-8601 日期时间组成的扁平字典**，不得使用 ORM 对象。订阅者按 ID 重新查询详细数据。载荷只是通知，不保证数据库行已经提交。
- 添加或修改事件后更新模型，并重新生成事件目录。
- 目录：[docs/architecture/events.md](docs/architecture/events.md)。

<a id="33-типобезопасность"></a>

### 3.3 类型安全

- `mypy` 覆盖整个后端和契约测试（`tests/contracts`），必须始终通过。新后端模块按目录自动纳入。通过 `[[tool.mypy.overrides]]` 逐模块收紧要求，不启用全局 `strict`。

<a id="34-миграции"></a>

### 3.4 数据库迁移

- 手写的**幂等**迁移器（`db/migrator/` 包）先检查数据库结构，再执行条件 DDL（`IF NOT EXISTS`、列检查）。已应用 ID 记录在 `schema_migrations`。
- **只追加。** 新增迁移，不得修改或重排已有迁移。插件迁移链使用命名空间（`<plugin>.0001_*`）。
- 从其他机器人（remnashop／旧版本）导入的兼容逻辑有意保留，见第 6 节。

<a id="35-плагины"></a>

### 3.5 插件

- 通过抽象基类 `Plugin` + `PluginContext`（`bot/plugins/spec.py`）扩展，使用入口点组 `minishop.plugins` 发现插件。钩子：`setup`、`setup_bot`、`setup_web`、`worker_tasks`、`queue_handlers`、`migrations`、`locales_dir`、`entitlements_provider`。
- 插件 API 是公开扩展接口，必须保持稳定。订阅者接收原始 `(event_name, dict)`；类型化模型是附加便利，不能成为强制接口。
- 契约：[插件契约](docs/development/plugin-contract.md)、[插件开发](docs/development/plugins.md)。

---

<a id="4-соглашения-фронтенда"></a>

## 4. 前端约定

使用 Svelte + Vite。API 客户端类型**来自 OpenAPI 规范**。

- 通过类型化客户端 `lib/webapp/publicApi.ts`（`createApiClient`）调用 API：`api("/api/...")` 从 `paths` 推导响应，`publicApi` 推导请求体。**使用字面量路径**，变量会拓宽类型并丢失推导。使用 `unwrap(...)` 解包 `{ok,…}`。
- `openapi.generated.ts` 从 `docs/openapi.json` 生成，**CI 会检查漂移**；后端契约变化后必须重新生成。
- 所有自有代码均使用 TypeScript：新模块为 `.ts`，组件为 `<script lang="ts">`；状态存储明确类型（`writable<State>`），使后端契约变化时 `check:svelte` 在实际消费者处报错。架构门禁（`first_party_js`、`svelte_lang_ts`）禁止新增无类型文件。没有 JS 文件时不需要全局 `checkJs`，**不得开启**。
- 界面文案使用 `t(...)`／`at(...)`，并在 `locales/ru.json`、`locales/en.json` 提供真实基础条目；中文路径同时补齐 `locales/zh-hans.json`。后台 `at("tariff_title", ...)` 查找 `admin_tariff_title`，须检查最终键名。添加新文案组时，增加小范围测试或现有语言检查，防止只有回退文案。
- 自有 Svelte 前端只使用 Svelte 5 runes。不得恢复 `export let`、`$:`、`$$props`、`$$restProps`、`<slot>`、`<svelte:component>`、`createEventDispatcher` 或类 API `$set`。`frontend/vite.config.mjs` 和 `frontend/vitest.config.mjs` 为 `frontend/src` 开启 `runes: true`；旧语法会使 `npm run check:runes`、`svelte-check`、构建及 Vitest 失败。

---

<a id="41-переиспользование-ui"></a>

### 4.1 界面组件复用

修改界面前，找到对应组件并查看**两个实际使用位置**。选择顺序：实体／操作组件 → 通用组合组件 → 基础组件。例如支付提供商应使用 `PaymentProviderCell`，而不是随意拼装 `AdminBadge`。配置 shadcn、安装 Bits UI 本身并不保证界面一致。

- 缺少所需变体时扩展共享组件；只有没有适用组件时才新建，并在变更说明中解释选择及受影响消费者。
- 不得复制其他区域的实体样式、面板结构或 CSS；不得用一个页面的全局样式控制另一个页面。通用元素的尺寸与移动端行为由共享组件负责，差异通过参数表达。
- `patterns` 组件直接导入或经其索引导入。基础组件与图标从 `$components/ui` 导入；仅 `components/ui` 层可直接导入 `bits-ui` 和图标库。
- 页面中禁止普通 `select`、新增原生 `input`／`textarea`，以及手工用 `btn`／`admin-btn` 类装饰的按钮；使用对应组件。语义容器、链接、列表及专用导航按钮不受此禁令限制。
- 日期时间使用 `DateInput`（时间用 `withTime`），复选框用 `Checkbox`，其他特殊字段使用下表对应组件。`Input` 仅允许文本和数字类型；日历、复选框、文件上传等由静态检查与类型检查禁止。检查器识别导入别名及表达式中的字面量。

组件选择表（路径相对于 `frontend/src`；文件名均为真实示例）：

| 任务 | 共享组件 | 两处使用示例 |
|---|---|---|
| 后台按钮 | `lib/components/patterns/admin/AdminButton.svelte` | `admin/sections/GiftsSection.svelte`、`admin/sections/PaymentsSection.svelte` |
| 应用按钮 | `lib/components/ui/button.svelte` | `webapp/gifts/GiftEntry.svelte`、`webapp/gifts/GiftFeature.svelte` |
| 输入框 | `lib/components/ui/input.svelte` | `admin/sections/users/UsersView.svelte`、`admin/sections/GiftCreateDialog.svelte` |
| 字段标签／提示 | `lib/components/patterns/admin/AdminField.svelte` | `admin/sections/AdsSection.svelte`、`admin/sections/promos/PromoCreateDialog.svelte` |
| 下拉菜单 | `lib/components/patterns/admin/AdminSelect.svelte` | `admin/sections/users/UsersView.svelte`、`admin/sections/GiftCreateDialog.svelte` |
| 列表工具栏 | `lib/components/patterns/admin/AdminListToolbar.svelte` | `admin/sections/users/UsersView.svelte`、`admin/sections/GiftsSection.svelte`；另见 `PaymentsSection.svelte` |
| 表格与分页 | `lib/components/patterns/admin/AdminTable.svelte`、`AdminPagination.svelte` | `admin/sections/PaymentTable.svelte`、`admin/sections/GiftsSection.svelte` |
| 实体跳转 | `lib/components/patterns/admin/AdminEntityLink.svelte` | `admin/sections/partners/PartnerDashboardTables.svelte`、`admin/sections/partners/PartnerDetailActivity.svelte` |
| 支付提供商及其标志／表情 | `lib/components/patterns/admin/PaymentProviderCell.svelte` | `admin/sections/PaymentTable.svelte`、`admin/sections/GiftsSection.svelte` |
| 表格中可复制值 | `lib/components/patterns/admin/AdminCopyableValue.svelte` | `admin/sections/PaymentTable.svelte`、`admin/sections/PaymentDetailModal.svelte` |
| 可复制链接字段 | `lib/components/patterns/CopyLinkField.svelte` | `webapp/screens/InviteScreen.svelte`、`webapp/gifts/GiftCard.svelte`；`GiftsSection.svelte` 使用 `admin` 变体 |
| 对话框 | `lib/components/ui/dialog.svelte` | `admin/sections/GiftCreateDialog.svelte`、`webapp/gifts/GiftFeature.svelte` |

查找嵌套表单时用 `rg` 搜索组件名。若尚无第二个消费者，查看最接近的共享组件，并在变更说明中明确记录。

列表工具栏在后台各区域的适用范围：

| 列表与面板 | 方案 |
|---|---|
| 用户、付款、礼品 | `AdminListToolbar`：搜索、筛选、计数与操作 |
| 合作伙伴、申请、提现 | `PartnerProgramTables.svelte` 三个标签页均使用该组件 |
| 日志 | 同一组件：用户筛选、重置、计数、刷新 |
| 支持工单 | 同一组件：搜索和筛选；状态计数留在标签页，不能用当前页条数冒充未知的总数 |
| 备份 | 同一组件，不提供搜索或独立计数；操作和目录放在 `metadata` 插槽；桌面单行，移动端换行 |
| 激活码、广告、群发历史 | 不单设筛选工具栏的表格；通用 `AdminTable`／`AdminPagination`，页面操作留在标题处 |
| 设置、翻译、套餐编辑器、图表 | 专用编辑与范围面板，不属于实体列表工具栏 |

共享工具栏的 `total` 可选；传入真实查询总数，不能用当前页大小替代。仅使样式相似不算完成迁移。静态检查禁止恢复旧列表面板类（`admin-toolbar`、`admin-toolbar-card`、`partners-filters`、支持面板）。

**自动保护。** `npm --prefix frontend run lint` 检查 `frontend/eslint.config.mjs` 和 `frontend/scripts/eslint-ui-reuse.mjs` 的界面约束，属于 `npm run check` 和 CI。旧字段有精确的 `nativeFieldBaseline` 清单，包含文件、类型、数量和原因。这是历史页面债务，不能为了通过检查新增豁免。迁移字段后减少或删除记录，数量增减都会被发现。基础组件内部允许原生元素。历史例外包括充值金额动画和文本编辑器自有区域。

**结果验证。** 修改共享组件必须验证受影响的消费者，不能只测辅助函数。列表工具栏检查搜索、排序、分页、移动端筛选显示及元素等高；菜单检查打开、选择、键盘和 Escape，避免丢失父对话框；支付提供商检查表格和卡片中的实际标志／表情与名称；链接检查完整值、复制和手动选择。检查桌面和移动端深色主题，避免裁切及对话框多余滚动。共享界面场景在 `frontend/e2e/ui-reuse.spec.ts`，规则测试在 `frontend/src/lib/uiReuse.test.ts`。截图有助视觉审查，但不能证明组件复用。用户要求界面审批时，在修改**前**保存截图，并在提交前展示前后对比。

---

<a id="5-принципы-рефакторинга"></a>

## 5. 重构原则

- **先拆分，再完善类型。** 大型或复杂文件先按职责拆成小型类型化模块，而不是原地加类型，一次工作同时改善类型和体积。目标为**没有超过约 900 行且无书面理由的模块**。唯一认可的理由是生成产物：`scripts/architecture_gates.json` 的 `module_size.allowlist` 只包含生成器输出（`templates/*.js`、`openapi.generated.ts`、`demoDataset.js`），由 `tests/contracts/test_architecture_gates.py::test_module_size_allowlist_is_generated_artifacts_only` 保护。手写文件过大必须拆分，不得加入允许清单。
- **monkeypatch／重新导出的陷阱。** 测试常用 `monkeypatch.setattr(module, "name", …)`。把 `name` 移到子模块再重新导出，只恢复导入兼容，**不能**恢复 monkeypatch 语义；补丁和调用分属不同副本时会静默失效，测试虽然通过却不正确。拆分前在 `tests/` 搜索补丁目标；若被替换符号和调用将跨模块，**先修改测试，让补丁指向新模块**，再迁移。始终确认替身确实被调用。
- **支付提供商结构：** 每个提供商一个包、统一接口（`__init__` 导出 `SPEC` 与工厂入口，始终包含 `config` + `service`；`webhook`／`callbacks`／`payment_methods`／`router` 仅在有实际内容时拆出，不制造只有五行的 webhook 模块）。不得更改 `id`／`provider_key`／webhook 路径，它们已持久化并配置在面板中。
- **导入整理：** 拆分后运行 `ruff check --fix --select F401,F811`，不要照搬原导入块。不同模块重复框架导入是正常的；**不得**经通用模块的星号导入集中转发，这是已清除的反模式。

---

<a id="6-что-намеренно-а-что-removable"></a>

## 6. 应保留与可删除的内容

**保留：这些是功能，而非废旧代码：**

- 跨机器人**迁移兼容性**（`MIGRATION_REMNASHOP_*`、`backend/scripts/import_legacy.py`、`legacy_referral_codes`／`legacy_import_mappings`、对账迁移）。它们实现其他机器人迁移与安装向导（`scripts/install.sh`）。核心和带命名空间的插件迁移顺序由 `tests/contracts/test_migration_chain_snapshot.py` 固定；重排或重新编号会直接使 CI 失败，因此只追加规则由机器验证。
- `config/settings.py` 中的**废弃环境变量别名**（`ignore_deprecated_*`）保护现有部署，只能在明确弃用期后删除。
- 包内部的 `_runtime.py` 共享模块承担实际职责，不是死代码。

**可删除（先查导入者和补丁目标）：** 重构遗留的重新导出兼容层、标注“kept for compatibility”但已无调用的废弃辅助函数，以及转用类型化契约后失去用途的序列化器。

---

<a id="7-ключевые-решения-почему"></a>

## 7. 关键决策及原因

- **手写类型化契约，而非更换框架。** 保留 aiohttp，加入 pydantic 请求／响应与事件模型，再从实际路由生成 OpenAPI。在已有代码工作的地方强制契约，避免重写。
- **mypy／svelte-check 要求只能收紧。** 类型覆盖持续增加且必须通过；已发现真实潜在缺陷，例如 aiogram `Message | InaccessibleMessage`。
- **先拆分，再完善类型。** 巨型文件先拆成聚焦模块；小单元比复杂大文件更容易、安全地补充类型。
- **生成产物及漂移检查**（`openapi.json`、`events.md`、`openapi.generated.ts`）让前后端边界的契约可以自动验证。

---

<a id="8-рабочий-процесс"></a>

## 8. 工作流程

- 从 `dev`（或维护者指定分支）建立分支；PR 指向 `dev`／`main`，必须通过第 1 节所有门禁。
- **提交说明：** 英文 Conventional Commits 前缀（`fix:`、`feat:`、`refactor:`、`chore:`、`docs:`、`ci:`、`build:`、`perf:`、`test:`、`style:`），**不得**添加 `Co-Authored-By` 尾注。
- **[CHANGELOG.md](CHANGELOG.md) 是仓库和文档站 `/changelog/` 的唯一更新历史来源。** 文档站经 `sync:docs` 获取，不得修改生成副本。
- 提交值得记录的核心变更前，更新**“开发中 · dev”**：只使用需要的分类“新增”“变更”“修复”“性能”“文档”“升级注意”。描述最终效果，不罗列提交。先读完整 dev 区和最近发布版本，补充同一功能已有条目、合并重复、删除撤回承诺。修复尚未发布的新功能通常修改原条目；已发布版本的回归可单列。无新增效果的内部测试、格式调整或 CI 重跑无需单列。
- 公开说明使用中性术语：**“激活码”**、有效期增加、价格调整、额外流量。这是项目编辑规则，不改变 API、设置名或功能含义。
- 发布时，只将真正发布的变更从 dev 移入 `## vX.Y.Z — YYYY-MM-DD`；未发布项留在顶部，并附发布链接。日期取 Release API 的实际 UTC 发布时间，不使用标签、提交或镜像同步日期；镜像日期不同时使用 GitLab 原始 `released_at`。版本按新到旧排列；已发布历史仅允许有证据的事实修正，以及不改变事实的语言翻译。
- 每次提交只包含一个连贯变更；重构优先把纯移动独立为便于审查的差异。
- 契约变化后，在同一变更内重新生成相关产物（第 1 节）。
- 兼容门面（`admin_api`、`subscription_webapp`、`subscription_service`）仅用于兼容。实现代码优先导入具体 `*_impl`／领域模块，除非公开兼容契约要求，否则不得为自有代码新增对门面的依赖。
