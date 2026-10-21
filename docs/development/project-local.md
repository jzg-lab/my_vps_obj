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

基础测试数据仅包含三个虚构账号，不预置付款、套餐或节点身份绑定；重复启动不会覆盖已编辑的账号。页面当前仍是上游单套餐模型，不能作为多服务业务验收。没有实际节点，也不会交付可用的代理连接；Remnawave 写操作默认为 dry-run。后续新增服务时再明确标注模拟数据。

本项目开发配置关闭 Telegram、在线支付、自动试用、余额、分销、订阅通知、遥测及备份。保留上游功能代码以减少派生差异；这些功能不因此进入 MVP 范围。后台 worker 使用同一个本地面板和数据库。上游后台会提示本地地址使用 HTTP；公网 HTTPS 部署仍是后续阶段，不通过隐藏提示冒充生产就绪。

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
- 正式部署、现有 3x-ui 节点接管和数据迁移另行安排。
- `experiments/` 保存早期离线评估，单独按目录 README 运行；正常 `pytest` 只收集 `tests/`，不将“复现上游缺口”的实验当成产品回归测试。
