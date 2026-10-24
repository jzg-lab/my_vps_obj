# 项目架构

<!-- 保留翻译前的章节锚点，以兼容既有链接。 -->
<a id="архитектура-проекта"></a>

本文说明本项目的技术职责、运行进程、契约和仓库布局。首次接手从[接手指南](handoff.md)开始，
开发规范与质量门禁以仓库内的[贡献指南](../CONTRIBUTING.md)为准。
实施进度及证据只见[实施计划 §14：本轮本地最终验收](implementation-plan.md#本轮本地最终验收)，
不能由源码存在、接口定义或本地通过推断生产已交付。

## 业务与执行职责

本项目基于 Minishop 二开：一个登录账号可以持有多份独立服务；一期人工开通，不接在线支付。
管理台沿**客户**与**节点**两条主线组织，日常操作使用同一网站、同一账号，
Remnawave 继续承担执行层职责。产品边界以[需求](requirements.md)和[统一管理台指南](admin-console-guide.md)为准。

| 层次 | 负责什么 | 技术入口 |
| --- | --- | --- |
| 网站与管理台 | 用户查看自己的服务；管理员从客户或节点追溯服务、资源及操作结果。 | `frontend/src/webapp/`、`frontend/src/admin/` |
| 业务层 | 账号、模板、开通记录、服务权益、周期、已确认用量和专用出口占用。 | [独立服务模型](development/independent-services.md)、[权益与计量契约](development/entitlement-metering-contract.md) |
| 连接交付与同步 | 为每份服务维护独立连接身份，按权益核对远端权限、用量和撤销结果。 | [连接与资源交付](development/service-delivery.md) |
| Remnawave／Node | 管理节点、Host、授权组和连接配置，执行数据面权限并提供统计来源。 | [面板 API 兼容性目录](architecture/remnawave-api-compatibility.md) |
| 扩展与上游兼容 | 保留插件、旧单订阅业务及跨机器人迁移契约；不把保留能力当作本项目 MVP 入口。 | [上游兼容参考](upstream/index.md)、[插件契约](development/plugin-contract.md) |

账号、服务、连接身份不是同一个对象。上游单订阅路径不能代替多服务的独立额度、有效期和停用；
授权组描述可访问资源，不能据此推断当前在线连接。待接入节点仅登记名称、地址、备注，
不执行远程安装或探测；实际接入按指南 F06 验证。低频复杂配置保留高级维护入口，不另建权益账本。

运行环境选择见[项目隔离开发环境](development/project-local.md)；上游原文仅作对照：
[上游贡献规范](https://gitlab.com/3252a8/remnawave-minishop/-/blob/main/CONTRIBUTING.md)。
<!-- GitHub 源链接（未启用）：[贡献规范](https://github.com/3252a8/remnawave-minishop/blob/main/CONTRIBUTING.md) -->

## 软件架构

<a id="архитектура-по"></a>

### 运行进程

<a id="рантайм-процессы"></a>

应用通过两个进程运行，共用同一套初始化与依赖装配：

- **backend**（`main_backend.py`）：基于 aiohttp，提供用户网站与管理台 HTTP API、
  Telegram Webhook 及保留的上游回调路径；本项目支付和账号级 Panel 回调返回 410。
  它在不同端口启动两个 aiohttp 应用：一个提供 Webhook 路由，另一个提供网站与 `/api/*`。
- **worker**（`main_worker.py`）：执行独立服务交付、计量、周期、资源操作、同步及重试。
  保留旧商业处理代码不表示已启动对应 worker；旧核心权益事件按现有边界转入死信核对，不发放权益。

两个进程都会调用 `run_setup(ctx)` 和 `register_core_reactions(ctx)`，
因此**两者都会监听领域事件总线**并激活插件。事件层的任何改动都必须在两个进程中一致生效。

### 分层与请求流程

<a id="слои-и-поток-запроса"></a>

```text
HTTP 路由 → parse_body / 请求契约 → 服务层（业务逻辑）→ DAL → _ok/_error 响应封装
                                         │
                                         └─ emit_model(...) → 事件总线 → 事件响应逻辑/插件
```

- **路由**由 `setup_subscription_webapp_routes`、`setup_admin_routes` 显式注册，
  也可由插件通过 `Plugin.setup_web` 在运行时注册。
- **DAL**（`db/dal`）是数据库访问的唯一入口；服务层不绕过它直接执行 SQL。
- **服务层**（`bot/services`）承载业务逻辑，并在关键节点发布事件。

### 四类类型化契约

<a id="четыре-типизированных-контракта"></a>

架构以四类显式、可自动验证的契约为依据，作为统一的事实来源：

1. **HTTP API**：Pydantic 请求与响应模型，以及用于生成 `openapi.json` 的
   `route_contracts` 注册表。详见 [HTTP API 契约](architecture/http-api.md)。
2. **领域事件总线**：每个事件对应一个 Pydantic 模型（`bot/infra/event_payloads.py`），
   通过 `emit_model` 发布；载荷是由基本类型组成的扁平字典。
   详见[事件目录](architecture/events.md)。
3. **插件**：抽象基类 `Plugin` 与 `PluginContext`，通过入口点组
   `minishop.plugins` 发现插件。详见[插件契约](development/plugin-contract.md)。
4. **Remnawave API**：记录对外调用操作、Webhook 契约、API 代际及已认证的精确版本的
   类型化注册表。详见 [Remnawave API 兼容性目录](architecture/remnawave-api-compatibility.md)。

### 扩展机制

<a id="расширяемость"></a>

插件可通过独立软件包与入口点扩展应用；这是保留的公开扩展能力，不代表本项目仅靠插件实现。
可扩展的部分包括 HTTP 路由（`setup_web`）、aiogram 路由器（`setup_bot`）、
后台任务、队列处理器、带命名空间的迁移链、本地化资源和权益提供器。
内置插件始终启用；外部插件由 `PLUGINS_ENABLED` 控制。

### 前后端契约

<a id="контракт-фронтбэк"></a>

OpenAPI 规范（`docs/openapi.json`）从实际路由器生成，再据此生成前端 TypeScript 类型
（`frontend/src/lib/api/openapi.generated.ts`）。类型化客户端 `publicApi.ts`
根据调用路径推导请求与响应结构。CI 对这两份生成物执行一致性检查；
后端契约发生变化而前端未同步时，构建会失败。

## 仓库布局

<a id="раскладка-репозитория"></a>

仓库按运行职责划分：

```text
backend/              应用的 Python 代码
  bot/
    app/web/          aiohttp API：Web App 与管理后台、路由契约（route_contracts）、
                      请求解析、OpenAPI 生成器
    infra/            领域事件总线（events、event_payloads）、Redis、Webhook 队列
    plugins/          扩展入口（minishop.plugins 入口点）
    payment_providers/ 支付服务商（每个服务商一个软件包）
    handlers/         aiogram 处理器（用户端/管理端）
    services/         业务逻辑与事件响应逻辑
    middlewares/, keyboards/, utils/   机器人基础设施
  config/             Pydantic 设置及套餐/主题加载器
  db/                 SQLAlchemy 模型、DAL、幂等迁移器
  main_backend.py     aiohttp 后端入口
  main_worker.py      后台 worker 入口
  main_migrate.py     一次性迁移入口
  requirements.txt    Python 运行依赖

frontend/             基于 Svelte/Vite 的 Mini App 与管理后台
  src/                Svelte 源码（类型化 API 客户端位于 lib/webapp/publicApi.ts）
  src/                仅使用 Svelte 5 runes；Vite/Vitest 以 runes 模式编译 src，
                      check:runes 禁止旧语法
  src/lib/api/        从 OpenAPI 生成的 TypeScript 类型
  scripts/            前端构建辅助脚本
  package.json        Node.js 脚本与依赖

deploy/
  docker/             Dockerfile，以及运行时 nginx 和 Caddy 配置
  examples/           上游 Compose 与部署配置参考，不替代本项目源码镜像

data/                 挂载到容器中的运行数据
locales/              机器人与 Web App 的翻译
docs/                 文档，包括生成的 openapi.json 与事件目录
tests/                Python 测试
```

## 部署

<a id="деплой"></a>

主 `docker-compose.yml` 位于仓库根目录，提供基础部署拓扑。
本项目本地开发使用 `project:*` 命令及项目 overlay，具体配置见[项目环境](development/project-local.md)；
通用兼容测试环境另见 [dev-stand](development/dev-stand.md)，两者的 seed 与生命周期不同。
它通过 `deploy/docker/Dockerfile` 构建三个应用镜像：

- `backend`：aiohttp API 与 Webhook。
- `worker`：独立服务、资源操作、面板同步及对应队列处理器。
- `frontend`：由 nginx 提供的 Svelte 静态资源。

Mini App 与管理后台以 ES 模块构建，并拆分代码包：页面通过
`<script type="module">` 引入入口，其他代码块
（`subscription_webapp.<name>.<hash>.js`）按需加载。
除首页与设置页之外的页面均通过 `lib/webapp/lazyScreen.svelte.ts` 动态导入，
因此支持页面中的消息编辑器不会进入首屏加载内容。
代码块文件名包含内容哈希，并以 `immutable` 缓存策略提供。
aiohttp 路由、nginx 配置和资源准备逻辑必须采用相同的文件命名规则；
不一致会导致代码块返回 404，进而使页面无法打开。

`migrate` 是基于 backend 镜像的一次性容器，属于标准 Compose 依赖图。
Postgres 与 Redis 进入健康状态后，`migrate` 执行 `Base.metadata.create_all`
和待应用的 `schema_migrations`；只有迁移成功结束，`backend` 与 `worker` 才会启动。
这样，`docker compose up` 仍会自动执行迁移，但不会在每个后端副本内部重复启动迁移。

Python 导入有意保留在 `bot.*`、`config.*` 和 `db.*` 命名空间中。
运行容器设置 `PYTHONPATH=/app/backend`；本地测试通过 `pytest.ini` 使用相同布局。

下列是基础 Compose／构建命令参考，不是项目环境的初始化步骤。
执行前按对应环境文档确认 Docker context、Compose 文件和配置；生产更新另按
[环境记录](development/project-local.md#production-access)及明确授权安排。

```bash
docker compose up -d --build
docker compose run --rm migrate
docker compose logs -f backend worker frontend
npm run build:webapp
pytest -q
```
