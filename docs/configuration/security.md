# 安全

<a id="безопасность"></a>

本项目的安全配置包括固定密钥、环境隔离、公开入口及管理权限。先从[本地源码流程](../development/project-local.md)核对环境；账号和服务操作遵循[统一管理台指南](../admin-console-guide.md)的 UA-02／UA-20，不因有 SSH 别名或历史运维记录就获得生产操作授权。

> 本页同时记录上游保留功能的安全要求。支付、试用等描述不表示本项目 MVP 已启用这些功能；当前范围见[需求文档](../requirements.md)。本地验证使用[隔离开发环境](../development/project-local.md)，不得将现有生产节点作为可随意重置的测试资源。

## 密钥

<a id="секреты"></a>

- `WEBAPP_SESSION_SECRET` 必须在重启之间保持不变，否则 Web App 会话会失效。
- `EMAIL_AUTH_SECRET` 保护邮箱验证码和免密链接；已有环境不得为排障随意重新生成固定密钥。
- `WEBHOOK_SECRET_TOKEN` 用于保护 Telegram webhook。
- `PANEL_WEBHOOK_SECRET` 是上游账号级 Panel webhook 的校验配置；本项目对应旧回调已退役，不靠它驱动独立服务同步，也不要求为独立服务重新开启旧回调。
- 支付令牌和 webhook 密钥应保存在 `.env` 或管理后台设置中，并相应限制服务器访问权限。

仅为新环境生成尚未配置的密钥；下列命令只输出随机值，不自动修改现有配置：

```bash
openssl rand -hex 32
```

## Telegram 防刷

<a id="telegram-антифлуд"></a>

Telegram 机器人的更新先经过防刷中间件，再进入需要访问数据库的
资料同步、频道检查及操作日志环节。默认策略较宽松，不应影响正常的连续点击；
它会在来自同一来源的大量消息和回调导致数据库写入、支付处理激增或
Telegram FloodWait 之前，将这类异常突发流量丢弃。

设置位于**管理后台 → 系统 → 设置 → 系统 → Telegram 防刷**。
对于常规的私聊销售机器人，默认值通常足够，因此 `.env.example` 未列出这些参数。
只有实际流量表明阈值需要放宽或收紧时才修改。

- `TELEGRAM_DROP_NON_PRIVATE_UPDATES=True` 会在高开销中间件之前丢弃群组和
  频道更新。如果机器人不需要在私聊之外工作，请保持开启。
- `TELEGRAM_ANTIFLOOD_ENABLED=True` 启用按用户、按聊天的限流。
  某个数值限额设为 `0`，只会关闭该项限额。
- `TELEGRAM_ANTIFLOOD_WINDOW_SECONDS=60` 设置共用的滑动窗口。
  默认值适合正常的频繁按钮操作：每个窗口内所有更新 `180` 次、消息 `120` 次、
  回调 `240` 次、内联查询 `60` 次、`/start` 命令 `30` 次、高开销回调 `60` 次。
- `TELEGRAM_ACTION_COOLDOWN_ENABLED=True` 会去除同一用户完全重复的支付和试用回调。
  不同支付载荷不会合并，因此正常的下单流程彼此独立。

## 管理员访问

<a id="доступ-администраторов"></a>

- 管理后台访问由内部账号保存的 `owner` 和 `admin` 角色决定。
- 首位所有者需在验证邮箱后，通过服务器命令指定。
- `ADMIN_IDS` 仅用作旧管理员的一次性导入来源，且要求 Telegram 身份已可靠绑定。
- 管理员使用本项目同一账号进入客户与节点管理流程；外部高级维护仍使用外部面板自己的认证，不承诺 SSO。

## 公开 URL

<a id="публичные-url"></a>

- 使用 Telegram 等已启用 webhook 时，`WEBHOOK_BASE_URL` 指向 backend 的 webhook 服务。
- 上游单订阅部署的 Panel `WEBHOOK_URL` 采用 `WEBHOOK_BASE_URL` 加 `/webhook/panel`；本项目账号级 Panel 和支付回调返回 `410 legacy_business_retired`，不能将配置该地址当作独立服务接入步骤。
- `SUBSCRIPTION_MINI_APP_URL` 必须指向 frontend/Mini App 域名。
- 不要在 `SUBSCRIPTION_MINI_APP_URL` 后追加 `/api`、`/auth` 或 webhook 路径。
- `PUBLIC_APP_URL` 是浏览器用户中心及邮件使用的公开地址；本机隔离环境的回环 HTTP 地址不用于公网。
- 高级维护只接受显式且通过安全校验的 `PANEL_PUBLIC_URL`，不从内部 `PANEL_API_URL` 自动推导，也不在浏览器链接中携带 API 密钥或 Cookie。

## 前后端分离部署

<a id="раздельное-размещение-frontend-и-backend"></a>

- 用户浏览器应只访问前端源：`https://app.example.com/api/...`。
- 将 `WEBAPP_API_BASE_URL` 保持为 `/api`；在前端 JavaScript 中填写独立后端源并不能提供保护，反而会将 WebApp API 直接暴露给用户。
- 连接受保护的上游时，配置前端 nginx 的 `WEBAPP_BACKEND_UPSTREAM` 和 `MINISHOP_EDGE_TOKEN`，由 nginx 在服务端向上游请求添加令牌。
- 不得将 `MINISHOP_EDGE_TOKEN` 放入运行时配置或前端包；任何浏览器可见的令牌都能在开发者工具中读到。
- 令牌、防火墙和 VPN 保护应用于 WebApp API 端口 `backend:8081`。Telegram 及保留的上游 webhook 路由使用 `backend:8080`，不得要求 `MINISHOP_EDGE_TOKEN`；其中已退役的支付和账号级 Panel 回调仍返回 410。
- 上游为 `https://bot.example.com` 时，设置 Host/SNI（`WEBAPP_BACKEND_UPSTREAM_HOST=bot.example.com`）及路由顺序，让 `/api/*`、`/auth/*`、`/open-app`、标志、主题和网站图标路径在通用 webhook 兜底路由之前转发至 `8081`。

## Webhook IP 白名单

<a id="ip-allowlist-вебхуков"></a>

- `WEBHOOK_BASE_URL` 的反向代理必须通过 `X-Forwarded-For` 传递发送方的真实 IP。
- `TRUSTED_PROXIES` 必须包含 backend 前最后一跳代理的 IP/CIDR，否则支付 webhook 处理器会用代理或 Docker 网关的 IP 检查白名单。
- 域名位于 Cloudflare 后方时，只有最近的不受信任跳点属于 [Cloudflare 官方网络](https://www.cloudflare.com/ips/)，backend 才接受 `CF-Connecting-IP`。无需将这些公开 CIDR 加入 `TRUSTED_PROXIES`。
- 未设置 `TRUSTED_PROXIES` 时，应用、Compose 配置和安装程序默认信任回环地址及标准服务 `frontend`、`caddy`、`nginx`、`angie`、`newt`、`newt-2`。`host:` 名称只解析为单独的 IP，每分钟刷新一次；服务不存在时忽略。这样可支持多个代理和容器重建，无需手动修改地址。
- 使用自定义代理时，在下方标准列表中追加其精确 IP/CIDR 或 `host:服务名`。安装程序会自动添加所选容器名称；使用 host-network 时，会添加应用 Docker 网络的精确网关地址。操作员显式设置的值会保留。升级时请替换 `.env` 中旧的“信任所有私有网络”配置。
- 如果确实需要信任任意代理跳点，可使用 `0.0.0.0/0,::/0`，但前提是 backend 不直接公开，且外部代理会清理入站 `X-Forwarded-For`。

标准安装无需设置该变量。需要额外代理时，可使用：

```dotenv
TRUSTED_PROXIES=127.0.0.1,::1,host:frontend,host:caddy,host:nginx,host:angie,host:newt,host:newt-2,host:my-proxy
```

受信任入站代理列表不会授权向内部网络发起出站连接。
公开 SMTP、支付 API 和监控服务继续使用常规设置；
内部地址及自建 API 网关通过下述管理员配置授权。

## 其他安全要求

<a id="дополнительно"></a>

Xray Checker 和 Uptime Kuma 的出站请求会检查实际 DNS 地址及重定向。
内部监控服务器按操作员在 `.env` 或管理后台设置的当前 URL 的精确主机名和端口授权。
默认信任管理员设置：保存、替换和重置 URL 会立即更新授权及连接，无需重启 backend。
已发起的请求使用原设置完成，新请求使用当前地址；旧主机和旧端口不再保留授权。
不允许链路本地地址，包括元数据地址。

SMTP 同样检查 DNS，连接已验证的 IP，并使用原始主机名验证 TLS。
内部 SMTP 仅按 `.env` 或管理后台当前明确设置的 `SMTP_HOST`、`SMTP_PORT` 和
`SMTP_FALLBACK_PORTS` 授权。修改无需重启，下一次连接即生效；
已移除的主机和端口不再获得授权。

PayKilla 汇率 URL 只接受 HTTP(S)；同步和异步请求路径都会限制响应大小，
并检查 DNS 和每次重定向。可通过 `.env` 或管理后台中的 `PAYKILLA_EXCHANGE_RATE_URL`
指定内部汇率服务。两条路径均使用当前地址，修改 URL 会更新授权及汇率缓存的选择，无需重启。

支付 API 只向当前 `<PROVIDER>_BASE_URL` 指定的地址发送密钥，包括其协议和端口。
该地址可在 `.env` 中设置或在管理后台保存；此前保存的设置也会生效。
管理后台修改无需重启，已开始的请求使用原设置完成。
显式配置的 API 网关可使用私有 IP 或内部主机名。保存前验证 HTTP(S) 地址，
连接时检查 DNS；禁止元数据等服务地址。重定向至其他源时不会转发密钥，
即使目标是支付渠道的常规地址也不例外。

独立 worker 每 5 秒从数据库刷新 SMTP 和支付渠道设置，包括重置回 `.env` 值的操作。
修改地址无需重启 worker；backend 进程中的配置在保存后立即生效。

上游订阅指南文件只能位于 `data/subpage-config` 内，或使用 `.env` 中原始配置的路径。
读取仅限普通文件，大小上限为 4 MiB；管理员修改路径不会获得读取任意服务器文件的权限。

本项目独立服务教程读取随源码交付的 `deploy/examples/independent-services-guides.json`，不使用上述旧指南配置覆盖；参见[初始配置](../getting-started/configuration.md)。

- 所有公开域名均应使用 HTTPS。
- 限制服务器及 `.env` 的访问权限。
- 关注支付 webhook 和面板 webhook 的日志。
- 轮换密钥后，重启相应服务并检查 webhook。

另见[环境变量](env-vars.md)和[部署](../getting-started/deployment.md)。
