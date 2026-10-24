# 常见问题

<a id="проблемы"></a>

排障先确认环境与对象：本机使用[隔离源码流程](../development/project-local.md)，已有线上资料见 [production-access](../development/project-local.md#production-access)。客户问题按“客户 → 具体服务 → 资源与节点”定位，节点问题反查潜在影响客户；对应[统一管理台指南](../admin-console-guide.md) F02／F03、UC-05、UA-13。当前验证边界只查[本轮本地最终验收](../implementation-plan.md#本轮本地最终验收)。

> 本页保留上游 Telegram、支付等功能的排障说明，并不表示本项目 MVP 已启用这些业务。本项目当前采用管理员手动激活、无支付的方案；开发与验收使用[隔离开发环境](../development/project-local.md)，不得将现有生产节点作为测试资源。

## 服务栈无法启动

<a id="стек-не-стартует"></a>

- 本地用 `npm run project:config`、`npm run project:ps`；日志命令见[日志](logs.md)。这些检查不启动或重建容器。
- 查看目标项目的 `migrate` 日志，不为读日志重新运行迁移。
- 确认 PostgreSQL 和 Redis 健康。
- 检查该环境实际读取的文件和覆盖值；本地是 `.env.project-dev` 及项目 overlays，通用部署是对应 `.env`。

如果日志出现 `password authentication failed for user "remnawave_minishop"` 或
`InvalidPasswordError`，先核对应用实际连接的主机、数据库、账号、密码与已有卷。
常见原因是环境文件密码与初始化时不一致，也可能连错数据库或加载了错误环境，不能仅凭错误就断定卷损坏。已有数据不得通过删卷排障；确认原凭据后修正配置，确需轮换时另行制定数据库与应用同步步骤。不要使用无范围 `down -v` 或 `prune`。

## 服务存在但无法连接

先查账号封禁、单份服务暂停、到期与额度，再查交付、同步、线路及节点观测。业务记录成功、面板在线和订阅返回 HTTP 200 都不能单独证明实际连接可用。

- `dry_run` 不产生可用的真实交付证明，默认开发模板没有数据面 Node。
- “待接入节点”只是名称、地址、备注登记，不探测或安装服务器，也不按名称／地址自动认领已纳管 Node。
- 订阅出现 `No hosts found` 等占位项时，核对 Host、入站、授权组和该服务身份；不能把非空订阅一概当作可用线路。
- 客户端按具体服务刷新订阅。原生核心验证不能替代该平台 GUI 操作验证；旧配置和已有连接的停用也需单独核对。
- 断连能力须按实施计划中的固定 Node／协议／适配器边界理解，不能从某个本地适配通过推导默认 Node 或所有协议都精准断连。
- 不通过重建身份、清零用量、重复开通或消费另一份服务掩盖异常。共享组／线路变更按 F07 展示影响并确认，专用出口不能自动降为共享出口。

## 高级维护入口不可用

统一管理台高级维护只使用显式且通过安全校验的 `PANEL_PUBLIC_URL`。留空、内部主机、私有地址或嵌入凭据等值会使入口不可用，不回退到 `PANEL_API_URL`。这不等于 backend 无法连接面板 API；核对两者用途及权限，不能把凭据拼入浏览器 URL，也不承诺自动登录。

## Telegram webhook 不工作

<a id="вебхук-telegram-не-работает"></a>

仅适用于已明确启用 Telegram 的上游兼容环境；本项目默认关闭时不应通过启用 Telegram 修复其他服务问题。

- 检查 `WEBHOOK_BASE_URL`。
- 确认域名可通过 HTTPS 访问。
- 检查 `WEBHOOK_SECRET_TOKEN`。
- 查看入站事件发生时的 backend 日志。

## Mini App 无法打开

<a id="mini-app-не-открывается"></a>

以下为 Telegram Mini App 兼容检查；普通浏览器网站先核对 frontend、`PUBLIC_APP_URL` 与同源 API。

- 检查 `SUBSCRIPTION_MINI_APP_URL`。
- 确认 URL 指向 frontend，而非 `/api` 或 webhook 域名。
- 检查 BotFather 设置。
- 查看 frontend 和 backend 日志。

## 管理后台报告数据挂载不一致

<a id="админка-сообщает-о-разных-data-mount"></a>

`data_mount_mismatch` 表示 `migrate`、`backend` 和 `worker` 的 `/app/data`
使用了不同的源数据卷或绑定挂载，或某个服务缺少该挂载。这会导致迁移、套餐、翻译及备份
作用于不同的文件集合。

- 打开诊断消息指定的 Compose 文件。
- 比较 `migrate`、`backend` 和 `worker` 中 `:/app/data` 左侧的源。
- 标准安装的三个服务应共用同一 `shop-data:/app/data`；使用绑定挂载时，
  应共用同一宿主机路径，例如 `./data:/app/data`。
- 确认唯一数据源、备份与允许中断范围后，按目标项目完整 Compose 参数修正并重建相关容器，再次打开设置诊断。不要把不同卷直接合并或清空。

不要将不同数据卷之间逐个复制文件作为长期解决方式。应先确定唯一的数据来源，
再让三个服务共用它。

## 付款未入账

<a id="платеж-не-засчитался"></a>

仅适用于已启用支付的上游兼容环境。本项目一期人工开通，不以测试支付作为服务排障前置。

- 检查支付渠道是否启用。
- 检查 webhook URL 和密钥。
- 查看 backend 日志。
- 核对管理后台与支付渠道后台中的付款状态。

详情参见[日志](logs.md)和[部署](../getting-started/deployment.md)。
