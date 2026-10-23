# 系统要求

<a id="системные-требования"></a>

Remnawave Minishop 使用 Docker Compose 运行 PostgreSQL、Redis、backend、worker 和 frontend。本项目一期还需要独立的 Remnawave Panel 与测试节点来验收连接交付。小规模部署可以使用基础 VPS；额外内存有助于更新、备份和排障。

## VPS 资源

<a id="конфигурация-vps"></a>

| 场景 | CPU | 内存 | SSD 可用空间 |
| --- | ---: | ---: | ---: |
| 最小启动或小型项目 | 1 vCPU | 1 GB | 至少 10 GB |
| 常规生产环境建议 | 2 vCPU | 2 GB | 至少 20 GB |
| 较高负载、频繁备份或多个附加服务 | 至少 4 vCPU | 至少 4 GB | 至少 40 GB |

1 vCPU、1 GB 内存是小型 Minishop 的实际下限。此时建议配置 1–2 GB swap 并监控磁盘余量。常规生产环境建议从 2 vCPU、2 GB 内存起步，以容纳容器启动、更新和短时负载峰值。表中只计算 Minishop；若 Remnawave Panel、反向代理或监控也运行在同一 VPS，请叠加其资源需求。数据库、日志和本地备份增长后还需增加磁盘空间。

:::tip[服务器选择]
[wCloud VPS 与节点服务器](https://wcloud.host/?from=yKyhIg2jXbNdWZsFzd_tyxLVBYiicNjK)

可按实际需求选择 VPS，包括适用于 Remnawave Node 的服务器。购买前应独立比较价格、地区和资源，不把供应商示例当作本项目的必选条件。
:::

## 操作系统与工具

<a id="операционная-система-и-программы"></a>

- `amd64`（x86_64）架构的 64 位 Linux。建议使用仍受维护的 Ubuntu Server 或 Debian，无需图形桌面。
- 安装 Docker 和配置网络所需的 `root` 或 `sudo` 权限。
- Docker Engine **25.0+**、Docker Compose plugin **2.20.2+**。使用 `docker compose` 命令，不使用旧版独立 `docker-compose`。
- 安装向导需要 `curl`；辅助下载也可使用 `wget`。生成密钥和检查 TLS 证书需要 `openssl`。
- 下载安装器和镜像，以及访问已启用的外部服务所需的出站网络。

标准 VPS 部署不需要单独安装 Python、Node.js、PostgreSQL 或 Redis；它们随容器运行。只有手动克隆仓库或从源码构建时才需要 Git。

## 网络与外部依赖

<a id="сеть-и-внешние-зависимости"></a>

- **高于 2.7.0** 的 Remnawave Panel、面板 API 密钥和 webhook 密钥。具体接口兼容性仍须按[面板 API 说明](../architecture/remnawave-api-compatibility.md)核对，不能只根据版本号推断。
- 使用邮箱登录时需配置 SMTP、公开的网站地址和持久化的邮箱登录密钥。只有启用 Telegram 时才需要机器人令牌；管理员权限通过账号角色授予。
- Backend 与网站的公开 DNS 名称及 HTTPS。可使用两个域名，或按反向代理配置共用一个域名。
- 使用 Caddy、Angie 或 Nginx 时，将 80、443 TCP 端口和 DNS 指向 VPS。使用 Pangolin/Newt 时，应用服务器可能无需开放入站端口。

准备好服务器后，可阅读[安装步骤](setup.md)。本项目开发与测试请先使用[隔离环境](../development/project-local.md)。
