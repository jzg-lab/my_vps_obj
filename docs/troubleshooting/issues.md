# 常见问题

<a id="проблемы"></a>

排障时先检查容器状态和日志，再核对公开 URL 和密钥。

> 本页保留上游 Telegram、支付等功能的排障说明，并不表示本项目 MVP 已启用这些业务。本项目当前采用管理员手动激活、无支付的方案；开发与验收使用[隔离开发环境](../development/project-local.md)，不得将现有生产节点作为测试资源。

## 服务栈无法启动

<a id="стек-не-стартует"></a>

- 检查 `docker compose ps`。
- 查看 `docker compose logs migrate`。
- 确认 PostgreSQL 和 Redis 健康。
- 检查 `.env` 中的必填变量。

如果日志出现 `password authentication failed for user "remnawave_minishop"` 或
`InvalidPasswordError`，说明 `.env` 中当前的 `POSTGRES_PASSWORD` 与已经初始化的
PostgreSQL Docker 数据卷不匹配。只有确实要全新安装、且不再需要旧数据时，
才通过安装向导删除旧数据库卷，或使用 `docker compose down -v`；
后者会删除该服务栈的数据卷，不仅是数据库卷。如果需要保留数据，请恢复 `.env` 中的旧密码。

## Telegram webhook 不工作

<a id="вебхук-telegram-не-работает"></a>

- 检查 `WEBHOOK_BASE_URL`。
- 确认域名可通过 HTTPS 访问。
- 检查 `WEBHOOK_SECRET_TOKEN`。
- 查看入站事件发生时的 backend 日志。

## Mini App 无法打开

<a id="mini-app-не-открывается"></a>

- 检查 `SUBSCRIPTION_MINI_APP_URL`。
- 确认 URL 指向 frontend，而非 `/api` 或 webhook 域名。
- 检查 BotFather 设置。
- 查看 frontend 和 backend 日志。

## 管理后台报告数据挂载不一致

<a id="админка-сообщает-о-разных-data-mount"></a>

`data_mount_mismatch` 表示 `migrate`、`backend` 和 `worker` 的 `/app/data`
使用了不同的源数据卷或绑定挂载，或某个服务缺少该挂载。这会导致迁移、套餐、翻译及备份
作用于不同的文件集合。

- 打开诊断消息指定的 Compose 文件。
- 比较 `migrate`、`backend` 和 `worker` 中 `:/app/data` 左侧的源。
- 标准安装的三个服务应共用同一 `shop-data:/app/data`；使用绑定挂载时，
  应共用同一宿主机路径，例如 `./data:/app/data`。
- 修正后重建相关容器，再次打开设置诊断。

不要将不同数据卷之间逐个复制文件作为长期解决方式。应先确定唯一的数据来源，
再让三个服务共用它。

## 付款未入账

<a id="платеж-не-засчитался"></a>

- 检查支付渠道是否启用。
- 检查 webhook URL 和密钥。
- 查看 backend 日志。
- 核对管理后台与支付渠道后台中的付款状态。

详情参见[日志](logs.md)和[部署](../getting-started/deployment.md)。
