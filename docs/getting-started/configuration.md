# 初始配置

<a id="первичная-настройка"></a>

项目支持两层配置：

- `.env`：启动配置、基础设施、固定密钥和 Remnawave 基础访问凭据。
- Web App 管理后台：首次启动后，推荐通过这里修改产品设置。

管理后台将覆盖值保存在数据库中，并优先于 `.env` 生效。支付、外观、支持、通知、旧版定价及大多数用户参数都可以这样管理。套餐在**系统 → 套餐**中单独编辑，并保存到 `TARIFFS_CONFIG_PATH` 指定的 JSON 文件。

> 本页说明 Minishop 上游保留的配置能力，不表示本项目 MVP 已启用支付、试用、礼品或余额等商业流程。本项目当前采用管理员手动激活、无支付及一个账号管理多个独立服务；范围见[需求文档](../requirements.md)，本地运行使用[项目隔离开发环境](../development/project-local.md)。

完整变量说明参见[环境变量参考](../configuration/env-vars.md)。

## 最小 `.env` 配置

<a id="минимальный-env"></a>

从简短示例开始：

```bash
cp .env.example .env
nano .env
```

至少填写以下配置：

| 变量 | 用途 |
| --- | --- |
| `TELEGRAM_ENABLED`, `BOT_TOKEN` | Telegram 开关及机器人令牌。仅通过浏览器使用时，设置 `TELEGRAM_ENABLED=False` 并将令牌留空。 |
| `ADMIN_IDS` | 可选的一次性旧管理员导入来源，要求已验证其 `telegram_id`；日常访问权限由账号角色控制。 |
| `WEBHOOK_BASE_URL` | backend webhook 域名的公开 URL。Remnawave Panel 的 `WEBHOOK_URL` 为 `WEBHOOK_BASE_URL` 加 `/webhook/panel`，例如 `https://app.example.com/webhook/panel`。 |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Compose 和 backend 使用的 PostgreSQL 凭据。 |
| `WEBAPP_ENABLED` | 启用 Web App 和管理后台。首次启动时保持 `True`。 |
| `WEBAPP_SESSION_SECRET` | Web App 会话的固定密钥。 |
| `EMAIL_AUTH_SECRET` | 邮箱验证码和免密登录链接独立使用的固定密钥。 |
| `PUBLIC_APP_URL` | 浏览器用户中心的公开 HTTPS URL，用于邮件和付款后返回。 |
| `WEBHOOK_SECRET_TOKEN` | Telegram webhook 的固定密钥令牌。 |
| `SUBSCRIPTION_MINI_APP_URL` | Mini App/frontend 的公开 HTTPS URL，例如 `https://app.domain.com/`。Telegram 按钮打开该地址，BotFather 也填写该地址；不要追加 `/api` 或 webhook 路径。 |
| `SUBSCRIPTION_GUIDES_ENABLED`, `SUBSCRIPTION_GUIDES_BOT_MENU_ENABLED` | Web App 和机器人按钮中的内置安装指南。默认开启，通常在管理后台修改即可。 |
| `SUBSCRIPTION_GATEWAY_ENABLED` | 通过公开链接 `/s/<token>` 向客户端应用提供订阅。默认开启，开关位于管理后台的“连接指南”中。 |
| `PANEL_API_URL`, `PANEL_PUBLIC_URL`, `PANEL_API_KEY`, `PANEL_WEBHOOK_SECRET` | Remnawave 基础集成。`PANEL_API_URL` 用于 backend 和 worker 的请求；`PANEL_PUBLIC_URL` 用于管理员在浏览器中访问面板。如果 API 使用内部地址，请单独设置浏览器可访问的公开地址；留空则继续用 `PANEL_API_URL` 生成链接。在 Remnawave Panel 中设置 webhook 密钥，再将同一值填入机器人设置。这些值建议保存在 `.env` 中，也可按需通过管理后台覆盖。 |

可用以下命令生成 `WEBAPP_SESSION_SECRET` 和 `WEBHOOK_SECRET_TOKEN`：

```bash
openssl rand -hex 32
```

如果这些密钥留空，应用会为每个进程生成密钥；重启后 Web App 会话会失效，Telegram webhook 的 `secret_token` 也会改变。

如果只能通过 SOCKS5 访问 Telegram Bot API，可添加可选配置
`TELEGRAM_BOT_PROXY_URL=socks5://host:port`。该设置作用于 `backend` 和 `worker`
中的机器人客户端出站请求，服务端 Telegram OAuth 的 token/JWKS 请求也会自动使用同一代理。
若需让 OAuth 直连，设置 `TELEGRAM_OAUTH_USE_BOT_PROXY=False`。入站 webhook 和
浏览器打开的 OAuth 页面不经过此代理。完整规则、Docker 注意事项及回退方式见
[Telegram Bot API 的 SOCKS5 代理](../configuration/env-vars.md#socks5-proxy-для-telegram-bot-api)。

## Web App 被关闭时

<a id="если-web-app-выключен"></a>

`WEBAPP_ENABLED=False` 会关闭用户 Web App，同时关闭管理后台。此时无法进入**系统 → 设置**，也无法通过界面重新启用 Web App。

恢复访问的方法：

1. 在 `.env` 中设置 `WEBAPP_ENABLED=True`。
2. 重建 backend/frontend 容器，例如执行 `docker compose up -d --force-recreate backend frontend`。
3. 使用具有 `owner` 或 `admin` 角色的账号登录用户中心，并在管理后台检查该设置。

## 通过管理后台配置

<a id="настройка-через-админку"></a>

启动后，先验证首位所有者的邮箱，再执行 `docker compose exec backend python backend/scripts/bootstrap_owner.py --email owner@example.com`，登录用户中心并打开管理后台。详情参见[独立运行模式指南](../features/telegram-optional.md)。

上游完整功能的推荐初始配置顺序如下；套餐销售和支付设置不属于本项目当前 MVP 的启用步骤：

1. **系统 → 设置 → Remnawave Panel**：检查 `PANEL_API_URL`、`PANEL_API_KEY`、`PANEL_WEBHOOK_SECRET` 和基础 squad。在 Remnawave 设置旁，管理后台会显示面板应填写的 `WEBHOOK_URL`，例如 `https://app.example.com/webhook/panel`。
2. **系统 → 套餐**：创建 JSON 套餐目录，选择 Internal Squads，配置按时长或按流量的计费模式、高级 squad、下单时可调整的限额以及购买后单独加购的套餐包。
3. **系统 → 设置 → 连接指南**：确认 Remnawave Panel 返回所需的 Subscription Page 配置。只有需要临时替换面板配置时，才启用 JSON 覆盖。
4. **系统 → 设置 → 支付**：启用所需支付渠道，并填写密钥。
5. **外观**：设置名称、主题、标志、网站图标和强调色。
6. **系统 → 设置 → 支持 / 通知**：设置工单、日志聊天、邮件通知和提醒。
7. **常规设置**：填写支持、文档和服务状态链接；如有需要，配置必须加入的频道。

通过管理后台进行的修改写入 `app_setting_overrides` 表。重置覆盖值后，重新使用 `.env` 或代码中的默认值。

## 应保留在 `.env` 中的配置

<a id="что-оставить-только-в-env"></a>

并非所有配置都适合移到数据库。以下内容保留在 `.env` 中：

- `TELEGRAM_ENABLED`、启用 Telegram 时所需的机器人令牌，以及用于一次性导入的可选 `ADMIN_IDS` 列表。
- `TELEGRAM_BOT_PROXY_URL` 和可选的 OAuth 直连开关 `TELEGRAM_OAUTH_USE_BOT_PROXY`。
- PostgreSQL、Redis、端口及 Compose 参数。
- `WEBHOOK_BASE_URL`，因为 Telegram webhook 会在启动时注册。
- 固定密钥 `WEBAPP_SESSION_SECRET`、`EMAIL_AUTH_SECRET` 和 `WEBHOOK_SECRET_TOKEN`。
- `WEBAPP_THEMES_DIR`、`TARIFFS_CONFIG_PATH` 及底层 TTL、连接池和 worker 参数。
- Remnawave 的基础访问凭据；即使为了方便允许在管理后台修改，也应保留这里的基础配置。

安装指南配置通常无需存放在本地 `data` 文件中：默认情况下，应用从 Remnawave Panel 读取 Subscription Page 配置。`SUBSCRIPTION_PAGE_CONFIG_PATH` 和 `SUBSCRIPTION_PAGE_CONFIG_JSON` 用作备用来源，或用于管理后台的显式覆盖。

## 文件数据

<a id="файловые-данные"></a>

Compose 示例从所选 `docker-compose.yml` 旁的本地 `./data` 目录挂载数据，其中包含套餐、主题、标志及其他应用文件。

`./data` 会挂载到 `migrate`、`backend` 和 `worker` 的 `/app/data`。手动修改 Compose 文件时，不要移除 `migrate` 的这一挂载，否则 `docker compose run --rm migrate` 无法读取 `TARIFFS_CONFIG_PATH` 指向的 `data/tariffs.json`。

首次启动前，创建目录并将其交给容器用户：

```bash
mkdir -p data/themes data/webapp-logo data/tariffs
touch data/locales-overrides.json
chown -R 10001:10001 data
chmod -R u+rwX data
docker compose run --rm migrate
docker compose up -d --force-recreate backend worker
```

可用以下命令检查权限：

```bash
docker compose exec backend sh -lc 'id; touch /app/data/themes/test && rm /app/data/themes/test'
```

## 延伸阅读

<a id="дополнительные-разделы"></a>

- [环境变量](../configuration/env-vars.md)：完整的 `.env` 变量参考。
- [管理后台](../features/admin-panel.md)：配置覆盖值和设置白名单的工作方式。
- [套餐](../features/tariffs.md)：JSON 套餐目录和套餐编辑器。
- [用户余额](../features/user-balance.md)：币种、充值、购买支付和余额管理。
- [Web App / Mini App](../features/web-app.md)：Mini App 域名、安装指南及代理配置。
- [登录方式](../features/login-methods.md)：邮箱验证码、邮箱与密码、Telegram、Google、
  Yandex 和通行密钥（passkey）。
- [支持与工单](../features/support.md)：支持工单和通知。
- [部署](deployment.md)：Docker Compose、反向代理、Caddy/Angie/Nginx 及更新。
