# AGENTS.md

## my_vps_obj 项目决策

先阅读[需求](docs/requirements.md)、[产品设计](docs/product-design.md)、[实施计划](docs/implementation-plan.md)和相关本地文档。遵循第一性原理，采用最小且完整的修改；区分已验证行为与拟议行为。业务规则未确定时，先询问再实现。

本项目基于 Minishop 二次开发，不是仅靠插件实现。目标是一个账号持有多份独立服务。MVP 由管理员人工开通，不接支付，使用通用订阅客户端；自有 App 后续开发。流量按上传加下载的业务载荷计算，用户体验优先于绝对零超额承诺。使用[隔离项目开发环境](docs/development/project-local.md)，不得把现有生产 3x-ui 节点当作可随意处置的测试设施。

保留下述上游约定。若存在 `.codegraph/`，理解或查找代码时先用 CodeGraph，再做文本搜索；未经用户要求不得创建索引。

本文是 AI 智能体入口。开发约定、架构及强制质量门禁的唯一来源为中文[贡献指南](CONTRIBUTING.md)，**改代码前必须阅读**。架构概览：[docs/architecture.md](docs/architecture.md)。

不可违反的规则（详见贡献指南第 2 节）：

- 生成产物必须运行生成器，不得手改，包括 `openapi.json`、`events.md`、`openapi.generated.ts` 和设置清单。
- 数据库迁移只能追加，不得修改或重排已有迁移。
- 不得用 `# type: ignore`／`any` 压制自有代码类型检查；整个后端 mypy 必须通过。
- 不得破坏线上契约：HTTP `{"ok": …}` 包装、事件扁平字典载荷、插件 `(event_name, dict)` 订阅签名。
- `frontend/src` 自有 Svelte 只使用 runes，禁止 `export let`、`$:`、`$$props`、`$$restProps`、`<slot>`、`<svelte:component>`、`createEventDispatcher` 和类 API `$set`。所有自有前端使用 TypeScript（`.ts`／`<script lang="ts">`），由架构门禁保护；不开全局 `checkJs`，使用 API 字面量路径，并 `unwrap` 响应包装。
- 用户和管理员文案必须本地化，不得硬编码。新增或变更的界面／机器人键至少包含 `locales/ru.json`、`locales/en.json` 基础条目，中文路径同时提供 `locales/zh-hans.json`；组件回退不能替代基础语言键。
- 必须复用界面组件：遵循贡献指南第 4.1 节及组件表，优先已有实体／操作组件，查看两个实际消费者，先扩展共享模式，再考虑局部替代。共享 CSS 不等于共享组件。验证受影响消费者的桌面／手机布局，包括打开的菜单和对话框。
- 先拆分再完善类型；没有理由的模块不得超过约 900 行；注意 monkeypatch／重新导出陷阱（贡献指南第 5 节）。
- “兼容其他机器人”是应保留的功能，不是可删除旧代码。
- 核心与单独交付的 PRO 隔离。公开核心文档和导航可提及 minishop PRO、概述公开能力并链接官网；不得复制 PRO 代码、私有契约、资源或运行时依赖到核心。
- 余额工作必须包含删除礼品退款。丢弃未使用已付礼品却不退款的临时流程，只能保留到余额退款集成完成。实现或修改用户余额流程时，必须先原子地把礼品实付金额记入购买者余额，再撤销／移除礼品权益。退款路径及回归测试实现前保留 `TODO(balance-gift-refund)`。

推送前按贡献指南第 1 节修改区域矩阵验证。产品或共享代码运行相关门禁，无法证明隔离时完整检查；纯文档或仅文档站修改运行其中规定的限定检查。提交采用英文 Conventional Commits，不加 `Co-Authored-By` 尾注。

根 `CHANGELOG.md` 是唯一发布历史来源，由文档生成器发布到 `/changelog/`。提交值得记录的核心修改前，更新“开发中 · dev”：描述最终行为，合并相关条目，移除失效或重复项；不按每次提交新增条目，也不重复已发布行为。更新历史和提交说明使用“激活码”／“activation codes”等中性措辞。版本滚动和来源规则见贡献指南第 8 节。
