# 快速启动

<a id="быстрый-запуск"></a>

本页是 **my_vps_obj 二开项目**的启动入口。先读[接手说明](../handoff.md)、[需求基线](../requirements.md)与[统一管理台指南](../admin-console-guide.md)，再从[隔离项目开发环境](../development/project-local.md)运行当前仓库源码。一期由管理员人工开通，一个账号持有多份独立服务，不接支付。

上游安装器、公开 Minishop 镜像和上游仓库克隆不会自动包含本项目改造，不能用于替换当前二开站点。已有环境先核对源码、配置、Docker context 与验收记录，不把首次安装步骤重放到正在使用的工作树或数据卷。

开始前检查[系统要求](system-requirements.md)。完整目录见[文档索引](../index.md)。

## 最小启动流程

<a id="минимальный-запуск"></a>

**环境与前置：仅首次建立本机隔离开发环境。** 先完成[本机引擎选择与核对](../development/project-local.md#先选择并核对本机引擎)，在同一终端、本项目仓库根目录运行；确认端口未被其他项目使用，且尚无 `.env.project-dev`。已配置环境按[本地开发说明](../development/project-local.md)检查，不覆盖配置、不为更新重播 seed。

```bash
test -e .env.project-dev || cp deploy/dev/project-dev.env.example .env.project-dev
npm run project:config
npm run project:up
npm run project:ps
npm run project:logs
```

`project:up` 包含构建、迁移和 seed，并非只读检查。源码来自当前工作树，未提交修改也会进入构建；提交号不能单独代表实际运行内容。默认入口为 `http://127.0.0.1:18082`，测试凭据及隔离限制见本地开发说明，禁止用于公网。

## 优先填写的配置

<a id="что-заполнить-в-первую-очередь"></a>

本地使用 `.env.project-dev` 与 Compose overlays 的隔离默认值，不复制线上 `.env`、真实账号或订阅。切换真实面板、`PANEL_WRITE_MODE=live`、邮箱发送或公网监听会改变影响范围，须先明确测试目标和授权。

配置分层、面板 API 与浏览器地址、登录及 webhook 见[初始配置](configuration.md)。完整变量名和默认值见[环境变量参考](../configuration/env-vars.md)；参考中保留的支付、营销和 Telegram 配置不是一期启用清单。

## 选择 Compose 方案

<a id="как-выбрать-compose-вариант"></a>

本项目开发使用 `package.json` 中的 `project:*` 命令，固定组合基础开发 Compose、Remnawave overlay 和项目 overlay。已有线上站点的目录、版本、备份及连接资料见 [production-access](../development/project-local.md#production-access)；更新前单独核对部署记录和回退方案，本地验收不等于生产发布。

以下链接保留**上游通用部署兼容参考**。其中示例目录默认使用公开上游镜像，不能原样当作当前项目部署：

- [安装向导](deployment.md#интерактивный-install-wizard)：上游新装或旧机器人迁移。
- [Caddy](deployment.md#caddy-рекомендуемый-вариант)：自动 HTTPS 的上游方案。
- [Angie](deployment.md#angie)：适合需要 Caddy 式自动 HTTPS、同时偏好 Nginx 配置语法的场景。
- [Nginx](deployment.md#nginx)：适合已有 TLS 证书、需要在 Docker 网络内使用 Nginx 的场景。
- [Pangolin/Newt](deployment.md#pangolin--newt)：适合无法开放应用服务器入站端口的场景。
- [无反向代理](deployment.md#без-обратного-прокси)：适合本地检查或由外部服务终止 TLS 的场景。

## Web App 配置

<a id="настройки-для-веб-апп"></a>

- [登录方式](../features/login-methods.md)：邮箱验证码、邮箱与密码、Telegram、Google、
  Yandex 和通行密钥（passkey）。

## 首次登录后

<a id="после-первого-входа"></a>

1. 使用本机测试账号登录，确认管理员能从网站进入管理台，普通用户不能访问管理接口。
2. 沿“客户 → 服务”和“节点 → 资源 → 关联服务”两条路径核对对象与权限；无资源或未知指标保持真实空态。
3. 仅在已约定的隔离场景中创建模板、人工开通独立服务；记录所用服务和资源标识，避免重复开通。
4. 分别核对页面、远端执行、客户端订阅及实际连接；dry-run、模拟页面、待接入登记不能替代真实交付。

这些是操作顺序，不是已通过的验收声明。对应 UC-01～UC-09、F01～F07 与 UA 验收项见[统一管理台指南](../admin-console-guide.md)；当前进度、证据及未验收边界只查[本轮本地最终验收](../implementation-plan.md#本轮本地最终验收)。
