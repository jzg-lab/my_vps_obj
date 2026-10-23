# 分离部署与受保护上游

Mini App 前端位于独立服务器，但浏览器请求仍需保持同源时使用：

```text
browser -> https://app.example.com/api -> frontend nginx -> protected backend upstream
```

`WEBAPP_API_BASE_URL` 保持 `/api`，仅在前端服务器配置 `WEBAPP_BACKEND_UPSTREAM`。

后端区分两类入口：

- `backend:8080`：Telegram、支付提供商与 Remnawave Panel 的公开 webhook。
- `backend:8081`：`/api`、`/auth`、`/open-app` 及网页应用资源的私有 API。

使用单一后端域名时，webhook 路径转发到 `backend:8080`，不携带 `MINISHOP_EDGE_TOKEN`；`/api/*`、`/auth/*`、`/open-app` 及标志／主题／站点图标路径转发到 `backend:8081`，携带 `X-Minishop-Edge-Token`。

私有 IP／VPN 模式可设 `WEBAPP_BACKEND_UPSTREAM=http://10.0.0.5:8081`，通过防火墙／VPN／允许清单限制 `8081`。

配置检查：

```bash
docker compose -f frontend.docker-compose.yml config
docker compose -f backend.docker-compose.yml config
```
