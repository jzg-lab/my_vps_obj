# 我的 VPN：本地开发

本仓库基于 Minishop v3.8.2（`04b0ca5e210a33209bbf15485003865ee29304bc`），保留 MIT 许可和上游历史。当前项目必须从本仓库源码进入，不能用上游安装器、公开镜像或上游克隆代替。先读[接手说明](../handoff.md)、[需求基线](../requirements.md)、[统一管理台指南](../admin-console-guide.md)和[产品设计](../product-design.md)。

本文维护环境入口和操作前提，不维护产品完成清单。当前进度、源码快照、验收证据及未验收范围只查[实施计划 §14：本轮本地最终验收](../implementation-plan.md#本轮本地最终验收)。历史记录从[历史索引](../archive/index.md)查阅；历史测试状态不能作为当前待办。

## 启动

需要 Docker、Docker Compose 和 Buildx；执行 `npm run project:*` 需要主机 Node.js/npm。主机质量检查使用 Python 3.12、Node.js 24+，具体门禁见 [CONTRIBUTING.md](../../CONTRIBUTING.md)。

### 先选择并核对本机引擎

在任何 `npm run project:*` 命令之前，先用 `docker context ls` 查看可用 context，并在当前终端用 `export DOCKER_CONTEXT=你的本机开发context名称` 指定已核对的本机开发引擎。可使用 Docker Desktop、本机 Docker Engine 或独立 Colima；不要求所有平台安装 Colima，也不默认接受当前 daemon。

**macOS 可选隔离引擎：**仅在准备使用名为 `my-vps-obj` 的独立 Colima 实例时运行以下命令；已有实例先核对配置，不擅自调整资源。使用其他引擎时跳过此段，保留自己选定的本机 context。

```sh
colima start my-vps-obj --activate=false --cpu 2 --memory 4 --disk 40
export DOCKER_CONTEXT=colima-my-vps-obj
```

先只读核对 context 名称及 Docker endpoint，确认指向本机开发环境，不是生产或其他项目的远程引擎：

```sh
docker context show
docker context inspect "${DOCKER_CONTEXT:?请先设置为已核对的本机开发context名称}"
```

确认端点后运行 `docker info` 检查引擎可用性，再执行下方首次初始化命令。`DOCKER_CONTEXT` 只影响当前终端，不切换其他项目的全局 Docker context；新终端须重新选择并核对。首次拉取与构建需要联网。端口冲突时在本地配置调整端口及对应 URL，不停止其他项目。

### 首次初始化

**环境与前置：仅首次创建本机隔离开发栈。** 在当前仓库根目录核对工作树、Docker context、端口和数据卷归属；已有环境不要覆盖配置或重新初始化。构建读取当前工作树，包含未提交修改，不能只凭 Git 提交号声称运行内容一致；接手时保留他人未提交内容，并对照实施计划中的源码与镜像记录。

```sh
# 只读确认：此处应是本项目源码目录和已选定的隔离引擎。
git status --short
# 仅首次复制；已有文件必须先阅读并保留。
test -e .env.project-dev || cp deploy/dev/project-dev.env.example .env.project-dev
npm run project:config
npm run project:up
npm run project:ps
```

`project:up` 包含镜像构建、追加迁移和 seed，不是只读检查或通用更新命令。已有验收环境更新须先确定源码范围、备份和迁移步骤，不为更新重播 seed。配置、数据库、缓存和本地抓取资料不提交 Git；不要从线上复制配置、用户数据或真实订阅。

若网络需要代理，Docker daemon 和主机构建客户端都需能访问镜像仓库；仅设置构建参数不能解决镜像认证请求超时。主机客户端使用 `HTTP_PROXY` / `HTTPS_PROXY`，构建步骤可用 `DEV_BUILD_PROXY` 指定容器可访问的代理地址。这些地址只放在本地配置或当前终端环境。

| 服务 | 默认本机地址 |
| --- | --- |
| 网站与管理入口 | http://127.0.0.1:18082 |
| 后端健康检查 | http://127.0.0.1:18080/healthz |
| 测试 Remnawave | http://127.0.0.1:3000 |
| 面板健康检查 | http://127.0.0.1:3001/health |

开发模板仅绑定本机地址。测试管理员邮箱为 `runes.admin@example.com`，密码为 `Minishop-Dev-2026!`（上游公开测试夹具）。不要将此环境、测试凭据或 QA 登录功能用于公网部署。

`deploy/dev/seed-project-accounts.sql` 是首次初始化用的合成账号数据，不是正在运行数据库的库存清单。已有环境中的账号、套餐、服务和资源以实际记录及实施计划为准，不按初始夹具数量重置或清理。

`deploy/dev/project-dev.env.example` 默认使用 `PANEL_WRITE_MODE=dry_run`，关闭 Telegram、在线支付相关业务、自动试用、余额、分销、订阅通知、遥测及备份；默认 Compose 组合不部署数据面 Node。这里描述的是模板，不是对本机现有环境的探测结果。切换 live、增加 Node 或写入面板前，须核对隔离对象、写入时段和清理范围；仅切换配置不能证明连接交付。

## 检查与停止

**环境与前置：本机源码质量检查。** 以下安装命令仅用于尚未准备好的开发依赖；在共享工作树中先协调依赖使用。按 CONTRIBUTING.md 的修改区域矩阵选择检查，文档修改不因此要求重跑产品全量矩阵。

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt -r requirements-dev.txt
npm ci --prefix frontend
PATH="$PWD/.venv/bin:$PATH" npm run check
```

**环境与前置：仅已授权的隔离本地 QA。** 下例会登录并测试设置保存，属于有写入的测试；先核对目标 URL、测试账号和回退条件，不能对生产站点运行。

```sh
NO_PROXY=127.0.0.1,localhost,::1 QA_FULLSTACK=1 .venv/bin/python -m pytest -q tests/qa/test_fullstack_stand.py \
  -k 'email_auth_session_and_csrf or admin_settings_save_roundtrip'
```

日常只读检查使用 `npm run project:ps`、`npm run project:logs`。**仅在确认没有其他窗口使用同一隔离栈、允许中断本地服务时**，运行：

```sh
npm run project:down
```

该命令限定 `my-vps-obj` 项目并保留数据卷。不要使用无范围的 `down -v` 或 `prune` 排障。仅在确认 VM 没有其他任务时，可用 `colima stop my-vps-obj` 释放该实例资源；恢复使用前重新核对环境，不将重新初始化当作启动前提。

首次运行浏览器测试需执行 `npm exec --prefix frontend -- playwright install chromium`。macOS 的 `/usr/bin/openssl` 可能是 LibreSSL；安装器证书测试需要 OpenSSL，可在测试命令的 `PATH` 前加入已有 Homebrew `openssl@3/bin`，不用替换系统程序。构建文档时也需将 `.venv/bin` 放入 `PATH`。

## 仓库与集成边界

- `origin`：`https://github.com/jzg-lab/my_vps_obj.git`。
- `upstream`：`https://gitlab.com/3252a8/remnawave-minishop.git`；不自动合并更新。[上游兼容参考](../upstream/index.md)保留旧功能和协议资料，不是本项目部署入口。
- `frontend/`、`backend/`、`tests/`、`deploy/` 复用上游目录和接口契约；数据库迁移只追加，不改旧迁移。
- `package.json` 的 `project:*` 固定组合 `docker-compose-dev.yml`、`docker-compose.remnawave-dev.yml`、`docker-compose.project-dev.yml`，并指定项目名及配置文件。项目 overlay 隔离镜像、容器、网络和卷名。
- 常规 CI、面板版本矩阵和发布行为以仓库工作流为准；不能从上游发布标签推断本项目已发布。
- `experiments/` 保存早期离线评估，单独按目录 README 运行；正常 `pytest` 只收集 `tests/`，不将复现上游缺口的实验当成产品回归测试。
- 客户、服务、节点与资源操作对齐指南 F01～F07、UC-01～UC-09 及对应 UA 验收项；模型与契约见[独立服务开发说明](independent-services.md)、[权益与计量契约](entitlement-metering-contract.md#local-validation-and-remaining-acceptance-2026-10-23)。这些文档不替代实施计划的当前证据。

## 本机真实 Node 与恢复演练

当前验证范围及保留边界统一查[本轮本地最终验收](../implementation-plan.md#本轮本地最终验收)。[早期 Node 与恢复演练](../implementation-plan.md#local-node-and-recovery-acceptance)保留历史依据，不能将其中的临时环境、数量或“尚未验证”复制为当前状态。

重复真实节点测试前须独占本地面板写入时段，先记录资源标识，使用隔离商店 schema 和回环端口，结束后仅清理本轮创建的资源。默认无 Node 面板 QA 必须等临时 Node 清理后运行，不修改其保护条件。原生客户端核心验证、各平台 GUI 验证和公网固定独享出口是不同证据，不能互相替代。

恢复步骤与 CLI 入口见[备份说明](../features/backups.md)。恢复会写入数据库或应用文件，须先停止目标写入、保留旧数据及日志，再核查健康和远端差异；商店备份不等于外部面板同步快照。私有演练摘要与归档位于忽略的 `data/backups/`，不公开提交。

下方生产资料保留已记录的地址、版本、密钥路径、备份和节点信息，供后续运维使用；不是本次本地验收的发布证明。已有明确授权在原目标与操作范围内可延续，无需为读全文、普通只读核查或已授权的后续步骤重复请示；文档本身不扩大授权。执行前核对目标服务器及停机、写入范围，超出原范围时再确认。节点接入和共享资源变更仍按指南 F06／F07 完成影响预览与确认；任务明确排除生产访问时，只阅读记录。

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
| 本次源码与构建材料 | 当前 `/opt/my-vps-obj/releases/076c718b-country-20261028`；旧发布目录保留 |
| 当前部署摘要 | `/opt/my-vps-obj/last-deployment.json` |
| 切换前备份 | 当前 `/opt/my-vps-obj/backups/pre-076c718b-country-20261028-final`；旧备份及本轮中断备份保留 |
| 面板 / HTTPS / Node 目录 | `/opt/remnawave`、`/opt/remnawave-edge`、`/opt/remnawave-node` |

SSH 公钥认证原本关闭，本轮已启用并通过不复用旧连接的密钥登录验证；保留原密码登录方式。密码不存入本文、Git 或服务器资料。换电脑时需另行配置密钥，不能假设本机别名自动同步。

### 当前发布（2026-10-28）

backend／worker／frontend 均为远程 `origin/main` 的准确提交 `076c718bcd65b1be87b7ae15c6151a30ab6be00b`，镜像标签 `076c718b-country-20261028`，由仓库完整 Dockerfile 在服务器构建。环境配置与基础服务沿用原部署；追加迁移已应用到 `0122_node_metadata`。实际镜像摘要、各组件提交、源码及最终备份以 `/opt/my-vps-obj/last-deployment.json` 为准。节点列表／详情 API 已验收，实际国家码为一个 `US` 和两个 `XX`，后两者无有效国家信息。完整门禁、切换中断及修复、验收边界见[实施计划第 14 节](../implementation-plan.md#14-统一管理台执行追踪2026-10-24)。下方首次替换过程为历史记录。

### 首次替换与配置基线（2026-10-23，历史）

当时镜像为 `my-vps-obj/backend:b70eb48e-simple-home-20261023`、`my-vps-obj/worker:b70eb48e-simple-home-20261023`、`my-vps-obj/frontend:b70eb48e-simple-home-20261023`，迁移任务引用同一 backend 镜像。本次发布以 `b70eb48ed8596d90baffb71beeeb1b71deb3ff3b` 为基线，包含首页与独立套餐菜单的工作区源码快照，不是该提交的原样构建；发布归档 SHA-256 为 `11785e3b58e91072a71f6d1464f26c3aaf4b4b6ff3b0148f7586a3e6086f12a2`。首次替换产品为 `32185a1631438c9997747bf7f103cf53436789b4`。面板 **3.4.5**、Node **3.4.2**、数据库、Redis 与 Caddy 沿用原部署，没有随业务程序升级。本次无数据库迁移。

为降低 4 GB 服务器上的构建负载，前端在本机按正式构建脚本生成，再在服务器重建三个应用镜像。Python 依赖文件与服务器原固定摘要镜像逐字节一致（SHA-256 `ad6edf1a019a9d1f3dfff1e46a4d41552c607afa5a93cf782db536ea8452b8ec`）；前端 package/lock 和运行入口相对 v3.8.2 未变。因此本轮使用原固定摘要运行环境，完整替换 backend/locales 和前端静态文件，并加入服务教程。构建文件 `Dockerfile.redeploy`、对应 ignore、元数据和前端产物留在本次源码目录；该做法仅适用于这次依赖相同的提交，后续依赖变化应使用仓库完整 Dockerfile 构建。

运行配置为 `APP_RUNTIME_MODE=production`、`PANEL_WRITE_MODE=live`、`DEFAULT_LANGUAGE=zh-hans`；QA 登录、测试支付、Telegram、试用、余额及分销关闭。原 SMTP、账号、会话密钥、面板凭据和域名保留。原有一个账号和一份旧测试订阅保留；旧订阅没有自动变成新服务，新套餐与服务从后台自行创建和开通。首页调整验收时已有用户自行创建的套餐及服务，仅做读取与页面查看，没有改动这些记录。

原部署目录为 root 的 `0700`，导致容器内健康检查无法遍历 Compose 文件。本轮将目录及两个 Compose 文件的组设为应用组 `10001`，权限分别为 `0750`、`0640`；`.env` 保持 `0600`。修复后后台健康接口返回空告警列表。面板 API 正常读取两个节点组；直接诊断内部面板时须使用项目客户端，它会附带面板要求的转发请求头。

### 客户端订阅名称

2026-10-24（北京时间），按用户要求将线上 Remnawave 订阅设置的 `customResponseHeaders.profile-title` 从 `rwEncodeBase64:Remnawave` 改为 `rwEncodeBase64:Yourouter`，作为客户端导入时使用的默认品牌名称。只修改该响应头，不更改订阅链接、节点、流量、有效期或其他订阅设置。使用 Hiddify 4.1.1 与 v2rayN 请求标识，从公网读取现有服务订阅均返回 HTTP 200，`profile-title` 解码结果均为 `Yourouter`；本轮未操作本机 Hiddify，也未验证旧配置是否自动重命名。

变更前设置保留在服务器私有备份 `/opt/my-vps-obj/backups/subscription-title-20261024.json`。操作期间临时增加集成令牌的 `subscription-settings:write`，完成后已恢复原权限，并清除 Redis 与进程内权限缓存。后续更改导入名称应修改面板订阅设置，不需要重建网站镜像。

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

2026-10-23 后续已将简洁首页及独立「我的套餐」菜单部署到同一站点：`/home` 显示品牌与套餐数量摘要，`/services` 承载服务、目录与详情。桌面／手机页面、直接刷新、菜单切换和已有服务详情已在线验证，backend／frontend 健康，worker 运行。用户浏览器可正常访问；本机普通 urllib 公网请求被 Cloudflare 返回 403，不能将其混记为应用故障或该请求通过。完整源码门禁与此轮界面证据见[首页调整记录](../implementation-plan.md#simple-home-20261023)。


### 当前线上节点与新增节点

2026-10-23 只读核查面板：只有一台 Node `US Management Test` 已连接，部署在网站服务器 `38.76.215.26`，面板内部管理地址为 `remnanode:2222`。对客户端发布的 Host 为 `US - Operator Test`，入口 `38.76.215.26:443`，对应 `Operator Test` 组与 `Operator Test WS` 配置中的 `VLESS_WS_TEST` 入站（VLESS / WebSocket，内部端口 10080）。管理端口、内部入站端口与客户端入口不可混淆；用户应导入完整订阅，不是直接输入 IP 即可连接。

`Default-Squad` 原先仅关联 `Default-Profile` 的 Shadowsocks 入站（1234），没有对应的已发布客户端 Host，导致该组服务的订阅返回 `No hosts found` 等占位节点。2026-10-23 经用户授权，已保留原入站并将 `VLESS_WS_TEST` 加入默认组；节点重新载入了该组现有 5 份服务身份，后续使用该组的服务也可获得这条美国测试线路。没有重置额度或到期时间。操作期间临时增加集成令牌的 `internal-squads:write`，完成后已恢复原权限，并清除 Redis 与进程内权限缓存。组变更前记录保留于服务器 `/opt/my-vps-obj/backups/default-squad-connectivity-fix-20261023.jsonl`。

修复后，从用户 Mac 读取原故障服务的真实订阅配置，临时运行官方 sing-box 1.14.3（发布资产 SHA-256 已核对），经该节点访问 Google 连通性检测返回 204、Cloudflare 与 Wikipedia 返回 200；Cloudflare 报告出口为 `38.76.215.26`。临时内核已关闭，含身份的临时配置已删除。此证据验证了该服务的公网数据面，但本轮未完成 Hiddify 界面内的订阅更新与切换，客户端仍需刷新旧占位节点缓存。两台现用 3x-ui 服务器的后续并行接入证据见实施计划第 15 节。

新增多节点套餐线路的顺序：

1. 在新服务器部署 Remnawave Node，由当前 [Remnawave 面板](https://panel.yourouter.org/auth/login) 统一管理；不需要每台重新安装一套面板。
2. 在面板建立 Node 及对应配置/入站，再建立客户端 Host，填写实际地址、端口和协议所需参数，确认 Node 在线。
3. 将该入站加入目标内部节点组（Internal Squad），例如普通线路组或优化线路组。服务通过组获得节点权限；新增 Host 本身不等于授予所有用户访问。
4. 在 [网站套餐后台](https://vpn.yourouter.org/admin/service-plans) 创建/编辑模板并选择该节点组，再从用户管理开通服务。模板更换组只影响后续开通，已有服务保留资源范围快照；在已有组内增加入站则会改变该组成员可用的线路。
5. 用一份已授权服务在通用客户端更新订阅，核对节点出现、可连接和流量归属。没有实测前不以面板“在线”代替连接成功。

已有 3x-ui 服务器不能仅录入 IP 就纳管：需要明确并行部署还是迁移，在端口和现有配置安排好后接入 Remnawave Node。单人单 IP 套餐还需实际独享出口及资源验证，增加节点组不会自动创造独享 IP。

### 两台现用 3x-ui 服务器的 SSH 连接

用户于 2026-10-24（北京时间）选择保留 3x-ui、并行部署 Remnawave Node，并授权配置本机密钥登录。后续使用下列已保存连接，不再重复索取密码：

| 本机命令 | 服务器 | SSH 用户／端口 |
| --- | --- | --- |
| `ssh vpn-node-103` | `103.214.68.94` | `root`／`22` |
| `ssh vpn-node-93` | `93.115.10.171` | `root`／`22` |

别名保存在本机 `~/.ssh/config`，专用 Ed25519 私钥为 `~/.ssh/my_vps_obj_nodes_ed25519`，权限 `0600`；公钥已追加到两台服务器的 `/root/.ssh/authorized_keys`。密钥无口令，因此这台 Mac 上能够读取私钥的进程具有相应服务器访问能力；私钥不写入仓库，也不传到服务器。两台均已通过禁用密码认证且不复用连接的 SSH 登录验证，原密码登录保留。换电脑需要安全迁移密钥或另行授权新公钥，本机别名不会自动同步。

服务器私有备份目录均为 `/root/my-vps-obj-backups/20261024-parallel-node`，包含 SQLite 在线备份及原配置；备份数据库已通过完整性检查。实际接入进度与验收结果仅在[实施计划第 15 节](../implementation-plan.md#existing-node-onboarding-20261024)维护。

两台并行 Node 的运行位置：

| 项目 | 位置／配置 |
| --- | --- |
| 部署目录 | `/opt/remnawave-node`；`node.env` 私有凭据禁止提交 |
| 服务／容器 | `remnawave-node.service`、`remnawave-management-guard.service`；`remnanode` |
| 镜像 | `remnawave/node:3.4.2@sha256:1f97485b4bc7e4944f1ae95cc57d176376813b0022e9567b705f384f1a2e909d` |
| 客户端入口 | 各自公网 IP 的 TCP 24443，VLESS／Reality／Vision |
| 管理入口 | TCP 2222，仅中央服务器 38.76.215.26；nft 表 `inet remnawave_management` |
| Profile | `Parallel Reality 103`、`Parallel Reality 93` |
| Host | `Reality - 103.214.68.94`、`Reality - 93.115.10.171` |
| 授权组 | `Parallel Nodes`、`Default-Squad`，默认组保留原入站 |
| 兼容配置 | 两个新配置 `minClientVer=0.0.0`，SNI／目标 `www.cloudflare.com`，认证和加密保留 |

容器使用 host 网络、内存上限 320 MiB、无额外 swap、CPU shares 256、PID 上限 256、日志 10 MiB × 3。检查可用 `ssh vpn-node-103 'systemctl status remnawave-node --no-pager'`，另一台替换 SSH 别名。旧 3x-ui 身份、订阅、用量及到期由旧系统独立维护；不要在未确认端口影响前替换旧配置。
