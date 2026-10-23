# 项目概览

<a id="обзор"></a>

本项目基于 Remnawave Minishop 改造，目标是一个账号管理多份独立服务。网站和运营后台共用同一套业务记录；一期由管理员人工开通，不启用在线支付。客户端使用通用订阅应用，自有 App 后续开发。完整规则见[需求基线](../requirements.md)与[产品设计](../product-design.md)。

## 主要组件

<a id="основные-компоненты"></a>

- **Backend**：网站和后台 API、账号与服务规则、Remnawave 面板对接。
- **Worker**：后台同步、用量采集、重试和周期处理。
- **Frontend**：用户网站、运营后台和演示页面。
- **PostgreSQL**：账号、套餐、服务、资源、订单历史及其他业务记录。
- **Redis**：缓存、队列、状态和分布式锁；独立服务的账号变更使用数据库账号行锁串行化。
- **Remnawave Panel**：连接身份、订阅与节点侧权限。真实节点尚待隔离验收。

生产部署使用 Docker Compose。开发和测试请使用[项目隔离环境](../development/project-local.md)，不要把现用节点当作可销毁的测试资源。

## 用户流程

<a id="для-пользователей"></a>

用户登录后可查看自己的多份服务，选择其中一份核对资源、流量、到期时间和连接状态。每份服务的订阅与计量独立；一份服务耗尽不会自动使用另一份的额度。等待配置或核验时，页面应明确显示当前状态。[客户端中文教程](../user-guide/clients-zh.md)说明如何选择服务、安装客户端、导入和更新；导入及连接实测仍待完成。

上游 Minishop 还包含邮箱验证码、邮箱密码、Telegram、Google、Yandex 和通行密钥等[登录方式](../features/login-methods.md)，以及购买订阅、流量包、设备扩容、试用、[激活码](../features/promocodes.md)、推荐和站内客服工单。这些能力有对应代码或文档，但不表示本项目一期启用支付、营销和推荐流程。上游还提供内嵌安装说明及公开 `/s/<token>` 链接；独立服务必须使用当前服务已交付的订阅入口。

## 管理员流程

<a id="для-администраторов"></a>

管理员配置套餐，人工开通服务，登记专用出口，处理暂停、续期、用量核对和账号生命周期。模板额度修改影响同模板已开通服务的当前及未来额度；已用流量、价格、到期时间与资源快照保留。详细接口和状态见[独立服务说明](../development/independent-services.md)。

上游后台还包含支付配置、外观、客服、群发、激活码和日志等页面，也可与 Remnawave Panel 手动同步，并维护 JSON 套餐目录。相关功能分别见[网页管理后台](../features/admin-panel.md)、[网页应用](../features/web-app.md)和[客服与工单](../features/support.md)。

## 演示与验收边界

<a id="демо-режим"></a>

[打开演示](/demo/home)可以在浏览器中查看模拟用户和后台流程，不需要真实数据库、面板或节点。演示成功只证明界面行为，不代表订阅、计量、限额、停用或专用 IP 在真实连接中通过验收。

演示默认使用简体中文和独立服务模式，语言设置中仍可切换英语或俄语；再次打开会保留已保存的语言偏好。连接教程从服务详情中的“导入订阅”展开，所用订阅地址仅为演示占位。

常用演示入口：[用户首页](/demo/home)、[服务与连接教程](/demo/home?delivery=1)、[后台用户](/demo/admin/users)、[后台备份](/demo/admin/backups)、[登录与注册](/demo/login?mock=auth)。演示由 `docs-site/scripts/build-demo-runtime.mjs` 随文档站一起构建：`docs-demo` 模式接入模拟数据和 API，构建后将主要 `/demo/*` 路由生成静态页面。演示运行时不进入正式网站构建。

## 继续阅读

<a id="куда-идти-дальше"></a>

- [快速开始](setup.md)：使用 Docker Compose 启动的最短路径。
- [生产部署](deployment.md)：Docker Compose、Caddy、Angie、Nginx、Pangolin/Newt 等部署方式。
- [初始配置](configuration.md)：连接 Remnawave，配置网站与后台。
- [登录方式](../features/login-methods.md)：邮箱、Telegram、OAuth 与通行密钥。
- [实施计划](../implementation-plan.md)、[本地开发](../development/project-local.md)、[简体中文覆盖说明](../development/chinese-localization.md)：本项目的进度、隔离测试和翻译边界。
