# 我的 VPN · 文档目录

<a id="remnawave-minishop"></a>

一个账号可以拥有多份独立服务；管理员沿**客户**与**节点**两条主线，在同一网站完成日常管理。业务网站基于 Minishop 二次开发，节点执行继续使用 Remnawave。

本目录按任务组织文档。当前交付和未验收范围统一查看[实施计划第 14 节](implementation-plan.md#14-统一管理台执行追踪2026-10-24)，不以方案、演示或历史记录替代当前证据。

<a id="minishop-start-title"></a>

## 1. 项目接手与规格

| 文档 | 解决的问题 |
| --- | --- |
| [项目接手指南](handoff.md) | 新窗口、新开发者从哪里读起，哪些规则不能误解。 |
| [项目概览](getting-started/overview.md) | 产品组成、客户与管理员的核心流程。 |
| [需求基线](requirements.md) | 已确认规则、一期范围、待定事项。 |
| [统一管理台实施指南](admin-console-guide.md) | 页面职责、客户与节点流程、指标及验收编号。 |
| [信息展示与运营闭环实施方案](information-experience-plan.md) | 可信展示、关键反例、经营事实与真实任务验收，含实践调整机制。 |
| [产品设计](product-design.md) | 用户体验、业务对象和服务生命周期。 |
| [架构决策](architecture-assessment.md) | 为什么采用当前结构，以及保留哪些边界。 |
| [实施计划与验收](implementation-plan.md) | 当前工作包、证据、遗留项及独立生产记录。 |
| [文档维护规范](documentation.md) | 事实归属、分类、生成器和更新检查。 |

## 2. 日常使用

- **管理员**：[操作手册](user-guide/admin-workflows.md)、[管理台页面与权限](features/admin-panel.md)、[服务器状态入口](features/server-status.md)。
- **客户**：[我的套餐与网页应用](features/web-app.md)、[选择客户端与导入服务](user-guide/clients-zh.md)。
- **账号与沟通**：[登录方式](features/login-methods.md)、[不使用 Telegram](features/telegram-optional.md)、[客服与工单](features/support.md)、[通知](features/notifications.md)。

操作步骤描述受支持流程；某部署是否开放、某客户端是否实测，要结合该页适用范围和实施证据判断。

## 3. 开发与运维

- **启动项目**：[隔离项目环境](development/project-local.md)、[快速启动](getting-started/setup.md)、[系统要求](getting-started/system-requirements.md)、[初始配置](getting-started/configuration.md)。
- **发布与维护**：[部署参考](getting-started/deployment.md)、[日常维护](troubleshooting/maintenance.md)、[备份](features/backups.md)、[安全](configuration/security.md)。
- **定位问题**：[常见问题](troubleshooting/issues.md)、[日志](troubleshooting/logs.md)、[环境变量](configuration/env-vars.md)、[匿名遥测](configuration/telemetry.md)。
- **开发验证**：[开发操作指南](development/how-to.md)、[测试环境](test-environments.md)、[通用开发环境](development/dev-stand.md)、[Runes 验收](development/runes-migration-qa.md)、[Graphify](development/graphify.md)。

当前项目开发优先使用项目环境文档。通用开发环境和上游部署方案有各自用途，不能直接覆盖已有项目数据。

## 4. 技术参考

- **业务与结构**：[架构概览](architecture.md)、[独立服务模型与接口](development/independent-services.md)、[权益与计量契约](development/entitlement-metering-contract.md)、[连接与资源交付](development/service-delivery.md)、[中文与体验](development/chinese-localization.md)。
- **接口**：[API 总览](api/index.md)、[HTTP 契约](architecture/http-api.md)、[公开订阅网关](architecture/subscription-gateway.md)、[Remnawave 兼容目录](architecture/remnawave-api-compatibility.md)、[事件目录](architecture/events.md)。
- **扩展**：[插件开发](development/plugins.md)、[扩展 SDK](development/plugin-extensions.md)、[页面与卡片组合](development/plugin-ui-composition.md)、[插件契约](development/plugin-contract.md)。

源码层面的开发规则和质量门禁见仓库根目录 `CONTRIBUTING.md`；生成目录不是手写文档。

<a id="minishop-features-title"></a>

## 5. 上游兼容与可选扩展

[兼容参考索引](upstream/index.md)集中说明哪些内容属于原单订阅业务、哪些是可复用基础能力：

- 单订阅套餐、支付、礼品、余额、激活码与合作伙伴。
- 广告来源、报表与平台数据导入。
- 主题、主题包与界面效果。
- 从其他机器人迁移，以及独立交付的 PRO 公开说明。

这些能力仍需维护，但不能据此推断本项目一期启用支付、营销或旧单订阅流程。

## 6. 历史与发布

- [历史归档](archive/index.md)：初始架构调查、旧阶段实施和交接记录。
- [发布历史](../CHANGELOG.md)：唯一发布记录，开发中条目不等于已部署。

接手时先看当前实施计划；只有追查某个决定或证据时才进入归档。
