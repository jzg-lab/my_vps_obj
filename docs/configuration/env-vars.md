# 环境变量

<a id="переменные-окружения"></a>

`.env` 主要用于启动配置：数据库访问、公开 URL 和固定密钥；仅启用 Telegram 时需要机器人令牌。首次登录后，大多数产品设置可在 Web App 管理后台修改，并以覆盖 `.env` 的形式保存在数据库中。

> 本参考保留 Minishop 上游的完整变量说明；列出支付、试用、礼品、余额或营销参数，不表示本项目当前 MVP 已启用这些功能。本项目采用管理员手动激活、无支付及一个账号管理多个独立服务的方案。当前范围见[需求文档](../requirements.md)，开发和验收使用[项目隔离开发环境](../development/project-local.md)。

上游完整功能的推荐配置顺序：

1. 根据 `.env.example` 填写最小 `.env`。
2. 启动服务栈，验证邮箱，并通过[独立运行模式指南](../features/telegram-optional.md)中的服务器命令指定首位所有者。
3. 通过管理后台配置 Remnawave、支付、外观、支持、通知和套餐；本项目 MVP 不执行支付启用步骤。

## 参考目录

<a id="навигация-по-справочнику"></a>

| 类别 | 章节 |
| --- | --- |
| 启动与基础设施 | [最小启动配置](#минимальный-bootstrap) · [基础设施与 Compose](#инфраструктура-и-compose) · [开发与质量检查](#разработка-и-проверка-качества) · [缓存、限流与 worker](#кеши-rate-limits-и-worker) |
| 产品 | [常规设置](#общие-настройки) · [Remnawave](#remnawave) · [Web App 与外观](#веб-приложение-внешний-вид-и-telegram-login) · [SMTP 与邮箱登录](#smtp-и-вход-по-email) |
| 销售 | [支付](#платежи) · [套餐与旧版定价](#тарифы-и-legacy-цены) · [优惠码](#промокоды) · [试用、邀请返利与通知](#пробный-период-рефералы-и-уведомления) |
| 运维 | [支持](#поддержка) · [日志](#логирование) · [收据、连接链接与内联功能](#чеки-ссылки-подключения-и-inline) |

各支付渠道的操作说明见[支付 → 支付渠道](../features/payments.md#платёжные-провайдеры)。

## 最小启动配置

<a id="минимальный-bootstrap"></a>

| 变量 | 修改位置 | 用途 |
| --- | --- | --- |
| `TELEGRAM_ENABLED` | 仅 `.env` | 启用 Telegram 适配器。浏览器模式设为 `False`；为兼容旧安装，默认 `True`。 |
| `BOT_TOKEN` | 仅 `.env` | Telegram 机器人令牌，仅在 `TELEGRAM_ENABLED=True` 时必填。 |
| `TELEGRAM_BOT_PROXY_URL` | 仅 `.env` | `backend` 和 `worker` 的 Telegram Bot API 出站请求使用的可选 SOCKS5 代理；也可供服务端 OAuth 使用。 |
| `TELEGRAM_BOT_API_BASE_URL` | 仅 `.env` | `backend` 和 `worker` 使用的自建 Local Bot API HTTP(S) 端点，可选。 |
| `TELEGRAM_OAUTH_USE_BOT_PROXY` | 仅 `.env` | 允许服务端 Telegram OAuth 请求使用 `TELEGRAM_BOT_PROXY_URL`。默认 `True`；未设置 URL 时仍直连。 |
| `ADMIN_IDS` | 仅 `.env` | 按已保存的 Telegram 身份一次性导入旧管理员，可选；后续权限作为账号角色保存。 |
| `WEBHOOK_BASE_URL` | `.env` | backend/webhook 域名的公开 URL，用于 Telegram、支付渠道及 Remnawave 的 webhook URL。 |
| `POSTGRES_USER` | `.env` / Compose | PostgreSQL 用户。 |
| `POSTGRES_PASSWORD` | `.env` / Compose | PostgreSQL 密码。 |
| `POSTGRES_DB` | `.env` / Compose | PostgreSQL 数据库名称。 |
| `WEBAPP_ENABLED` | `.env` / 管理后台 | 启用 Web App 和管理后台。首次启动保持 `True`；关闭后只能通过 `.env` 和重启恢复访问。 |
| `WEBAPP_SESSION_SECRET` | `.env` | Web App 会话的固定 HMAC 密钥。留空则按进程生成，但重启后会话会重置。 |
| `EMAIL_AUTH_SECRET` | `.env` | 邮箱验证码和免密登录链接独立使用的固定密钥。未设置时使用 `WEBAPP_SESSION_SECRET`。 |
| `PUBLIC_APP_URL` | `.env` | 浏览器用户中心的公开地址，用于邮件链接和付款后返回。 |
| `WEBHOOK_SECRET_TOKEN` | `.env` | Telegram webhook 密钥。留空则按进程生成。 |

### Telegram Bot API 的 SOCKS5 代理

<a id="socks5-proxy-для-telegram-bot-api"></a>

未设置代理时，Telegram Bot API 和服务端 Telegram OAuth 均直连。
让 `backend` 和 `worker` 的 `aiogram.Bot` 出站请求使用同一 SOCKS5 端点：

```dotenv
TELEGRAM_BOT_PROXY_URL=socks5://proxy.example.com:1080
```

需要认证时：

```dotenv
TELEGRAM_BOT_PROXY_URL=socks5://username:password@proxy.example.com:1080
```

用户名与密码必须成对设置。凭据中的特殊字符必须经过百分号编码，例如
`user@example.com` 写为 `user%40example.com`，`p:a/ss` 写为 `p%3Aa%2Fss`。
必须包含主机名及 `1..65535` 范围内的端口；IPv6 地址使用方括号：
`socks5://[2001:db8::10]:1080`。

仅支持 `socks5://`。不支持 `socks5h://`、SOCKS4、HTTP/HTTPS 代理、代理链，
也不支持 `PROXY_URL`、`ALL_PROXY`、`HTTPS_PROXY` 别名。留空或未设置时保持直连。

所有出站 Bot API 方法都会经过代理，包括 `get_me`、`get_webhook_info`、
`set_webhook`、消息、文件和 worker 通知。默认情况下，服务端 Telegram OAuth
的令牌交换和 JWKS 下载也自动使用同一路径。若只让 OAuth 保持直连，显式设置：

```dotenv
TELEGRAM_OAUTH_USE_BOT_PROXY=False
```

默认 `True` 时，`backend` 通过 SOCKS5 请求 `POST https://oauth.telegram.org/token`
和 `https://oauth.telegram.org/.well-known/jwks.json`。TLS 仍端到端连接 Telegram，
DNS 名称在 SOCKS5 代理端解析。未设置代理 URL 时，`True` 会安全地保留直连。

以下流量不使用该代理：

- Telegram 向 `WEBHOOK_BASE_URL` 投递的入站 webhook。
- 用户浏览器打开 `https://oauth.telegram.org/auth` 的请求；服务器不控制浏览器的网络路径。
- Remnawave Panel、支付渠道、SMTP 及其他 HTTP 客户端。

Webhook 模式仍需要 Telegram 可访问的公开 HTTPS 端点。
SOCKS5 只改变 Bot API，以及未显式禁用代理时的服务端 OAuth 出站路径。

代理必须能从 `backend` 和 `worker` 两个容器访问。容器中的 `127.0.0.1`
指向容器自身，不是 Docker 宿主机。代理也在容器中时，使用其 Compose 服务名和共同网络；
外部代理则使用容器可访问的 DNS/IP。

修改后重建两个进程所在的容器：

```bash
docker compose up -d --force-recreate backend worker
docker compose logs --tail=100 backend worker
```

启动日志只显示脱敏后的端点。排障时不要公开 `.env` 或完整代理 URL。
仅修改 `TELEGRAM_OAUTH_USE_BOT_PROXY` 时，重建 `backend` 即可；
修改 URL 或 Bot API 路径时，需要重建 `backend` 和 `worker`。
让 OAuth 完全回退为直连时，设置 `TELEGRAM_OAUTH_USE_BOT_PROXY=False` 并重建 `backend`。
让全部 Telegram 请求恢复直连时，删除或清空 `TELEGRAM_BOT_PROXY_URL`，
并重建 `backend` 和 `worker`。

### 本地 Telegram Bot API 服务器

<a id="локальный-сервер-telegram-bot-api"></a>

通过自建 Telegram Bot API 服务器发送大文件时，设置其基础 URL：

```dotenv
TELEGRAM_BOT_API_BASE_URL=http://telegram-bot-api:8081
```

Minishop 会为 `backend` 和 `worker` 的所有 Bot API 调用启用 aiogram 本地模式。
服务器需单独启动并授权，其 URL 必须能从两个容器访问。
URL 不支持查询参数、片段或凭据；Compose 服务应使用 DNS 名称，而非 `127.0.0.1`。
删除该变量即可恢复官方 Telegram Bot API。

修改后重建两个进程所在的容器：

```bash
docker compose up -d --force-recreate backend worker
```

## 基础设施与 Compose

<a id="инфраструктура-и-compose"></a>

| 变量 | 修改位置 | 用途 |
| --- | --- | --- |
| `DEPLOYMENT_PROFILE` | 安装向导 | 所选方案的信息标记（`caddy`、`angie`、`nginx`、`newt`、`no-proxy`、`egames`）。`egames` 让后续仅迁移运行知道应复用现有 `eGamesAPI/remnawave-reverse-proxy` Nginx。 |
| `APP_ENV_FILE` | CLI/Compose | 替代 `.env` 的环境文件路径。 |
| `IMAGE_TAG` | CLI/Compose | Docker 镜像标签。 |
| `FRONTEND_PORT` | `.env` / Compose | 前端 nginx 的宿主机端口，默认 `8082`。 |
| `WEB_SERVER_HOST` | `.env` | backend webhook 服务的内部监听地址，通常为 `0.0.0.0`。 |
| `WEB_SERVER_PORT` | `.env` / Compose | backend webhook 服务的宿主机端口，默认 `8080`。 |
| `WEB_SERVER_INTERNAL_PORT` | `.env` / 容器 | backend 内部监听端口。Compose 固定为 `8080`；直接启动且未设置时使用 `WEB_SERVER_PORT`。 |
| `WEBAPP_SERVER_HOST` | `.env` | Web App API 服务的内部监听地址，通常为 `0.0.0.0`。 |
| `WEBAPP_SERVER_PORT` | `.env` | Web App API 服务的内部端口，默认 `8081`。 |
| `WEBAPP_API_BASE_URL` | `.env` / frontend | Mini App 前端向浏览器公开的 API 基础路径。保持 `/api`；前后端分离通过服务端 `WEBAPP_BACKEND_UPSTREAM` 配置。 |
| `WEBAPP_BACKEND_UPSTREAM` | frontend 环境变量 | 前端 nginx 转发 `/api`、`/auth`、`/open-app` 和 Web App 资源的目标。默认 `http://backend:8081`；分离部署可指定受保护后端上游、私有 IP/VPN 或 `http://rathole-server:18081`。 |
| `WEBAPP_BACKEND_UPSTREAM_HOST` | frontend 环境变量 | 上游 Host/SNI 覆盖值，例如 `WEBAPP_BACKEND_UPSTREAM=https://bot.example.com` 时填写 `bot.example.com`。 |
| `MINISHOP_EDGE_TOKEN` | backend/frontend 代理环境变量 | 保护 WebApp API 端口 `8081` 的可选服务端令牌。由前端 nginx/API 边缘代理添加，不发送给浏览器。 |
| `MINISHOP_EDGE_TOKEN_HEADER` | backend/frontend 代理环境变量 | 边缘代理令牌的请求头名称，默认 `X-Minishop-Edge-Token`。 |
| `FRONTEND_BACKEND_MODE` | 安装向导 | 前后端连接模式的信息标记：`same-origin`、`protected-upstream` 或 `rathole`。 |
| `INSTALL_NODE_ROLE` | 安装向导 | 当前服务器角色：`full-stack`、`backend-node` 或 `frontend-node`。 |
| `WEBAPP_SERVER_BIND` | 分离部署的后端节点 | 需要回环或私有宿主机上游时，WebApp API 端口 `8081` 的宿主机绑定地址。没有防火墙或令牌保护时，不要绑定到 `0.0.0.0`。 |
| `RATHOLE_IMAGE` | Rathole Compose | Rathole 镜像，默认 `rapiz1/rathole:v0.5.0`，可为其他架构覆盖。 |
| `RATHOLE_CONTROL_BIND` | Rathole 前端节点 | Rathole 服务端公开的控制端口，例如 `0.0.0.0:2333`。 |
| `RATHOLE_CONTROL_REMOTE` | Rathole 后端节点 | 后端客户端连接的前端 Rathole 控制端口地址。 |
| `RATHOLE_SERVICE_TOKEN` | Rathole 两端 | WebApp API 隧道必需的服务令牌，前后端服务器必须一致。 |
| `RATHOLE_SERVICE_PORT` | Rathole 前端节点 | Rathole 服务端供前端 nginx 使用的内部服务端口，默认 `18081`。 |
| `POSTGRES_HOST` | Compose | PostgreSQL 主机，标准 Compose 设置为 `postgres`。 |
| `POSTGRES_PORT` | `.env` | PostgreSQL 端口。 |
| `DB_POOL_SIZE` | `.env` | 异步 SQLAlchemy 连接池大小。 |
| `DB_MAX_OVERFLOW` | `.env` | 超出连接池大小后允许创建的额外临时数据库连接数。 |
| `DB_POOL_TIMEOUT_SECONDS` | `.env` | 等待连接池连接的超时时间。 |
| `DB_POOL_RECYCLE_SECONDS` | `.env` | 数据库连接回收周期。 |
| `REDIS_URL` | Compose | 用于 FSM、缓存、限流、队列和锁的 Redis；Compose 自动设置。 |
| `REDIS_KEY_PREFIX` | `.env` | Redis 键前缀。 |
| `TRUSTED_PROXIES` | `.env` | 受信任反向代理的 IP/CIDR 或 `host:服务名`。默认信任回环地址及 frontend、Caddy、Nginx、Angie、Newt、`newt-2` 服务；忽略不存在的服务。额外代理需将地址或名称加入[安全设置](security.md)中的标准列表。 |
| `HTTP_BIND` / `HTTPS_BIND` | Caddy/Angie Compose | Caddy 和 Angie 方案公开服务的绑定地址。 |
| `NEWT_ID` / `NEWT_SECRET` | 开发 Compose | 开发 Compose 中的 Newt 凭据。 |
| `DEV_POSTGRES_PORT` | 开发 Compose | 统一开发环境中供全栈 QA 使用的 PostgreSQL 宿主机端口，默认 `6768`。 |

## 开发与质量检查

<a id="разработка-и-проверка-качества"></a>

这些变量用于本地开发环境和 CI 全栈 QA。不要在生产 `.env` 中启用。

| 变量 | 用途 |
| --- | --- |
| `QA_AUTH_ENABLED` | 在 `APP_RUNTIME_MODE=development\|test` 时，将一次性邮箱验证码返回在 `/api/auth/email/request` 响应中，让 QA 无需 SMTP 即可完成常规验证。 |
| `QA_PAYMENT_ENABLED` | 在开发／测试运行环境中，为 Mini App 支付启用本地 `qa` 渠道。 |
| `QA_PAYMENT_ADMIN_ONLY_ENABLED` | 仅允许管理员使用 `qa` 渠道。开发环境通常为 `False`。 |
| `QA_PAYMENT_SECRET` | `/webhook/qa-payment` 的 HMAC 密钥；测试通过 `X-QA-Payment-Signature` 对载荷签名。 |

`TRUSTED_PROXIES` 不只用于日志：启用 IP 过滤的支付 webhook 处理器，会将处理
`X-Forwarded-For` 后的客户端 IP 与渠道白名单比较。外部代理未传递该请求头，
或其 IP 不在 `TRUSTED_PROXIES` 中时，backend 看到的是代理／Docker 网关 IP，
可能拒绝合法 webhook。`deploy/examples` 中的 Caddy/Angie/Nginx/Newt 使用默认值即可；
自定义基础设施需添加代理 CIDR，或缩小为具体代理 IP。webhook 域名经 Cloudflare 代理时，
只有最近的不受信任跳点属于 Cloudflare 官方网络，backend 才安全地使用 `CF-Connecting-IP`；
无需将 Cloudflare 网络加入 `TRUSTED_PROXIES`。
全信任配置为 `0.0.0.0/0,::/0`，但只有 backend 无法被直接访问、
且外部代理会清理入站 `X-Forwarded-For` 时才安全。

## 缓存、限流与 worker

<a id="кеши-rate-limits-и-worker"></a>

这些值通常无需修改。

`BACKUP_*` 控制自动备份和恢复。实际操作、Compose 目录挂载和归档检查见[备份章节](../features/backups.md)。

| 变量 | 用途 |
| --- | --- |
| `WEBAPP_ME_CACHE_TTL_SECONDS` | `/api/me` 缓存的 TTL。 |
| `WEBAPP_DEVICES_CACHE_TTL_SECONDS` | Web App 设备缓存的 TTL。 |
| `PANEL_USER_CACHE_TTL_SECONDS` | Remnawave `/users/{uuid}` 缓存的 TTL。 |
| `PANEL_DEVICES_CACHE_TTL_SECONDS` | Remnawave 用户设备缓存的 TTL。 |
| `PANEL_ALL_USERS_CACHE_TTL_SECONDS` | Remnawave 全量用户扫描缓存的 TTL。 |
| `PANEL_ALL_USERS_PAGE_SIZE` | Remnawave `/users` 的分页大小。 |
| `PANEL_ALL_USERS_PAGE_DELAY_SECONDS` | 全量扫描 `/users` 时的页间等待，默认 `0.1`。大型面板（10 万以上用户）每次同步可能因此等待数十秒；面板能承受更频繁请求时，可降低或设为 `0`。 |
| `PANEL_API_TOTAL_TIMEOUT_SECONDS` | Remnawave API 请求总超时。 |
| `PANEL_API_CONNECT_TIMEOUT_SECONDS` | 获取 Remnawave API 连接的超时。 |
| `PANEL_API_SOCK_CONNECT_TIMEOUT_SECONDS` | 建立 Remnawave API TCP/TLS 连接的超时。 |
| `PANEL_API_SOCK_READ_TIMEOUT_SECONDS` | 等待 Remnawave API 响应数据的超时。 |
| `ADMIN_PANEL_STATS_CACHE_TTL_SECONDS` | 管理后台 Remnawave 统计缓存的 TTL。 |
| `ADMIN_DB_STATS_CACHE_TTL_SECONDS` | 管理后台高开销数据库聚合结果缓存的 TTL。 |
| `ADMIN_USERS_LIST_CACHE_TTL_SECONDS` | 管理后台用户列表缓存的 TTL。 |
| `ADMIN_BROADCAST_AUDIENCE_COUNTS_CACHE_TTL_SECONDS` | 管理后台群发目标群体计数缓存的 TTL。 |
| `PROFILE_SYNC_CACHE_TTL_SECONDS` | 用户 Telegram 资料同步的最小间隔。 |
| `PANEL_SYNC_LIFETIME_TRAFFIC_MIN_INTERVAL_SECONDS` | 累计总流量写入的最小间隔。 |
| `PANEL_SYNC_LIFETIME_TRAFFIC_MIN_DELTA_BYTES` | 触发提前写入的累计总流量增量。 |
| `WEBAPP_RATE_LIMIT_TTL_SECONDS` | Web App 限流窗口。 |
| `WEBAPP_RATE_LIMIT_MAX_REQUESTS` | 限流窗口内允许的请求数。 |

操作额度按用户和 IP 分别生效，IP 额度为用户额度的四倍。
所有 `/api/` 还受总体上限约束：用户额度的四倍、IP 额度的八倍。
代码验证、应用、金额计算及支付创建共用一份额度，包括礼品流程。
套餐切换和支付状态轮询在访问数据库前使用各自独立的额度。
触发限流返回 `429` 和 `Retry-After`。已配置但不可用的 Redis 会返回带 `Retry-After`
的 `503`，不会悄悄切换到各进程独立的计数器。未设置 `REDIS_URL` 时，
可使用有内存上限的单进程本地模式；多进程必须使用 Redis。

| 变量 | 用途 |
| --- | --- |
| `TELEGRAM_DROP_NON_PRIVATE_UPDATES` | 在访问数据库的中间件之前丢弃群组／频道 Telegram 更新，默认 `True`。 |
| `TELEGRAM_ANTIFLOOD_ENABLED` | 对异常 Telegram 刷屏启用宽松的按用户、按聊天限流，默认 `True`。 |
| `TELEGRAM_ANTIFLOOD_WINDOW_SECONDS` | Telegram 防刷限流窗口，默认 `60`。 |
| `TELEGRAM_ANTIFLOOD_MAX_UPDATES_PER_WINDOW` | 每个来源在一个窗口内的 Telegram 更新总上限，默认 `180`；`0` 关闭该限额。 |
| `TELEGRAM_ANTIFLOOD_MESSAGE_MAX_PER_WINDOW` | 每个来源的消息上限，默认 `120`；`0` 关闭该限额。 |
| `TELEGRAM_ANTIFLOOD_CALLBACK_MAX_PER_WINDOW` | 每个来源的回调查询上限，默认 `240`；`0` 关闭该限额。 |
| `TELEGRAM_ANTIFLOOD_INLINE_MAX_PER_WINDOW` | 每个来源的内联查询上限，默认 `60`；`0` 关闭该限额。 |
| `TELEGRAM_ANTIFLOOD_START_MAX_PER_WINDOW` | 每个来源的 `/start` 上限，默认 `30`；`0` 关闭该限额。 |
| `TELEGRAM_ANTIFLOOD_EXPENSIVE_CALLBACK_MAX_PER_WINDOW` | 每个窗口内支付、试用、优惠及账号变更回调的上限，默认 `60`；`0` 关闭该限额。 |
| `TELEGRAM_ACTION_COOLDOWN_ENABLED` | 去除同一用户完全重复的支付和试用回调，默认 `True`。 |
| `TELEGRAM_PAYMENT_CALLBACK_COOLDOWN_SECONDS` | 完全重复的支付回调冷却时间，默认 `20`；`0` 关闭冷却。 |
| `TELEGRAM_TRIAL_CALLBACK_COOLDOWN_SECONDS` | 完全重复的试用回调冷却时间，默认 `30`；`0` 关闭冷却。 |
| `WEBHOOK_QUEUE_NAME` | 高开销 webhook 处理使用的 Redis 队列。 |
| `WEBHOOK_QUEUE_CONCURRENCY` | webhook 队列的 worker 消费者数量。 |
| `WEBHOOK_QUEUE_MAX_ATTEMPTS` | webhook 转入死信队列前的最大处理次数，默认 `5`。 |
| `WEBHOOK_QUEUE_RETRY_BASE_SECONDS` | webhook 指数退避重试的初始延迟，默认 `1`。 |
| `WEBHOOK_QUEUE_RETRY_MAX_SECONDS` | webhook 重试之间的最大延迟，默认 `30`。 |
| `WORKER_PANEL_SYNC_INTERVAL_SECONDS` | 后台面板同步间隔。 |
| `TARIFF_WORKER_LOCK_TTL_SECONDS` | 套餐 worker 的 Redis 锁 TTL。 |
| `TARIFF_WORKER_TICK_SECONDS` | 套餐 worker 执行间隔。 |
| `TARIFF_WORKER_BULK_PANEL_FETCH_THRESHOLD` | 触发批量获取面板用户的活跃订阅数阈值。 |
| `TARIFF_PREMIUM_FAST_TICK_SECONDS` | 套餐 worker 两次完整执行之间快速检查高级流量限额的间隔，默认 `60`；设为 `0` 或不小于 `TARIFF_WORKER_TICK_SECONDS` 的值会关闭快速检查。 |
| `TARIFF_PREMIUM_FAST_WATCH_PERCENT` | 订阅进入快速检查时的高级流量已用百分比，默认 `80`。 |
| `TARIFF_PREMIUM_FAST_BATCH_LIMIT` | 每次快速检查的订阅数量上限，默认 `200`；`0` 表示不限。 |
| `TARIFF_PREMIUM_DROP_CONNECTIONS` | 高级流量耗尽后断开高级节点上的现有会话。Core 自动选择兼容路径：Remnawave 2.8.1 使用 `POST /api/ip-control/drop-connections`，3.x 使用 `POST /api/connections/drop`。默认 `True`，要求 Remnawave 节点具有 `CAP_NET_ADMIN`。 |
| `TARIFF_PREMIUM_DROP_CONNECTIONS_COOLDOWN_SECONDS` | 同一订阅两次断开会话的最小间隔，默认 `300`。 |
| `BACKUP_ENABLED` | 在 worker 容器中启用定期备份，默认 `False`。 |
| `BACKUP_INTERVAL_SECONDS` | 备份间隔，默认 `3600`；执行时间对齐整点，如 12:00、13:00。 |
| `BACKUP_CHAT_ID` | 接收归档的 Telegram 聊天 ID。留空则使用 `LOG_CHAT_ID`。 |
| `BACKUP_THREAD_ID` | 接收归档的话题／线程 ID。留空则使用 `LOG_THREAD_ID`。 |
| `BACKUP_DIR` | 容器内保存归档的本地目录，默认数据卷 `shop-data` 中的 `data/backups`。 |
| `BACKUP_LOCAL_RETENTION` | 发送后保留的本地 ZIP 归档数量，默认 `100`。 |
| `BACKUP_POSTGRES_DUMP_ENABLED` | 将 PostgreSQL 的 `pg_dump` 加入归档。 |
| `BACKUP_PG_DUMP_PATH` | worker 容器内的 `pg_dump` 路径。 |
| `BACKUP_PG_DUMP_TIMEOUT_SECONDS` | `pg_dump` 执行超时。 |
| `BACKUP_PG_RESTORE_PATH` | backend 容器内的 `pg_restore` 路径，用于管理后台恢复。 |
| `BACKUP_PG_RESTORE_TIMEOUT_SECONDS` | `pg_restore` 执行超时。 |
| `BACKUP_COMPOSE_ENABLED` | 将 Compose 目录快照加入归档。缺少挂载时不会导致数据库备份失败。 |
| `BACKUP_COMPOSE_SOURCE_DIR` | 容器内的 Compose 目录路径，标准 Compose 为 `/app/compose-source`。 |
| `BACKUP_COMPOSE_RESTORE_DIR` | Compose 文件恢复位置。留空则使用 `BACKUP_COMPOSE_SOURCE_DIR`。 |
| `BACKUP_COMPOSE_EXCLUDE_DIRS` | 不包含在 Compose 快照中的目录名称。 |
| `COMPOSE_BACKUP_SOURCE` | Docker Compose 挂载为 `/app/compose-source` 的宿主机路径，默认当前 Compose 文件所在目录。 |
| `COMPOSE_RESTORE_MODE` | backend 的挂载模式：`rw` 允许从管理后台恢复 Compose 目录，`ro` 为只读。 |

## 常规设置

<a id="общие-настройки"></a>

这些字段位于管理后台的**系统 → 设置**。

| 变量 | 用途 |
| --- | --- |
| `DEFAULT_LANGUAGE` | 默认语言。上游默认为 `ru`，原有语言包含 `ru` 和 `en`；本项目的简体中文语言代码为 `zh-hans`。 |
| `DEFAULT_CURRENCY_SYMBOL` | 界面中的货币符号或代码。 |
| `SUPPORT_LINK` | 外部 HTTP(S) 支持链接；Telegram 的 `@username` 和 `t.me/username` 会自动规范为 `https://t.me/username`。 |
| `SERVER_STATUS_URL` | 数据源为 `url` 时使用的外部状态页面。 |
| `PRIVACY_POLICY_URL` | 隐私政策的外部备用链接。当**系统 → 文档**中尚无角色为 `privacy_policy` 的非空文档时使用；不在管理后台常规设置中显示。 |
| `USER_AGREEMENT_URL` | 用户协议的外部备用链接。当**系统 → 文档**中尚无角色为 `user_agreement` 的非空文档时使用；不在管理后台常规设置中显示。 |
| `MENU_BUTTONS_JSON` | 本地化自定义按钮的 JSON 数组。Markdown 页面使用 `kind: "page"` 和绝对 `target`；托管文档 URL 为 `/<slug>`，系统根路径被占用时为 `/docs/<slug>`。存储和路由说明见 [Web App](../features/web-app.md#документы-и-markdown-страницы)。 |
| `REQUIRED_CHANNEL_ID` | 必须加入的 Telegram 频道 ID，用于检查订阅状态；机器人可访问频道时，也用于自动获取按钮链接。 |
| `REQUIRED_CHANNEL_LINK` | 无法通过 ID 获取链接时，使用的可选频道备用链接（`@username` 或邀请链接）。 |
| `START_COMMAND_DESCRIPTION` | Telegram 菜单中 `/start` 的说明。 |
| `DISABLE_WELCOME_MESSAGE` | 禁用 `/start` 欢迎消息。 |
| `REGISTRATION_INVITE_ONLY_ENABLED` | 默认 `False`。开启后，新的公开注册必须使用有效邀请链接；已有用户仍可通过 Telegram、Web App、邮箱验证码、免密链接或密码登录。 |

### 服务器状态

<a id="статус-серверов"></a>

默认关闭，只能选择一个数据源，不支持 `both`。
Uptime Kuma、xray-checker、缓存及排障配置见[专门指南](../features/server-status.md)。

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `SERVER_STATUS_ENABLED` | `False` | 启用 Web App 服务器状态页面。 |
| `SERVER_STATUS_SHOW_ON_HOME` | `False` | 额外在首页显示状态卡片；设置中的入口不受此开关影响。 |
| `SERVER_STATUS_PROVIDER` | `url` | 数据源：`url`、`uptime-kuma` 或 `xray-checker`。 |
| `SERVER_STATUS_URL` | 空 | `url` 数据源的外部页面；内置数据源不使用此值。 |
| `SERVER_STATUS_KUMA_URL` | 空 | 已发布的 Uptime Kuma 状态页完整 URL，例如 `https://status.example.com/status/default`。允许在 `/status/` 前添加反向代理路径前缀，例如 `/kuma/status/default`；禁止查询参数、片段和凭据。 |
| `SERVER_STATUS_XRAY_CHECKER_URL` | 空 | 不含 API 路径的 xray-checker 基础 URL；对于 `https://checker.example.com/api/v1/public/proxies`，填写 `https://checker.example.com`。 |
| `SERVER_STATUS_CACHE_TTL_SECONDS` | `30` | 内置数据源成功响应的缓存时间。 |
| `SERVER_STATUS_STALE_TTL_SECONDS` | `300` | 数据源出错时，继续提供最近一次成功响应的最长时间。 |
| `SERVER_STATUS_TIMEOUT_SECONDS` | `5` | 外部 HTTP 请求的最大等待秒数。 |

## Remnawave

这些字段建议保存在 `.env` 中作为面板集成的基础配置。管理后台也提供这些设置，便于快速修正访问凭据或临时覆盖，无需手动编辑文件和重启。

| 变量 | 用途 |
| --- | --- |
| `PANEL_API_URL` | backend 和 worker 请求使用的 API URL，例如共同 Docker 网络中的 `http://remnawave:3000/api`，或 `https://panel.example.com/api`。 |
| `PANEL_PUBLIC_URL` | 管理员浏览器访问面板的地址，例如 `https://panel.example.com`。用于 Remnawave 3.x 用户详情链接，允许路径前缀和 `/api` 后缀。留空则为兼容现有安装，从 `PANEL_API_URL` 生成链接。 |
| `PANEL_API_KEY` | 面板 API 密钥。 |
| `PANEL_API_COOKIE` | 受 `eGamesAPI/remnawave-reverse-proxy` 保护的面板所需的可选 Cookie 请求头内容（`name=value`）。安装向导也接受 `Cookie:`/`Set-Cookie:` 行，或仅含一组查询参数的完整 eGames 访问 URL，并保存规范值。Cookie 不能替代 `PANEL_API_KEY`。 |
| `APP_RUNTIME_MODE` | 运行模式：`production`、`development`、`staging`、`test`。 |
| `PANEL_WRITE_MODE` | `auto`、`live` 或 `dry_run`。`dry_run` 读取实际 Remnawave Panel，但用户变更只验证并记录日志。`auto` 在 `development`/`test` 中启用 dry-run，生产环境仍使用 live。 |
| `PANEL_DRY_RUN_VALIDATE_REMOTE` | dry-run 时，通过实际 `GET` 检查面板用户和 Internal Squads 引用。 |
| `PANEL_DRY_RUN_SYNTHETIC_CREATE` | dry-run 尝试 `POST /users` 时返回模拟面板用户，让开发流程可在本地数据库中完成。 |
| `PANEL_WEBHOOK_SECRET` | Remnawave webhook 验证密钥。在 Remnawave Panel 设置后，将同一值填入此处或管理后台。 |
| `USER_SQUAD_UUIDS` | 未使用 JSON 目录的旧版模式下，默认 Internal Squads。 |
| `USER_EXTERNAL_SQUAD_UUID` | 可选 External Squad。 |
| `USER_TRAFFIC_LIMIT_GB` | 旧版用户流量限额。 |
| `USER_TRAFFIC_STRATEGY` | 旧版流量限额策略。 |
| `USER_HWID_DEVICE_LIMIT` | 旧版默认 HWID 设备数量限制。 |
| `HWID_DEVICE_TRAFFIC_BONUS_GB` | 对早于套餐包赠送量快照机制创建、且仍有效的 HWID 加购项提供旧版备用值。新赠送量在 `tariffs[].hwid_device_packages` 的 `traffic_bonus_gb` 中配置；管理后台隐藏全局字段。 |

面板位于共同 Docker 网络时，可设置 `PANEL_API_URL=http://remnawave:3000/api`
和 `PANEL_PUBLIC_URL=https://panel.example.com`。backend 和 worker 容器必须可访问内部地址。
公开 URL 不改变 API 密钥、Cookie、webhook 或面板返回的订阅地址；
eGames 访问参数仍保存在 `PANEL_API_COOKIE`。

安装向导分别建议两个地址：内部 API 来源于当前 `.env`、Remnashop/Bedolaga 或
Remnawave 配置；浏览器地址来源于面板的 `FRONT_END_DOMAIN` / `REMNAWAVE_PANEL_URL`，
或旧机器人的公开 API 地址。Docker 服务名和私有 API 地址不会自动填为公开 URL。
重新配置或迁移 Bedolaga 时，已设置的 `PANEL_PUBLIC_URL` 会保留。

Remnawave Panel 的 `WEBHOOK_URL` 应指向公开 Minishop webhook，即 `WEBHOOK_BASE_URL` 加 `/webhook/panel`。例如应用公开域名为 `https://app.example.com` 时，最终地址为 `https://app.example.com/webhook/panel`。

### 用户通知渠道

<a id="каналы-пользовательских-уведомлений"></a>

**系统 → 设置 → 通知 → 用户通知投递**中提供自动通知矩阵，
每个类别可分别选择 Telegram 和邮箱。某类别两个渠道均关闭时，不发送该类别通知。

启用 `USER_NOTIFICATION_SINGLE_CHANNEL_FALLBACK_ENABLED` 后，如果所选渠道对用户不可用，
可改用用户唯一的其他可用渠道。例如类别仅选择 Telegram，但用户只有邮箱时，会改发邮件。
所选渠道可用时，不会向已关闭的渠道重复投递。临时发送错误不视为渠道不可用，
也不会触发备用渠道。

| 变量 | 用途 |
| --- | --- |
| `USER_NOTIFICATION_PREFERENCES_ENABLED` | 允许用户在用户中心和邮件链接页面管理通知渠道，默认 `True`。 |
| `USER_NOTIFICATION_SINGLE_CHANNEL_FALLBACK_ENABLED` | 所选渠道对用户不可用时，使用唯一的其他已绑定渠道，默认 `True`。 |
| `USER_NOTIFICATION_PAYMENTS_TELEGRAM_ENABLED`, `USER_NOTIFICATION_PAYMENTS_EMAIL_ENABLED` | 支付成功和失败通知的渠道。 |
| `SUBSCRIPTION_NOTIFICATIONS_ENABLED`, `SUBSCRIPTION_EMAIL_NOTIFICATIONS_ENABLED` | 订阅生命周期通知的 Telegram 和邮箱渠道。 |
| `USER_NOTIFICATION_TRAFFIC_TELEGRAM_ENABLED`, `USER_NOTIFICATION_TRAFFIC_EMAIL_ENABLED` | 流量预警、耗尽和重置通知的渠道。 |
| `USER_NOTIFICATION_DEVICES_TELEGRAM_ENABLED`, `USER_NOTIFICATION_DEVICES_EMAIL_ENABLED` | HWID 设备购买和续期通知的渠道。 |
| `USER_NOTIFICATION_DEVICE_ACTIVITY_TELEGRAM_ENABLED`, `USER_NOTIFICATION_DEVICE_ACTIVITY_EMAIL_ENABLED` | `user_hwid_devices.added` webhook 触发的新增 HWID 设备通知渠道。 |
| `USER_NOTIFICATION_DEVICE_LIMIT_TELEGRAM_ENABLED`, `USER_NOTIFICATION_DEVICE_LIMIT_EMAIL_ENABLED` | 最后一个 HWID 设备名额被占用时的通知渠道。 |
| `TORRENT_BLOCKER_TELEGRAM_NOTIFICATIONS_ENABLED`, `TORRENT_BLOCKER_EMAIL_NOTIFICATIONS_ENABLED` | Torrent Blocker 限制通知的渠道；总启用开关仍独立控制。 |
| `USER_NOTIFICATION_SUPPORT_TELEGRAM_ENABLED`, `USER_NOTIFICATION_SUPPORT_EMAIL_ENABLED` | 用户工单回复和状态变化通知的渠道。 |
| `USER_NOTIFICATION_REFERRALS_TELEGRAM_ENABLED`, `USER_NOTIFICATION_REFERRALS_EMAIL_ENABLED` | 邀请返利通知的渠道。 |

### Torrent Blocker 通知

<a id="уведомления-torrent-blocker"></a>

对于 Remnawave Panel 2.7+，Minishop 通过同一个带签名的 `/webhook/panel`
接收 `torrent_blocker.report` 事件。该功能默认关闭，在
**系统 → 设置 → 通知 → Torrent Blocker**中配置。

只有 Node Plugin 完整配置后才会产生该事件：Remnawave Panel 和 Node 2.7+、
Xray-Core 26.3.27+、`NET_ADMIN`、nftables、正确的流量嗅探，以及已启用的 Torrent Blocker。
还应确认面板通知配置未禁用 `torrent_blocker.report` webhook 渠道。
详细检查项见[通知](../features/notifications.md#блокировка-торрентов-torrent-blocker)。

| 变量 | 用途 |
| --- | --- |
| `TORRENT_BLOCKER_NOTIFICATIONS_ENABLED` | 用户通知总开关，默认 `False`。 |
| `TORRENT_BLOCKER_TELEGRAM_NOTIFICATIONS_ENABLED` | 向已绑定 Telegram 发送通知，默认 `True`。 |
| `TORRENT_BLOCKER_EMAIL_NOTIFICATIONS_ENABLED` | 配置 SMTP 后，同时向已绑定邮箱发送通知，默认 `False`。 |
| `TORRENT_BLOCKER_NOTIFICATION_COOLDOWN_SECONDS` | 向同一用户同一渠道重复通知的间隔，默认 `3600`；`0` 关闭冷却，最大 `31536000` 秒。 |
| `TORRENT_BLOCKER_NOTIFICATION_INCLUDE_IP` | 在通知中显示已验证的被封禁 IP，默认 `False`。 |

## Web App、外观与 Telegram Login

<a id="веб-приложение-внешний-вид-и-telegram-login"></a>

部分外观字段（`WEBAPP_PRIMARY_COLOR`、`WEBAPP_LOGO_*`、`WEBAPP_FAVICON_*`）为兼容保留，但加载时忽略其环境变量值。请在**管理后台 → 外观**中设置。

Mini App 的实际配置见 [Web App](../features/web-app.md)，所有认证方式见[登录方式](../features/login-methods.md)。

> 本项目独立服务教程使用登录后的 `/api/service-guides`，读取随程序提供的 `deploy/examples/independent-services-guides.json`；不读取面板教程配置或后台 JSON 覆盖值。下表的 `SUBSCRIPTION_GUIDES_*`、`SUBSCRIPTION_GATEWAY_*`、`SUBSCRIPTION_LINK_MODE` 和 `SUBSCRIPTION_PAGE_CONFIG_*` 描述上游兼容行为，不能恢复已退役的 `/s/`、`/api/subscription-guides` 及旧公开教程入口（`410 legacy_business_retired`）。当前用户须从具体服务获取独立订阅链接，见[独立服务交付](../development/service-delivery.md)。

| 变量 | 修改位置 | 用途 |
| --- | --- | --- |
| `WEBAPP_ENABLED` | `.env` / 管理后台 | 启用 Web App。设为 `False` 时，用户 Web App 和管理后台都不可用，需通过 `.env` 重新开启并重启。 |
| `SUBSCRIPTION_MINI_APP_URL` | `.env` / 管理后台 | Mini App/frontend 的公开 HTTPS URL，例如 `https://app.domain.com/`，用于 Telegram 按钮、邀请链接、邮箱登录及 BotFather Mini App 设置。不要填写 `/api` 或 webhook 路径。 |
| `WEBAPP_API_BASE_URL` | `.env` | 浏览器可见的 API 基础路径，用于 `/bootstrap`、`/me`、支付和管理后台。保持 `/api`，不向浏览器提供完整后端 URL。 |
| `WEBAPP_BACKEND_UPSTREAM` | frontend 环境变量 | 前端 nginx 为 `/api`、`/auth`、`/open-app` 和 Web App 资源使用的服务端上游。 |
| `WEBAPP_BACKEND_UPSTREAM_HOST` | frontend 环境变量 | HTTPS 上游的 Host/SNI 覆盖值。 |
| `MINISHOP_EDGE_TOKEN` | `.env` / frontend 环境变量 | 受保护上游的服务端共享密钥。backend 仅在 WebApp API 端口 `8081` 要求该请求头；前端 nginx 向上游请求添加此头。 |
| `MINISHOP_EDGE_TOKEN_HEADER` | `.env` / frontend 环境变量 | 边缘代理令牌请求头，默认 `X-Minishop-Edge-Token`。 |
| `SUBSCRIPTION_GUIDES_ENABLED` | `.env` / 管理后台 | 启用 Web App 内置安装指南，默认 `True`。配置不可用或无效时，连接按钮打开普通的最终订阅链接。 |
| `SUBSCRIPTION_GATEWAY_ENABLED` | `.env` / 管理后台 | 允许客户端通过公开链接 `/s/<token>` 获取和更新订阅，默认 `True`；开关位于“连接指南”。关闭后指南页仍可用，但客户端无法取得配置。 |
| `SUBSCRIPTION_LINK_MODE` | `.env` / 管理后台 | 选择发放的链接：默认 `panel`，或使用 `/s/<token>` 的 `minishop`。在“连接指南”中开启“使用 Minishop 内置订阅链接”，会为机器人和安装指南启用 `minishop` 模式。链接生效还要求开启 `SUBSCRIPTION_GATEWAY_ENABLED`。 |
| `SUBSCRIPTION_GUIDES_BOT_MENU_ENABLED` | `.env` / 管理后台 | 允许机器人按钮打开 Mini App `/install`，并显示公开指南链接 `/s/<token>`。默认 `True`；关闭后机器人直接跳转到最终 Remnawave Subscription Page。 |
| `SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED` | `.env` / 管理后台 | 从面板读取 Remnawave Subscription Page 配置供内置指南使用，默认 `True`。有效订阅优先使用按 `shortUuid` 解析的配置（包括 External Squad 设置），再使用面板默认配置。 |
| `SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED` | `.env` / 管理后台 | 使用 `SUBSCRIPTION_PAGE_CONFIG_JSON` 字段中的 JSON 替代面板配置，默认 `False`。 |
| `SUBSCRIPTION_PAGE_CONFIG_PATH` | `.env` / 管理后台 | 面板配置关闭或不可用时，本地 Remnawave Subscription Page v1 JSON 的备用路径。默认 `data/subpage-config/multiapp.json`；不会自动创建文件。 |
| `SUBSCRIPTION_PAGE_CONFIG_JSON` | 管理后台 | 可选的 Remnawave Subscription Page v1 JSON 覆盖值。仅在 `SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED` 开启时生效；保存时 backend 会验证 JSON。 |
| `WEBAPP_TITLE` | 管理后台 | Web App 标题。 |
| `WEBAPP_THEMES_DIR` | `.env` | 自定义主题目录。 |
| `WEBAPP_DEFAULT_THEME` | `.env` / 管理后台 | 默认主题键。 |
| `WEBAPP_SESSION_TTL_SECONDS` | `.env` / 管理后台 → 常规 | Web App 会话有效秒数，默认 2592000（30 天）。 |
| `WEBAPP_AUTH_MAX_AGE_SECONDS` | `.env` | Telegram Mini Apps `initData` 的最大有效时长。 |
| `WEBAPP_LOGIN_TOKEN_TTL_SECONDS` | `.env` | 外部登录链接的 TTL。 |
| `WEBAPP_COMPACT_LOGIN_ENABLED` | `.env` / 管理后台 → 外观 | 多种登录方式可用时，以紧凑图标显示，默认 `True`。 |
| `TELEGRAM_OAUTH_CLIENT_ID` | `.env` | Telegram OAuth / OpenID Connect 客户端 ID。留空则从 `BOT_TOKEN` 获取机器人 ID。 |
| `TELEGRAM_OAUTH_CLIENT_SECRET` | `.env` | Telegram OAuth / OpenID Connect 客户端密钥。 |
| `TELEGRAM_OAUTH_REQUEST_ACCESS` | `.env` | 额外权限，例如 `write`。 |
| `TELEGRAM_OAUTH_USE_BOT_PROXY` | `.env` | 允许服务端 OAuth token/JWKS 请求自动使用已配置的 `TELEGRAM_BOT_PROXY_URL`，默认 `True`；浏览器重定向不经过该代理。 |
| `TELEGRAM_LOGIN_ENABLED` | 管理后台 | 显示 Telegram 登录。 |
| `TELEGRAM_LOGIN_RECOMMENDED` | `.env` / 管理后台 | 用户绑定 Telegram 前显示提醒标记，默认 `True`。 |
| `TELEGRAM_LOGIN_WIDE_BUTTON` | `.env` / 管理后台 | 紧凑登录模式中保留 Telegram 宽按钮，默认 `False`。 |
| `EMAIL_LOGIN_ENABLED` | 管理后台 | 配置 SMTP 后显示邮箱登录。 |
| `EMAIL_LOGIN_RECOMMENDED` | `.env` / 管理后台 | 用户绑定邮箱前显示提醒标记，默认 `True`。 |
| `EMAIL_LOGIN_WIDE_BUTTON` | `.env` / 管理后台 | 紧凑登录模式中直接显示邮箱表单，默认 `True`。 |
| `EMAIL_ADDRESS_CHANGE_ENABLED` | 管理后台 | 验证当前及新邮箱后，允许用户修改主邮箱，默认开启。 |
| `GOOGLE_OIDC_ENABLED` | 管理后台 | 启用 Google OIDC，需要客户端 ID 和密钥。 |
| `GOOGLE_LOGIN_RECOMMENDED` | `.env` / 管理后台 | 用户绑定 Google 前显示提醒标记，默认 `True`。 |
| `GOOGLE_LOGIN_WIDE_BUTTON` | `.env` / 管理后台 | 紧凑登录模式中保留 Google 宽按钮，默认 `False`。 |
| `GOOGLE_OIDC_CLIENT_ID` | 管理后台 | Google Cloud 中 OAuth 2.0 Web application 的客户端 ID。 |
| `GOOGLE_OIDC_CLIENT_SECRET` | 管理后台 | Google OAuth 客户端密钥。 |
| `YANDEX_OIDC_ENABLED` | 管理后台 | 启用 Yandex ID 登录，需要客户端 ID 和密钥。 |
| `YANDEX_LOGIN_RECOMMENDED` | `.env` / 管理后台 | 用户绑定 Yandex ID 前显示提醒标记，默认 `True`。 |
| `YANDEX_LOGIN_WIDE_BUTTON` | `.env` / 管理后台 | 紧凑登录模式中保留 Yandex 宽按钮，默认 `False`。 |
| `YANDEX_OIDC_CLIENT_ID` | 管理后台 | Yandex OAuth 中用于用户授权的应用 ID。 |
| `YANDEX_OIDC_CLIENT_SECRET` | 管理后台 | Yandex OAuth 应用密钥。 |
| `DISCORD_OIDC_ENABLED` | 管理后台 | 启用 Discord 登录，需要客户端 ID 和密钥。 |
| `DISCORD_LOGIN_RECOMMENDED` | `.env` / 管理后台 | 用户绑定 Discord 前显示提醒标记，默认 `True`。 |
| `DISCORD_LOGIN_WIDE_BUTTON` | `.env` / 管理后台 | 紧凑登录模式中保留 Discord 宽按钮，默认 `False`。 |
| `DISCORD_OIDC_CLIENT_ID` | 管理后台 | Discord Developer Portal 中的 Application ID。 |
| `DISCORD_OIDC_CLIENT_SECRET` | 管理后台 | Discord 应用客户端密钥。 |
| `PASSKEY_LOGIN_ENABLED` | 管理后台 | 启用通行密钥（passkey）/WebAuthn 注册和登录。 |
| `PASSKEY_LOGIN_RECOMMENDED` | `.env` / 管理后台 | 用户添加通行密钥前显示提醒标记，默认 `True`。 |
| `PASSKEY_LOGIN_WIDE_BUTTON` | `.env` / 管理后台 | 紧凑登录模式中保留通行密钥宽按钮，默认 `False`。 |
| `QR_LOGIN_ENABLED` | `.env` / 管理后台 | 二维码登录：浏览器显示二维码，已登录设备扫描并通过屏幕上的数字确认。新设备无需访问 Telegram。默认 `False`。 |
| `QR_LOGIN_WIDE_BUTTON` | `.env` / 管理后台 | 紧凑登录模式中保留二维码登录宽按钮，默认 `False`。 |
| `PASSKEY_RP_ID` | 管理后台 | Relying Party 域名，不含协议、端口和路径。默认从公开 Web App URL 获取。 |
| `PASSKEY_RP_NAME` | 管理后台 | 创建通行密钥时显示的服务名称。 |
| `PASSKEY_ORIGINS` | 管理后台 | 允许的 HTTPS 源，以逗号分隔。 |
| `PASSKEY_CHALLENGE_TTL_SECONDS` | 管理后台 | 一次性 WebAuthn 质询的有效时间。 |
| `WEBAPP_PRIMARY_COLOR` | 管理后台 | 已弃用的环境字段，读取时忽略。 |
| `WEBAPP_LOGO_URL` | 管理后台 | 已弃用的环境字段，读取时忽略。 |
| `WEBAPP_FAVICON_USE_CUSTOM` | 管理后台 | 已弃用的环境字段，读取时忽略。 |
| `WEBAPP_FAVICON_URL` | 管理后台 | 已弃用的环境字段，读取时忽略。 |
| `WEBAPP_LOGO_FAVICON_URL` | 管理后台 | 已弃用的环境字段，读取时忽略。 |

安装指南兼容 Remnawave Subscription Page v1 配置：`version`、`locales`、`brandingSettings`、`uiConfig`、`baseSettings`、`baseTranslations`、`svgLibrary` 和 `platforms`。文本字段按文本渲染；`svgLibrary` 中的 SVG 在返回 Web App 前会进行安全清理。

回调 URL、Google/Yandex 配置、通行密钥要求、账号合并规则，以及主邮箱与
Remnawave Panel 用户字段的关系，见[登录方式](../features/login-methods.md)。

## SMTP 与邮箱登录

<a id="smtp-и-вход-по-email"></a>

只有填写 `SMTP_HOST`、`SMTP_PORT`、`SMTP_USERNAME`、`SMTP_PASSWORD` 和 `SMTP_FROM_EMAIL` 后，才会显示邮箱登录。

SMTP、免密链接和密码登录的实际配置流程见[登录方式](../features/login-methods.md#общая-настройка-email)。

| 变量 | 用途 |
| --- | --- |
| `SMTP_HOST` | SMTP 主机。 |
| `SMTP_PORT` | 首选 SMTP 端口。 |
| `SMTP_FALLBACK_PORTS` | 备用端口，以逗号分隔。 |
| `SMTP_TIMEOUT_SECONDS` | 单次 SMTP 尝试的超时。 |
| `SMTP_USERNAME` | SMTP 用户名。 |
| `SMTP_PASSWORD` | SMTP 密码或 API 密钥。 |
| `SMTP_FROM_EMAIL` | 已验证的发件人地址。 |
| `SMTP_FROM_NAME` | 发件人名称。 |
| `SMTP_STARTTLS` | 使用 STARTTLS。 |
| `SMTP_USE_SSL` | 使用 SSL 封装连接。 |
| `EMAIL_CODE_TTL_SECONDS` | 邮箱验证码的 TTL。 |
| `EMAIL_CODE_RESEND_SECONDS` | 重新发送前的等待时间。 |
| `EMAIL_CODE_MAX_ATTEMPTS` | 验证码最大输入尝试次数。 |
| `BRUTE_FORCE_MAX_FAILURES` | 触发临时封锁的失败次数。 |
| `BRUTE_FORCE_WINDOW_SECONDS` | 失败次数统计窗口。 |
| `BRUTE_FORCE_LOCK_SECONDS` | 封锁持续时间。 |

## 支付

<a id="платежи"></a>

本节记录上游支付能力；本项目当前 MVP 不启用支付。各渠道的开关、密钥和显示设置位于**系统 → 设置 → 支付**。

| 变量 | 用途 |
| --- | --- |
| `PAYMENT_METHODS_ORDER` | 下拉列表或独立按钮中的支付方式顺序。Platega 支持 `platega_sbp`、`platega_card`、`platega_crypto`、`platega_international`、`platega_all_methods`、`platega_subscription`；旧值 `platega` 会展开为全部选项。RollyPay 支持 `rollypay`、`rollypay_sbp`、`rollypay_card`、`rollypay_international`、`rollypay_crypto`、`rollypay_subscription`。 |
| `PAYMENT_METHODS_DISPLAY_MODE` | Mini App 支付方式显示形式：默认紧凑下拉列表 `dropdown`，或独立按钮 `buttons`。后台位置：**支付 → 支付界面**。 |
| `SUBSCRIPTION_PURCHASE_DESCRIPTION_ENABLED` | 在选择时长前显示订阅说明。 |
| `SUBSCRIPTION_PURCHASE_DESCRIPTION_RU` / `SUBSCRIPTION_PURCHASE_DESCRIPTION_EN` | 本地化订阅说明。 |
| `PAYMENT_REQUEST_TIMEOUT_SECONDS` | 单次支付渠道 API 请求的总超时秒数，默认 `20`。 |
| `PAYMENT_FAILURE_NOTIFICATION_GRACE_SECONDS` | 支付失败通知的延迟，默认 `300`；期间重试付款成功会抑制过时的失败通知。`0` 关闭延迟。 |
| `USER_BALANCE_ENABLED` | 启用用户余额、充值及余额支付，在**常规 → 用户余额**中配置。 |
| `USER_BALANCE_CURRENCY` | 普通余额及可兑换推广伙伴余额的币种；留空继承 `DEFAULT_CURRENCY_SYMBOL`。 |
| `USER_BALANCE_TOPUP_MIN_AMOUNT` / `USER_BALANCE_TOPUP_MAX_AMOUNT` | 单次充值允许的金额范围；最大值不能小于最小值。 |
| `USER_BALANCE_TOPUP_PRESETS` | 快捷充值金额的 JSON 数组，例如 `[500, 1000, 2000, 5000]`。 |
| `PAYMENT_<METHOD>_WEBAPP_LABEL_RU` / `PAYMENT_<METHOD>_WEBAPP_LABEL_EN` | Web App 中支付渠道按钮的文本。 |
| `PAYMENT_<METHOD>_WEBAPP_ICON` | Web App 按钮的 Lucide 图标。 |
| `PAYMENT_<METHOD>_TELEGRAM_LABEL_RU` / `PAYMENT_<METHOD>_TELEGRAM_LABEL_EN` | Telegram 按钮文本。 |
| `PAYMENT_<METHOD>_TELEGRAM_EMOJI` | Telegram 按钮表情符号。 |
| `STARS_ENABLED` | 启用 Telegram Stars。 |
| `YOOKASSA_ENABLED` | 启用 YooKassa。 |
| `FREEKASSA_ENABLED` | 启用 FreeKassa。 |
| `PLATEGA_ENABLED` | 启用 Platega。 |
| `PLATEGA_SBP_ENABLED` / `PLATEGA_CARD_ENABLED` / `PLATEGA_CRYPTO_ENABLED` | Platega 的独立 SBP 快速支付、银行卡和加密货币按钮。 |
| `PLATEGA_INTERNATIONAL_ENABLED` | 国际银行卡按钮，默认 `paymentMethod: 12`。 |
| `PLATEGA_ALL_METHODS_ENABLED` | 由付款人选择支付方式的统一 Platega 链接。 |
| `PLATEGA_SUBSCRIPTION_ENABLED` | Platega 周期性 SBP 订阅按钮。 |
| `ROLLYPAY_ENABLED` | 启用 RollyPay 服务总开关。 |
| `ROLLYPAY_ALL_METHODS_ENABLED` / `ROLLYPAY_SBP_ENABLED` / `ROLLYPAY_CARD_ENABLED` | RollyPay 托管页面选择支付方式，以及独立 SBP、银行卡按钮。 |
| `ROLLYPAY_INTERNATIONAL_ENABLED` / `ROLLYPAY_CRYPTO_ENABLED` | RollyPay 境外银行卡和加密货币按钮。 |
| `ROLLYPAY_SUBSCRIPTION_ENABLED` | RollyPay 周期性 SBP 订阅，支持 1、3、12 个月周期。 |
| `SEVERPAY_ENABLED` | 启用 SeverPay。 |
| `WATA_ENABLED` | 启用 Wata。 |
| `CRYPTOPAY_ENABLED` | 启用 CryptoPay。 |
| `HELEKET_ENABLED` | 启用 Heleket。 |
| `OXAPAY_ENABLED` | 启用 OxaPay Generate Invoice。 |
| `PAYKILLA_ENABLED` | 启用 PayKilla。 |
| `LAVA_ENABLED` | 启用 LAVA。 |
| `PALLY_ENABLED` | 启用 Pally / PayPalych。 |
| `CLOUDPAYMENTS_ENABLED` | 启用 CloudPayments。 |
| `OVERPAY_ENABLED` | 启用 Overpay。 |
| `TRIBUTE_ENABLED` | 通过 Shop API 和／或 Creator 备用流程启用 Tribute 支付。 |

具体的显示配置键：

```text
PAYMENT_YOOKASSA_WEBAPP_LABEL_RU
PAYMENT_YOOKASSA_WEBAPP_LABEL_EN
PAYMENT_YOOKASSA_WEBAPP_ICON
PAYMENT_YOOKASSA_TELEGRAM_LABEL_RU
PAYMENT_YOOKASSA_TELEGRAM_LABEL_EN
PAYMENT_YOOKASSA_TELEGRAM_EMOJI
PAYMENT_FREEKASSA_WEBAPP_LABEL_RU
PAYMENT_FREEKASSA_WEBAPP_LABEL_EN
PAYMENT_FREEKASSA_WEBAPP_ICON
PAYMENT_FREEKASSA_TELEGRAM_LABEL_RU
PAYMENT_FREEKASSA_TELEGRAM_LABEL_EN
PAYMENT_FREEKASSA_TELEGRAM_EMOJI
PAYMENT_PLATEGA_SBP_WEBAPP_LABEL_RU
PAYMENT_PLATEGA_SBP_WEBAPP_LABEL_EN
PAYMENT_PLATEGA_SBP_WEBAPP_ICON
PAYMENT_PLATEGA_SBP_TELEGRAM_LABEL_RU
PAYMENT_PLATEGA_SBP_TELEGRAM_LABEL_EN
PAYMENT_PLATEGA_SBP_TELEGRAM_EMOJI
PAYMENT_PLATEGA_CARD_WEBAPP_LABEL_RU
PAYMENT_PLATEGA_CARD_WEBAPP_LABEL_EN
PAYMENT_PLATEGA_CARD_WEBAPP_ICON
PAYMENT_PLATEGA_CARD_TELEGRAM_LABEL_RU
PAYMENT_PLATEGA_CARD_TELEGRAM_LABEL_EN
PAYMENT_PLATEGA_CARD_TELEGRAM_EMOJI
PAYMENT_PLATEGA_CRYPTO_WEBAPP_LABEL_RU
PAYMENT_PLATEGA_CRYPTO_WEBAPP_LABEL_EN
PAYMENT_PLATEGA_CRYPTO_WEBAPP_ICON
PAYMENT_PLATEGA_CRYPTO_TELEGRAM_LABEL_RU
PAYMENT_PLATEGA_CRYPTO_TELEGRAM_LABEL_EN
PAYMENT_PLATEGA_CRYPTO_TELEGRAM_EMOJI
PAYMENT_PLATEGA_INTERNATIONAL_WEBAPP_LABEL_RU
PAYMENT_PLATEGA_INTERNATIONAL_WEBAPP_LABEL_EN
PAYMENT_PLATEGA_INTERNATIONAL_WEBAPP_ICON
PAYMENT_PLATEGA_INTERNATIONAL_TELEGRAM_LABEL_RU
PAYMENT_PLATEGA_INTERNATIONAL_TELEGRAM_LABEL_EN
PAYMENT_PLATEGA_INTERNATIONAL_TELEGRAM_EMOJI
PAYMENT_PLATEGA_ALL_METHODS_WEBAPP_LABEL_RU
PAYMENT_PLATEGA_ALL_METHODS_WEBAPP_LABEL_EN
PAYMENT_PLATEGA_ALL_METHODS_WEBAPP_ICON
PAYMENT_PLATEGA_ALL_METHODS_TELEGRAM_LABEL_RU
PAYMENT_PLATEGA_ALL_METHODS_TELEGRAM_LABEL_EN
PAYMENT_PLATEGA_ALL_METHODS_TELEGRAM_EMOJI
PAYMENT_PLATEGA_SUBSCRIPTION_WEBAPP_LABEL_RU
PAYMENT_PLATEGA_SUBSCRIPTION_WEBAPP_LABEL_EN
PAYMENT_PLATEGA_SUBSCRIPTION_WEBAPP_ICON
PAYMENT_PLATEGA_SUBSCRIPTION_TELEGRAM_LABEL_RU
PAYMENT_PLATEGA_SUBSCRIPTION_TELEGRAM_LABEL_EN
PAYMENT_PLATEGA_SUBSCRIPTION_TELEGRAM_EMOJI
PAYMENT_SEVERPAY_WEBAPP_LABEL_RU
PAYMENT_SEVERPAY_WEBAPP_LABEL_EN
PAYMENT_SEVERPAY_WEBAPP_ICON
PAYMENT_SEVERPAY_TELEGRAM_LABEL_RU
PAYMENT_SEVERPAY_TELEGRAM_LABEL_EN
PAYMENT_SEVERPAY_TELEGRAM_EMOJI
PAYMENT_WATA_WEBAPP_LABEL_RU
PAYMENT_WATA_WEBAPP_LABEL_EN
PAYMENT_WATA_WEBAPP_ICON
PAYMENT_WATA_TELEGRAM_LABEL_RU
PAYMENT_WATA_TELEGRAM_LABEL_EN
PAYMENT_WATA_TELEGRAM_EMOJI
PAYMENT_STARS_WEBAPP_LABEL_RU
PAYMENT_STARS_WEBAPP_LABEL_EN
PAYMENT_STARS_WEBAPP_ICON
PAYMENT_STARS_TELEGRAM_LABEL_RU
PAYMENT_STARS_TELEGRAM_LABEL_EN
PAYMENT_STARS_TELEGRAM_EMOJI
PAYMENT_CRYPTOPAY_WEBAPP_LABEL_RU
PAYMENT_CRYPTOPAY_WEBAPP_LABEL_EN
PAYMENT_CRYPTOPAY_WEBAPP_ICON
PAYMENT_CRYPTOPAY_TELEGRAM_LABEL_RU
PAYMENT_CRYPTOPAY_TELEGRAM_LABEL_EN
PAYMENT_CRYPTOPAY_TELEGRAM_EMOJI
PAYMENT_HELEKET_WEBAPP_LABEL_RU
PAYMENT_HELEKET_WEBAPP_LABEL_EN
PAYMENT_HELEKET_WEBAPP_ICON
PAYMENT_HELEKET_TELEGRAM_LABEL_RU
PAYMENT_HELEKET_TELEGRAM_LABEL_EN
PAYMENT_HELEKET_TELEGRAM_EMOJI
PAYMENT_OXAPAY_WEBAPP_LABEL_RU
PAYMENT_OXAPAY_WEBAPP_LABEL_EN
PAYMENT_OXAPAY_WEBAPP_ICON
PAYMENT_OXAPAY_TELEGRAM_LABEL_RU
PAYMENT_OXAPAY_TELEGRAM_LABEL_EN
PAYMENT_OXAPAY_TELEGRAM_EMOJI
PAYMENT_PAYKILLA_WEBAPP_LABEL_RU
PAYMENT_PAYKILLA_WEBAPP_LABEL_EN
PAYMENT_PAYKILLA_WEBAPP_ICON
PAYMENT_PAYKILLA_TELEGRAM_LABEL_RU
PAYMENT_PAYKILLA_TELEGRAM_LABEL_EN
PAYMENT_PAYKILLA_TELEGRAM_EMOJI
PAYMENT_LAVA_WEBAPP_LABEL_RU
PAYMENT_LAVA_WEBAPP_LABEL_EN
PAYMENT_LAVA_WEBAPP_ICON
PAYMENT_LAVA_TELEGRAM_LABEL_RU
PAYMENT_LAVA_TELEGRAM_LABEL_EN
PAYMENT_LAVA_TELEGRAM_EMOJI
PAYMENT_PALLY_WEBAPP_LABEL_RU
PAYMENT_PALLY_WEBAPP_LABEL_EN
PAYMENT_PALLY_WEBAPP_ICON
PAYMENT_PALLY_TELEGRAM_LABEL_RU
PAYMENT_PALLY_TELEGRAM_LABEL_EN
PAYMENT_PALLY_TELEGRAM_EMOJI
PAYMENT_CLOUDPAYMENTS_WEBAPP_LABEL_RU
PAYMENT_CLOUDPAYMENTS_WEBAPP_LABEL_EN
PAYMENT_CLOUDPAYMENTS_WEBAPP_ICON
PAYMENT_CLOUDPAYMENTS_TELEGRAM_LABEL_RU
PAYMENT_CLOUDPAYMENTS_TELEGRAM_LABEL_EN
PAYMENT_CLOUDPAYMENTS_TELEGRAM_EMOJI
PAYMENT_OVERPAY_WEBAPP_LABEL_RU
PAYMENT_OVERPAY_WEBAPP_LABEL_EN
PAYMENT_OVERPAY_WEBAPP_ICON
PAYMENT_OVERPAY_TELEGRAM_LABEL_RU
PAYMENT_OVERPAY_TELEGRAM_LABEL_EN
PAYMENT_OVERPAY_TELEGRAM_EMOJI
PAYMENT_STRIPE_WEBAPP_LABEL_RU
PAYMENT_STRIPE_WEBAPP_LABEL_EN
PAYMENT_STRIPE_WEBAPP_ICON
PAYMENT_STRIPE_TELEGRAM_LABEL_RU
PAYMENT_STRIPE_TELEGRAM_LABEL_EN
PAYMENT_STRIPE_TELEGRAM_EMOJI
PAYMENT_TRIBUTE_WEBAPP_LABEL_RU
PAYMENT_TRIBUTE_WEBAPP_LABEL_EN
PAYMENT_TRIBUTE_WEBAPP_ICON
PAYMENT_TRIBUTE_TELEGRAM_LABEL_RU
PAYMENT_TRIBUTE_TELEGRAM_LABEL_EN
PAYMENT_TRIBUTE_TELEGRAM_EMOJI
```

### YooKassa

| 变量 | 用途 |
| --- | --- |
| `YOOKASSA_SHOP_ID` | 商店 ID。 |
| `YOOKASSA_SECRET_KEY` | 密钥。 |
| `YOOKASSA_RETURN_URL` | 付款后返回 URL。 |
| `YOOKASSA_DEFAULT_RECEIPT_EMAIL` | 默认收据邮箱。 |
| `YOOKASSA_VAT_CODE` | 增值税代码。 |
| `YOOKASSA_AUTOPAYMENTS_ENABLED` | 通过已保存的支付方式自动续订。 |
| `YOOKASSA_AUTOPAYMENTS_REQUIRE_CARD_BINDING` | 要求绑定银行卡。 |
| `AUTO_RENEW_RETRY_ENABLED` | 启用可持久运行的 YooKassa 安全重试队列，默认关闭。 |
| `AUTO_RENEW_RETRY_DRY_RUN` | 不实际扣款，只检查并记录已就绪的重试，默认开启。 |
| `AUTO_RENEW_MAX_FINANCIAL_ATTEMPTS` | 每周期实际扣款尝试的最大次数，包含首次，上限为 `2`。 |
| `AUTO_RENEW_MAX_TRANSPORT_REPLAYS` | 对同一请求和 `Idempotence-Key` 进行传输层重试的最大次数。 |
| `AUTO_RENEW_WORKER_TICK_SECONDS` | 重试队列轮询间隔。 |
| `AUTO_RENEW_WORKER_BATCH_SIZE` | worker 单次处理的最大周期数。 |
| `AUTO_RENEW_RETRY_GRACE_HOURS` | 订阅到期后允许再次尝试实际扣款的额外窗口。 |
| `AUTO_RENEW_SCHEDULER_ENABLED` | 启用无需面板 webhook 的待续订订阅备用扫描，默认关闭。 |
| `AUTO_RENEW_SCHEDULER_LEAD_HOURS` | 备用调度器提前多少小时开始考虑某个订阅。 |

### FreeKassa

| 变量 | 用途 |
| --- | --- |
| `FREEKASSA_MERCHANT_ID` | 商店 ID。 |
| `FREEKASSA_API_KEY` | API 密钥。 |
| `FREEKASSA_SECOND_SECRET` | 通知密钥。 |
| `FREEKASSA_PAYMENT_IP` | `backend` 稳定的公开出站 IPv4，创建订单时作为付款人 IP 的备用值。 |
| `FREEKASSA_PAYMENT_METHOD_ID` | 支付方式 ID。 |
| `FREEKASSA_TRUSTED_IPS` | 受信任 webhook 来源 IP 列表。 |

FreeKassa 创建订单 API 要求 `ip` 字段，但 Telegram 不向机器人提供用户 IP，因此当前集成使用 `backend` 的出站地址。可从运行中的容器获取：

```bash
docker compose exec backend sh -lc 'curl -4fsS https://api.ipify.org; echo'
```

不要填写 Docker/Kubernetes 内部 IP、反向代理地址或 `FREEKASSA_TRUSTED_IPS` 中的值。如果流量通过 NAT、VPN 或独立网关出站，应使用上述命令显示的地址。详细配置顺序见[支付 → FreeKassa](../features/payments.md#freekassa)。

### Platega

| 变量 | 用途 |
| --- | --- |
| `PLATEGA_BASE_URL` | API 基础 URL。 |
| `PLATEGA_MERCHANT_ID` | 商户 ID。 |
| `PLATEGA_SECRET` | API 密钥。 |
| `PLATEGA_PAYMENT_METHOD` | 旧版／备用支付方式 ID。 |
| `PLATEGA_SBP_METHOD` | SBP 支付方式 ID。 |
| `PLATEGA_CARD_METHOD` | 银行卡支付方式 ID，默认 `11`。 |
| `PLATEGA_CRYPTO_METHOD` | 加密货币支付方式 ID。 |
| `PLATEGA_INTERNATIONAL_METHOD` | 国际银行卡支付方式 ID，默认 `12`。 |
| `PLATEGA_SUBSCRIPTION_METHOD` | 周期性 SBP 订阅支付方式 ID，默认 `6`。 |
| `PLATEGA_SUPPORTED_CURRENCIES` | 商户及所选支付方式已启用的币种，以逗号分隔。 |
| `PLATEGA_RETURN_URL` | 支付成功返回 URL。 |
| `PLATEGA_FAILED_URL` | 支付失败返回 URL。 |

### RollyPay

| 变量 | 用途 |
| --- | --- |
| `ROLLYPAY_ENABLED` | 服务总开关。 |
| `ROLLYPAY_BASE_URL` | API 基础 URL，默认 `https://rollypay.io/api/v1`。 |
| `ROLLYPAY_API_KEY` | 用于 `X-API-Key` 的商户 API 密钥。 |
| `ROLLYPAY_SIGNING_SECRET` | 终端 webhook 的 HMAC-SHA256 密钥。 |
| `ROLLYPAY_TERMINAL_ID` | 支付终端；订阅计划也必须提供该终端 ID。 |
| `ROLLYPAY_ALL_METHODS_ENABLED` | 不固定支付方式的托管页面。 |
| `ROLLYPAY_SBP_ENABLED` / `ROLLYPAY_CARD_ENABLED` | 独立的 `sbp` 和 `card` 支付方式。 |
| `ROLLYPAY_INTERNATIONAL_ENABLED` | `intl_card` 支付方式；唯一支持 `EUR` 的 RollyPay 按钮。 |
| `ROLLYPAY_CRYPTO_ENABLED` | `crypto` 支付方式。 |
| `ROLLYPAY_SUBSCRIPTION_ENABLED` | 由渠道提供的周期性 SBP 订阅，要求 `ROLLYPAY_TERMINAL_ID`。 |
| `ROLLYPAY_<METHOD>_ADMIN_ONLY_ENABLED` | 仅向管理员角色账号显示指定按钮。`<METHOD>` 可为 `ALL_METHODS`、`SBP`、`CARD`、`INTERNATIONAL`、`CRYPTO`、`SUBSCRIPTION`。 |
| `ROLLYPAY_TEST_MODE` | 发送 `test: true`；一次性支付仅管理员可用，周期性支付关闭。 |
| `ROLLYPAY_SUCCESS_URL` / `ROLLYPAY_FAIL_URL` | 显式返回 URL；未设置时使用标准机器人链接。 |
| `ROLLYPAY_WEBHOOK_TOLERANCE_SECONDS` | `X-Timestamp` 允许的最大时间差，默认 `300`。 |
| `ROLLYPAY_WEBHOOK_LOOKUP_TIMEOUT_SECONDS` | 必须执行的 API 支付核验超时，范围 `1..9`，默认 `8`。 |
| `ROLLYPAY_PLAN_CACHE_SECONDS` | 订阅计划缓存 TTL，默认 `300`。 |
| `ROLLYPAY_RECONCILE_INTERVAL_SECONDS` | 扣款授权状态核对周期，默认 `300`。 |
| `ROLLYPAY_RECONCILE_BATCH_SIZE` | 每次核对的最大扣款授权数量，默认 `100`。 |

### SeverPay

| 变量 | 用途 |
| --- | --- |
| `SEVERPAY_BASE_URL` | API 基础 URL。 |
| `SEVERPAY_MID` | 商户 MID。 |
| `SEVERPAY_TOKEN` | API 令牌或密钥。 |
| `SEVERPAY_RETURN_URL` | 返回 URL。 |
| `SEVERPAY_LIFETIME_MINUTES` | 支付链接有效时间。 |

### Wata

| 变量 | 用途 |
| --- | --- |
| `WATA_ENABLED` | 启用常规一次性 Wata 支付。 |
| `WATA_ADMIN_ONLY_ENABLED` | 仅向管理员显示常规 Wata 支付。 |
| `WATA_BASE_URL` | API 基础 URL。 |
| `WATA_API_TOKEN` | Bearer 令牌。 |
| `WATA_RETURN_URL` | 支付成功返回 URL。 |
| `WATA_FAILED_URL` | 支付失败返回 URL。 |
| `WATA_LINK_TTL_MINUTES` | 支付链接有效分钟数，默认 15，最小 15，最大 43200。 |
| `WATA_WEBHOOK_VERIFY_SIGNATURE` | 验证 `X-Signature`。 |
| `WATA_PUBLIC_KEY` | 缓存公钥；留空则从 API 下载。 |
| `WATA_TRUSTED_IPS` | 受信任 webhook 来源 IP 列表。 |
| `WATA_SUBSCRIPTION_ENABLED` | 启用由 Wata 调度的独立支付方式，终端必须已开通订阅。 |
| `WATA_SUBSCRIPTION_ADMIN_ONLY_ENABLED` | 仅向管理员显示周期性 Wata 支付方式。 |
| `WATA_SUBSCRIPTION_MAX_PERIODS` | 新 Wata 订阅的最大周期数，默认 `120`。 |
| `PAYMENT_WATA_SUBSCRIPTION_WEBAPP_LABEL_RU` | Wata 周期性支付按钮的俄语文本。 |
| `PAYMENT_WATA_SUBSCRIPTION_WEBAPP_LABEL_EN` | Wata 周期性支付按钮的英语文本。 |
| `PAYMENT_WATA_SUBSCRIPTION_WEBAPP_ICON` | Wata 周期性支付方式的 Lucide 图标。 |

### CryptoPay

| 变量 | 用途 |
| --- | --- |
| `CRYPTOPAY_TOKEN` | CryptoPay API 令牌。 |
| `CRYPTOPAY_NETWORK` | `mainnet` 或 `testnet`。 |
| `CRYPTOPAY_CURRENCY_TYPE` | `fiat` 或 `crypto`。 |
| `CRYPTOPAY_ASSET` | 资产，例如 `RUB`、`USDT`、`BTC`。 |

### Tribute

| 变量 | 用途 |
| --- | --- |
| `TRIBUTE_ENABLED` | 启用 Tribute 渠道及其 webhook 处理。 |
| `TRIBUTE_API_KEY` | Tribute Shop/Creator API 密钥；同一密钥也用于验证 `trbt-signature` 中的 HMAC-SHA256。 |
| `TRIBUTE_SHOP_ENABLED` | 将 Shop API 作为主模式，按本地精确金额创建动态订单。必须同时设置 `TRIBUTE_SHOP_ID`；否则忽略此开关，只保留 Creator 订阅。 |
| `TRIBUTE_SHOP_ID` | 指定 Shop 的正整数 ID，Shop 模式实际运行所必需。创建订单时传递，并在每个 Shop webhook 中核验。未设置 ID 时，已开启的 `TRIBUTE_SHOP_ENABLED` 只记录警告，不影响启动，仍销售已配置的 Creator 订阅。 |

`TRIBUTE_SHOP_ENABLED=true` 时，周期性 Shop Orders 仅支持本地 1/3/6/12 个月时长；
流量、高级流量、独立 HWID 设备及套餐切换补差价使用一次性订单。
金额由 Minishop 本地计算。Shop API 接受 `100` 到 `300000` 个最小货币单位
（戈比／分）；超出此范围时，Minishop 会在网络请求前拒绝订单。

链接和 ID 不是全局环境设置。它们在套餐编辑器中定义固定的 Creator 备用流程：
订阅使用 `tribute.link`、`tribute.subscription_id` 和 `period_ids`；
Digital Products 使用含 `product_id` 和链接的 `traffic_products`/`premium_traffic_products`。
备用流程的价格在 Tribute 中配置，不会将本地价格发送至 Tribute API。

Minishop 集成不支持 Stars Shop 订单、Token Charging/`paymentToken`、预付余额和
Creator 捐赠。具体场景及生命周期见 [Tribute 配置](../features/payments.md#tribute)。

### Heleket

| 变量 | 用途 |
| --- | --- |
| `HELEKET_BASE_URL` | API 基础 URL。 |
| `HELEKET_MERCHANT_ID` | 商户 UUID。 |
| `HELEKET_API_KEY` | 支付 API 密钥。 |
| `HELEKET_CURRENCY` | 账单币种。 |
| `HELEKET_TO_CURRENCY` | 兑换的目标加密货币。 |
| `HELEKET_NETWORK` | 网络，例如 `tron`、`bsc`、`eth`。 |
| `HELEKET_RETURN_URL` | 取消或过期后的 URL。 |
| `HELEKET_SUCCESS_URL` | 支付成功后的 URL。 |
| `HELEKET_LIFETIME_SECONDS` | 账单 TTL：300..43200。 |
| `HELEKET_VERIFY_WEBHOOK_SIGNATURE` | 验证 webhook 签名。 |
| `HELEKET_TRUSTED_IPS` | 受信任 webhook 来源 IP 列表。 |

### OxaPay

| 变量 | 用途 |
| --- | --- |
| `OXAPAY_MERCHANT_API_KEY` | 用于 Generate Invoice、Payment Information 和 HMAC-SHA512 webhook 验证的商户 API 密钥。 |
| `OXAPAY_BASE_URL` | API 基础 URL，默认 `https://api.oxapay.com/v1`。 |
| `OXAPAY_RETURN_URL` | 支付成功返回 URL；留空则使用 Telegram 机器人链接。 |
| `OXAPAY_LIFETIME_MINUTES` | 账单有效时间，`15` 到 `2880` 分钟，默认 `60`。 |
| `OXAPAY_FEE_PAID_BY_PAYER` | 账单手续费承担方；留空保留 Merchant Service 设置。 |
| `OXAPAY_UNDER_PAID_COVERAGE` | 允许少付的百分比，范围 `0` 到 `60`；留空保留 Merchant Service 设置。 |
| `OXAPAY_TO_CURRENCY` | 可选的到账金额自动兑换，支持 `USDT`。 |
| `OXAPAY_AUTO_WITHDRAWAL` | 自动将到账资金提现到 OxaPay Address List 中的地址；留空保留 Merchant Service 设置。 |
| `OXAPAY_MIXED_PAYMENT` | 允许使用其他币种补足金额；留空保留 Merchant Service 设置。 |
| `OXAPAY_SANDBOX` | 创建测试账单，默认关闭。 |
| `OXAPAY_TRUSTED_IPS` | 可选的 webhook 来源 IP 列表，以逗号分隔；向 OxaPay 支持获取当前列表。 |

每张账单都会自动携带回调 URL：`WEBHOOK_BASE_URL` 加 `/webhook/oxapay`。
始终依据请求的精确原始字节验证 `HMAC` 请求头，没有可关闭验证的绕过参数。
详情见[支付 → OxaPay](../features/payments.md#oxapay)。

### PayKilla

收款需要具有 **INVOICE** 权限的 **HMAC** 类型 API 密钥。订阅支付不需要 **WITHDRAWAL** 权限；只在单独集成付款转出功能时启用该权限。

在 PayKilla Dashboard 的 **Settings → Webhooks** 中设置 webhook，填写 `WEBHOOK_BASE_URL` 加 `/webhook/paykilla`，例如 `https://bot.example.com/webhook/paykilla`。至少启用 `INVOICE_PAID` 和 `INVOICE_EXPIRED`。推荐勾选 `INVOICE_PAID`、`PAYMENT_COMPLETED`、`PAYMENT_FAILED`、`PAYMENT_OVERPAID`、`PAYMENT_UNDERPAID`、`PAYMENT_PARTIAL`、`INVOICE_EXPIRED`、`COMPLIANCE_FAILED`。需要在 PayKilla 日志查看中间状态时，另启用 `INVOICE_CREATED`、`PAYMENT_PENDING`、`TRANSACTION_CONFIRMED` 和 `TRANSACTION_FINAL`。

| 变量 | 用途 |
| --- | --- |
| `PAYKILLA_BASE_URL` | API 基础 URL，默认 `https://account-api.paykilla.com`。 |
| `PAYKILLA_WIDGET_URL` | 托管收银台 URL，默认 `https://gopay.paykilla.com`。 |
| `PAYKILLA_API_KEY` / `PAYKILLA_V2_API_KEY` | 具有 `INVOICE` 权限的公开 HMAC 密钥。 |
| `PAYKILLA_SECRET_KEY` / `PAYKILLA_V2_SECRET_KEY` | 用于 API 请求签名和 webhook 验证的 HMAC 私密密钥。 |
| `PAYKILLA_CURRENCY` | 套餐币种不在 `PAYKILLA_INVOICE_CURRENCIES` 中时使用的 PayKilla 备用账单币种，默认 `USD`。 |
| `PAYKILLA_INVOICE_CURRENCIES` | PayKilla 创建账单时 `currency` 字段接受的币种，默认 `USD,EUR`。套餐使用 `RUB` 时，Minishop 将金额兑换为 `PAYKILLA_CURRENCY`。 |
| `PAYKILLA_PAYMENT_CURRENCIES` | 可用于付款的加密货币代码，默认 `USDTTRC,BTC,ETH,USDTBSC,USDTTON`；只保留 PayKilla Dashboard 中该商户账号可用的代码。 |
| `PAYKILLA_SUPPORTED_CURRENCIES` | 本商店允许使用 PayKilla 的套餐／支付币种。 |
| `PAYKILLA_INVOICE_TYPE` | 可选覆盖值：`FIAT_BASED`、`FIXED_AMOUNT` 或 `OPEN_AMOUNT`。 |
| `PAYKILLA_LIFETIME_SECONDS` | 账单 TTL，以 `expiredAt` 发送。 |
| `PAYKILLA_RECV_WINDOW_MS` | 签名 API 请求的 `recvWindow`。 |
| `PAYKILLA_USER_PAYS_SERVICE_FEE` | 用户承担服务费时设为 `true`。 |
| `PAYKILLA_USER_PAYS_NETWORK_FEE` | 用户承担网络费时设为 `true`。 |
| `PAYKILLA_EXCHANGE_RATE_URL` | 将套餐币种兑换为账单币种的免费、无需密钥的汇率端点，默认 `https://open.er-api.com/v6/latest/{source}`。支持 `{source}` 和 `{target}` 占位符。 |
| `PAYKILLA_EXCHANGE_RATE_CACHE_SECONDS` | 汇率及 PayKilla 币种限额的缓存秒数，默认 `3600`。 |
| `PAYKILLA_MIN_PAYMENT_AMOUNT` | PayKilla 最低支付金额，默认 `10`。 |
| `PAYKILLA_MIN_PAYMENT_CURRENCY` | `PAYKILLA_MIN_PAYMENT_AMOUNT` 的币种，默认 `USD`；卢布套餐的阈值通过 `PAYKILLA_EXCHANGE_RATE_URL` 换算。 |
| `PAYKILLA_VERIFY_WEBHOOK_SIGNATURE` | 根据 webhook 原始请求体验证 `X-API-SIGN`。 |
| `PAYKILLA_WEBHOOK_URL` | 签名验证使用的精确公开 webhook URL，仅在其不同于 `WEBHOOK_BASE_URL` 加 `/webhook/paykilla` 时填写。 |
| `PAYKILLA_TRUSTED_IPS` | 可选的受信任 webhook 来源 IP 列表。 |

### LAVA

LAVA Business 账单只使用卢布。出站请求按原始请求体计算 HMAC-SHA256 签名，放在 `Signature` 请求头中；webhook 通过 `Authorization` 请求头验证。

| 变量 | 用途 |
| --- | --- |
| `LAVA_BASE_URL` | API 基础 URL，默认 `https://api.lava.ru`。 |
| `LAVA_SHOP_ID` | LAVA Business 商店 ID。 |
| `LAVA_SECRET_KEY` | 商店密钥，用于出站 API 请求签名。 |
| `LAVA_WEBHOOK_SECRET` | 用于验证 webhook 签名的商店附加密钥；留空使用 `LAVA_SECRET_KEY`。 |
| `LAVA_RETURN_URL` | 付款后返回 URL（`successUrl`/`failUrl`）。 |
| `LAVA_LIFETIME_MINUTES` | 账单有效分钟数：1..7200。 |
| `LAVA_INCLUDE_SERVICES` | 账单页面的支付方式，以逗号分隔，例如 `card,sbp`。 |

### Pally

Pally / PayPalych 通过 `POST /api/v1/bill/create` 创建账单。请求使用 Bearer 令牌认证；回调以 `application/x-www-form-urlencoded` 发送，按 `SignatureValue = strtoupper(md5(OutSum:InvId:token))` 验证。

| 变量 | 用途 |
| --- | --- |
| `PALLY_BASE_URL` | API 基础 URL，默认 `https://pally.info/api/v1`。账号后台仍使用旧域名时，可手动填写 `https://pal24.pro/api/v1`。 |
| `PALLY_API_TOKEN` | Pally API 集成页面提供的 Bearer 令牌。 |
| `PALLY_SIGNATURE_TOKEN` | 回调签名验证令牌；留空使用 `PALLY_API_TOKEN`。 |
| `PALLY_SHOP_ID` | Pally 商店 ID。缺少时，账单的 Result URL、Success URL 和 Fail URL 不生效。 |
| `PALLY_RETURN_URL` | 支付页面“返回商店”链接的 URL。 |
| `PALLY_SUCCESS_URL` | 支付成功返回 URL。 |
| `PALLY_FAIL_URL` | 支付失败返回 URL。 |
| `PALLY_TTL_SECONDS` | 账单有效秒数。 |
| `PALLY_MIN_PAYMENT_AMOUNT_RUB` | 由外部渠道收取的账单最低卢布金额，默认 `30`。使用推广伙伴余额支付时，Minishop 为渠道保留该金额。`0` 关闭限制。 |
| `PALLY_MIN_PAYMENT_AMOUNT_USD` | 由外部渠道收取的账单最低美元金额，默认 `0`。 |
| `PALLY_MIN_PAYMENT_AMOUNT_EUR` | 由外部渠道收取的账单最低欧元金额，默认 `0`。 |
| `PALLY_PAYER_PAYS_COMMISSION` | 买方承担手续费时，传递 `payer_pays_commission=1`。 |
| `PALLY_PAYMENT_METHOD` | 可选的预选支付方式：`BANK_CARD` 或 `SBP`。 |
| `PALLY_LOCALE` | 支付表单语言：`ru` 或 `en`；留空时机器人尝试传递用户语言。 |
| `PALLY_NAME` | 支付表单中的链接名称。 |

### CloudPayments

CloudPayments 通过 Orders API 接受银行卡付款。出站请求使用 HTTP Basic auth（`CLOUDPAYMENTS_PUBLIC_ID`/`CLOUDPAYMENTS_API_SECRET`）；Pay/Fail 通知使用 HMAC-SHA256 签名，按 base64 编码放在 `Content-HMAC` 请求头中。

| 变量 | 用途 |
| --- | --- |
| `CLOUDPAYMENTS_BASE_URL` | API 基础 URL，默认 `https://api.cloudpayments.ru`。 |
| `CLOUDPAYMENTS_PUBLIC_ID` | CloudPayments 后台的 Public ID，作为 HTTP Basic auth 用户名。 |
| `CLOUDPAYMENTS_API_SECRET` | CloudPayments 后台的 API Secret，作为 HTTP Basic auth 密码及签名验证密钥。 |
| `CLOUDPAYMENTS_RETURN_URL` | 支付成功返回 URL。 |
| `CLOUDPAYMENTS_FAILED_URL` | 支付出错返回 URL；留空使用 `CLOUDPAYMENTS_RETURN_URL`。 |
| `CLOUDPAYMENTS_RECURRING_ENABLED` | 使用已保存的 CloudPayments `Token` 扣款，实现订阅自动续期。 |
| `CLOUDPAYMENTS_VERIFY_WEBHOOK_SIGNATURE` | 验证通知的 `Content-HMAC` 请求头。 |
| `CLOUDPAYMENTS_TRUSTED_IPS` | 可选的受信任 webhook 来源 IP 列表。 |

### Overpay

Overpay 基于 BeGateway 平台：机器人创建托管收银台（支付令牌），并将用户重定向至 `redirect_url`。出站请求使用 HTTP Basic auth（`OVERPAY_SHOP_ID`/`OVERPAY_SECRET_KEY`）；通知以 JSON POST 发送，使用相同的 HTTP Basic 凭据。自动续订通过网关 API 对已保存的 `credit_card.token` 扣款。通知 URL 设置为 `WEBHOOK_BASE_URL` 加 `/webhook/overpay`。

| 变量 | 用途 |
| --- | --- |
| `OVERPAY_SHOP_ID` | Overpay 后台的 Shop ID，作为 HTTP Basic auth 用户名。 |
| `OVERPAY_SECRET_KEY` | Overpay 后台的 Secret Key，作为 HTTP Basic auth 密码并验证入站 webhook。 |
| `OVERPAY_CHECKOUT_URL` | 收银台 API 基础 URL，默认 `https://checkout.overpay.io`。 |
| `OVERPAY_GATEWAY_URL` | 令牌扣款使用的网关 API 基础 URL，默认 `https://gateway.overpay.io`。 |
| `OVERPAY_RETURN_URL` | 支付页面“返回商店”的 URL。 |
| `OVERPAY_SUCCESS_URL` | 支付成功返回 URL。 |
| `OVERPAY_DECLINE_URL` | 支付被拒绝时返回的 URL。 |
| `OVERPAY_FAIL_URL` | 支付出错时返回的 URL。 |
| `OVERPAY_LANGUAGE` | 支付表单语言，例如 `ru`、`en`；留空时机器人尝试传递用户语言。 |
| `OVERPAY_TEST_MODE` | 向 Overpay 沙箱发送交易。 |
| `OVERPAY_RECURRING_ENABLED` | 在收银台请求银行卡令牌，并使用该令牌扣款以自动续订。 |
| `OVERPAY_VERIFY_WEBHOOK_SIGNATURE` | 要求入站 webhook 提供 HTTP Basic auth（Shop ID / Secret Key）。 |
| `OVERPAY_TRUSTED_IPS` | 可选的受信任 webhook 来源 IP 列表。 |

### Stripe

Stripe 创建托管 Checkout Sessions，并通过用户不在线时的 off-session PaymentIntents 确认应用管理的自动续订。webhook 端点设置为 `WEBHOOK_BASE_URL` 加 `/webhook/stripe`。

推荐 Stripe 事件：`checkout.session.completed`、`checkout.session.expired`、`payment_intent.succeeded`、`payment_intent.payment_failed`、`payment_intent.canceled`。

| 变量 | 用途 |
| --- | --- |
| `STRIPE_ENABLED` | 启用 Stripe。 |
| `STRIPE_SECRET_KEY` | Stripe Dashboard 提供的私密 API 密钥。 |
| `STRIPE_WEBHOOK_SECRET` | 端点签名密钥（`whsec_...`），用于验证 `Stripe-Signature`。 |
| `STRIPE_BASE_URL` | Stripe API 基础 URL，默认 `https://api.stripe.com`。 |
| `STRIPE_RETURN_URL` | Checkout 成功后返回 URL；留空使用机器人链接。 |
| `STRIPE_CANCEL_URL` | 取消 Checkout 时返回 URL；留空使用 `STRIPE_RETURN_URL`。 |
| `STRIPE_PAYMENT_METHOD_TYPES` | Checkout 支付方式类型，以逗号分隔，默认 `card`。 |
| `STRIPE_SUPPORTED_CURRENCIES` | 界面允许显示的可选币种列表，以逗号分隔；留空表示不做本地过滤。 |
| `STRIPE_RECURRING_ENABLED` | 保存 Checkout 支付方式，用于 off-session 自动续订。 |
| `STRIPE_VERIFY_WEBHOOK_SIGNATURE` | 使用 `STRIPE_WEBHOOK_SECRET` 验证 `Stripe-Signature`。 |
| `STRIPE_WEBHOOK_TOLERANCE_SECONDS` | webhook 签名允许的时钟偏差，默认 `300`。 |

## 套餐与旧版定价

<a id="тарифы-и-legacy-цены"></a>

推荐通过管理后台的**系统 → 套餐**配置套餐，JSON 保存到 `TARIFFS_CONFIG_PATH`。

存在且通过验证的 JSON 目录时，按时长套餐的价格、周期及邀请奖励均从 JSON 读取。下列旧版变量只在没有 JSON 目录时使用。

| 变量 | 用途 |
| --- | --- |
| `TARIFFS_CONFIG_PATH` | 套餐 JSON 目录文件路径。 |
| `TARIFF_TRAFFIC_WARNING_LEVELS` | 流量预警百分比阈值。 |
| `1_MONTH_ENABLED` | 无 JSON 目录时，旧版 1 个月周期是否可用。 |
| `3_MONTHS_ENABLED` | 无 JSON 目录时，旧版 3 个月周期是否可用。 |
| `6_MONTHS_ENABLED` | 无 JSON 目录时，旧版 6 个月周期是否可用。 |
| `12_MONTHS_ENABLED` | 无 JSON 目录时，旧版 12 个月周期是否可用。 |
| `RUB_PRICE_1_MONTH`, `RUB_PRICE_3_MONTHS`, `RUB_PRICE_6_MONTHS`, `RUB_PRICE_12_MONTHS` | 旧版 RUB 价格，默认依次为 `200`、`600`、`1200`、`2400`。 |
| `STARS_PRICE_1_MONTH`, `STARS_PRICE_3_MONTHS`, `STARS_PRICE_6_MONTHS`, `STARS_PRICE_12_MONTHS` | 旧版 Stars 价格。 |
| `TRAFFIC_PACKAGES` | 旧版 RUB 流量包，格式为 `10:199,50:799`。 |
| `STARS_TRAFFIC_PACKAGES` | 旧版 Stars 流量包。 |

## 优惠码

<a id="промокоды"></a>

具体使用流程见[优惠码](../features/promocodes.md)。

| 变量 | 用途 |
| --- | --- |
| `PROMO_DURATION_MULTIPLIER_MAX` | 优惠码的订阅时长最大倍数，默认 `12.0`。 |
| `PROMO_TRAFFIC_MULTIPLIER_MAX` | 优惠码的发放流量最大倍数，默认 `12.0`。 |
| `MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED` | 已导入 Remnashop 代码的兼容模式：先按原始大小写查找，再按常规方式转换为大写。 |

## 试用、邀请返利与通知

<a id="пробный-период-рефералы-и-уведомления"></a>

这些上游设置可在管理后台调整；当前 MVP 不启用试用、礼品和营销流程。

| 变量 | 用途 |
| --- | --- |
| `TRIAL_ENABLED` | 启用试用期。 |
| `TRIAL_PAYMENT_ENABLED` | 激活试用前要求付款成功，默认 `False`。 |
| `TRIAL_PAYMENT_PRICE` | 以默认支付币种计价的试用激活价格，默认 `100`。 |
| `TRIAL_PAYMENT_STARS_PRICE` | 以 Telegram Stars 计价的试用激活价格。`0` 隐藏此次付款的 Stars 选项，默认 `100`。 |
| `TRIAL_DURATION_DAYS` | 试用时长。 |
| `TRIAL_TRAFFIC_LIMIT_GB` | 试用流量限额。 |
| `TRIAL_PREMIUM_TRAFFIC_LIMIT_GB` | 试用独立高级流量限额；`0` 关闭单独限制。 |
| `TRIAL_PREMIUM_TITLE` | 首页试用订阅高级流量区域的标题。留空使用用户语言的默认标题，也可在“系统 → 套餐 → 试用期”中设置。 |
| `TRIAL_HWID_DEVICE_LIMIT` | 试用 HWID 设备上限。留空保留面板或默认限制，`0` 表示不限。 |
| `TRIAL_DAYS_STRATEGY` | 试用有效期内购买套餐的规则：`add_remaining` 将剩余试用天数加入付费时长，`start_from_payment` 从付款日期开始计算付费时长。由管理员决定，用户付款时不能修改。 |
| `TRIAL_TRAFFIC_STRATEGY` | 试用流量限额策略。 |
| `TRIAL_WITHOUT_OAUTH_ENABLED` | 允许未绑定 OAuth 提供方时激活试用，默认开启。关闭时要求绑定 Telegram 或任意外部 OAuth 身份；一次性邮箱域名仍要求 Telegram。旧名称 `TRIAL_WITHOUT_TELEGRAM_ENABLED` 作为已弃用环境别名保留。 |
| `TRIAL_SQUAD_UUIDS` | 试用 Internal Squads，以逗号分隔；留空使用 `USER_SQUAD_UUIDS`。 |
| `TRIAL_PREMIUM_SQUAD_UUIDS` | 试用高级 Internal Squads，以逗号分隔；留空不为试用提供高级访问权限。 |
| `GIFTS_ENABLED` | 在“奖励”中启用新的[礼品订阅](../features/gifts.md)购买，默认 `True`。后台位置为“设置 → 常规”。关闭后，已付费礼品的历史、交付和激活仍可用。 |
| `REFERRAL_PROGRAM_ENABLED` | 全局启用普通邀请链接、归因、欢迎奖励及支付奖励，默认 `True`。关闭后，“奖励”仍保留优惠码输入和可用礼品；推广伙伴计划独立运行。 |
| `REFERRAL_ONE_BONUS_PER_REFEREE` | 开启后，双方获得时长奖励仅限首次事件：个人成功购买，或通过 `REFERRAL_GIFT_ACTIVATION_ENABLED` 纳入统计的礼品激活。 |
| `REFERRAL_GIFT_ACTIVATION_ENABLED` | 默认 `true`。礼品成功激活时，按领取人已有邀请关系计入奖励；显式 `false` 关闭统计。购买礼品和打开链接不计入，不追溯旧激活记录。 |
| `REFERRAL_WELCOME_BONUS_DAYS` | 通过邀请链接注册的新用户欢迎奖励。它不替代试用期，奖励结束后被邀请人仍可激活试用。 |
| `REFERRAL_WELCOME_BONUS_ADDS_TO_TRIAL` | 将欢迎奖励天数加入免费试用：受邀注册时不另建奖励订阅，而延长被邀请人的试用。仅在免费试用开启时生效，默认 `False`。 |
| `REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED` | 允许向未绑定 Telegram 的用户发放邀请欢迎奖励；一次性邮箱域名仍要求 Telegram。 |
| `REFERRAL_WEBAPP_LINK_ENABLED` | 在 Web App 奖励区显示网站邀请链接。两个链接显示开关至少开启一个。 |
| `REFERRAL_TELEGRAM_LINK_ENABLED` | 在 Web App 奖励区显示 Telegram 机器人邀请链接。两个链接显示开关至少开启一个。 |
| `LEGACY_REFS` | 允许旧式 `/start ref_<telegram_id>` 链接，其载荷包含邀请人的 Telegram/用户 ID。 |
| `DISPOSABLE_EMAIL_DOMAINS` | 一次性邮箱域名，以逗号或换行分隔。默认使用内置的已核验快照；这些邮箱只有绑定 Telegram 后才能使用试用和邀请欢迎奖励。 |
| `REFERRAL_BONUS_DAYS_1_MONTH`, `REFERRAL_BONUS_DAYS_3_MONTHS`, `REFERRAL_BONUS_DAYS_6_MONTHS`, `REFERRAL_BONUS_DAYS_12_MONTHS` | 无 JSON 目录时，旧版邀请人奖励。JSON 套餐使用 `referral_bonus_days_inviter`。 |
| `REFEREE_BONUS_DAYS_1_MONTH`, `REFEREE_BONUS_DAYS_3_MONTHS`, `REFEREE_BONUS_DAYS_6_MONTHS`, `REFEREE_BONUS_DAYS_12_MONTHS` | 无 JSON 目录时，旧版被邀请人奖励。JSON 套餐使用 `referral_bonus_days_referee`。 |
| `SUBSCRIPTION_NOTIFICATIONS_ENABLED` | 启用订阅提醒的 Telegram 渠道。 |
| `SUBSCRIPTION_EMAIL_NOTIFICATIONS_ENABLED` | 配置 SMTP 且用户有邮箱时，启用订阅生命周期的邮件通知渠道。 |
| `SUBSCRIPTION_NOTIFY_ON_EXPIRE` | 到期当天通知。 |
| `SUBSCRIPTION_NOTIFY_AFTER_EXPIRE` | 到期后通知。 |
| `SUBSCRIPTION_NOTIFY_DAYS_BEFORE` | 提前多少天提醒。 |
| `SUBSCRIPTION_NOTIFY_HOURS_BEFORE` | 额外提前多少小时提醒。 |
| `SUBSCRIPTION_NOTIFICATION_WORKER_TICK_SECONDS` | 本地通知检查周期。 |

### 推广伙伴计划

<a id="партнёрская-программа"></a>

推广伙伴计划默认关闭。常规参数在 Web App 管理后台的
**设置 → 营销计划 → 推广伙伴计划**中修改。收款信息加密密钥只能通过环境变量设置，
管理 API 不会返回该密钥。管理后台设置立即应用于运行中的 backend；
切换 `PARTNER_PROGRAM_ENABLED` 时，当前管理员会话会重新读取 Mini App 公开数据，
无需重启或整页刷新。

| 变量 | 用途 |
| --- | --- |
| `PARTNER_PROGRAM_ENABLED` | 启用新申请、归因和佣金入账，默认 `False`。关闭后，历史记录及已产生义务的处理仍可用。 |
| `PARTNER_AUTO_ENROLLMENT_ENABLED` | 默认 `False`。在管理后台应用该设置且推广伙伴计划开启时，为全部现有未封禁用户直接创建 active 档案，无需申请。通过环境配置启用时，以及新用户的情况，在首次机器人／Web App 流程中创建档案。已有 paused/closed 档案、个人佣金比例及财务历史不变。关闭只停止后续自动加入，不删除已建档案。 |
| `PARTNER_REFERRAL_PROGRAM_DISABLED` | 默认 `False`。推广伙伴计划开启时，仅阻止已有伙伴档案用户的普通邀请操作。active 伙伴的旧邀请链接会创建伙伴首次触达归因；paused/closed 伙伴链接不创建归因。其他用户继续使用普通邀请计划。切换不会追溯修改已有关系和奖励。 |
| `PARTNER_WITHDRAWALS_ENABLED` | 允许活跃伙伴创建新的提现申请，默认 `True`。关闭后，已有申请仍可处理。 |
| `PARTNER_BALANCE_PAYMENT_ENABLED` | 允许 active 伙伴用伙伴余额全额或部分支付。部分支付时，余额不足部分交给所选外部渠道，并满足其最低金额要求；默认 `True`。 |
| `PARTNER_CLIENT_WELCOME_BONUS_ENABLED` | 允许通过 active 伙伴链接注册的新客户获得一次欢迎奖励。使用普通邀请欢迎奖励的额度和套餐，默认 `False`。 |
| `PARTNER_CLIENT_PAYMENT_BONUS_ENABLED` | 按客户套餐矩阵中“被邀请人奖励”列向伙伴客户发放天数，默认 `False`。不追溯旧支付。 |
| `PARTNER_ONE_BONUS_PER_CLIENT` | 开启后，套餐矩阵奖励天数只针对用户历史上的首次成功付款，即使该付款早于归因或奖励启用。此设置不影响普通邀请计划，默认 `True`。 |
| `PARTNER_DEFAULT_COMMISSION_BPS` | 默认佣金比例，以基点表示：`3000` 为 30%。允许 `0..10000`；个人比例保存在伙伴档案和入账快照中。 |
| `PARTNER_COMMISSION_HOLD_DAYS` | 佣金由 pending 转入可用余额前等待的天数，范围 `0..365`，默认 `0`。 |
| `PARTNER_ELIGIBLE_CURRENCIES` | 币种 JSON 数组，例如 `["RUB","USD"]`，默认 `["RUB"]`。列表不能为空，不同币种余额绝不合并。 |
| `PARTNER_EXCLUDED_SALE_MODES` | 不计佣金的内部销售模式 JSON 数组，默认 `[]`。 |
| `PARTNER_WITHDRAWAL_METHODS_JSON` | 手动打款方式的 JSON 数组，默认 `[]`，推荐通过管理后台专用表单编辑。 |
| `PARTNER_TELEGRAM_LINK_ENABLED`, `PARTNER_WEBAPP_LINK_ENABLED` | 分别启用 Telegram/Web App 伙伴链接，均默认 `True`，至少保留一个渠道。 |
| `PARTNER_APPLICATION_MESSAGE_MAX_LENGTH` | 申请文本的最大长度，范围 `10..10000`，默认 `2000` 字符。申请文本本身至少 10 字符。 |
| `PARTNER_MAX_ACTIVE_WITHDRAWALS` | 伙伴同时处于活跃状态的提现申请上限，范围 `1..50`，默认 `3`。 |
| `PARTNER_REAPPLICATION_ENABLED`, `PARTNER_REAPPLICATION_COOLDOWN_DAYS` | 允许被拒后重新申请，并设置 `0..3650` 天等待期。默认关闭重新申请，等待期为 `0`；管理员显式重新开放另行处理。 |
| `PARTNER_LIST_PAGE_LIMIT` | 用户和管理员列表的分页大小上限，范围 `10..200`，默认 `50`。 |
| `PARTNER_APPLICATION_RATE_LIMIT_HOURS`, `PARTNER_WITHDRAWAL_RATE_LIMIT_SECONDS` | 服务端按用户限制申请频率：分别为 `1..8760` 小时（默认 `24`）和 `1..3600` 秒（默认 `10`）。 |
| `PARTNER_AUDIT_RETENTION_DAYS`, `PARTNER_REQUISITES_RETENTION_DAYS` | 伙伴审计记录保留期为 `0..3650` 天，`0` 及默认值表示永久保留；已完成打款的收款信息密文保留期为 `1..3650` 天，默认 `90` 天。脱敏信息和财务历史保留。 |
| `PARTNER_REQUISITES_ENCRYPTION_KEY` | 仅 `.env`：采用 URL 安全 base64 编码的 16/24/32 字节 AES 密钥；生产使用 32 字节。没有有效密钥时，为安全起见禁用收款信息创建及明文查看。 |
| `PARTNER_REQUISITES_KEY_ID` | 当前密钥的非秘密版本标识，最长 32 字符，默认 `v1`。仅在数据完成原子轮换后修改。 |

生成 32 字节密钥：

```bash
openssl rand -base64 32 | tr '+/' '-_'
```

完整设置、打款处理、核对报告、密钥轮换和回退见[推广伙伴计划指南](../features/partner-program.md)。

## 支持

<a id="поддержка"></a>

具体流程见[用户支持与工单](../features/support.md)。

| 变量 | 用途 |
| --- | --- |
| `SUPPORT_TICKETS_ENABLED` | 启用 Mini App 工单。 |
| `SUPPORT_ADMIN_TELEGRAM_NOTIFICATIONS_ENABLED` | 通过 Telegram／日志渠道通知管理员新工单及用户回复。 |
| `SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED` | 向管理员发送邮件通知。 |
| `SUPPORT_TICKET_MAX_BODY_LENGTH` | 消息最大长度。 |
| `SUPPORT_TICKET_MAX_SUBJECT_LENGTH` | 主题最大长度。 |
| `SUPPORT_TICKET_RATE_LIMIT_PER_HOUR` | 每小时新建工单上限。 |
| `SUPPORT_MESSAGE_RATE_LIMIT_PER_MINUTE` | 用户每分钟工单消息上限。 |
| `SUPPORT_IMAGE_RATE_LIMIT_PER_DAY` | 用户每日工单图片上限。 |
| `SUPPORT_ADMIN_NOTIFICATION_COOLDOWN_SECONDS` | Telegram／日志通知之间的间隔。 |
| `SUPPORT_ADMIN_EMAIL_COOLDOWN_SECONDS` | 邮件通知之间的间隔。 |

## 日志

<a id="логирование"></a>

部分设置可在管理后台调整。

| 变量 | 用途 |
| --- | --- |
| `LOG_LEVEL` | `DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`。 |
| `LOGS_PAGE_SIZE` | 管理后台日志分页大小。 |
| `LOG_CHAT_ID` | 接收服务通知的 Telegram 聊天／群组 ID。 |
| `LOG_THREAD_ID` | 共用日志聊天的话题／线程 ID。 |
| `LOG_SUPPORT_THREAD_ID` | 支持话题／线程 ID。 |
| `LOG_NEW_USERS` | 记录新注册。 |
| `LOG_PAYMENTS` | 记录支付。 |
| `LOG_SUPPORT` | 记录支持工单。 |
| `LOG_PROMO_ACTIVATIONS` | 记录优惠码激活。 |
| `LOG_TRIAL_ACTIVATIONS` | 记录试用激活。 |
| `LOG_SUSPICIOUS_ACTIVITY` | 记录可疑活动。 |
| `LOG_ADMIN_ACTIONS` | 记录管理员操作。 |

## 收据、连接链接与内联功能

<a id="чеки-ссылки-подключения-и-inline"></a>

| 变量 | 用途 |
| --- | --- |
| `NALOGO_INN` | LKNPD 使用的自雇者税号（INN）。 |
| `NALOGO_PASSWORD` | LKNPD /“我的税务”服务密码。 |
| `NALOGO_API_URL` | LKNPD API 基础 URL。 |
| `NALOGO_RECEIPT_NAME_SUBSCRIPTION` | 订阅收据中的条目名称。 |
| `NALOGO_RECEIPT_NAME_TRAFFIC` | 流量包收据中的条目名称。 |
| `CRYPT4_ENABLED` | 为连接链接启用 happ crypt4。 |
| `CRYPT4_REDIRECT_URL` | 连接按钮的包装 URL。 |
| `CRYPT4_LINK_CACHE_TTL_SECONDS` | crypt4 链接缓存的 TTL。 |
| `MY_DEVICES_SECTION_ENABLED` | 显示“我的设备”区域。 |
| `INLINE_REFERRAL_THUMBNAIL_URL` | 邀请内联结果的预览图。 |
| `INLINE_USER_STATS_THUMBNAIL_URL` | 用户统计内联结果的预览图。 |
| `INLINE_FINANCIAL_STATS_THUMBNAIL_URL` | 财务统计内联结果的预览图。 |
| `INLINE_SYSTEM_STATS_THUMBNAIL_URL` | 系统统计内联结果的预览图。 |
