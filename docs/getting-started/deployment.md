# 生产部署

<a id="production-развертывание"></a>

本文说明项目拆分为 `backend`、`frontend` 和 `worker` 后的生产启动方式。
开始前，按[初始配置](configuration.md)填写最小 `.env`。完整变量参考见[环境变量](../configuration/env-vars.md)；首次登录后，大多数产品设置可通过 Web App 管理后台调整。

> 以下保留 Minishop 上游部署、镜像、迁移和商业功能说明。上游安装脚本及公开镜像不代表本项目当前版本；支付、试用等能力也不代表当前 MVP 已启用。本项目使用管理员手动激活、无支付及一个账号管理多个独立服务的方案。开发和验收必须使用[项目隔离开发环境](../development/project-local.md)，不得将现有生产节点作为测试资源；本文不构成生产部署、真实 Node 或固定／独享出口的验收证据。

## 快速开始

<a id="быстрый-старт"></a>

```bash
cp .env.example .env
nano .env
docker compose up -d --build
docker compose ps
docker compose logs -f backend worker frontend
```

## 交互式安装向导

<a id="интерактивный-install-wizard"></a>

在新服务器上，下载并运行安装脚本：

```bash
curl -fsSL https://gitlab.com/3252a8/remnawave-minishop/-/raw/main/scripts/install.sh -o install.sh
sh install.sh
```

<!-- GitHub 上的备用安装脚本链接（未启用）：

```bash
curl -fsSL https://raw.githubusercontent.com/3252a8/remnawave-minishop/main/scripts/install.sh -o install.sh
sh install.sh
```
-->

安装向导使用数字菜单和 `y/n` 确认，支持以下操作：

- 使用完整的俄语界面，默认建议安装目录 `/opt/remnawave-minishop`。
- 下载所选 Compose 配置（`Caddy`、`Angie`、`Nginx`、`Pangolin/Newt`、`no-proxy`，或复用现有 eGames 反向代理的配置）。
- 接入服务器上已运行的反向代理：除 eGames 方案外，还可查找已运行的 Nginx/Angie/Caddy 容器，将其连接到 Minishop 的 Docker 网络；使用 host-network 时则代理到本地端口。向导会添加带有 `BEGIN/END remnawave-minishop` 标记的托管配置块，执行配置检查（`nginx -t` / `angie -t` / `caddy validate`），失败则回退。对于 eGames，它会复用现有配置中的实际 TLS 方案（`TCP/443` 或带 PROXY protocol 的 Unix socket），并且只接受 SAN 覆盖新增主机名的证书。
- 通过独立、可撤销的步骤使用 Pangolin（Newt）发布 Web App：“将 Web App 接入 Pangolin（Newt）”和“断开 Web App 与 Pangolin（Newt）”菜单项会通过 `.env` 中的 `COMPOSE_FILE` 添加或移除 `docker-compose.pangolin.yml`，不修改主部署配置。
- 生成最小 `.env`，包括密码和固定密钥。
- 在签发 TLS 证书前，检查 `WEBHOOK_HOST` 和 `MINIAPP_HOST` 的 A 记录。
- 为 Nginx 使用 Certbot Cloudflare DNS-01 或独立 HTTP-01 模式签发证书，也可使用已放入 `ssl/<hostname>/` 的证书文件。
- 覆盖现有文件前保存备份。
- 为应用文件准备可写的 `data/`，必要时将目录所有者改为容器用户 `10001:10001`。
- 执行 `docker compose pull && docker compose up -d`。
- 通过 `docker compose ps` 和 `migrate` 日志检查当前服务栈。
- 从支持的机器人迁移：Remnashop 和旧版 `remnawave-tg-shop`。
- 选择 frontend 到 backend WebApp API 的连接方式：同源、受保护的上游或 Rathole 隧道。

常规流程不会询问仓库及 ref，默认使用 `3252a8/remnawave-minishop` 的 `main`。
测试其他分支、标签或派生仓库时，在启动前指定来源：

```bash
MINISHOP_INSTALL_REPO=3252a8/remnawave-minishop \
MINISHOP_INSTALL_REF=main \
sh install.sh
```

Remnashop 迁移首先执行不写入的检查（`dry-run`），显示简要结果，并将完整
JSON 和原始输出保存到 `.installer/`。如果选择当前 Compose 数据库，向导会建议将
目标数据库及主要部署文件备份到 `backups/pre-remnashop-migration-*`，并提供 `restore.sh`。
检查成功后，应用迁移的确认项默认值为 `Y`：按 Enter 会执行迁移，输入 `n` 则停止且不写入。
如果提供旧 Remnashop 的 `.env`，向导会将 `APP_CRYPT_KEY`、Remnawave API 设置，
以及 `payment_gateways` 表中受支持的支付渠道设置传给导入程序。
应用迁移后，向导更新兼容设置，重启 `backend`、`worker` 和 `frontend`；
eGames 配置还会执行 `nginx -t` 并重新加载或重启 eGames Nginx。
随后向管理员和日志聊天发送 Telegram 通知，最后打印 Remnawave Panel、Telegram
及支付渠道的新 webhook URL。

旧版 `remnawave-tg-shop` 的迁移采用兼容数据库升级流程：向导尝试从旧数据库容器
自动构造源 DSN，将旧数据库的 `pg_dump` 保存到 `backups/pre-remnawave-tg-shop-source-*`，
使用 `.env` 中新的 `POSTGRES_*` 重建目标数据库卷，将备份恢复到目标 Compose 数据库，
然后运行 `migrate` 服务。旧数据卷 `remnawave-tg-shop-db-data` 不会被删除。

### 安装向导会询问什么

<a id="что-спрашивает-install-wizard"></a>

向导尽量提供安全的默认值。在带有公开域名的常规 VPS 上，
如果显示的默认值符合实际情况，通常可以直接按 Enter。下表将俄语提示的含义译为中文，
并不表示上游安装向导已经提供中文界面。

| 问题 | 含义 | 常见选择 |
| --- | --- | --- |
| 安装目录 | 保存下载的 `docker-compose.yml`、`.env`、代理配置，以及后续 `data/` 和 `backups/` 的目录。 | 若服务器没有特殊目录规划，保留 `/opt/remnawave-minishop`。 |
| 部署方案 | 应用向外公开的方式。 | 新的公开服务器使用 `Caddy HTTPS`；偏好 Nginx 语法且需要自动证书时使用 `Angie HTTPS`；已管理证书时使用 `Nginx HTTPS`；入站端口关闭时使用 `Pangolin/Newt`；外部平台终止 TLS 时选择无代理；同机已通过 eGames 或其他 Nginx/Angie/Caddy 容器运行 Remnawave 时，选择现有反向代理方案。 |
| 接入现有反向代理 | 现有代理方案中的选项：自动识别 eGames（`TCP/443` 或 Unix socket）、通用接入已运行的 Nginx/Angie/Caddy 容器，或跳过。 | eGames 脚本安装的 Remnawave 使用 eGames 方案，其他情况使用通用接入。向导会复用实际 TLS 监听方式，检查证书 SAN 是否覆盖两个新增主机名；`nginx -t`、`angie -t` 或 `caddy validate` 失败时回退配置。 |
| Docker Compose 项目名称 | Docker 网络、数据卷和容器的名称前缀。 | 保留 `remnawave-minishop`；仅在同一服务器需要多个独立服务栈时修改。 |
| Docker 镜像标签 | backend、worker、frontend 镜像版本。 | 常规上游安装保留 `latest`，或指定已发布的具体版本标签。 |
| 是否启用 Telegram 机器人 | `TELEGRAM_ENABLED` 开关。 | 使用邮箱的浏览器模式选择“否”。 |
| Telegram 机器人令牌 | BotFather 提供的 `BOT_TOKEN`。 | 仅在启用 Telegram 时必填。 |
| Telegram Bot API 出站请求的 SOCKS5 代理 | `backend` 和 `worker` 可选的 `TELEGRAM_BOT_PROXY_URL`。 | 留空表示直连，或填写 `socks5://host:port`；含凭据的值在向导中只显示脱敏版本。 |
| 服务端 Telegram OAuth token/JWKS 是否使用 SOCKS5 代理 | `backend` 的可选 `TELEGRAM_OAUTH_USE_BOT_PROXY`。 | 填写代理后默认选择“是”；只有需要 OAuth 直连时才选择“否”，不影响用户浏览器。 |
| 旧管理员 Telegram ID | 按明确的 Telegram 绑定关系一次性导入角色，可选。 | 新安装留空，首位所有者通过已验证邮箱指定。 |
| SMTP 主机及发件人邮箱 | 发送登录验证码的邮件服务。 | 独立运行模式必填；服务器要求认证时，另行设置 SMTP 凭据。 |
| PostgreSQL 用户、密码及数据库 | Minishop 内部数据库凭据。 | 用户和库名可保留默认值；向导自动生成密码，按 Enter 可接受。 |
| Web App 名称 | 界面显示的应用名称。 | 可保留 `remnawave-minishop`，稍后在设置中修改。 |
| Remnawave Panel API URL | 面板 API 地址，通常为 `https://panel.example.com/api`。 | 填写以 `/api` 结尾的面板公开 URL。 |
| Remnawave Panel API 密钥 | 面板用于读取和修改用户的令牌。 | 填写具有所需权限的 API 令牌；面板位于 Cookie 代理后方时，还需填写 Cookie。 |
| Remnawave Panel 访问方式 | 直连 Panel API，或通过 eGames 反向代理访问远程面板；此选择独立于 Minishop 自身的发布方案。 | 另一台服务器上的面板由 eGames 脚本安装时，选择第二项并填写访问 Cookie 或完整访问 URL。 |
| Remnawave Panel webhook 密钥 | 面板发送至 Minishop 的 webhook 签名密钥。 | 可接受自动生成的值，但必须在 Remnawave Panel 中设置同一密钥。 |
| Telegram OAuth client secret | BotFather Web Login 的密钥，用于 Telegram 外的浏览器登录。 | 仅需要 Telegram Mini App 时可留空。 |
| `WEBHOOK_HOST` / `MINIAPP_HOST` | 不含 `https://`、路径和端口的公开域名。 | 例如 `webhooks.example.com` 和 `app.example.com`。Caddy/Angie/Nginx/eGames 方案要求 DNS 指向服务器或其前方的代理。 |
| `HTTP_BIND` / `HTTPS_BIND` | Caddy/Angie/Nginx 监听入站 HTTP/HTTPS 的 IP 和端口。 | 通常为 `0.0.0.0:80` 和 `0.0.0.0:443`；不能只填 IP 而不填端口。 |
| `WEB_SERVER_BIND` / `FRONTEND_BIND` | no-proxy/eGames 方案直接公开 backend 和 frontend 的端口。 | no-proxy 通常使用 `0.0.0.0:8080` 和 `0.0.0.0:8082`；eGames 建议使用 `127.0.0.1:8080` 和 `127.0.0.1:8082`，仅供本机 Nginx 访问。 |
| `WEBHOOK_PUBLIC_URL` / `MINIAPP_PUBLIC_URL` | no-proxy/eGames 方案中 Telegram、支付渠道和用户访问应用的公开 URL。 | 生产环境必须使用 HTTPS URL。no-proxy 本地检查可临时使用 `http://127.0.0.1:...`。 |
| `FRONTEND_BACKEND_MODE` | 前端 nginx 访问 WebApp API 端口 `8081` 的方式。 | 常规 Compose 使用 `same-origin`；独立前端服务器使用 `protected-upstream`；私有隧道使用 `rathole`。所有模式下浏览器 API 基础路径均保持 `/api`。 |
| `WEBAPP_BACKEND_UPSTREAM` | 前端 nginx 为 `/api`、`/auth`、`/open-app` 及 Web App 资源使用的服务端上游。 | 常规 Compose 为 `http://backend:8081`；受保护的后端域名模式为 `https://bot.example.com`；Rathole 为 `http://rathole-server:18081`。 |
| `MINISHOP_EDGE_TOKEN` | 前端 nginx/API 边缘代理与后端 WebApp API 之间的服务端密钥。 | 用于受保护的公开后端上游。不要加入前端 JavaScript，也不要要求 webhook 端口 `8080` 携带该令牌。 |

Remnawave Panel 集成单独配置。新安装未发现相关参数时，直接按 Enter 会跳过此步骤，
写入空值而非 `change_me`。Minishop 可以启动，但同步、订阅发放及其他依赖面板的操作
在完成配置前不可用。

输入参数后，向导会安全地请求 `/system/stats`，检查 HTTP 状态、
`Content-Type: application/json` 和响应结构。远程面板位于 eGames 后方时，可填写
标准 `name=value`、`Cookie: name=value`、`Set-Cookie: name=value; ...`，
或形如 `https://panel.example.com/auth/login?name=value` 的完整访问 URL。
向导只提取并保存 Cookie 请求头；带多个查询参数的 URL、控制字符和用 JWT 代替 Cookie
都会被拒绝。访问 Cookie 用于通过外部反向代理，不能替代 `PANEL_API_KEY`。

“已通过 eGames 安装 Remnawave”方案仅用于 Minishop 接入同一服务器的 eGames Nginx。
面板在其他服务器时，可选择适合 Minishop 的任意发布方案，再在单独的 Panel API
接入步骤中配置 eGames 保护。检查失败后默认建议跳过集成；只有显式选择另一选项
才能保存未验证的值，这适用于安装时面板暂时不可用的情况。

绑定字段 `HTTP_BIND`、`HTTPS_BIND`、`WEB_SERVER_BIND` 和 `FRONTEND_BIND`
必须使用 `PORT` 或 `IP:PORT` 格式，例如 `80`、`0.0.0.0:80`、`<服务器IP>:80`、
`127.0.0.1:8080`。只填 IP 而不填端口是错误格式，Docker Compose 会将其视为
宿主机端口并报错 `invalid hostPort`。

新安装开始时，向导会检查 Docker Engine 和 Docker Compose。最低版本分别为
Docker Engine `25.0.0` 和 Docker Compose `2.20.2`，以支持当前 Compose 配置中的
`healthcheck.start_interval`。独立的 `docker-compose` 命令不再视为兼容运行环境；
向导要求现代 Docker CLI 插件，只使用 `docker compose`。

运行环境兼容时，向导显示检测到的版本，并询问一次是否升级 Engine 和 Compose 至最新稳定版。
对已经运行的服务器，默认回答为“否”，因为升级 Engine 可能重启守护进程，短暂影响其他容器。
版本缺失或低于最低要求时，会建议升级；拒绝则在下载和启动服务栈前停止安装。

Engine 从已配置的系统仓库（`apt`、`dnf/yum`、`apk`、`pacman`）升级至最新软件包。
Docker 官方便捷安装脚本只用于全新安装 Engine，不用于升级现有生产运行环境。
Compose 插件另从 GitHub 最新官方发行版下载，按发布的 SHA-256 校验并原子安装。
如果服务器不适合自动安装，请手动安装当前版本的 Docker Engine 和 Docker Compose 插件，
然后重新运行向导。

写入 `.env` 和 Compose 文件后，向导必定执行 `docker compose config --quiet`。
配置结构不兼容、无法识别 `start_interval`、Engine API 过旧或存在其他配置错误时，
不会执行 `pull` 和 `up`。向导会立即显示检测到的版本和具体提示，
完整输出保存到 `.installer/compose-last-error.log`。

`docker compose pull` 或 `docker compose up -d` 失败时，除 Docker 原始输出外，
向导还会对常见问题给出俄语说明：绑定地址错误、端口占用、服务器未分配该 IP、
Docker 守护进程未启动、无权访问 Docker socket、镜像仓库不可达或 `IMAGE_TAG` 不存在。
最近一次 Compose 错误的完整输出保存在安装目录内的 `.installer/compose-last-error.log`。

### 通过 SOCKS5 访问 Telegram Bot API

<a id="telegram-bot-api-через-socks5"></a>

向导只接受 `socks5://host:port` 或 `socks5://username:password@host:port`；
凭据中的特殊字符必须经过百分号编码。该值保存为 `TELEGRAM_BOT_PROXY_URL`，
重启后应用于 `backend` 和 `worker` 两个进程的 Bot API 出站调用。
填写代理后，向导还会单独询问 `backend` 的 OAuth token 端点和 JWKS 是否使用该代理，
默认为“是”。选择“否”会显式写入 `TELEGRAM_OAUTH_USE_BOT_PROXY=False`。

该配置不为入站 webhook 建立隧道：Telegram 仍需访问公开 HTTPS
`WEBHOOK_PUBLIC_URL`/`WEBHOOK_BASE_URL`。即使服务端 token/JWKS 请求走代理，
OAuth 授权页面仍通过浏览器自身的网络打开。Panel API 和支付客户端使用各自的连接路径。
Docker 中若未单独配置宿主机网关，不要用 `127.0.0.1` 访问宿主机代理，
因为容器中的回环地址指向容器自身。请从两个容器分别检查代理端点。

详细示例、协议限制和回退方法见
[Telegram Bot API 的 SOCKS5 代理](../configuration/env-vars.md#socks5-proxy-для-telegram-bot-api)。

常规 `docker compose up -d --build` 会启动：

- 带健康检查的 `postgres` 和 `redis`；PostgreSQL 健康检查会验证 `.env` 中的用户名和密码，而不只检查端口是否打开。
- 使用 backend 镜像的一次性 `migrate` 服务。
- 仅在迁移成功后启动的 `backend`。
- 仅在迁移成功后启动的 `worker`。
- 使用独立 nginx 镜像、不含 Python 运行环境的 `frontend`。

标准迁移路径是独立的 `migrate` 服务。`backend` 和 `worker` 启动时也会在
PostgreSQL advisory lock 保护下安全检查数据库结构，因此不通过 Compose 直接启动服务时，
也会补齐迁移，且不会在数据库结构变更上产生竞争。

再次运行时，向导会检查现有 PostgreSQL Docker 数据卷。
如果该卷已使用旧密码初始化，向导会在应用启动前停止，并建议恢复旧 `POSTGRES_PASSWORD`，
或在确实要进行全新安装时显式删除该卷。

## 现成的启动目录

<a id="готовые-папки-запуска"></a>

生产部署建议使用 `deploy/examples` 中独立的 Docker Compose 示例。每个目录都有自己的 `docker-compose.yml`、`.env.example` 和所需代理配置。

常规公开服务器优先选择 **Caddy**，它会自动签发和续期 HTTPS 证书，配置比手动管理 Nginx 更短。偏好 Nginx 语法时，可以使用 **Angie**，它是原生支持 ACME 的 Nginx 分支，也提供自动 HTTPS。

| 目录 | 适用场景 |
| --- | --- |
| [`deploy/examples/caddy`](https://gitlab.com/3252a8/remnawave-minishop/-/tree/main/deploy/examples/caddy) | 需要简单的公开 HTTPS 和自动 Let's Encrypt 证书。 |
| [`deploy/examples/angie`](https://gitlab.com/3252a8/remnawave-minishop/-/tree/main/deploy/examples/angie) | 需要 Caddy 式自动 HTTPS，同时使用 Nginx 配置语法；Angie 是原生支持 ACME 的 Nginx 分支。 |
| [`deploy/examples/nginx`](https://gitlab.com/3252a8/remnawave-minishop/-/tree/main/deploy/examples/nginx) | 已使用 Nginx，并能将 TLS 证书放在示例目录旁。 |
| [`deploy/examples/newt`](https://gitlab.com/3252a8/remnawave-minishop/-/tree/main/deploy/examples/newt) | 通过 Pangolin/Newt 发布服务，不开放应用服务器的入站端口。 |
| [`deploy/examples/no-proxy`](https://gitlab.com/3252a8/remnawave-minishop/-/tree/main/deploy/examples/no-proxy) | 直接开放 backend/frontend 的 HTTP 端口，或在外部 TLS 终止器后方检查服务栈。 |
| [`deploy/examples/split-protected-upstream`](https://gitlab.com/3252a8/remnawave-minishop/-/tree/main/deploy/examples/split-protected-upstream) | 前后端位于不同服务器，前端 nginx 将 `/api` 转发到受保护或私有的后端上游。 |
| [`deploy/examples/rathole`](https://gitlab.com/3252a8/remnawave-minishop/-/tree/main/deploy/examples/rathole) | 前后端位于不同服务器，WebApp API 通过私有 Rathole 隧道传输。 |
| 向导中的“已通过 eGames 安装 Remnawave，复用其 Nginx/TLS” | 同一主机已通过 [`eGamesAPI/remnawave-reverse-proxy`](https://github.com/eGamesAPI/remnawave-reverse-proxy) 安装 Remnawave Panel；向导使用 no-proxy Compose，将 backend/Mini App 路由加入检测到的 eGames `nginx.conf`，并在迁移后重新加载 Nginx。 |

<!-- GitHub 源文件 URL（未启用）：
https://github.com/3252a8/remnawave-minishop/tree/main/deploy/examples/caddy
https://github.com/3252a8/remnawave-minishop/tree/main/deploy/examples/angie
https://github.com/3252a8/remnawave-minishop/tree/main/deploy/examples/nginx
https://github.com/3252a8/remnawave-minishop/tree/main/deploy/examples/newt
https://github.com/3252a8/remnawave-minishop/tree/main/deploy/examples/no-proxy
https://github.com/3252a8/remnawave-minishop/tree/main/deploy/examples/split-protected-upstream
https://github.com/3252a8/remnawave-minishop/tree/main/deploy/examples/rathole
-->

## Caddy（推荐方案）

<a id="caddy-рекомендуемый-вариант"></a>

适用于 `WEBHOOK_HOST` 和 `MINIAPP_HOST` 的 DNS 记录指向应用服务器，且入站 `80/tcp` 和 `443/tcp` 已开放的场景。

```bash
cd deploy/examples/caddy
cp .env.example .env
nano .env
docker compose up -d
docker compose logs -f caddy backend worker frontend
```

至少修改 `.env` 中的以下配置：

- `WEBHOOK_HOST` 和 `MINIAPP_HOST`。
- 独立运行模式使用 `TELEGRAM_ENABLED=False`；启用 Telegram 时填写 `BOT_TOKEN`。
- `EMAIL_AUTH_SECRET`、`PUBLIC_APP_URL`、SMTP，以及首位所有者已验证的邮箱。
- `POSTGRES_PASSWORD`。
- `WEBAPP_SESSION_SECRET`、`WEBHOOK_SECRET_TOKEN`。
- `PANEL_API_URL`、`PANEL_API_KEY`、`PANEL_WEBHOOK_SECRET`。

需要自定义 Caddy 行为时，修改 Compose 旁的 `Caddyfile` 并重建容器：

```bash
docker compose up -d --force-recreate caddy
```

标准 `Caddyfile` 包含针对 `X-Telegram-Bot-Api-Secret-Token` 的全局日志过滤器。
整体替换配置文件时请保留该过滤器，防止 webhook 密钥写入 Caddy 日志。

## Angie

Angie 由原 Nginx 核心开发者创建，原生支持 ACME：像 Caddy 一样自动签发和续期
Let's Encrypt 证书，同时保留 Nginx 配置语法。适用于 `WEBHOOK_HOST` 和 `MINIAPP_HOST`
的 DNS 记录指向应用服务器，且入站 `80/tcp` 和 `443/tcp` 已开放的场景。

```bash
cd deploy/examples/angie
cp .env.example .env
nano .env
docker compose up -d
docker compose logs -f angie backend worker frontend
```

至少修改 `.env` 中的以下配置：

- `WEBHOOK_HOST` 和 `MINIAPP_HOST`。
- 独立运行模式使用 `TELEGRAM_ENABLED=False`；启用 Telegram 时填写 `BOT_TOKEN`。
- 用于邮箱登录的 `EMAIL_AUTH_SECRET`、`PUBLIC_APP_URL` 和 SMTP。
- `POSTGRES_PASSWORD`。
- `WEBAPP_SESSION_SECRET`、`WEBHOOK_SECRET_TOKEN`。
- `PANEL_API_URL`、`PANEL_API_KEY`、`PANEL_WEBHOOK_SECRET`。

容器启动时会将 `.env` 中的主机名填入配置：镜像 `docker.angie.software/angie:templated`
通过 gomplate 渲染 `angie.conf.template`，占位符为 `{{.Env.WEBHOOK_HOST}}` 和
`{{.Env.MINIAPP_HOST}}`。ACME 账号和证书保存在数据卷
`remnawave-minishop-angie-acme`（`/var/lib/angie/acme`）中，重建容器不会重新签发证书。
首次启动后，Angie 要等第一张证书签发完成才会响应 `443`，通常不到一分钟。

需要自定义 Angie 行为时，修改 Compose 旁的 `angie.conf.template` 并重建容器：

```bash
docker compose up -d --force-recreate angie
```

## Nginx

Nginx 方案在应用所在的同一 Docker 网络中运行 Nginx：

- `WEBHOOK_HOST` 转发至 `backend:8080`。
- `MINIAPP_HOST` 转发至 `frontend:80`。
- `frontend` 自行将内部 `/api`、`/auth` 和主题资源转发至 `backend:8081`。

```bash
cd deploy/examples/nginx
cp .env.example .env
nano .env
```

将 TLS 证书放入 `ssl/`：

```text
ssl/
  webhooks.example.com/
    fullchain.pem
    privkey.pem
  app.example.com/
    fullchain.pem
    privkey.pem
```

目录名必须与 `.env` 中的 `WEBHOOK_HOST` 和 `MINIAPP_HOST` 一致。

```bash
docker compose up -d
docker compose logs -f nginx backend worker frontend
```

需要修改请求头、限制或 TLS 设置时，编辑 `nginx.conf.template` 并重建 Nginx 容器：

```bash
docker compose up -d --force-recreate nginx
```

## Pangolin / Newt

此方案不开放应用服务器的入站端口。Newt 主动连接 Pangolin，公开域名通过 Pangolin 面板中的资源配置。

```bash
cd deploy/examples/newt
cp .env.example .env
nano .env
docker compose up -d
```

填写 `.env`：

- `WEBHOOK_HOST` 和 `MINIAPP_HOST`：Pangolin 资源的公开域名。
- `PANGOLIN_ENDPOINT`、`NEWT_ID`、`NEWT_SECRET`：Pangolin 站点／客户端设置中的值。
- 常规应用变量：`TELEGRAM_ENABLED`、`POSTGRES_PASSWORD`、密钥、SMTP 和 Remnawave 访问凭据；仅启用 Telegram 时需要 `BOT_TOKEN`。

在 Pangolin 中为该 Newt 站点创建两个 HTTP 资源：

| 公开域名 | 上游地址 |
| --- | --- |
| `https://webhooks.example.com` | `http://backend:8080` |
| `https://app.example.com` | `http://frontend:80` |

检查：

```bash
docker compose ps
docker compose logs -f newt backend worker frontend
```

### 为已安装的 Minishop 接入 Pangolin

<a id="подключение-pangolin-к-уже-установленному-minishop"></a>

上述 `Pangolin/Newt` 方案将 Newt 作为应用的唯一入口。Minishop 已使用其他方案
（Caddy、Angie、Nginx、no-proxy、eGames）安装时，也可稍后通过可撤销步骤添加
Pangolin 发布方式：安装向导提供“将 Web App 接入 Pangolin（Newt）”及
“断开 Web App 与 Pangolin（Newt）”菜单项。

接入时会将 `PANGOLIN_ENDPOINT`、`NEWT_ID` 和 `NEWT_SECRET` 写入 `.env`，
创建额外的 `docker-compose.pangolin.yml`，在同一 Docker 网络运行 `newt` 容器，
并通过 `.env` 中的 `COMPOSE_FILE` 启用。Pangolin 资源分别指向
`http://frontend:80`（Mini App）和 `http://backend:8080`（API/webhook）。
断开时会停止并删除 `newt` 容器，从 `COMPOSE_FILE` 移除该文件，
但保留 `.env` 中的 `NEWT_*` 值，便于再次接入。

## 无反向代理

<a id="без-обратного-прокси"></a>

此方案直接公开两个 HTTP 端口：

- backend/webhook：`WEB_SERVER_BIND`，默认为 `0.0.0.0:8080`。
- frontend/Mini App：`FRONTEND_BIND`，默认为 `0.0.0.0:8082`。

```bash
cd deploy/examples/no-proxy
cp .env.example .env
nano .env
docker compose up -d
```

应用容器不会自行签发 TLS 证书。实际使用 Telegram webhook 和 Mini App 时，公开 URL 必须为 HTTPS。此方案适用于本地检查、内部网络，或外部平台终止 HTTPS 后将流量转发到这些端口的场景。

本地检查：

```bash
curl http://127.0.0.1:8080/healthz
curl http://127.0.0.1:8082/health
docker compose logs -f backend worker frontend
```

根目录的 `docker-compose.yml` 用于从源码进行本地构建。`deploy/examples` 中的示例使用预构建的 Docker Hub 镜像，无需指定 `-f`。

## 前后端分离部署

<a id="раздельное-размещение-frontend-и-backend"></a>

分离部署时，浏览器不直接访问后端。`WEBAPP_API_BASE_URL` 保持 `/api`，由前端 nginx 在服务端代理到上游：

```text
browser -> https://app.example.com/api -> frontend nginx -> WEBAPP_BACKEND_UPSTREAM
```

后端提供两组不同的 HTTP 接口：

- `backend:8080`：公开 webhook 接口，用于 Telegram、支付渠道和 Remnawave Panel。
- `backend:8081`：WebApp API、认证和资源接口，供前端 nginx、私有网络、受保护上游或 Rathole 使用。

不另设后端 API 域名时，受保护上游通常如下：

```text
Telegram/payments/Panel -> https://bot.example.com/webhook/... -> backend:8080
frontend nginx         -> https://bot.example.com/api/...     -> backend:8081
frontend nginx         -> https://bot.example.com/auth/...    -> backend:8081
```

后端代理只能在转发到 `8081` 的 `/api/*`、`/auth/*`、`/open-app`、标志、主题和网站图标路径上要求 `X-Minishop-Edge-Token`。转发到 `8080` 的 webhook 路由不得要求该令牌。

检查配置：

```bash
docker compose -f deploy/examples/split-protected-upstream/frontend.docker-compose.yml config
docker compose -f deploy/examples/split-protected-upstream/backend.docker-compose.yml config
```

使用 Rathole 时，前端服务器运行 `rathole-server`，后端服务器运行 `rathole-client`，前端 nginx 设置 `WEBAPP_BACKEND_UPSTREAM=http://rathole-server:18081`。两台服务器之间只开放 Rathole 控制端口，例如 `2333`；服务端口 `18081` 不对外公开。

Rathole 检查项：

- `rathole.server.toml` 与 `rathole.client.toml` 使用相同的服务令牌。
- 后端客户端可访问 `backend:8081`。
- 前端 nginx 上游指向 `rathole-server:18081`。
- 支付渠道和面板的 webhook 仍指向后端 `WEBHOOK_BASE_URL`，而非前端域名。

## 数据库迁移

<a id="миграции"></a>

常规启动时会自动应用迁移：

```bash
docker compose up -d --build
```

手动重新执行：

```bash
docker compose run --rm migrate
```

查看迁移日志：

```bash
docker compose logs migrate
```

`backend` 和 `worker` 通过 `service_completed_successfully` 依赖 `migrate`；
迁移失败时，应用不会在未准备好的数据库上启动。不通过 Compose 直接启动
`backend` 或 `worker` 时，同一个 `init_db` 也会在服务逻辑启动前补齐迁移。

## 服务

<a id="сервисы"></a>

- `backend`：aiohttp API、Telegram webhook、支付 webhook、面板 webhook，以及 `/healthz` 健康检查。
- `worker`：TariffTrafficWorker、面板同步任务、群发处理、webhook 队列消费者。
- `frontend`：通过 nginx 提供静态 Svelte 资源。
- `postgres`：PostgreSQL 17。
- `redis`：Redis 7，用于 FSM、缓存、限流、队列和锁。

生产示例通过 `deploy/examples` 中对应方案的 `caddy`、`angie`、`nginx`、`newt` 或直接映射 `ports` 提供外部访问。

## 日志与检查

<a id="логи-и-проверка"></a>

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f frontend
```

健康检查端点：

```bash
curl http://127.0.0.1:8080/healthz
curl http://127.0.0.1:8080/health
```

常规 Compose 将 backend 绑定到 `127.0.0.1:${WEB_SERVER_PORT:-8080}`，
frontend 绑定到 `127.0.0.1:${FRONTEND_PORT:-8082}`。
新的生产示例请检查对应目录的绑定变量：`HTTP_BIND`、`HTTPS_BIND`、
`WEB_SERVER_BIND` 或 `FRONTEND_BIND`。

## 更新

<a id="обновление"></a>

从仓库进行本地构建：

```bash
git pull
docker compose up -d --build
docker compose logs -f migrate backend worker
```

仅重新构建应用镜像：

```bash
docker compose build frontend backend worker
docker compose up -d
```

## Docker Hub 镜像

<a id="образы-docker-hub"></a>

应用镜像采用统一命名：

```text
docker.io/3252a8/remnawave-minishop-backend:<tag>
docker.io/3252a8/remnawave-minishop-worker:<tag>
docker.io/3252a8/remnawave-minishop-frontend:<tag>
```

构建并立即将全部三个镜像发布到 Docker Hub 前，先登录：

```bash
docker login docker.io
IMAGE_TAG=3.6.1 bash scripts/docker-build-push-images.sh
```

PowerShell 版本：

```powershell
$env:IMAGE_TAG = "3.6.1"
docker login docker.io
powershell -ExecutionPolicy Bypass -File .\scripts\docker-build-push-images.ps1
```

脚本默认使用：

- `IMAGE_REGISTRIES=docker.io`
- `IMAGE_NAMESPACE=3252a8`
- `IMAGE_PREFIX=remnawave-minishop`
- `TARGETS=backend worker frontend`
- `DOCKERFILE=deploy/docker/Dockerfile`

需要自建镜像仓库或其他命名空间时，可覆盖变量：

```bash
IMAGE_REGISTRIES=registry.example.com IMAGE_NAMESPACE=other IMAGE_TAG=3.6.1 bash scripts/docker-build-push-images.sh
```

原有的分步命令仍然保留：

```bash
IMAGE_TAG=3.6.1 scripts/docker-build-images.sh
IMAGE_TAG=3.6.1 scripts/docker-push-images.sh
```

PowerShell 对应脚本为 `scripts/docker-build-images.ps1` 和
`scripts/docker-push-images.ps1`。发布到其他镜像仓库、命名空间或使用其他名称前缀时，
覆盖 `IMAGE_NAMESPACE`、`IMAGE_REGISTRY` 或 `IMAGE_PREFIX`。

为兼容旧流程，还保留只面向 Docker Hub 的脚本：

```bash
docker login
IMAGE_TAG=3.6.1 bash scripts/dockerhub-build-push-images.sh
```

PowerShell 版本：

```powershell
$env:IMAGE_TAG = "3.6.1"
docker login
powershell -ExecutionPolicy Bypass -File .\scripts\dockerhub-build-push-images.ps1
```

如果 PowerShell 因 `PSSecurityException` / Execution Policy 阻止本地脚本，
可仅为当前进程绕过执行策略，运行相同脚本：

```powershell
$env:IMAGE_TAG = "3.6.1"
docker login docker.io
powershell -ExecutionPolicy Bypass -File .\scripts\docker-build-images.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\docker-push-images.ps1
```

该绕过只对启动的 `powershell` 进程有效，不修改系统策略。

## 扩容

<a id="масштабирование"></a>

当前 Compose 文件显式设置了 `container_name`，因此不能对 `backend`、`frontend`
和 `worker` 使用 `docker compose --scale`，Docker 无法创建多个同名容器。
需要水平扩容时，应移除待扩容服务的 `container_name`，或将配置迁移到容器编排平台。

FSM 状态、限流和短期缓存放在 Redis 中，套餐周期任务通过 Redis 分布式锁保护。
代码已为多副本做准备，但当前 Compose 文件仍面向固定容器名称。

## 数据与数据卷

<a id="данные-и-volumes"></a>

生产 Compose 使用命名数据卷：

- `postgres-data`。
- `redis-data`。

Caddy 方案还使用 `caddy-data` 和 `caddy-config`；Angie 方案使用 `angie-acme`
保存 ACME 账号和 Let's Encrypt 证书。

应用文件从所选 `docker-compose.yml` 旁的本地 `./data` 目录挂载到 `/app/data`，
其中包含套餐、主题、标志及其他应用文件。

同一个 `/app/data` 必须挂载到 `migrate`、`backend` 和 `worker`。这对 `data/tariffs.json` 尤其重要：`docker compose run --rm migrate` 应读取与应用相同的套餐目录。当前 Compose 文件已为三个服务配置这一挂载。

首次在服务器启动前，预先授予容器用户 `10001` 所需权限：

```bash
mkdir -p data/themes data/webapp-logo data/tariffs
touch data/locales-overrides.json
chown -R 10001:10001 data
chmod -R u+rwX data
docker compose run --rm migrate
docker compose up -d --force-recreate backend worker
```

检查权限：

```bash
docker compose exec backend sh -lc 'id; touch /app/data/themes/test && rm /app/data/themes/test'
```

## PostgreSQL 备份

<a id="резервная-копия-postgresql"></a>

标准自动 ZIP 备份、发送至 Telegram 及通过管理后台恢复的流程，见[备份与恢复](../features/backups.md)。以下命令是 PostgreSQL 的最小手动备用方案。

```bash
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > backup.sql
```

恢复到空数据库（以下操作会删除并重建目标数据库）：

```bash
docker compose stop backend worker
docker compose exec postgres sh -c 'dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB"'
docker compose exec postgres sh -c 'createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backup.sql
docker compose run --rm migrate
docker compose up -d backend worker
```

## 反向代理

<a id="обратный-прокси"></a>

现成的反向代理示例已在前文说明：

- [Caddy](#caddy-рекомендуемый-вариант)：自动 HTTPS。
- [Angie](#angie)：使用 Nginx 语法的自动 HTTPS。
- [Nginx](#nginx)：证书放在旁边的 `ssl/` 目录。
- [Newt/Pangolin](#pangolin--newt)：无需开放应用服务器入站端口。

所有方案采用相同的基本路径：

- webhook/backend 域名整体转发到 `backend:8080`。
- Mini App/frontend 域名整体转发到 `frontend:80`。
- Mini App 的 API、认证和主题路由由前端 nginx 继续转发到 `backend:8081`。

支付渠道使用 IP 白名单时，反向代理必须通过 `X-Forwarded-For` 传递发送方的真实 IP，
backend 则通过 `TRUSTED_PROXIES` 信任最后一跳代理的 IP。
现成配置及应用默认信任回环地址和 `frontend`、`caddy`、`nginx`、`angie`、
`newt`、`newt-2` 服务的单独地址。可不设置该变量；不存在的服务会被忽略，容器地址每分钟刷新。
自定义代理需将其精确 IP/CIDR 或 `host:` 名称加入[标准列表](../configuration/security.md)。
安装程序会自动添加所选容器；host-network 模式还会添加精确的 Docker 网关。
域名位于 Cloudflare 后方时，只有最近的外部跳点属于 Cloudflare 官方网络，
backend 才安全地接受 `CF-Connecting-IP` 中的真实地址；无需将这些网络加入 `TRUSTED_PROXIES`。
可通过 `0.0.0.0/0,::/0` 启用全信任模式，但只能在 backend 无法被直接访问、
且外部代理会清理入站 `X-Forwarded-For` 的情况下使用。

最小 Caddy 配置：

```caddyfile
webhooks.example.com {
	reverse_proxy backend:8080
}

app.example.com {
	reverse_proxy frontend:80
}
```

最小 Nginx 配置使用同样的路径：`webhooks.example.com` 转发到 `backend:8080`，
`app.example.com` 转发到 `frontend:80`。`deploy/examples/nginx/nginx.conf.template`
已包含 `X-Forwarded-*` 请求头、HTTP 到 HTTPS 重定向及证书路径。

## 指定其他环境文件

<a id="переменный-env-файл"></a>

Compose 默认读取 `.env`。冒烟测试或独立环境可以使用其他文件：

```bash
APP_ENV_FILE=.env.staging docker compose --env-file .env.staging up -d --build
```

## 与生产环境并行的开发 dry-run

<a id="dev-dry-run-рядом-с-production"></a>

以下为上游只读联调说明；本项目开发与验收以[隔离开发环境](../development/project-local.md)
为准，默认 dry-run，不据此声称已通过真实 Node 验收。

需要针对同一 Remnawave Panel 检查功能时，开发服务栈应使用独立环境文件、独立 Telegram
机器人和本地数据库。开发模式仍从实际面板读取用户、squad、设备和统计，但不向
Remnawave 用户发送写入请求：只验证载荷，并输出类似
`[PANEL DRY-RUN OK] would PATCH /users ...` 的日志。

最小 `.env.dev` 片段：

```env
APP_RUNTIME_MODE=development
PANEL_WRITE_MODE=dry_run
PANEL_DRY_RUN_VALIDATE_REMOTE=True
PANEL_DRY_RUN_SYNTHETIC_CREATE=True

REDIS_KEY_PREFIX=remnawave-tg-shop-dev
BACKUP_ENABLED=False
```

启动：

```bash
APP_ENV_FILE=.env.dev docker compose --env-file .env.dev up -d --build
```

只有独立的测试 Remnawave Panel 才能设置 `PANEL_WRITE_MODE=live`，因为该模式
会真实修改面板用户。

第二个服务栈位于同一宿主机时，还必须使用不同端口：根目录 Compose 使用
`WEB_SERVER_PORT` 和 `FRONTEND_PORT`；不含内置 TLS 的生产示例使用
`WEB_SERVER_BIND` 和 `FRONTEND_BIND`。生产环境位于其他服务器时，本地端口可保留默认值。
