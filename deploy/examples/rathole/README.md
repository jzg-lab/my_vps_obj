# Rathole 私有隧道

前端服务器无法直接访问后端网页应用 API 时使用。浏览器仍仅请求前端同源地址：

```text
browser -> https://app.example.com/api -> frontend nginx -> rathole-server:18081 -> backend:8081
```

服务器之间只公开 Rathole 控制端口，例如 `2333/tcp`；服务端口 `18081` 仅在前端 Docker 网络内部使用。

## 配置步骤

1. 前端服务器将 `rathole.server.toml.example` 复制为 `rathole.server.toml`。
2. 后端服务器将 `rathole.client.toml.example` 复制为 `rathole.client.toml`。
3. 两份文件使用相同 `token`。
4. 前端服务器启动 `frontend-server.docker-compose.yml`。
5. 后端服务器启动常规后端服务，并叠加 `backend-server.override.yml`。

配置检查：

```bash
docker compose -f frontend-server.docker-compose.yml config
docker compose -f backend-server.override.yml config
```
