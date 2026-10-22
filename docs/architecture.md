# 项目架构

<!-- 保留翻译前的章节锚点，以兼容既有链接。 -->
<a id="архитектура-проекта"></a>

本文说明**系统如何组织**（“软件架构”一节），以及**仓库与部署如何安排**（后续章节）。
贡献规范与可自动检查的质量门禁见[贡献规范](https://gitlab.com/3252a8/remnawave-minishop/-/blob/main/CONTRIBUTING.md)。
<!-- GitHub 源链接（未启用）：[贡献规范](https://github.com/3252a8/remnawave-minishop/blob/main/CONTRIBUTING.md) -->

## 软件架构

<a id="архитектура-по"></a>

### 运行进程

<a id="рантайм-процессы"></a>

应用通过两个进程运行，共用同一套初始化与依赖装配：

- **backend**（`main_backend.py`）：基于 aiohttp，提供 Mini App 与管理后台的 HTTP API、
  Telegram Webhook，以及支付服务商和面板的 Webhook。它在不同端口启动两个 aiohttp 应用：
  一个处理 Webhook，另一个提供 Subscription WebApp（Mini App 与 `/api/*`）。
- **worker**（`main_worker.py`）：执行套餐后台任务、面板同步和 Webhook 队列处理等后台工作。

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

外部代码通过独立软件包与入口点形式的插件扩展应用，无需派生核心代码。
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
  examples/           可直接使用的 Docker Compose 启动示例

data/                 挂载到容器中的运行数据
locales/              机器人与 Web App 的翻译
docs/                 文档，包括生成的 openapi.json 与事件目录
tests/                Python 测试
```

## 部署

<a id="деплой"></a>

主 `docker-compose.yml` 位于仓库根目录，使 `docker compose up` 保持为简单的生产启动方式。
它通过 `deploy/docker/Dockerfile` 构建三个应用镜像：

- `backend`：aiohttp API 与 Webhook。
- `worker`：套餐后台任务、面板同步与 Webhook 队列处理器。
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

主要命令：

```bash
docker compose up -d --build
docker compose run --rm migrate
docker compose logs -f backend worker frontend
npm run build:webapp
pytest -q
```
