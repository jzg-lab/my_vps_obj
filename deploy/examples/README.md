<a id="примеры-docker-compose"></a>

# Docker Compose 示例

各启动方案的完整文档见[部署指南](../../docs/getting-started/deployment.md)。

本目录只保留可运行 Compose 示例和配置，不重复详细说明，使文档站和 README 导航使用同一来源。

应用文件 `/app/data`（上游套餐文件、主题、标志）从所选 `docker-compose.yml` 同级 `data` 目录挂载到 `migrate`、`backend`、`worker`。自定义主题需创建 `data/themes`。`data/tariffs.json` 仅供上游单订阅套餐目录使用，不能代替本项目保存在数据库中的独立服务模板 `ServicePlan`；相关入口见[独立服务模型](../../docs/development/independent-services.md)。

| 目录 | 文档 |
| --- | --- |
| `caddy` | [Caddy 部署](../../docs/getting-started/deployment.md#caddy-推荐方案) |
| `angie` | [Angie 部署](../../docs/getting-started/deployment.md#angie) |
| `nginx` | [Nginx 部署](../../docs/getting-started/deployment.md#nginx) |
| `newt` | [Pangolin／Newt 部署](../../docs/getting-started/deployment.md#pangolin--newt) |
| `no-proxy` | [无反向代理](../../docs/getting-started/deployment.md#无反向代理) |
| `mail` | [本地 SMTP](../../docs/features/login-methods.md#本地-smtp-配置) |
