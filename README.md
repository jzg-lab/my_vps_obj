# 我的 VPN · my_vps_obj

基于 Minishop 二次开发的 VPN 业务网站与统一管理台。产品围绕**客户**和**节点**组织：一个账号可拥有多份独立服务，管理员在同一网站管理客户、服务、节点与资源；Remnawave 负责节点控制和执行。

一期由管理员人工开通，使用通用订阅客户端，不接在线支付；自有 App 后续规划。统一的是产品和业务流程，业务应用、Panel 与 Node 仍按职责独立运行。

## 接手项目

| 要做什么 | 从哪里开始 |
| --- | --- |
| 第一次接手或换窗口继续 | [项目接手指南](docs/handoff.md) |
| 查完整文档分类 | [文档目录](docs/index.md) |
| 确认业务规则 | [需求基线](docs/requirements.md) |
| 修改管理入口、客户、节点或指标 | [统一管理台实施指南](docs/admin-console-guide.md) |
| 判断完成了什么、还缺什么 | [实施计划第 14 节](docs/implementation-plan.md#14-统一管理台执行追踪2026-10-24) |
| 使用和排查管理台 | [管理员操作手册](docs/user-guide/admin-workflows.md) |
| 启动当前项目开发环境 | [隔离本地环境](docs/development/project-local.md) |
| 修改代码、准备验证 | [贡献指南](CONTRIBUTING.md)与[架构概览](docs/architecture.md) |

当前进度、验收范围和遗留项只在实施计划维护。**本地通过、真实节点验证和生产发布是不同状态**；早期线上试测或其他窗口的节点记录，不代表全部工作区改动已上线。

<a id="возможности"></a>

## 核心模型

- **账号／客户**：登录与管理身份，可以拥有多份服务。
- **套餐模板**：定义资源类型、额度、周期、有效期及价格。
- **独立服务**：保存具体客户的权益、条款快照、用量和状态。
- **连接身份**：每份服务独立绑定，订阅与计量不会因共用账号而合并。
- **节点与资源**：节点、线路、授权组和专用出口可追溯到服务与客户。

业务规则和体验见[需求](docs/requirements.md)及[产品设计](docs/product-design.md)。上游的单订阅、支付、礼品和营销配置不能替代本项目的独立服务模型。

<a id="стек"></a>

## 工程与环境

沿用 Svelte 5／TypeScript、Python／aiohttp、SQLAlchemy、PostgreSQL、Redis 与现有 worker。版本以依赖锁文件、Compose 和对应部署记录为准；不要仅凭 README 推断正在运行的镜像。

| 位置 | 职责 |
| --- | --- |
| `frontend/` | 用户网站、统一管理台与共享组件。 |
| `backend/bot/app/web/` | HTTP 路由、权限和类型化契约。 |
| `backend/bot/services/`、`backend/db/` | 业务生命周期、同步、模型、DAL 与追加迁移。 |
| `deploy/`、Compose 文件 | 环境与执行层部署材料。 |
| `docs/` | 手写文档及由指定生成器维护的技术目录。 |
| `docs-site/` | 文档站、导航和生成副本。 |

<a id="быстрый-старт"></a>
<a id="полезные-команды"></a>

开发时先读[项目环境记录](docs/development/project-local.md)，使用指定 Docker context、环境文件和 Compose 项目。上游安装器或公开 Minishop 镜像不包含本仓库全部二开改动。不要把通用演示 seed、现有生产节点或默认 Docker daemon 当成本项目可任意重置的测试环境。

质量门禁按 [CONTRIBUTING.md 第 1 节](CONTRIBUTING.md#1-质量门禁推送前按修改范围选择)执行。生成产物运行生成器，数据库迁移只追加；已有未提交改动和其他窗口工作应保留。

<a id="документация"></a>

## 文档维护

需求、规格、进度、运行资料和历史分别维护，详见[文档维护规范](docs/documentation.md)。旧实施过程保存在[历史归档](docs/archive/index.md)，不再作为当前任务清单。

[English overview](README.en.md) · [发布历史](CHANGELOG.md) · [安全说明](SECURITY.md)

<a id="совместимость"></a>

## 上游与许可

本项目基于 Minishop v3.8.2，导入基线提交为 `04b0ca5e210a33209bbf15485003865ee29304bc`。保留 [MIT 许可](LICENSE)、版权、Git 历史及仍有效的兼容功能。

上游单订阅、支付、营销、主题、插件和其他机器人迁移资料按适用范围归入[上游兼容与扩展](docs/upstream/index.md)。Remnawave 受支持接口以[生成的兼容目录](docs/architecture/remnawave-api-compatibility.md)为准；声明兼容不等于全部版本和场景均已实测。
