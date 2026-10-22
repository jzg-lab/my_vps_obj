# 日志

<a id="логи"></a>

日志是排查启动、支付、webhook 及 Remnawave Panel 同步问题的主要依据。

> 本页保留上游功能的日志说明。当前 MVP 使用管理员手动激活、无支付；Telegram 和支付相关检查仅适用于已配置相应上游能力的环境。本项目开发与验收使用[隔离开发环境](../development/project-local.md)。

## 常用命令

<a id="основные-команды"></a>

```bash
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f frontend
docker compose logs migrate
```

## 重点查找的内容

<a id="что-искать"></a>

- `migrate` 中的迁移错误。
- `backend` 中的 Telegram webhook 和支付 webhook 错误。
- `worker` 中的 webhook 队列及后台任务问题。
- `frontend` 中 `/api`、`/auth` 及主题资源的代理错误。
- Mini App 和 Telegram OAuth 的认证错误。

## frontend 代理、`/api`、`/auth` 与主题资源

<a id="проксирование-frontend-api-auth-и-ассеты-тем"></a>

`frontend` 是 Mini App 的 nginx 容器，提供静态资源，并将 Web App 路由转发到 backend 的内部 WebApp 服务 `backend:8081`。

先查看 nginx 日志：

```bash
docker compose logs -f frontend
```

出现 `404`、`502`、`upstream` 或 `connect() failed` 时，检查路由：

- `/api/*` 和 `/auth/*` 应进入 `frontend:80`，再由 frontend 转发至 `backend:8081`。
- `/webapp-logo`、`/webapp-uploaded-logo/*`、`/webapp-favicon/*`、`/webapp-theme-css/*` 和 `/webapp-theme-assets/*` 同样经过 frontend 代理。
- 外部反向代理不得将 `/api` 或 `/auth` 单独转发到 webhook 服务 `backend:8080`。

从外部快速检查：

```bash
curl -i https://app.domain.com/health
curl -i https://app.domain.com/api/bootstrap
curl -i https://app.domain.com/auth/telegram/start
curl -i https://app.domain.com/webapp-theme-css/dark/style.css
```

如果 `/health` 正常，而 `/api/bootstrap` 或主题资源失败，同时查看 frontend 和 backend：

```bash
docker compose logs -f frontend backend
```

配置检查位置：

- 前端 nginx：`deploy/docker/frontend/nginx.conf`。
- 外部 Caddy/Angie/Nginx：`deploy/examples/caddy/Caddyfile`、`deploy/examples/angie/angie.conf.template` 或 `deploy/examples/nginx/nginx.conf.template`。
- Web App 域名：`SUBSCRIPTION_MINI_APP_URL`，必须是 frontend 的公开 HTTPS URL，不含 `/api`、`/auth` 或 webhook 路径。
- backend 的 WebApp 服务：`WEBAPP_ENABLED=True`、`WEBAPP_SERVER_HOST=0.0.0.0`、`WEBAPP_SERVER_PORT=8081`。

前后端分离部署时，额外检查：

- `frontend` 启动信息显示 `api base :: /api` 和预期的 `upstream :: ...`。
- 前端服务器可以访问 `WEBAPP_BACKEND_UPSTREAM`。
- 使用受保护上游时，前端 nginx 添加 `X-Minishop-Edge-Token`；不带令牌直接请求后端 `/api/bootstrap` 应返回 `401/403`。
- 后端域名的 webhook 路由仍进入 `backend:8080`，而非 `frontend` 或 `backend:8081`。

## Mini App 与 Telegram OAuth 认证

<a id="авторизация-mini-app-и-telegram-oauth"></a>

认证错误通常出现在 `backend` 中，因为 Telegram Mini Apps `initData`、Telegram OAuth `id_token`、nonce/state 及会话验证都在 backend 的 WebApp 服务中进行。

```bash
docker compose logs -f backend
```

查找以下消息：

- `Telegram WebApp initData hash mismatch`。
- `Telegram WebApp initData auth_date is stale`。
- `Failed to validate Telegram WebApp initData`。
- `Telegram OAuth nonce mismatch`。
- `Telegram OAuth ID token is stale`。
- `Failed to validate Telegram OAuth ID token`。
- `Telegram OAuth token exchange failed`。
- `Telegram OAuth callback failed`。
- `WebApp auth failed`。

对于 Telegram 内的 Mini App，检查：

- `SUBSCRIPTION_MINI_APP_URL` 与 BotFather Mini Apps 中设置的域名一致。
- 打开的是 HTTPS frontend 域名，而非 backend webhook 域名。
- 服务器时间已同步，否则会出现 `auth_date is stale`。
- `WEBAPP_AUTH_MAX_AGE_SECONDS` 没有设得过小。
- `WEBAPP_SESSION_SECRET` 在重启之间保持不变。

对于 Mini App 外的 Telegram OAuth，检查：

- `TELEGRAM_OAUTH_CLIENT_ID` 和 `TELEGRAM_OAUTH_CLIENT_SECRET`。
- Telegram OAuth/BotFather 中的回调地址：`https://app.domain.com/auth/telegram/callback`。
- `/auth/telegram/start` 和 `/auth/telegram/callback` 经前端 nginx 转发到 `backend:8081`。
- 回调后浏览器没有出现 `telegram_auth=invalid_state`、`invalid_token`、`not_configured`、`unauthorized` 或 `failed` 状态。

路由和 OAuth 配置详情参见 [Telegram](../features/login-methods.md#telegram)。

## 修改配置后

<a id="после-изменения-конфигурации"></a>

```bash
docker compose up -d
docker compose logs -f backend worker frontend
```

另见[常见问题](issues.md)和[部署](../getting-started/deployment.md)。
