# 系统要求

<a id="системные-требования"></a>

本项目从[隔离源码流程](../development/project-local.md)启动 PostgreSQL、Redis、backend、worker、frontend 和测试 Remnawave Panel。真实连接需要单独安排隔离 Node；默认开发模板不提供可交付的代理线路。接手顺序见[接手说明](../handoff.md)，本页不登记环境当前状态或验收结果。

本机需要 Git、Docker Engine、Compose plugin、Buildx 和 Node.js/npm；主机质量检查还需要 Python 3.12 与 Node.js 24+。macOS 的独立 Colima 用法、默认端口和代理边界见本地开发说明。共享工作树先检查已有环境，不重复初始化。

## VPS 资源

<a id="конфигурация-vps"></a>

以下是上游 Minishop 的容量参考，不是当前二开项目、源码构建、Panel 或真实 Node 的容量承诺。实际需求应结合负载、构建峰值、日志和备份测量。

| 上游参考场景 | CPU | 内存 | SSD 可用空间 |
| --- | ---: | ---: | ---: |
| 最小启动或小型项目 | 1 vCPU | 1 GB | 至少 10 GB |
| 常规生产环境建议 | 2 vCPU | 2 GB | 至少 20 GB |
| 较高负载、频繁备份或多个附加服务 | 至少 4 vCPU | 至少 4 GB | 至少 40 GB |

表中没有本项目容量验收证据，不能据此保证最低配置可用；也不应为满足表格擅改现有主机的 swap 或资源。若 Panel、Node、反向代理或监控同机运行，须计入其资源需求。数据库、日志和本地备份增长后还需增加磁盘空间。

## 操作系统与工具

<a id="операционная-система-и-программы"></a>

- 上游 VPS 说明以 `amd64`（x86_64）64 位 Linux 为例；本机开发不因此限于该架构。目标架构须逐一核对锁定镜像和构建工具，不从单一平台验收推断所有平台兼容。
- 安装 Docker 和配置网络所需的 `root` 或 `sudo` 权限。
- Docker Engine **25.0+**、Docker Compose plugin **2.20.2+**。使用 `docker compose` 命令，不使用旧版独立 `docker-compose`。
- 安装向导需要 `curl`；辅助下载也可使用 `wget`。生成密钥和检查 TLS 证书需要 `openssl`。
- 下载安装器和镜像，以及访问已启用的外部服务所需的出站网络。

仅运行上游预构建镜像时，Python、Node.js、PostgreSQL 和 Redis 随容器提供；这不是本项目源码开发的工具清单。上游安装器或克隆上游仓库不能代替当前项目源码。

## 网络与外部依赖

<a id="сеть-и-внешние-зависимости"></a>

- Remnawave Panel、API 密钥和 webhook 密钥须与使用环境匹配。上游“高于 2.7.0”的版本说明不是本项目所有操作的支持承诺，逐项以[面板 API 说明](../architecture/remnawave-api-compatibility.md)和[本轮本地最终验收](../implementation-plan.md#本轮本地最终验收)中的固定环境与边界为准。
- 使用邮箱登录时需配置 SMTP、公开的网站地址和持久化的邮箱登录密钥。只有启用 Telegram 时才需要机器人令牌；管理员权限通过账号角色授予。
- Backend 与网站的公开 DNS 名称及 HTTPS。可使用两个域名，或按反向代理配置共用一个域名。
- 使用 Caddy、Angie 或 Nginx 时，将 80、443 TCP 端口和 DNS 指向 VPS。使用 Pangolin/Newt 时，应用服务器可能无需开放入站端口。

准备好服务器后，可阅读[安装步骤](setup.md)。本项目开发与测试请先使用[隔离环境](../development/project-local.md)。
