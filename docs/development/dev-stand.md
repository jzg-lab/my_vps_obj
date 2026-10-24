# 上游兼容开发环境

<a id="统一开发环境"></a>

<a id="единый-dev-stand"></a>

dev-stand 是保留的通用 Docker Compose QA 工具链，运行 Mini Shop、PostgreSQL、Redis、本地 Remnawave Panel、Remnawave Subscription Page 和上游测试夹具。

> 本文保留上游开发环境说明。本项目日常开发和验收使用[项目隔离开发环境](project-local.md)及 `my-vps-obj` 专属 Docker context/project，不直接运行上游环境命令替换它。上游订阅、支付和奖励夹具不属于当前 MVP 的业务数据；无真实 Node 时，面板测试不能证明实际流量、独享出口或旧连接停用。

## 先选择环境

| 用途 | 配置与命令 | 初始数据和生命周期 |
| --- | --- | --- |
| 本项目独立服务开发 | `.env.project-dev`、`project:*`；基础两份 Compose 后叠加 `docker-compose.project-dev.yml` | `seed-project-accounts.sql` 只补基础账号与 owner 角色，已有账号不覆盖；`seed-project-panel.sql` 只补开发令牌，不造订阅、支付、面板用户或 Node。项目命令还启动 worker。 |
| 上游兼容 QA | `.env.remnawave-dev`、`dev:stand:*`；基础 `docker-compose-dev.yml` 加 Remnawave overlay | `seed-minishop.sql`、`seed-remnawave.sql` 使用账号级订阅／支付夹具；可另启用 `mock-data`。 |
| 可复用测试运行器 | `check:local`、`qa:local` | 工具依赖缓存及一次性测试资源，见[测试环境](../test-environments.md)，不是日常业务库。 |

这些区别可从根 `package.json`、项目 overlay 和 `deploy/dev/seed-project-*.sql` 核对。
相同的本机端口、测试邮箱或密码不表示同一环境；运行任何 seed 前先确认配置、Compose 项目和数据库。
通用 seed 的幂等不等于不覆盖夹具，不能在项目环境重播它来“补齐测试数据”。
源码中的旧业务停用策略也不会因加载通用 seed 而解除；下文旧支付／订阅场景是兼容参考，
不能据此承诺本派生项目全栈 QA 可不加区分地通过。接手顺序及验收证据见[接手指南](../handoff.md)。

从仓库根目录进入上游环境的简短命令：

```powershell
make dev DEV_PRESET=3.4.5
```

显式传入 `DEV_PRESET=3.4.5` 后，命令应用该预设、校验 Compose 并启动环境。
仓库 `Makefile` 的裸 `make dev` 默认仍为 `3.0.0`，不能将它当作下面 `3.4.5` 命令的等价写法。
其他预设例如 `make dev DEV_PRESET=2.8.0`。上述 `3.4.5` 的等价 npm 命令：

```powershell
npm run dev:stand:use:3.4.5
npm run dev:stand:config
npm run dev:stand:up
```

旧 Compose 文件分别承担以下职责，并非多个独立开发环境：

- `docker-compose-dev.yml`：基础本地 Mini Shop 服务栈。
- `docker-compose.remnawave-dev.yml`：Remnawave、Subscription Page 和初始数据覆盖层，与基础文件共同组成统一环境。
- `docker-compose.test.yml`：隔离的后端测试运行器。
- `docker-compose.demo.yml`：静态文档演示的 nginx。
- `docker-compose.yml`：接近生产的应用启动配置，不是 QA 环境。

## 版本

<a id="версии"></a>

仓库 `3.4.5` 预设固定以下版本；这是工具链版本，不是本项目实际环境或最新上游发布的声明：

- Remnawave Panel `v3.4.5`（`remnawave/backend:3.4.5`）。
- Remnawave Node `v3.3.0`（`remnawave/node:3.3.0`）。
- Remnawave Subscription Page `7.2.6`（`remnawave/subscription-page:7.2.6`）。

自动开发环境只启动本地 Panel 和 Subscription Page。单独的 Remnawave Node 需要先在面板登记并提供 `SECRET_KEY`；`REMNAWAVE_NODE_VERSION` 仅固定另行启动的本地节点版本。

手动检查其他组合时，在 `.env.remnawave-dev` 修改：

```env
REMNAWAVE_DEV_VERSION=3.4.5
REMNAWAVE_NODE_VERSION=3.3.0
REMNAWAVE_SUBSCRIPTION_PAGE_VERSION=7.2.6
```

同样的版本保存在 `deploy/dev/remnawave-versions.lock.json`，全栈 QA 检查环境示例与锁文件一致。

## 版本预设

<a id="версионные-пресеты"></a>

检查兼容性时不要复制整份 Compose 到版本目录。环境共用 `docker-compose.remnawave-dev.yml` 覆盖层，由 `deploy/dev/remnawave-stands/<panel-version>/` 中的小型预设指定版本及数据卷名：

- `stand.env`：Panel、Node、Subscription Page 标签及各版本专属数据卷。
- `versions.lock.json`：供测试和审查使用的机器可读锁文件。

存在预设不等于承诺支持。上游 Core 的认证矩阵记录为：

- **current**：`3.4.5`、`3.4.4`、`3.4.3`、`3.4.2`、`3.4.1`、`3.3.2`、`3.3.0`、`3.2.3`、`3.2.1`、`3.2.0`、`3.1.0`、`3.0.0`，使用数字用户 ID 的 API 代次。
- **maintenance**：`2.8.1`，使用 UUID 用户 ID 的 API 代次。

`2.8.0` 和 `2.7.4` 仅保留为手工诊断的历史预设，不在常规 CI 矩阵。本派生项目当前 CI 只运行 `3.4.5`，不能把上游认证记录当作本项目全矩阵验证。支持策略、实际 API 调用清单和新版本检查表由生成器写入 [Remnawave API 兼容目录](../architecture/remnawave-api-compatibility.md)。

Panel `3.4.1` 和 `3.4.2` 留在上游矩阵供回归，但实际使用应立即更新至至少 `3.4.3`，该版本修复 [GHSA-8mcp-v46j-fp26](https://github.com/remnawave/backend/security/advisories/GHSA-8mcp-v46j-fp26)。[Panel `3.4.5`](https://f.docs.rw/t/topic/354/26) 保持 Core 使用的 HTTP 契约，修复精确用户 ID 筛选和 Torrent-Blocker 报告归属，并修复 Xray 配置生成器的 gRPC `multiMode`，添加 `postStart` 插件结构和节点连接的 `SERVICE_SNI_VERIFICATION` 开关。这些是面板设置，升级不要求增加 Core 设置。

共有十五个预设：

- `3.4.5`：Panel `3.4.5`、Node `3.3.0`、Subscription Page `7.2.6`。
- `3.4.4`：Panel `3.4.4`、Node `3.3.0`、Subscription Page `7.2.6`。
- `3.4.3`：Panel `3.4.3`、Node `3.3.0`、Subscription Page `7.2.6`。
- `3.4.2`：Panel `3.4.2`、Node `3.3.0`、Subscription Page `7.2.6`。
- `3.4.1`：Panel `3.4.1`、Node `3.3.0`、Subscription Page `7.2.6`。
- `3.3.2`：Panel `3.3.2`、Node `3.3.0`、Subscription Page `7.2.6`。
- `3.3.0`：Panel `3.3.0`、Node `3.3.0`、Subscription Page `7.2.6`。
- `3.2.3`：Panel `3.2.3`、Node `2.8.0`、Subscription Page `7.2.6`。
- `3.2.1`：Panel `3.2.1`、Node `2.8.0`、Subscription Page `7.2.6`。
- `3.2.0`：Panel `3.2.0`、Node `2.8.0`、Subscription Page `7.2.6`。
- `3.1.0`：Panel `3.1.0`、Node `2.8.0`、Subscription Page `7.2.6`。
- `3.0.0`：Panel `3.0.0`、Node `2.8.0`、Subscription Page `7.2.6`。
- `2.8.1`：Panel `2.8.1`、Node `2.8.0`、Subscription Page `7.2.6`。
- `2.8.0`：Panel `2.8.0`、Node `2.8.0`、Subscription Page `7.2.6`。
- `2.7.4`：Panel `2.7.4`、Node `2.7.0`、Subscription Page `7.2.4`。

Node `3.3.0` 要求 Panel 至少为 `3.3.0`，因此 `3.3.x` 和 `3.4.x` 预设使用该节点版本。新面板向后兼容旧节点，反向组合不受支持。

切换到前一个兼容预设：

```powershell
npm run dev:stand:down
npm run dev:stand:use:2.8.1
npm run dev:stand:config
npm run dev:stand:up
```

返回本文使用的 `3.4.5` 预设：

```powershell
npm run dev:stand:down
npm run dev:stand:use:3.4.5
npm run dev:stand:config
npm run dev:stand:up
```

各预设使用不同 Docker 数据卷（`*-274`、`*-280`、`*-281`、`*-300`、`*-310`、`*-320`、`*-321`、`*-323`、`*-330`、`*-332`、`*-341`、`*-342`、`*-343`、`*-344`），避免不同面板迁移污染其他数据库。由于 Compose 保留固定容器名和端口，这些上游环境不能同时启动。需要并行时还须参数化项目名、容器名和端口；当前不预先增加这项运维复杂度。

上游支持策略是在确实支持升级路径期间保留最新和一个此前兼容预设。只有面板 API、webhook 契约或数据结构变化导致缺少独立回归存在较大风险时，才添加更旧版本。停止检查且用户不再需要后，经明确决定可移除过时预设。

## 环境变量

<a id="переменные-окружения"></a>

`deploy/dev/remnawave-dev.env.example` 已包含本地测试值。复制到 `.env.remnawave-dev`，只在本地修改：

```powershell
Copy-Item deploy/dev/remnawave-dev.env.example .env.remnawave-dev
```

默认对面板写入使用 dry-run：

```env
PANEL_WRITE_MODE=dry_run
PANEL_DRY_RUN_VALIDATE_REMOTE=False
PANEL_DRY_RUN_SYNTHETIC_CREATE=True
```

应用读取真实的本地面板，但可在不修改面板状态的情况下检查写入操作。若需在隔离本地面板使用 live 模式，应使用 Remnawave“Settings → API Tokens”中的令牌，并启用：

```env
PANEL_API_KEY=...
REMNAWAVE_DEV_API_TOKEN=...
PANEL_WRITE_MODE=live
PANEL_DRY_RUN_VALIDATE_REMOTE=True
```

示例中的固定 `REMNAWAVE_DEV_API_TOKEN` 由 `deploy/dev/seed-remnawave.sql` 写入。不更换令牌时不要修改 `REMNAWAVE_DEV_APP_SECRET`。覆盖层同时以 `APP_SECRET` 和旧 `JWT_AUTH_SECRET` 传给面板，兼容 Panel 3.0.0、2.8.1 和 2.8.0。3.0 已删除的 `JWT_AUTH_SECRET`、`JWT_API_TOKENS_SECRET` 和 `IS_DOCS_ENABLED` 仅为旧预设保留，Panel 3.x 忽略它们。

自动 QA 示例只启用开发／测试钩子：

```env
QA_AUTH_ENABLED=True
QA_PAYMENT_ENABLED=True
QA_PAYMENT_SECRET=dev_qa_payment_secret_change_me
```

`QA_AUTH_ENABLED` 仅在 `APP_RUNTIME_MODE=development|test` 时，将一次性邮箱验证码放入 `/api/auth/email/request` 响应。`QA_PAYMENT_ENABLED` 启用本地 `qa` 提供者，其 webhook 只接受通过 `X-QA-Payment-Signature` 携带 HMAC 签名的载荷。这些公开测试配置不得用于公网。

## 启动

<a id="запуск"></a>

```powershell
npm run dev:stand:config
npm run dev:stand:up
npm run dev:stand:ps
```

手工检查多种界面状态时，可改用附带模拟数据的可选配置：

```powershell
npm run dev:stand:config:mocks
npm run dev:stand:up:mocks
```

普通 `dev:stand:config` 和 `dev:stand:up` 不启用 `mock-data`。环境已启动时可重复应用模拟数据：

```powershell
npm run dev:stand:mocks
```

主要服务日志：

```powershell
npm run dev:stand:logs
```

在已启动环境运行全栈 QA：

```powershell
$env:QA_FULLSTACK = "1"
$env:QA_API_BASE_URL = "http://127.0.0.1:18082"
$env:QA_WEBHOOK_BASE_URL = "http://127.0.0.1:18080"
$env:QA_FRONTEND_URL = "http://127.0.0.1:18082"
$env:QA_REMNAWAVE_HEALTH_URL = "http://127.0.0.1:3001/health"
$env:QA_DB_DSN = "postgresql://remnawave_minishop:remnawave_minishop@127.0.0.1:6768/remnawave_minishop"
$env:QA_PAYMENT_SECRET = "dev_qa_payment_secret_change_me"
npm run qa:fullstack
```

没有 `QA_FULLSTACK=1` 时跳过 `tests/qa`，避免普通 `pytest` 依赖 Docker Compose。

Windows 上普通完整 pytest 可用隔离 Linux 运行器：

```powershell
docker compose -f docker-compose.test.yml run --build --rm test-runner
```

源码复制进镜像，后续运行复用 Python 依赖层。本地 Python 的文件锁测试在 Windows 执行；符号链接测试只在用户无创建权限时跳过。需要覆盖符号链接时启用 Windows 开发者模式或使用 Linux 运行器。

### 包含 Windows 的无跳过完整测试

<a id="все-тесты-без-пропусков-включая-windows"></a>

完整本地检查需要使用 Linux 容器的 Docker Desktop、Python、Node.js 24+ 及开发依赖，当前版本要求以根目录 `package.json` 和 CONTRIBUTING 为准：

```powershell
npm run qa:all
```

该命令构建当前 Core 和包含 `sh`、`bash`、OpenSSL、测试依赖的独立 Linux 镜像；启动隔离 Remnawave 2.8.1，验证 API，在**同一数据库**上升级至 3.4.5，再运行全部 `tests/`，包含安装器、试用、支付及升级后身份核对。之后运行架构、文档、lint、类型、界面检查、构建和 Playwright。任何后端测试跳过都会导致失败。这是上游全栈检查工具的覆盖范围，不表示当前 MVP 已恢复旧业务入口。

每次运行有独立容器名、网络和数据卷，不占用主机端口，不修改本地 `.env`、`.env.remnawave-dev`、`data/` 或已有环境。完成或失败后清理本轮容器和数据卷，日志及 JUnit 报告留在打印的 `tmp/minishop-qa-…/`。调试时可保留环境：

```powershell
npm run qa:all -- --keep-stand
```

结束时会输出独立 Compose 文件和项目名。清理该环境须对输出的 `--project-name` 与 `-f` 执行 `docker compose ... down --volumes`，不会影响普通开发环境。

验证特定预设的读写契约，包括版本探测、用户标识、精确批量分组及多节点带宽：

```powershell
$env:QA_FULLSTACK = "1"
$env:QA_REMNAWAVE_PRESET = "3.4.5" # 或在切换预设后使用 2.8.1
python -m pytest -q tests/qa/test_remnawave_panel_contract.py
```

以 Remnawave 3.4.4 认证使用的数据规模运行确定性的性能回归：

```powershell
npm run bench:bot -- --users 200,1000,10000,30000
```

`premium_usage_8_nodes_distinct_periods` 比较实际多节点调用次数与旧 `users × nodes` 估算；`premium_usage_1_node` 检查同一统计周期复用快照。路由、API 代次、回退规则和 live 覆盖情况由生成器写入 [API 兼容目录](../architecture/remnawave-api-compatibility.md)。

停止环境但保留数据库：

```powershell
npm run dev:stand:down
```

只有确实需要删除这套上游本地数据库和初始数据时，才手动对同一 Compose 执行 `down -v`：

```powershell
docker compose --env-file .env.remnawave-dev `
  -f docker-compose-dev.yml `
  -f docker-compose.remnawave-dev.yml `
  --profile seed `
  down -v
```

## 服务地址

<a id="адреса-сервисов"></a>

开发环境默认主机端口为界面 **18082**、backend **18080**，由 Compose 和环境示例设置。并行环境可用 `FRONTEND_PORT`、`WEB_SERVER_PORT` 覆盖，但还需处理前述固定容器名。旧 `.env.remnawave-dev` 应更新这两个变量、`SUBSCRIPTION_MINI_APP_URL` 和 `WEBHOOK_BASE_URL`：

- Mini Shop 前端：`http://127.0.0.1:18082`。
- Mini Shop 后端健康检查：`http://127.0.0.1:18080/healthz`。
- Mini Shop PostgreSQL：`127.0.0.1:6768`。
- Remnawave Panel：`http://127.0.0.1:3000`。
- Remnawave 指标健康检查：`http://127.0.0.1:3001/health`。
- Remnawave Subscription Page 上游：`http://127.0.0.1:3010`。

浏览器直接使用 Subscription Page 需要 HTTPS 反向代理。这里 `127.0.0.1:3010` 只是本地上游，即使服务健康并连接面板，普通 HTTP 请求也可能返回空响应。

## 初始数据

<a id="сиды"></a>

通用 dev-stand 的 `seed` 配置执行两份幂等 SQL；项目 overlay 会替换为前述专用脚本：

- `deploy/dev/seed-minishop.sql`：Mini Shop 用户、订阅和支付。
- `deploy/dev/seed-remnawave.sql`：API 令牌、Remnawave 用户和 `Default-Squad` 绑定。

Remnawave 3.0 删除 `users.uuid`，将内部 `t_id` 改名为 `id`。脚本运行时识别结构：2.8.1 使用 UUID/`t_id`，3.x 使用 username/`id`；HWID 和流量初始数据沿用同一兼容路径。

上游测试账号：

| Telegram/user ID | 邮箱 | 状态 | HWID 设备 |
| --- | --- | --- | --- |
| `910000001` | `runes.admin@example.com` | 有效 standard 订阅、管理员 ID | 2 / 3 |
| `910000002` | `runes.active@example.com` | 有效 premium 订阅，接近流量上限 | 3 / 5 |
| `910000003` | `runes.expired@example.com` | 已到期订阅 | 1 / 1 |

三份基础账号共用上游公开测试密码 `Minishop-Dev-2026!`。模拟配置加载文档交互演示使用的同一匿名快照：370 个用户、257 份订阅、485 笔支付、1600 个事件、3 张工单及 28 条消息、8 个激活码和 2 个广告活动；另创建已完成、进行中和计划中的群发。上述账号级订阅与支付夹具不是项目隔离环境的业务初始数据。

快照日期按启动时间平移，使“今天／本周／本月”图表和筛选保持可用；计划群发设在 2099 年。Minishop 的 Telegram ID 被清空，通知被禁止，订阅不参与后台通知，邮箱使用保留域 `client.example`，避免查看和编辑夹具时给真实用户发送消息。

Minishop 与 Remnawave 初始数据来自 `frontend/src/lib/webapp/demoDataset.js`，可重新生成并检查：

```powershell
npm run dev:stand:generate:mocks
npm run check:dev-mocks
```

生成器使用原文档演示保留的 ID，通过 upsert 写入；重复运行不生成重复记录，也不删除保留区间外手工创建的数据。

重复运行初始数据脚本：

```powershell
docker compose --env-file .env.remnawave-dev `
  -f docker-compose-dev.yml `
  -f docker-compose.remnawave-dev.yml `
  --profile seed `
  run --rm dev-seed
```

覆盖层使用所选预设的专属数据卷，例如 `remnawave-minishop-runes-dev-db-data-280` 和 `remnawave-minishop-runes-dev-redis-data-280`，避免破坏旧本地环境或混用不同面板版本数据库。

## 环境冒烟检查

<a id="smoke-проверка-стенда"></a>

```powershell
curl.exe -fsS http://127.0.0.1:18080/healthz
curl.exe -fsS http://127.0.0.1:3001/health
curl.exe -I -fsS http://127.0.0.1:18082/

docker compose --env-file .env.remnawave-dev `
  -f docker-compose-dev.yml `
  -f docker-compose.remnawave-dev.yml `
  --profile seed `
  exec -T postgres psql -U remnawave_minishop -d remnawave_minishop `
  -c "select count(*) from users; select count(*) from subscriptions; select count(*) from payments;"

docker compose --env-file .env.remnawave-dev `
  -f docker-compose-dev.yml `
  -f docker-compose.remnawave-dev.yml `
  --profile seed `
  exec -T remnawave-db psql -U postgres -d postgres `
  -c "select uuid from api_tokens where uuid='30000000-0000-4000-8000-000000000001'; select username from users where username like 'runes_%' order by username;"
```

## 真实后端 QA 自动化

<a id="автоматизация-реальных-qa-сценариев"></a>

`tests/qa` 通过 `npm run qa:fullstack` 在统一环境运行。runes 计划的模拟冒烟测试只检查不带 backend 的静态演示；全栈 QA 则检查真实认证、CSRF、支付 webhook、后台保存及数据库状态。

上游场景包括：

- 通过 `/api/auth/email/request` 和 `/api/auth/email/verify` 完成邮箱认证。
- 携 CSRF 保护请求 `/api/account/language`。
- 通过 `/api/payments` 使用 `qa` 提供者创建支付。
- 经 HMAC webhook `/webhook/qa-payment` 调用真实 `finalize_successful_payment` 激活订阅。
- webhook 后检查 PostgreSQL 的 `payments` 与 `subscriptions`。
- 管理员登录，并通过 `/api/admin/settings` 保存 `SERVER_STATUS_URL`。
- 检查 Remnawave 健康及 Panel/Subscription Page 固定版本。

`.github/workflows/fullstack-qa.yml` 对 `main`、`dev` 的 `pull_request`、`push` 及手动 `workflow_dispatch` 触发。本派生仓库当前矩阵固定为 `3.4.5`，上文 current/maintenance 列表不是本仓库实际执行的多版本矩阵。

同库升级任务保留 `2.8.1 → 3.4.5`：更新现有数据卷上的面板，Core 同步初始用户，检查本地 UUID 别名转换为十进制数字 ID 而不丢订阅。当前工作流没有启用定时触发，该任务通过手动触发执行；源码中保留的 schedule 条件不等于已配置定时任务。失败时工作流上传 Docker Compose 日志。

## 模拟配置中的广告检查

<a id="проверка-рекламы-в-mock-профиле"></a>

`npm run dev:stand:up:mocks` 增加四个 **QA** 广告活动：Web/Mini App、导入、暂停、归档。使用本地公开测试账号 `runes.admin@example.com` / `Minishop-Dev-2026!` 登录，进入“广告”并打开 QA 活动，可查看链接、`ADS_QA_CHECKOUT`/`ADS_QA_WELCOME`、支出、线索、RUB/XTR 购买、退款及两个投放产生的歧义匹配。导入使用虚构广告账号和 bot ID `qa_bot`，不是真实 Telegram Ads 样本。

广告夹具只创建一次，重跑保留管理员修改，不调用支付提供者、订阅发放或奖励。需要从头复现时使用前述独立本地数据卷。
