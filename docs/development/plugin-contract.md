# 插件契约

<a id="контракт-плагинов"></a>

类型化契约的唯一依据是 [`../../backend/bot/plugins/spec.py`](../../backend/bot/plugins/spec.py)。本页说明主要接口，不重复列出全部定义。

> 本文保留上游插件能力说明。支付、账号级订阅及营销扩展不因此进入本项目 MVP；当前采用人工开通、多份独立服务和无支付方案，详见[需求基线](../requirements.md)。

## API 版本与兼容性

<a id="версия-api-и-совместимость"></a>

当前公开插件 API 版本为 `PLUGIN_API_VERSION = 1`。新的外部插件必须在 `Plugin` 类上声明包含边界的 `plugin_api_min_version` 与 `plugin_api_max_version` 范围。如果当前核心版本不在范围内，或范围格式无效，加载器会在调用钩子前停止启动。API v1 暂时兼容未声明版本的旧插件；它们应在下一次不兼容发布前补齐明确范围。

插件继承 `Plugin`，只覆盖需要的钩子：

- `setup(ctx)`：注册服务及事件订阅。
- `setup_bot(ctx, user_root, admin_root)`：接入 aiogram 路由。
- `setup_web(ctx, app, scope)`：增加 aiohttp 路由。
- `worker_tasks(ctx)`：注册 worker 进程中的长期协程任务。
- `queue_handlers(ctx)`：注册 webhook 队列处理器。
- `migrations()`：返回插件迁移链。
- `locales_dir()`：提供额外的 JSON 语言目录。
- `locale_groups()`：提供后台插件翻译的可选分组层级。
- `entitlements_provider()`：接入功能开关。

`locale_groups()` 返回 `PluginLocaleGroup`：`path` 定义嵌套名称，`prefixes` 定义语言键前缀，可选 `path_keys` 为每个名称指定翻译键。`path_keys` 与 `path` 长度必须相同；缺少翻译时显示 `path` 中的名称。前缀重叠时选择最长匹配。没有匹配分组的文案归入该插件的“其他文案”组。

`entitlements_provider()` 是唯一权威来源，只允许一个提供者。多个插件返回提供者时，启动必定报配置错误，不按加载顺序任意选择。

`PluginContext` 包含设置、可选 bot/dispatcher/session factory、i18n 及共享 `services` 字典。`services` 是公开扩展接口，键必须为字符串；辅助入口可能缺少可选字段，钩子必须能处理这种情况。核心内部服务和类型化插件代码优先使用上下文辅助方法：

- `ctx.require_bot()`、`ctx.require_i18n()`、`ctx.require_session_factory()`：入口必须提供对应运行时对象时使用。
- `ctx.panel_service`、`ctx.subscription_service`、`ctx.notification_service` 及对应 `ctx.require_*`：无需字符串键即可获得类型化核心服务。
- `ctx.audience_segmentation_service` 与 `ctx.require_audience_segmentation_service()`：通过 `AudienceProvider` 注册额外的群发受众。
- `ctx.get_service("my_service", MyService)` / `ctx.require_service("my_service", MyService)`：访问插件添加的服务，并在运行时检查类型。

直接访问 `ctx.services[...]` 仍是外部插件和动态键的兼容 API。新的内部代码在键已知时，应使用类型化辅助方法。

Web 插件接收 `bot.plugins.spec` 中的以下一种作用域：

- `WEB_SCOPE_WEBAPP`：Mini App 和管理 API。
- `WEB_SCOPE_WEBHOOKS`：支付、面板、健康检查及 Telegram webhook 路由。

领域事件订阅器保留公开签名 `(event_name, dict)`。载荷结构见 [`../architecture/events.md`](../architecture/events.md)，由 `bot.infra.event_payloads` 中的 pydantic 模型校验；外部订阅器仍接收普通的扁平 `dict`。

最小可运行示例位于 [`../../examples/plugins/audit_logger_plugin`](../../examples/plugins/audit_logger_plugin)，演示 `setup`、`setup_web` 及通过 `bot.infra.events.subscribe` 订阅事件。

## 客服连接器

<a id="обработчики-поддержки"></a>

能力 `support_connector=3` 补充 `bot.plugins.support_connector` 的版本 1 和版本 2 导出。`SupportService.get_ticket_context(ticket_id, expected_user_id=...)` 检查所有者，返回只包含标量的 `SupportTicketContext`：修订号、状态、最近公开历史（最多 100 条消息）、是否有图片，以及获准读取的本人订阅、最近十笔支付、最后连接、HWID、设备型号、操作系统、应用和最后服务器信息。面板实时数据和已保存连接时间来源不同；不能根据记录更新时间推断未知设备或服务器。

该投影包含本人的订阅链接、已有公开教程、Mini App 页面和已配置的客户端下载链接。客户端配置按用户教程的相同规则解析：订阅指定配置、所有者外部分组配置、内置配置或默认值。设备或节点名称读取失败不会隐藏已有链接；最后服务器名称从节点目录查找，不传递网络地址。面板读取限时八秒，在事务外执行，随后重新检查所有者和修订号。内部备注、联系方式、支付标识和其他所有者的数据不在投影中。读取不标记消息为已读，会话在外部处理前关闭。

`support_dal.get_change_cursor(session)` 返回处理器启用时的起始边界；`support_dal.list_changed_tickets(session, after_cursor=..., limit=...)` 按稳定整数游标顺序返回 `SupportTicketChange`，每页 1～500 条。游标通过事务行串行化，较晚提交不会掩盖较早变更。核对返回已变更工单的当前状态，不是每次状态转换的完整日志。`support.message_created` 和 `support.ticket_updated` 在提交后发布，保留 `(event_name, dict)` 签名。

`SupportService.reply_from_connector(ticket_id, body, expected_user_id=..., expected_revision=..., idempotency_key=..., source=..., author_label=..., buttons=..., expected_account_binding=..., replay_only=False)` 使用普通发送者同一把锁，原子检查所有者、修订号、客服可用性、状态和分配的客服人员。新消息、内部备注、状态或分配变更都会使旧修订号失效。同一来源和幂等键重试返回原 `message_id`；同键的不同内容或按钮会被拒绝。可选 `buttons` 使用公开的 `MessageButtonInput` 和通常的消息组合限制；`SupportService.encode_reply_buttons()` 为客服回复提供相同的组合能力。

`facts.account_binding` 包含当前账号绑定的不可逆标识；传入 `expected_account_binding` 后在所有者锁下检查。`replay_only=True` 只返回已有回执，从不创建新消息，便于诊断上下文改变后安全恢复发送。回复使用 `author_role=connector`、`author_user_id=None`，并单独保存来源和署名。客服视角下的客户未读消息保持未读。外部通知仍尽力发送，不保证传输恰好一次。

能力 `ui_composition=3` 在选中工单的回复编辑器前增加受保护插槽 `admin.support.ticket.content`，只允许 `before`/`after`。`context` 包含 `ticketId`、`ticket`、数值 `revision`、`insertReplyDraft(text, buttons?)` 和 `refreshTicket()`。插入操作按编辑器长度限制填充公开回复草稿，不发送消息。工单或修订号已改变、按钮无效时返回 `false`，成功插入时返回 `true`。`replyButtonsSupported: true` 明确声明支持一次插入文本和最多四个普通按钮。仅传文本会保留已选按钮；无效插入同时保留原文本和按钮。较早的 Core 版本不提供这些契约，使用前应检查能力，并单独确认对应发布版本。

## 稳定的安装标识

<a id="стабильная-identity-установки"></a>

需要中立的本地安装标识时，插件调用 `bot.services.installation_identity.get_or_create_installation_identity(session)`。它返回持久化 UUID，不依赖是否启用遥测。插件通过 `ctx.require_session_factory()` 取得会话，并自行负责提交事务。

## 可观测性钩子

<a id="хуки-наблюдаемости"></a>

核心在 `bot.infra.observability` 提供可观测性空实现。插件可在 `setup(ctx)` 中将 `ErrorReporter` 实现放入 `ctx.services["error_reporter"]`，或将 `Metrics` 实现放入 `ctx.services["metrics"]`。`PluginContext.error_reporter` 和 `PluginContext.metrics` 优先返回插件实现，否则使用安全的默认空实现。

Web 和 worker 进程的全局错误处理器使用注册的 `ErrorReporter` 报告处理函数中未捕获的异常。报告器自身失败时只记录错误，不替换原始异常。这些服务键是增量扩展点，现有插件钩子签名不变。

## 额外的群发受众

<a id="дополнительные-аудитории-рассылки"></a>

插件可在 `setup(ctx)` 中向 `ctx.require_audience_segmentation_service()` 注册 `AudienceProvider`。提供者定义稳定的 `target`、本地化名称键与回退名称、异步用户 ID 解析器，以及可选的独立异步数量解析器。`is_available` 回调可动态隐藏受众并禁止解析。未知或不可用的目标绝不回退为全体受众。

## 结账时推荐个人激活码

<a id="персональные-промокоды-в-checkout"></a>

插件可在 `setup(ctx)` 中通过 `bot.infra.promo_policies.register_promo_checkout_suggestion_provider` 注册同步或异步提供者。它接收 `PromoCheckoutSuggestionContext`，包含会话、用户及已知的购买类型、期限、流量，返回单个代码、代码序列或 `None`。

推荐只是提示，不是授权依据。Core 最多规范化、去重 50 个代码，跳过失败的提供者，每次结账仍按常规规则重新校验。Mini App 使用首个建议；Telegram 机器人可比较多个代码，为每个订阅期限显示最佳有效选项。

## 按天期限的兼容性

<a id="совместимость-дневных-периодов"></a>

以下描述上游订单兼容契约，不改变本项目以北京时间日历月计算的独立服务额度周期。新订单使用 `duration_days` 和 `period_semantics: fixed_days`。不能根据访问起止日期推断购买期限，因为其中可能包含多次购买和奖励。公开事件新增可空的 `duration_days` / `purchased_days`；旧月份字段只在可以准确反向转换时保留为别名。365 天的别名是 12；7 天或 360 天没有月份别名。旧事件可能没有新增可空字段，订阅器签名 `(event_name, dict)` 不变。

购买／报价 HTTP 请求应传 `duration_days`。旧输入 `months` 按 `(months // 12) * 365 + (months % 12) * 30` 转换；同时传两个字段时，转换后的值必须一致，否则返回 400。新的 Mini App 发送 `X-Billing-Period-Unit: day`；没有该请求头时，服务器在商品目录隐藏不能准确映射为月份的期限。API 状态包含 `billing_period_unit: day` 与 `billing_period_schema_version: 2`。

旧支付提供者和 Telegram 的内部适配器可能继续使用通用 `months` 槽表示报价键、GB 或设备数量。这类适配器中的按天订单必须在 sale mode 中带 `|d<D>` 标记，并保存明确的按天字段。执行时读取本地订单，不能由支付提供者返回的 metadata 决定期限。结账快照版本为 3，本地自动扣款快照版本为 2；读取器仍接受旧版本，不重新解释其期限。
