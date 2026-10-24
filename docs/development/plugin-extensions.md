# 扩展 SDK v1

<a id="sdk-расширений-v1"></a>

Core 为用户中心、教程、外部服务、奖励和备份提供通用扩展点。具体游戏、票券、外部 VPN 服务和云存储由独立扩展实现。用户看到的是带有扩展名称和样式的普通产品页面，只有管理员能访问插件目录。

> 本文是上游扩展参考，不代表本项目 MVP 已启用支付、奖励或账号级订阅。本项目采用人工开通和独立服务，业务边界以[需求基线](../requirements.md)为准。

## 注册与兼容性

<a id="регистрация-и-совместимость"></a>

`Plugin.extensions(ctx)` 返回 `bot.plugins.extensions` 中的 `ExtensionContributions`。字段包括 `guides`、`resources`、`products`、`jobs`、`events`、`backups`、`storage`、`view_policy`、`permissions`，默认均为空。同一所有者的注册是原子的，标识冲突会阻止启动。所有者为 `Plugin.name`，本地标识符合 `[a-z][a-z0-9_-]{0,63}`，组合键为 `owner:id`；`core` 是保留名称。

该钩子只声明契约，不产生副作用。离线恢复也会调用它，此时 `PluginContext` 只有 `settings`；运行时依赖应在回调内部从回调上下文取得。恢复时不运行通常的 `setup`。插件 API 版本仍为 1，新增方法均有空默认值。

包在 `core_compatibility.mode = "capabilities"` 下通过 `requires` 请求所需契约：`user_ui`、`install_guides`、`external_orders`、`durable_jobs`、`rewards`、`backups` 均为版本 1；`support_connector: 1` 保留。未知或版本不匹配的能力会在安装前被拒绝。包更新仍使用签名 ZIP、不可变摘要，以及 backend/worker 代次切换。

扩展是在 Core 进程内运行的受信任代码，不是沙箱。签名确认来源，管理员仍需判断是否信任发行者。声明的 permissions 用于检查 SDK 使用是否合法，不隔离 Python 或 JavaScript。不要直接修改全局 Core 注册表或内部数据表。

## 用户界面

<a id="пользовательский-интерфейс"></a>

用户中心和后台已有页面中的卡片、子页面、区块替换、排序及故障处理见 [UI 组合 v1](plugin-ui-composition.md)。

签名清单具有独立的 `frontend.user`：

```json
{
  "entry": "customer/index.js",
  "styles": ["customer/style.css"],
  "assets": [],
  "pages": [{
    "id": "services", "view": "services", "label": "Мои устройства",
    "i18nKey": "devices_title", "icon": "device", "order": 100,
    "navigation": "primary"
  }],
  "slots": [{
    "id": "summary", "view": "summary", "label": "Мои устройства",
    "target": "user.home.cards", "order": 100
  }]
}
```

所有文件必须列在签名的 `files` 中。用户只能取得明确列出的 entry/styles/assets，不能取得管理模块文件。包可以只有 `frontend.user`，不提供管理端 `frontend.entry`。页面和视图标识符合 `[a-z][a-z0-9-]{1,63}`。图标支持 `star`、`gift`、`device`、`home`、`support`、`settings`、`shield`。`navigation: "hidden"` 隐藏菜单项但保留直接链接。`view_policy(UserContext, view_id)` 在服务器决定可见性；发生错误时关闭对应视图。可见性检查不能代替插件 HTTP 操作的授权检查。

页面路由为 `/extensions/<owner>/<id>`，保留用户中心的路由前缀。Core 不强制添加“插件”标题、卡片或页面样式。插件在 host 内渲染内容，外壳保留导航、返回和直接链接；手机上的长导航支持滚动。插槽包括 `user.home.cards`、`user.subscription.actions`（订阅／首页）、`user.profile.actions`（设置）、`user.install.blocks`（教程）。

ESM 导出为 `mountView(view, element, props) -> instance`、`unmountView(instance)`，以及可选 `updateView(instance, props)`；没有 `updateView` 时，上下文变化会重新挂载。`props = {host, language, context}`，其中 context 包含 screen 和订阅快照。使用 `host.version === 1` 的 SDK：`t`、`request`、`navigate`、`back`、`notify`、`confirm`、`createOrder`、`paymentMethods`、`checkout`、`orders`、`order`、`resource`。`request("/path")` 只携当前会话请求 `/api/plugins/<owner>/path`。插件通过 `setup_web` 注册自己的路由，并为每个操作检查用户、数据归属和权限。HTTP 响应采用 `{ok: true, ...}`。

使用 Core CSS 变量（`--bg`、`--text`、`--muted`、`--accent`、`--border`、`--radius`），并将选择器限制在自身容器内。卸载时 host 删除样式引用，模块自行清理定时器、监听器和门户节点。组件出错时显示通用错误，不阻塞其他页面。连接密钥及秘密值不得写入清单、JavaScript 或公开 context。

## 教程与资源

<a id="инструкции-и-ресурсы"></a>

`GuideProvider(id, resolve)` 接收 `UserContext(session, user_id, language)`，返回 `GuideContribution(config, order)` 或 `None`。`config` 是现行 v1 教程格式的完整文档，可包含任意平台。Core 校验后，为平台和 SVG 标识添加 `owner--provider--` 前缀，再与选定的 Panel/config 来源合并，不替换基础教程。最终平台标识最长 64 个字符，冲突片段会被跳过。管理员可在插件操作页面隐藏提供者或调整顺序。个人片段不进入公开分享教程。本项目独立服务的教程来源见[客户端体验](chinese-localization.md#客户端教程)，凭据核验见[服务交付](service-delivery.md)；不能用上游账号教程替代服务级凭据校验。

`ResourceProvider(id, resolve)` 接收用户和不透明资源键。回调必须检查资源键属于该用户，并返回 `ResourceResult(body, content_type, filename)`。`/api/extensions/resource?provider=owner:id&key=...` 只允许已登录且未被封禁的用户访问；结果以附件返回，标记 `no-store`，最大 2 MiB，不执行 HTML/SVG。模块下载优先使用返回 Blob 的 `host.resource(provider, key)`。教程可链接此路由，但不透明资源键本身不得包含私钥。

## 订单与支付

<a id="заказы-и-оплата"></a>

`ProductProvider(id, quote, fulfill, revoke, status=None, terms_versions=(1,))`：

- `quote(UserContext, options)` 返回 `ProductQuote`：title、amount_minor、currency、terms、version、expires_at。金额为货币最小单位的整数，报价有效期在当前时间至 24 小时内。报价不修改数据。条款原样保存并向购买者展示，不得包含秘密值。
- `fulfill(OperationContext, OrderSnapshot)` 创建／延长服务，返回 `FulfillmentResult(reference, data)`。data 是公开数据，配置密钥应通过资源提供者交付。续期作为独立订单，terms 携带原 reference，并在报价时由服务器检查。
- `revoke(OperationContext, OrderSnapshot)` 确认撤销服务。即使网络故障后尚未保存 reference，也必须能按 order.id 找到操作。
- `status(UserContext, OrderSnapshot)` 返回公开的当前状态；对已交付订单通过 `host.order(id, true)` 调用。

`extensions.commerce.create_order` 使用调用者的事务。`host.createOrder(local_product, options, idempotencyKey)` 使用 Core HTTP API。相同键和参数返回原订单及原价格，修改参数则返回冲突。结账以快照为准，不信任浏览器金额。Core 接受内部余额及兼容的一次性支付适配器，不自动接入周期扣款适配器。`host.paymentMethods(orderId)` 返回适合当前价格／货币的方式，并检查最低金额与余额设置。RUB 订单不能通过隐式兑换使用 Stars 支付。由外部目录决定价格的适配器被排除。一个订单只关联一个账单；账单取消或未创建时，应使用新键创建新订单。Core 不替换旧账单，防止迟到支付重复交付服务。

支付状态：pending → paid → refunding → refunded。交付状态：pending → fulfilling → fulfilled；退款后进入 revoking → revoked。报价过期或插件关闭后仍接受已确认支付，交付任务持久保存，等待兼容处理器重新启用。仍有未关闭订单时，更新后的提供者必须保留旧 `terms_versions`。

`extensions.commerce.request_refund` 是特权命令，不是公开用户 API。管理员通过“操作”选项卡先撤销服务，再向内部余额退款一次；这不是支付渠道原路退款。后台仅支持内部余额所用货币，其他货币需通过 SDK 配合支付提供者的独立退款流程。`to_balance=False` 用于单独确认过的外部退款，不会向支付提供者发起付款。不能换一种退款方式重试同一退款。交付进行中会暂时阻止退款。外部调用结果未知时须按 order.id 核对；外部服务须支持幂等撤销及阻止迟到创建。本地租约不能撤回已发送请求。

## 任务、事件与奖励

<a id="задания-события-и-награды"></a>

稳定导入路径为 `bot.plugins.extensions.jobs.{enqueue,publish}` 和 `bot.plugins.extensions.rewards.{Reward,grant}`，这些方法不提交事务。票券扣除、游戏结果、奖品预留及 grant/enqueue 应在同一次提交完成。结果由插件服务器选择，异常时回滚整个业务事务。Core 不定义游戏规则或奖品库存。

`JobHandler(id, run, timeout_seconds=60, max_attempts=10, interval_seconds=None)` 处理 `(OperationContext, payload) -> dict`。周期任务使用 UTC 时间槽，最小间隔 60 秒，不补跑错过的时间槽。任务存储在 PostgreSQL，处理器在长事务之外运行，使用租约、重试和结果写入保护防止过期执行者覆盖结果。任务至少交付一次，外部调用必须使用 operation_id 作为幂等键。JSON payload/result 最大 256 KiB。处理器错误保存为稳定错误码，不保存可能含秘密值的异常文本。

`DurableSubscription(event, job)` 将 job 订阅到事件。`publish` 在变更事务内为每个活跃订阅者保存交付记录。Core 在成功支付提交时发布 `payment.succeeded`，包含 payment_db_id、user_id、amount、currency、provider、sale_mode，同一事务固定接收者。相同 event/event_id 重试不创建新交付，不同 payload 则冲突。事件表示支付完成，不表示外部服务交付成功。按插件奖励规则过滤 sale_mode 和资金来源。

所有者关闭时阻止任务执行，不丢失数据或消耗尝试次数。尝试次数耗尽后管理员可查看并用原 operation_id 重试。旧代次执行者不能执行新操作。账号删除会清理其本地扩展任务／订单；账号合并将它们转移到目标账号，键冲突时保留两次购买。进行中的操作暂时阻止合并／删除。身份以最新 `OperationContext.user_id` 为准，旧 payload 内的标识只是事件快照。删除账号前撤销外部资源仍是集成方的责任。这些扩展记录不替代本项目须保留的独立服务和开通历史。

`grant(..., owner, user_id, idempotency_key, reward=Reward(...))` 必须显式声明 `rewards.balance`、`rewards.days`、`rewards.traffic` 或 `rewards.codes` 权限。数量分别使用货币最小单位、整数天、字节或个人代码天数。余额／代码在事务内发放；天数／流量修改本地权益并排队按绝对状态重试面板同步，要求存在有效订阅。个人代码是固定天数的一次性代码。天数不延长单独购买的设备包；外部自定义奖品使用自身任务实现。同一键重试不会重复 grant。

## 备份

<a id="бэкапы"></a>

`BackupContributor(id, version, collect, validate, restore)` 在独立目录 `extensions/<owner>/<id>` 中工作。collect 写文件并返回 JSON metadata；validate 只检查、不修改；restore 幂等恢复。不允许链接、目录逃逸或危险名称。插件表已包含在完整 PostgreSQL dump 中。清单记录全部活跃插件版本和每个契约版本。恢复要求版本及全部 contributors 匹配，并在 pg_restore 前检查；不含 extensions 的旧备份保持旧行为。

稳定模块 `bot.plugins.extensions.backups` 提供 `create_backup(ctx)`、`list_archives(storage)`、`download_archive(ctx, storage=..., name=...)`、`delete_archive(storage, name)`。下载导入并校验 Core 备份，返回本地名称，不启动恢复。外部存储名称不直接作为本地路径；额外调度使用普通 JobHandler。

`BackupStorageProvider(id, upload, download, list_archives, delete)` 负责传输已完成的备份。Core 在成功发送前保留单独副本，避免保留策略删掉尚未交付的备份。同名 upload 重试必须幂等，失败操作在后台可见。提交与删除副本之间崩溃可能在 `.extension-uploads` 留下文件；确认对应操作 succeeded 后可删除。加密和密钥由存储提供者负责，download 返回已解密的普通 Core 备份。

离线恢复先在候选数据库验证 contributors，再在数据库切换后执行文件回调。回调失败会留下 `recovery_required` 日志状态；幂等文件恢复完成前不要启动服务。PostgreSQL、本地文件和外部 API 之间没有统一的原子事务。解密密钥的唯一副本不得放在它所加密的备份内部。

## 集成检查

<a id="проверки-интеграции"></a>

交付插件前，检查请求／webhook 重试、外部调用后提交前断连、待支付时关闭插件、旧报价版本、无 reference 退款、他人资源键、账号合并、直接链接、加载中卸载、恢复时插件缺失或 validate 失败。检查桌面、Telegram／手机、俄文和英文，以及未安装用户模块的基础用户中心；本项目开放流程还需检查简体中文。Core 提供契约和日志，但外部幂等性的正确性须针对具体服务验证。
