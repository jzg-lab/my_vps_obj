<a id="миграция-с-remnawave-tg-shop-на-remnawave-minishop"></a>

# 从 remnawave-tg-shop 迁移到 remnawave-minishop

从旧关联项目迁移可使用通用安装向导：

```bash
curl -fsSL https://gitlab.com/3252a8/remnawave-minishop/-/raw/main/scripts/install.sh -o install.sh
sh install.sh
```

<!-- GitHub 备用安装地址（停用）：

```bash
curl -fsSL https://raw.githubusercontent.com/3252a8/remnawave-minishop/main/scripts/install.sh -o install.sh
sh install.sh
```
-->

上游向导目前使用俄语提示。本指南以中文说明选项含义：新服务器选择“安装新的 remnawave-minishop 并从其他机器人迁移数据”；Compose 目录已准备好时，选择“迁移到已安装的 remnawave-minishop”。来源选择“旧 remnawave-tg-shop”。以下流程是上游安装参考，不代表本项目生产迁移已获批准。

向导使用安全的 `pg_dump` 逻辑迁移，不复制旧 PostgreSQL 原始数据卷，因为其中已初始化旧角色和密码。它会：

- 自动查找旧 PostgreSQL 容器（`remnawave-tg-shop-db` 或 `LEGACY_TGSHOP_DB_CONTAINER`），从 `POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB` 构造源 DSN。
- 无法自动发现时，请求手动填写 `LEGACY_TGSHOP_SOURCE_DSN`／源 DSN。
- 删除目标卷前，将旧数据库逻辑备份保存至 `backups/pre-remnawave-tg-shop-source-*`。
- 删除 Minishop 目标数据库卷，用 `.env` 中新 `POSTGRES_*` 启动空 PostgreSQL。
- 恢复备份，再启动 `migrate`。

旧 `remnawave-tg-shop-db-data` 和源数据库不会自动删除，保留供回滚。

<a id="как-работает-перенос"></a>

## 迁移原理

两项目具有兼容的数据库结构历史。恢复旧 PostgreSQL 后，`migrate` 应用 `backend/db/migrator/` 中缺失迁移：先处理 `Base.metadata`，再按顺序执行 `schema_migrations`。该服务只运行一次，必须以 `0` 退出，然后才启动 backend、worker。

向导步骤：

1. 从旧容器或 `LEGACY_TGSHOP_SOURCE_DSN` 读取源 DSN。
2. 源 DSN 指向本地容器时，将其加入目标 Compose 网络。
3. 保存源备份：

   ```bash
   pg_dump --clean --if-exists --no-owner --no-privileges "$SOURCE_DSN" \
     > backups/pre-remnawave-tg-shop-source-*/dumps/remnawave-tg-shop-source.sql
   ```

4. 备份目标 Minishop 文件；目标数据库可用时，也保存替换前的逻辑备份。
5. 停止目标服务栈并删除目标数据库卷：

   ```bash
   docker volume rm remnawave-minishop-db-data
   ```

6. 启动 postgres、redis；PostgreSQL 按当前 `.env` 的 `POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB` 初始化。
7. 恢复预先保存的备份：

   ```bash
   psql "$TARGET_DSN" -v ON_ERROR_STOP=1 \
     < backups/pre-remnawave-tg-shop-source-*/dumps/remnawave-tg-shop-source.sql
   ```

8. 运行 Minishop 迁移，再启动完整服务栈。

<a id="что-меняется-в-архитектуре"></a>

## 架构变化

**容器：**

| 版本 | 服务 |
| --- | --- |
| `v2.7.0` | `remnawave-tg-shop`、`remnawave-tg-shop-db` |
| `v3.1.x-v3.3.x` | `remnawave-minishop`、`remnawave-minishop-db` |
| `v3.4+` | `remnawave-minishop-backend`、`remnawave-minishop-worker`、`remnawave-minishop-frontend`、`remnawave-minishop-migrate`、`remnawave-minishop-postgres`、`remnawave-minishop-redis` |

**数据卷：**

| 数据卷 | 行为 |
| --- | --- |
| `remnawave-minishop-db-data` | 重建并从源 DSN 恢复，不复制旧 PostgreSQL 原始卷 |
| `remnawave-minishop-redis-data` | 创建空卷 |
| `remnawave-minishop-shop-data` | 创建空卷；`/app/data` 运行文件后续通过后台或手动配置 |
| `remnawave-minishop-caddy-data`／`remnawave-minishop-caddy-config` | 新 Caddy 配置创建；旧 `remnawave-tg-shop-caddy-*` 保留供人工回滚 |
| `remnawave-minishop-angie-acme` | Angie 配置创建，保存 ACME 账号及 Let's Encrypt 证书 |

可用 Compose 文件：`docker-compose.yml`、`deploy/examples/caddy/docker-compose.yml`、`deploy/examples/angie/docker-compose.yml`、`deploy/examples/nginx/docker-compose.yml`、`deploy/examples/newt/docker-compose.yml`、`deploy/examples/no-proxy/docker-compose.yml`。

<a id="переменные-окружения"></a>

## 环境变量

启动前核对 `.env`，主要变化如下：

| 原配置 | 新配置 | 操作 |
| --- | --- | --- |
| `TELEGRAM_WEBHOOK_SECRET` | `WEBHOOK_SECRET_TOKEN` | 迁移原值或生成新的固定密钥 |
| `TELEGRAM_WEBHOOK_PATH` | 已删除 | webhook 路径自动计算 |
| `REQUIRED_CHANNEL_SUBSCRIBE_TO_USE` | 已删除 | 设置 `REQUIRED_CHANNEL_ID` 即开启限制 |
| `STARS_PROVIDER_TOKEN` | 已删除 | 直接使用 Telegram Stars |
| `POSTGRES_HOST=remnawave-tg-shop-db` | Compose 内为 `postgres` | Compose 按服务名覆盖主机 |
| `WEBHOOK_BASE_URL` | 必填 | 缺少公开 URL 时后端不能正常启动 |
| 无 | `REDIS_URL=redis://redis:6379/0` | Compose 自动设置 |
| 无 | `WEBAPP_SESSION_SECRET`、`WEBAPP_ENABLED`、`TARIFFS_CONFIG_PATH` | 网页应用与套餐目录新配置 |

其他产品设置建议在首次登录后台后核对。

<a id="обратный-прокси"></a>

## 反向代理

旧栈通常只有 `remnawave-tg-shop:8000` 上游，当前拆分为：

| 用途 | 服务 | 端口 |
| --- | --- | --- |
| Telegram、支付、面板 webhook | `backend` | `8080` |
| 健康检查 | `backend` | `8080`（`/healthz`） |
| 网页 API 与认证 | `backend` | Docker 内部 `8081` |
| 静态网页前端 | `frontend` | `80` |

外部 Nginx 最小示例：

```nginx
upstream remnawave_backend_webhooks { server backend:8080; }
upstream remnawave_frontend         { server frontend:80; }

server {
    server_name app.domain.com;
    listen 443 ssl;

    location /webhook/ { proxy_pass http://remnawave_backend_webhooks; }
    location /healthz  { proxy_pass http://remnawave_backend_webhooks; }
    location /         { proxy_pass http://remnawave_frontend; }
}
```

现成 Caddy、Angie、Nginx、Pangolin／Newt、无代理配置已包含路由。

<a id="проверка"></a>

## 核查

迁移后运行：

```bash
docker compose ps
docker compose logs migrate
docker compose logs -f backend worker frontend
```

`migrate` 必须成功退出；backend、worker、frontend、postgres、redis 应运行且健康。

确认新栈正常、回滚准备完备后，才考虑手动删除旧卷：

```bash
docker volume rm remnawave-tg-shop-db-data
docker volume rm remnawave-tg-shop-caddy-data remnawave-tg-shop-caddy-config 2>/dev/null || true
```
