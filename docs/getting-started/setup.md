# 快速启动

<a id="быстрый-запуск"></a>

先配置 `.env`，再启动 Compose 服务栈，并检查 backend、worker 和 frontend。

> 本页保留 Minishop 上游的通用安装说明。上游安装脚本、镜像及支付、试用等流程不代表本项目当前 MVP 已启用这些能力。本项目采用一个账号管理多个独立服务、管理员手动激活、无支付的方案；开发与验收请使用[项目隔离开发环境](../development/project-local.md)，当前范围以[需求文档](../requirements.md)为准。

开始前请检查[系统要求](system-requirements.md)。如果还没有合适的服务器，
可以参考[上游项目合作方 wCloud](https://wcloud.host/?from=yKyhIg2jXbNdWZsFzd_tyxLVBYiicNjK)。

## 最小启动流程

<a id="минимальный-запуск"></a>

在新服务器上，可以先使用交互式安装向导：它会下载所选 Compose 配置、
生成 `.env`、检查 DNS、准备 `data/`，并按需从 Remnashop 或旧版
`remnawave-tg-shop` 执行迁移。
详情参见[交互式安装向导](deployment.md#интерактивный-install-wizard)。

```bash
curl -fsSL https://gitlab.com/3252a8/remnawave-minishop/-/raw/main/scripts/install.sh -o install.sh
sh install.sh
```

从已下载的仓库手动执行最小启动流程：

```bash
cp .env.example .env
nano .env
docker compose up -d --build
docker compose ps
docker compose logs -f backend worker frontend
```

## 优先填写的配置

<a id="что-заполнить-в-первую-очередь"></a>

- 独立运行模式使用 `TELEGRAM_ENABLED=False`；只有启用 Telegram 时才需要 `BOT_TOKEN`。首位所有者需在验证邮箱后通过[服务器命令](../features/telegram-optional.md)指定。
- `WEBHOOK_BASE_URL` 用于支付和面板的 webhook；启用 Telegram 后也用于其 webhook。
- `PUBLIC_APP_URL` 用于用户中心和邮件；`SUBSCRIPTION_MINI_APP_URL` 保留为兼容别名。
- `EMAIL_AUTH_SECRET`、`SMTP_HOST` 和 `SMTP_FROM_EMAIL` 用于邮箱登录。
- `POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB`。
- `WEBAPP_SESSION_SECRET`、`WEBHOOK_SECRET_TOKEN`、`PANEL_API_URL`、`PANEL_API_KEY`、`PANEL_WEBHOOK_SECRET`。

如果容器通过内部地址访问面板 API，还需设置 `PANEL_PUBLIC_URL`，
作为管理员浏览器访问面板的地址。例如：
`PANEL_API_URL=http://remnawave:3000/api` 和 `PANEL_PUBLIC_URL=https://panel.example.com`。
安装向导会分别查找并建议这两个地址；未找到公开地址时可以手动输入。
参见 [Remnawave 配置](../configuration/env-vars.md)。

在 Remnawave 面板中，将 `WEBHOOK_URL` 设置为 `WEBHOOK_BASE_URL` 加 `/webhook/panel`，例如 `https://app.example.com/webhook/panel`。在 Remnawave Panel 中生成或设置密钥，再将同一密钥填入 `.env` 的 `PANEL_WEBHOOK_SECRET`，或稍后在**系统 → 设置 → Remnawave Panel**中填写。

## 选择 Compose 方案

<a id="как-выбрать-compose-вариант"></a>

上游生产部署默认建议使用 [Caddy](deployment.md#caddy-рекомендуемый-вариант)，它可以自动配置公开 HTTPS，无需手动放置证书。

```bash
cd deploy/examples/caddy
cp .env.example .env
nano .env
docker compose up -d
```

其他方案详见[部署章节](deployment.md#готовые-папки-запуска)：

- [Angie](deployment.md#angie)：适合需要 Caddy 式自动 HTTPS、同时偏好 Nginx 配置语法的场景。
- [Nginx](deployment.md#nginx)：适合已有 TLS 证书、需要在 Docker 网络内使用 Nginx 的场景。
- [Pangolin/Newt](deployment.md#pangolin--newt)：适合无法开放应用服务器入站端口的场景。
- [无反向代理](deployment.md#без-обратного-прокси)：适合本地检查或由外部服务终止 TLS 的场景。

## Web App 配置

<a id="настройки-для-веб-апп"></a>

- [登录方式](../features/login-methods.md)：邮箱验证码、邮箱与密码、Telegram、Google、
  Yandex 和通行密钥（passkey）。

## 首次登录后

<a id="после-первого-входа"></a>

以下是上游完整商业流程的检查顺序；本项目 MVP 不启用支付、购买或试用流程，
应按[执行文档](../implementation-plan.md)验证管理员手动激活和独立服务交付。

1. 通过 Mini App 打开管理后台。
2. 检查设置中的支付方式。
3. 配置套餐目录。
4. 检查连接指南。
5. 执行一次测试购买或试用激活。

详情参见[环境配置](configuration.md)和[部署](deployment.md)。
