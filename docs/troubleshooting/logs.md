# 日志

<a id="логи"></a>

日志用于解释目标账号、服务、节点或操作的实际结果。先从[接手说明](../handoff.md)核对环境，再按[统一管理台指南](../admin-console-guide.md) F02／F03、UC-05 排查；当前进度与证据统一查[本轮本地最终验收](../implementation-plan.md#本轮本地最终验收)。

> 本页保留上游功能的日志说明。当前 MVP 使用管理员手动激活、无支付；Telegram 和支付相关检查仅适用于已配置相应上游能力的环境。本项目开发与验收使用[隔离开发环境](../development/project-local.md)。

## 常用命令

<a id="основные-команды"></a>

以下命令**仅用于本项目已存在的本机隔离栈**，在仓库根目录、选定正确 Docker context 后运行，不会启动容器。先定义携带完整项目参数的临时 shell 函数，本页后续 Compose 日志命令沿用它：

```bash
project_compose() {
  docker compose --project-name my-vps-obj --env-file .env.project-dev \
    -f docker-compose-dev.yml -f docker-compose.remnawave-dev.yml \
    -f docker-compose.project-dev.yml --profile seed "$@"
}
project_compose ps
project_compose logs --since 10m --tail 100 backend worker frontend migrate
```

快速摘要也可用 `npm run project:logs`。上游或生产部署须使用其记录中的项目、环境文件及 Compose 组合，不能把本地函数换一个目录就用于生产。分享日志前移除密钥、Cookie、完整订阅、邮箱及其他不必要的个人信息；不要公开完整 `docker compose config` 输出。

## 重点查找的内容

<a id="что-искать"></a>

- `migrate` 中的迁移错误。
- `backend` 中的会话、权限、服务操作、资源影响预览和面板请求错误；Telegram／支付日志仅在对应模式启用时相关。
- `worker` 中的账号权限、独立交付、权益变更、用量同步及队列处理问题。结合对象标识、操作阶段和时间，超时先核对结果，不盲目重复写入。
- `frontend` 中 `/api`、`/auth` 及主题资源的代理错误。
- 当前流程的登录及权限错误；外部认证只检查已启用提供方。`429` 按 `Retry-After` 等待，不能通过持续重试制造噪声。

服务业务状态、任务执行和远端观测分别记录；日志中“请求成功”不等于连接已停用，也不把缺失样本记为零或正常。

## frontend 代理、`/api`、`/auth` 与主题资源

<a id="проксирование-frontend-api-auth-и-ассеты-тем"></a>

`frontend` 是 Mini App 的 nginx 容器，提供静态资源，并将 Web App 路由转发到 backend 的内部 WebApp 服务 `backend:8081`。

先查看 nginx 日志：

```bash
project_compose logs -f frontend
```

出现 `404`、`502`、`upstream` 或 `connect() failed` 时，检查路由：

- `/api/*` 和 `/auth/*` 应进入 `frontend:80`，再由 frontend 转发至 `backend:8081`。
- `/webapp-logo`、`/webapp-uploaded-logo/*`、`/webapp-favicon/*`、`/webapp-theme-css/*` 和 `/webapp-theme-assets/*` 同样经过 frontend 代理。
- 外部反向代理不得将 `/api` 或 `/auth` 单独转发到 webhook 服务 `backend:8080`。

仅对本机已启动的默认端口做只读检查；配置改过端口时相应调整。外部站点检查另需核对任务范围：

```bash
curl -i http://127.0.0.1:18082/health
curl -i http://127.0.0.1:18082/api/bootstrap
curl -i http://127.0.0.1:18082/webapp-theme-css/dark/style.css
```

如果 `/health` 正常，而 `/api/bootstrap` 或主题资源失败，同时查看 frontend 和 backend：

```bash
project_compose logs -f frontend backend
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

本节仅用于已启用 Telegram 的兼容环境；本项目默认关闭时，`/auth/telegram/start` 不可用并不证明网站故障。认证错误通常出现在 `backend` 中，因为 Telegram Mini Apps `initData`、Telegram OAuth `id_token`、nonce/state 及会话验证都在 backend 的 WebApp 服务中进行。

```bash
project_compose logs -f backend
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

配置生效与重建步骤见[维护说明](maintenance.md)。先区分数据库覆盖值、环境变量与镜像变化；不要为读日志重建容器，也不要用 `project:up` 重播已有环境 seed。完成已授权的修改后，只读核对目标日志与健康状态。

另见[常见问题](issues.md)和[部署](../getting-started/deployment.md)。
