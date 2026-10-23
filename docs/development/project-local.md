# 我的 VPN：本地开发

本仓库基于 Minishop v3.8.2（`04b0ca5e210a33209bbf15485003865ee29304bc`），保留 MIT 许可和上游历史。业务需求以[需求基线](../requirements.md)、[产品设计](../product-design.md)为准；上游文档描述的是原有功能，并不表示多套餐改造已经完成。

## 启动

需要 Docker、Docker Compose 和 Buildx。主机上执行质量检查另需 Python 3.12、Node.js 24+。下面的开发环境使用本仓库源码构建。

```sh
cp deploy/dev/project-dev.env.example .env.project-dev
npm run project:config
npm run project:up
npm run project:ps
```

只有第一次需要复制配置；不要覆盖已经修改的 `.env.project-dev`。配置、数据库、缓存和本地抓取资料不会提交到 Git。不要从线上复制配置、用户数据或真实订阅。

macOS 使用独立 Colima 环境时：

```sh
colima start my-vps-obj --activate=false --cpu 2 --memory 4 --disk 40
export DOCKER_CONTEXT=colima-my-vps-obj
npm run project:up
```

`DOCKER_CONTEXT` 只影响当前终端，不切换其他项目的全局 Docker context。首次拉取与构建需要联网。默认端口必须未被占用；若冲突，在本地配置修改端口及对应 URL 后重试，不停止其他项目。

若网络需要代理，Docker daemon 和主机上的构建客户端都需要能访问镜像仓库；仅设置构建参数不能解决镜像认证请求超时。主机客户端使用 `HTTP_PROXY` / `HTTPS_PROXY`，构建步骤可用 `DEV_BUILD_PROXY` 指定容器可访问的代理地址。这些地址只放在本地配置或当前终端环境。

| 服务 | 本机地址 |
| --- | --- |
| 网站与管理入口 | http://127.0.0.1:18082 |
| 后端健康检查 | http://127.0.0.1:18080/healthz |
| 测试 Remnawave | http://127.0.0.1:3000 |
| 面板健康检查 | http://127.0.0.1:3001/health |

开发服务仅绑定本机地址。测试管理员邮箱为 `runes.admin@example.com`，密码为 `Minishop-Dev-2026!`（上游公开测试夹具）。不要将此环境、测试凭据或 QA 登录功能用于公网部署。

基础测试数据仅包含三个虚构账号，不预置付款、套餐或节点身份绑定；重复启动不会覆盖已编辑的账号。用户首页已接入多份独立服务、套餐目录和服务详情；后台已有独立套餐、专用出口登记和用户多服务开通页面。用户端旧购买/营销入口已隐藏，账号合并、删除、历史保留及全服务封禁/解封的持久化同步已接入，后台历史页面已接入；网站旧业务接口和回调返回 410，旧权益 worker 不再运行，后台旧套餐操作、筛选及配置已收拢，Telegram 核心旧权益入口已隔离并导向网站。此时不构成完整业务验收。默认栈不包含实际节点，不交付可用代理连接；Remnawave 写操作默认为 dry-run。本地 HTTP 验证在测试管理员账号下创建了以 `Local QA` 开头的两份业务记录；状态为 pending，没有交付连接。

本项目开发配置关闭 Telegram、在线支付、自动试用、余额、分销、订阅通知、遥测及备份。保留上游功能代码以减少派生差异；这些功能不因此进入 MVP 范围。后台 worker 使用同一个本地面板和数据库。上游后台会提示本地地址使用 HTTP；公网 HTTPS 部署仍是后续阶段，不通过隐藏提示冒充生产就绪。

后台已支持单份服务暂停、恢复和续期；续期保留用量和月度锚点。独立身份用量采集已实现，只有 live 模式才运行，默认 dry-run 不产生伪造的真实采样。月度额度切换使用持久化的固定计数检查点，限额核对成功后才更新页面。修改套餐模板额度会排队更新同模板已有服务的当前及未来额度，保留已用流量。计数异常保留已有用量；管理员须暂停服务（已取消的服务保持取消）、确认面板停用并提供准确记录才能核对，核对不会恢复权限。取消时未完成的月度切换须做终止结算，保留旧周期与切点、记录切点后准确用量，不将额度记为确认成功；证据提交后才能删除身份。合并后的基础逻辑、取消核对和终止结算已通过完整单元、模拟浏览器、隔离数据库/无 Node 面板与实际本地网站验收；本轮另用临时 live 进程和两只真实 Docker Node 完成了数据面测试，测试后已清理；第三方客户端订阅导入及真实公网独享出口仍未验证，不能仅靠切换配置宣称通过。详细证据见[权益与计量契约](entitlement-metering-contract.md#local-validation-and-remaining-acceptance-2026-10-23)。

## 检查与停止

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt -r requirements-dev.txt
npm ci --prefix frontend
PATH="$PWD/.venv/bin:$PATH" npm run check

# 已启动本地环境后验证登录、权限和设置保存，不调用支付流程。
NO_PROXY=127.0.0.1,localhost,::1 QA_FULLSTACK=1 .venv/bin/python -m pytest -q tests/qa/test_fullstack_stand.py \
  -k 'email_auth_session_and_csrf or admin_settings_save_roundtrip'

npm run project:logs
npm run project:down
```

停止保留数据库卷；不要随意使用 `down -v`。只想释放本项目 VM 资源可运行 `colima stop my-vps-obj`，下次启动后再执行 `project:up`。

首次运行浏览器测试需执行 `npm exec --prefix frontend -- playwright install chromium`。macOS 的 `/usr/bin/openssl` 实际可能是 LibreSSL；安装器证书测试需要 OpenSSL，可在测试命令的 `PATH` 前加入 Homebrew 的 `openssl@3/bin`，不用替换系统程序。构建文档时也需将 `.venv/bin` 放入 `PATH`。

## 仓库与集成边界

- `origin`：`https://github.com/jzg-lab/my_vps_obj.git`。
- `upstream`：`https://gitlab.com/3252a8/remnawave-minishop.git`；不自动合并更新。
- `frontend/`、`backend/`、`tests/`、`deploy/` 复用上游目录和接口契约。后续迁移只追加，不改旧迁移。
- `docker-compose.project-dev.yml` 覆盖本项目的镜像、容器、网络和数据卷名称；基础 Compose 与 Remnawave overlay 继续复用。
- 常规 CI 运行源码检查；完整面板矩阵暂限 3.4.5。上游镜像发布和自动提 PR 工作流在本仓库不执行。
- 现有线上网站已按用户授权替换为二开版试测，见下方服务器资料；现有两台 3x-ui 节点接管仍另行安排。
- `experiments/` 保存早期离线评估，单独按目录 README 运行；正常 `pytest` 只收集 `tests/`，不将“复现上游缺口”的实验当成产品回归测试。

新业务模型、接口与当前未完成边界见[独立服务开发说明](independent-services.md)。


## 本机真实 Node 与恢复演练

2026-10-23 主窗口经用户授权，在此机临时部署两只 Remnawave Node，完成真实 VLESS TCP 的跨节点上传/下载计量、额度耗尽、暂停/恢复、封禁/解封、到期、撤销、月度切换及短时故障测试。节点和测试数据已清理，默认无 Node / dry-run 配置未修改。环境、步骤、实际超额和未验证边界见[实施计划第 11 节](../implementation-plan.md#local-node-and-recovery-acceptance)。这是本机真实数据面证据，不能替代公网出口或第三方客户端导入验收。

本轮还使用现有备份与恢复代码执行商店数据库恢复，包含月度检查点、额度调整、原始价格快照和合成资源绑定，88 张表恢复前后内容一致。恢复时停本项目 backend/worker，保留旧数据库及恢复日志，完成后重新启动并核查健康；不要把较旧商店备份直接视为外部面板已经同步。详细流程和 CLI 入口见[备份说明](../features/backups.md)。私有演练摘要和归档在忽略的 `data/backups/`，不公开提交。

重复真实节点测试前须独占本地面板写入时段，先记录本轮资源标识，使用临时商店 schema 和回环端口，结束后仅删除本轮资源。默认的无 Node 面板 QA 必须等临时 Node 清理后运行，不修改其保护条件。

## 线上服务器资料

<a id="production-access"></a>

2026-10-23（北京时间），用户授权直接替换现有线上站点并自行试测。网站与业务后台统一管理套餐、账号及服务；Remnawave 仍是独立的节点控制组件。线上环境与上文的本机 Colima 开发环境分别维护。

| 项目 | 已核实位置 |
| --- | --- |
| 用户网站 | <https://vpn.yourouter.org/home> |
| 套餐后台 | <https://vpn.yourouter.org/admin/service-plans> |
| 节点控制面板 | <https://panel.yourouter.org/auth/login> |
| 服务器 | `38.76.215.26`，Linux x86_64，4 CPU / 4 GB 内存 |
| SSH | `ssh vpn-prod`，`root`，端口 `22` |
| 本机连接配置 | `~/.ssh/config` 中的 `Host vpn-prod` |
| 本机专用私钥 | `~/.ssh/my_vps_obj_prod_ed25519`，权限 `0600`；公钥已加入服务器 `authorized_keys` |
| 网站 Compose 目录 | `/opt/remnawave-minishop`；使用 `docker-compose.yml` 与 `docker-compose.override.yml` |
| 线上配置与应用文件 | `/opt/remnawave-minishop/.env`、`/opt/remnawave-minishop/data` |
| 本次源码与构建材料 | `/opt/my-vps-obj/releases/32185a16` |
| 当前部署摘要 | `/opt/my-vps-obj/last-deployment.json` |
| 切换前备份 | `/opt/my-vps-obj/backups/pre-32185a16-20261023T091750Z` |
| 面板 / HTTPS / Node 目录 | `/opt/remnawave`、`/opt/remnawave-edge`、`/opt/remnawave-node` |

SSH 公钥认证原本关闭，本轮已启用并通过不复用旧连接的密钥登录验证；保留原密码登录方式。密码不存入本文、Git 或服务器资料。换电脑时需另行配置密钥，不能假设本机别名自动同步。

### 当前版本与配置

本次产品提交为 `32185a1631438c9997747bf7f103cf53436789b4`，镜像为 `my-vps-obj/backend:32185a16`、`my-vps-obj/worker:32185a16`、`my-vps-obj/frontend:32185a16`，迁移任务使用同一 backend 镜像。后台显示 `v3.8.2-feat-independent-services+g32185a16`。面板 **3.4.5**、Node **3.4.2**、数据库、Redis 与 Caddy 沿用原部署，没有随业务程序升级。

为降低 4 GB 服务器上的构建负载，前端在本机按正式构建脚本生成，再在服务器重建三个应用镜像。Python 依赖文件与服务器原固定摘要镜像逐字节一致（SHA-256 `ad6edf1a019a9d1f3dfff1e46a4d41552c607afa5a93cf782db536ea8452b8ec`）；前端 package/lock 和运行入口相对 v3.8.2 未变。因此本轮使用原固定摘要运行环境，完整替换 backend/locales 和前端静态文件，并加入服务教程。构建文件 `Dockerfile.redeploy`、对应 ignore、元数据和前端产物留在本次源码目录；该做法仅适用于这次依赖相同的提交，后续依赖变化应使用仓库完整 Dockerfile 构建。

运行配置为 `APP_RUNTIME_MODE=production`、`PANEL_WRITE_MODE=live`、`DEFAULT_LANGUAGE=zh-hans`；QA 登录、测试支付、Telegram、试用、余额及分销关闭。原 SMTP、账号、会话密钥、面板凭据和域名保留。原有一个账号和一份旧测试订阅保留；旧订阅没有自动变成新服务，新套餐与服务从后台自行创建和开通。

原部署目录为 root 的 `0700`，导致容器内健康检查无法遍历 Compose 文件。本轮将目录及两个 Compose 文件的组设为应用组 `10001`，权限分别为 `0750`、`0640`；`.env` 保持 `0600`。修复后后台健康接口返回空告警列表。面板 API 正常读取两个节点组；直接诊断内部面板时须使用项目客户端，它会附带面板要求的转发请求头。

### 日常检查与更新

```sh
ssh vpn-prod
cd /opt/remnawave-minishop
docker compose ps
docker compose config --quiet
curl -fsS http://127.0.0.1:8080/healthz
curl -fsS http://127.0.0.1:8082/health
docker compose logs --since 10m --tail 100 backend worker
```

后续更新仍在当前 Compose 项目内替换 backend、worker、frontend 与 migrate 的镜像，保留数据卷、绑定目录和网络。先构建并验证明确提交的自有镜像，再停止 backend/worker、备份、应用追加迁移并启动。不要把原上游镜像更新当作二开版更新，也不要把本机 `.env.project-dev` 或 QA 数据复制到公网。

### 备份与回退

本次切换前保存了完整应用目录归档 `application-files.tar.gz`、停止 backend/worker 后的 `postgres.dump`、原 Compose 展开记录、文件哈希清单、迁移及启动日志。PostgreSQL 归档已用 `pg_restore --list` 校验可读取。归档含配置与凭据，仅留服务器私有备份目录，不提交 Git。

需要回退时，先停止新 backend/worker 并另备份切换后的数据，再恢复这份备份中匹配的数据库、应用文件和旧镜像配置；不要只降级程序而让新业务数据继续由旧模型处理。数据库恢复会回到上述备份时点，之后新建的套餐/服务应先单独留存，并核对面板中已产生的连接。商店数据库恢复方法见[备份说明](../features/backups.md)，本次没有执行线上回退演练，也没有备份或恢复外部面板数据库。

公开站点、会话鉴权、用户服务/目录、后台套餐/资源接口，以及 1440px／390px 页面和套餐编辑弹窗已验证；节点组加载正常，无页面脚本异常和横向溢出。邮箱发码、真实客户端导入及公网独享出口本轮未重测；详细结果见[线上替换记录](../implementation-plan.md#production-cutover-20261023)。
