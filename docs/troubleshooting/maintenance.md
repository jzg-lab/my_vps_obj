# 日常维护

<a id="обслуживание"></a>

计划维护通常包括更新镜像、检查迁移、日志和备份。自动 ZIP 备份及恢复的详细步骤见[备份与恢复](../features/backups.md)。

> 本页保留上游运维流程，不代表本项目已完成生产部署或真实 Node 验收。当前 MVP 使用管理员手动激活、无支付；开发与验收使用[隔离开发环境](../development/project-local.md)，不将现有生产节点作为测试资源。

## 更新

<a id="обновление"></a>

```bash
docker compose pull
docker compose up -d
docker compose logs -f migrate backend worker
```

## PostgreSQL 备份

<a id="резервная-копия-postgresql"></a>

```bash
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > backup.sql
```

## 自动备份

<a id="автоматические-бэкапы"></a>

worker 可将 PostgreSQL 转储和 Compose 目录快照打包为 ZIP，发送到 Telegram，并在 `data/backups` 保留最近的归档。配置及恢复流程见[专门章节](../features/backups.md)。

修改 `.env` 中的备份设置后，重新启动 backend 和 worker：

```bash
docker compose up -d --build backend worker
docker compose logs -f backend worker
```

管理后台的**系统 → 备份**支持从归档恢复。也可在此手动上传 ZIP，选择“数据库”和／或“Compose 目录”；backend 会在开始前验证归档。详情参见[备份与恢复](../features/backups.md#восстановление-из-админки)。

## 维护后的检查

<a id="проверки-после-работ"></a>

- `docker compose ps`。
- `docker compose logs -f backend worker frontend`。
- backend 域名上的 `/healthz`。
- 登录 Mini App 和管理后台。
- 当前 MVP 检查管理员手动激活；上游已启用支付或试用的环境可检查测试付款或测试激活。
