# 初始配置

<a id="первичная-настройка"></a>

先按[隔离源码流程](../development/project-local.md)启动本项目，再核对有效配置。当前业务是一账号多份独立服务、管理员人工开通、无支付；管理操作以客户与节点为主线，见[统一管理台指南](../admin-console-guide.md)。本文是配置参考，当前进度只查[本轮本地最终验收](../implementation-plan.md#本轮本地最终验收)。

项目的配置和业务记录分开管理：

- 环境文件：本项目本地使用 `.env.project-dev`，通用部署使用所选 Compose 的 `.env`；保存启动配置、基础设施、固定密钥和 Remnawave 基础访问凭据。
- Web App 管理后台：首次启动后，推荐通过这里修改产品设置。

管理后台允许覆盖的设置保存在数据库中，并优先于环境文件生效。**本项目的套餐模板、独立服务、资源绑定与操作记录是数据库业务对象**，不通过 `TARIFFS_CONFIG_PATH` 编辑。该 JSON 路径及旧版定价、支付等字段属于上游兼容能力，不能当作本项目套餐配置入口。

> 本页说明 Minishop 上游保留的配置能力，不表示本项目 MVP 已启用支付、试用、礼品或余额等商业流程。本项目当前采用管理员手动激活、无支付及一个账号管理多个独立服务；范围见[需求文档](../requirements.md)，本地运行使用[项目隔离开发环境](../development/project-local.md)。

完整变量说明参见[环境变量参考](../configuration/env-vars.md)。

## 最小 `.env` 配置

<a id="минимальный-env"></a>

**仅上游兼容新装示例：**在单独准备的安装目录、确认不存在有效 `.env` 后才使用下列命令。本项目本地配置采用 `deploy/dev/project-dev.env.example`，已有线上配置按 [production-access](../development/project-local.md#production-access)维护，不复制开发模板覆盖。

```bash
test -e .env || cp .env.example .env
nano .env
```

以下为通用配置用途；按实际启用模式填写，不为本项目开启旧商业流程：

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
| `SUBSCRIPTION_GUIDES_ENABLED`, `SUBSCRIPTION_GUIDES_BOT_MENU_ENABLED` | 上游 Web App 和机器人按钮中的内置安装指南，默认开启。本项目的独立服务教程使用下述专用入口。 |
| `SUBSCRIPTION_GATEWAY_ENABLED` | 上游 `/s/<token>` 公开订阅网关开关，默认开启；本项目已退役该入口，开启此项不能恢复访问。 |
| `PANEL_API_URL`, `PANEL_PUBLIC_URL`, `PANEL_API_KEY`, `PANEL_WEBHOOK_SECRET` | Remnawave 基础集成。`PANEL_API_URL` 供 backend／worker 使用；统一管理台的高级维护入口只接受显式且通过安全校验的 `PANEL_PUBLIC_URL`，留空或非法时不回退到 API 地址。旧用户详情链接的兼容回退不适用于高级维护。面板 webhook 密钥必须与本项目一致；变更面板配置前核对影响范围。 |

本项目从“我的服务”中的具体服务获取独立订阅链接。教程由登录后的 `/api/service-guides` 读取随程序提供的 `deploy/examples/independent-services-guides.json`，不使用旧网关、面板教程配置或后台 JSON 覆盖值。交付条件与操作见[独立服务交付](../development/service-delivery.md)。

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

恢复访问前先确认目标环境、备份和允许中断的服务，并检查数据库覆盖值；不能把旧环境的恢复命令直接用于本项目开发栈。通用部署的处理顺序：

1. 在 `.env` 中设置 `WEBAPP_ENABLED=True`。
2. 在该环境已核对的 Compose 目录中重建受影响容器；通用单文件部署可用 `docker compose up -d --force-recreate backend frontend`。本项目隔离环境必须携带完整 project-dev overlays，不能省略项目名和环境文件。
3. 使用具有 `owner` 或 `admin` 角色的账号登录用户中心，并在管理后台检查该设置。

## 通过管理后台配置

<a id="настройка-через-админку"></a>

首位所有者引导是账号权限写入。**仅在已确认的新安装、邮箱已验证且确实尚无所有者时**，在目标 Compose 目录执行 `docker compose exec backend python backend/scripts/bootstrap_owner.py --email owner@example.com`，邮箱必须替换为已授权账号。已有本地测试栈使用其测试账号，不重做所有者引导。详情参见[独立运行模式指南](../features/telegram-optional.md)。

本项目先核对连接配置，再从套餐模板和客户详情人工开通服务，按指南 F01／F02 跟踪交付与故障；节点、线路、组变更按 F06／F07 预览存量影响并确认。主题、支持及通知仅按已启用范围配置。

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

上游安装指南从 Remnawave Panel 读取 Subscription Page 配置，`SUBSCRIPTION_PAGE_CONFIG_PATH` 和 `SUBSCRIPTION_PAGE_CONFIG_JSON` 是备用来源或显式覆盖。本项目的独立服务教程使用前述 `/api/service-guides`，不要用上游覆盖项排查或修改它。

## 文件数据

<a id="файловые-данные"></a>

`deploy/examples/` 中的 Compose 示例从所选文件旁的 `./data` 挂载主题、标志、旧套餐目录等应用文件；仓库根 `docker-compose.yml` 使用命名卷 `shop-data`。项目 overlays 可能改变挂载来源，应按最终 Compose 配置核对；文件目录不包含数据库中的全部独立服务记录。

无论使用绑定目录还是命名卷，`migrate`、`backend` 和 `worker` 都应挂载同一来源到 `/app/data`。手动修改 Compose 文件时，不要移除 `migrate` 的这一挂载，否则 `docker compose run --rm migrate` 无法读取 `TARIFFS_CONFIG_PATH` 指向的 `data/tariffs.json`。

**仅新建的上游兼容绑定目录：**确认当前目录、`data` 不是指向其他项目的链接、目标数据库和镜像正确，且已获迁移及重建授权后执行。下列递归权限修改与迁移不能用于修复未知的线上挂载；已有目录先备份并核对所有权。

```bash
mkdir -p data/themes data/webapp-logo data/tariffs
touch data/locales-overrides.json
chown -R 10001:10001 data
chmod -R u+rwX data
docker compose run --rm migrate
docker compose up -d --force-recreate backend worker
```

在同一已确认的 Compose 目录做只读权限检查：

```bash
docker compose exec backend sh -lc 'id; test -w /app/data/themes'
```

## 延伸阅读

<a id="дополнительные-разделы"></a>

- [环境变量](../configuration/env-vars.md)：完整的 `.env` 变量参考。
- [管理后台](../features/admin-panel.md)：配置覆盖值和设置白名单的工作方式。
- [独立服务](../development/independent-services.md)：本项目套餐模板与服务模型。
- [套餐](../features/tariffs.md)：上游 JSON 套餐目录兼容参考。
- [用户余额](../features/user-balance.md)：上游币种、充值及余额兼容参考，不是一期启用步骤。
- [Web App / Mini App](../features/web-app.md)：Mini App 域名、安装指南及代理配置。
- [登录方式](../features/login-methods.md)：邮箱验证码、邮箱与密码、Telegram、Google、
  Yandex 和通行密钥（passkey）。
- [支持与工单](../features/support.md)：支持工单和通知。
- [部署](deployment.md)：Docker Compose、反向代理、Caddy/Angie/Nginx 及更新。
