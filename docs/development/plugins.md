# 插件与扩展 API

<a id="api-плагинов-и-расширений"></a>

插件 API 允许独立 Python 包扩展 Remnawave Minishop。本项目保留该公开兼容能力，
契约以 `bot.plugins.spec` 及[插件契约](plugin-contract.md)为准；按 API 范围与 capability 版本检查兼容，
不能以“实验阶段”为由破坏已有钩子、事件签名或传输格式。修改遵循[贡献指南](../../CONTRIBUTING.md)。

> 这是上游扩展参考。本项目已经选择基于 Minishop 二开，插件能力不能替代一个账号管理多份独立服务的完整业务改造；本文中的支付、试用和营销能力不因此进入 MVP。业务边界见[需求基线](../requirements.md)。

## 发现插件

<a id="обнаружение"></a>

外部插件通过 Python entry point group `minishop.plugins` 发现。入口应返回 `bot.plugins.spec.Plugin` 子类或已创建的 `Plugin` 实例。

内置插件随应用提供并始终启用；`PLUGINS_ENABLED` 只控制外部 entry point 发现。`PLUGINS_STRICT=true` 将加载及钩子错误视为致命错误；默认记录错误后继续启动核心。

最小 `pyproject.toml`：

```toml
[project]
name = "minishop-example-plugin"
version = "0.1.0"
dependencies = []

[project.entry-points."minishop.plugins"]
example = "minishop_example_plugin:plugin"
```

插件须安装到 backend 所使用的同一 Python 环境，以访问核心 `bot`、`config` 和 `db` 包。

最小插件：

```python
from bot.plugins.spec import Plugin, PluginContext


class ExamplePlugin(Plugin):
    name = "example"
    version = "0.1.0"
    plugin_api_min_version = 1
    plugin_api_max_version = 1

    def setup(self, ctx: PluginContext) -> None:
        ctx.services["example_service"] = object()


plugin = ExamplePlugin()
```

仓库还提供可运行示例 [`examples/plugins/audit_logger_plugin`](../../examples/plugins/audit_logger_plugin)。在开发环境执行 `pip install -e examples/plugins/audit_logger_plugin` 后，`minishop.plugins` 入口会返回已创建的 `plugin` 对象。

## Plugin 契约

<a id="контракт-plugin"></a>

`PluginContext` 向插件提供当前进程的公共对象：

- `settings`：应用设置。
- `session_factory`：可用时提供 SQLAlchemy 会话工厂。
- `bot`：可用时提供 aiogram bot 实例。
- `i18n`：可用时提供 `JsonI18n` 字典。
- `dispatcher`：可用时提供 aiogram dispatcher。
- `services`：当前进程的可变服务注册表。
- `audience_segmentation_service`：注册额外群发受众的类型化入口；要求必须存在时使用 `require_audience_segmentation_service()`。

全部钩子可选，`Plugin` 基类提供空实现：

- `setup(ctx)`：每个进程最先调用一次，用于通用初始化、订阅领域事件和添加服务。
- `setup_bot(ctx, *, user_root, admin_root)`：注册 aiogram 路由，`admin_root` 已有管理员过滤器保护。
- `setup_web(ctx, app, *, scope)`：注册 aiohttp 路由，`scope` 为 `webhooks` 或 `webapp`。
- `worker_tasks(ctx) -> list[WorkerTaskSpec]`：添加 worker 长期任务。
- `queue_handlers(ctx) -> dict[str, QueueHandler]`：按提供者名称添加 webhook 队列处理器，拒绝核心或其他插件已占用的名称。
- `migrations() -> list[Migration]`：添加数据库迁移链。
- `locales_dir() -> Path | None`：添加本地化 JSON 文件。
- `entitlements_provider() -> EntitlementsProvider | None`：向核心和管理前端提供功能开关。

Web App 外壳只包含初始语言字典。切换语言时请求 `/api/i18n?scope=webapp&lang=<code>`，管理端另请求 `/api/i18n?scope=admin&lang=<code>`；`<code>` 是语言代码占位符。每个响应只含一种语言，同一打开页面复用已加载字典。因此插件的 `locales_dir()` 应为全部支持语言及所需作用域（`wa_`/`admin_`）提供键；本项目还需覆盖简体中文。

## 领域事件

<a id="доменные-события"></a>

插件在 `setup()` 内通过 `bot.infra.events.subscribe` 订阅，处理器接收 `(event_name, payload)`。`emit()` 顺序调用订阅器并记录其错误，不向核心主流程传播异常。

### 用户日志中的插件事件

<a id="события-плагина-в-логах-пользователя"></a>

插件自己的事件使用 `await ctx.emit_event(plugin.name, event_name, payload)`。方法在用户卡片“日志”中以 `plugin:<plugin-name>:<event-name>` 记录，其中两个占位符分别是插件名和事件名，然后向订阅器传递原始 `(event_name, payload)`。普通 `events.emit()` 行为不变，不会自行增加审计。

```python
await ctx.emit_event(
    plugin.name,
    "sample.completed",
    {"user_id": user_id, "result_id": result_id},
    content="Completed",  # Optional safe summary, limited to 1000 characters.
)
```

`user_id` 是现有用户的内部整数 ID，包含导入账号的负数 ID，并非 Telegram ID。应在提交后发布；未保存或已删除用户不会取得审计记录。缺少 `user_id` 或会话工厂时仍投递事件，但不写用户日志。载荷及其秘密值不复制到日志；未指定 `content` 时使用事件名。日志写入失败不阻止订阅器。这是尽力写入的审计，不是持久队列；重复发布会另写一条记录。该方法未修改已有钩子或订阅签名，插件 API 版本仍为 1。

事件载荷是仅含基本类型的扁平字典，如 ID、数字、字符串和 ISO 日期。不能传 ORM 对象；需要详情时插件按 ID 重读数据库。

下列为保留的公开事件及常用字段索引，不是完整 schema；新增可空字段、模型及发送方以
[生成事件目录](../architecture/events.md)为准。事件被定义不表示本项目独立服务模式会触发相应旧业务：

- `payment.succeeded`：`user_id`、`payment_db_id`、`provider`、`amount`、`currency`、`sale_mode`、`months`、`traffic_gb`、`end_date`、`is_auto_renew`。
- `payment.canceled`：`user_id`、`payment_db_id`、`provider`、`provider_payment_id`、`status`。
- `subscription.created` / `subscription.extended`：`user_id`、`subscription_id`、`tariff_key`、`end_date`、`provider`、`months`、`payment_db_id`。
- `trial.activated`：`user_id`、`end_date`、`days`、`traffic_gb`。
- `user.registered`：`user_id`、`language`、`referred_by_id`、`registered_via`。
- `account.email_linked`：`user_id`、`email`。
- `account.telegram_linked`：`user_id`、`telegram_id`。
- `account.merged`：`source_user_id`、`target_user_id`。
- `promo_code.applied`：`user_id`、`code`、`bonus_days`、`new_end_date`。
- `referral.bonus_granted`：`referee_user_id`、`referee_bonus_days`、`referee_new_end_date`、`inviter_bonus_applied`、`payment_db_id`、`reason`。
- `support.ticket_created`：`user_id`、`ticket_id`、`category`、`priority`。
- `panel.webhook_received`：`event`、`panel_user_uuid`、`telegram_id`。

订阅示例：

```python
from bot.infra import events


async def on_payment(event_name: str, payload: dict) -> None:
    user_id = payload.get("user_id")
    # При необходимости загрузите дополнительные данные по id.


class ExamplePlugin(Plugin):
    name = "example"
    version = "0.1.0"
    plugin_api_min_version = 1
    plugin_api_max_version = 1

    def setup(self, ctx: PluginContext) -> None:
        events.subscribe(events.PAYMENT_SUCCEEDED, on_payment)
```

契约测试固定公开签名为 `(event_name, payload)`，其中 `payload` 为普通扁平 `dict`。

## 结账、激活码与权益发放

<a id="checkout-промокоды-и-гранты"></a>

插件可以扩展结账代码使用的三条处理链：

- `bot.infra.pricing.register_price_modifier`：接收 `PriceContext`，返回一组 `PriceAdjustment`；折扣相加后最多为 `100%`。
- `bot.infra.grants.register_grant_modifier`：接收 `GrantContext`，返回包含额外天数或流量倍率的 `GrantAdjustment`。
- `bot.infra.promo_policies.register_promo_redemption_policy`：接收 `PromoRedemptionContext`，返回 `PromoRedemptionDecision.allow()` 或 `deny("reason_key")`。

核心始终先检查代码是否启用、有效期、总使用上限、用户是否重复使用、是否有使用同码的待支付订单，以及最低购买条件。插件策略随后执行，只能额外拒绝，或通过独立价格／权益修改器扩展行为。

## 数据库迁移

<a id="миграции-бд"></a>

插件使用与核心相同的 dataclass `db.migrator.Migration`，通过 `migrations()` 返回独立链。

- 迁移 ID 必须以 `"<plugin name>."` 开头，例如 `example.0001_initial`。
- 全部链共用 `schema_migrations` 表。
- 插件表使用 `ext_<plugin>_` 前缀，例如 `ext_example_events`。
- 迁移必须相对于目标结构幂等。

## 本地化

<a id="локали"></a>

`locales_dir()` 可返回与主语言目录同结构的 JSON 目录，例如 `en.json` 和 `ru.json`。

插件键不覆盖核心基础字典已有的键。后台设置中的运行时覆盖值在基础字典合并后应用。

后台翻译编辑器在“插件”下按插件名展示 `locales_dir()` 的键。只要某个键在任意一种核心语言中已定义，它仍归核心区域。插件可通过 `locale_groups()` 增加嵌套分组：

```python
from bot.plugins import Plugin, PluginLocaleGroup


class ExamplePlugin(Plugin):
    name = "example"

    def locale_groups(self) -> list[PluginLocaleGroup]:
        return [
            PluginLocaleGroup(path=("Billing", "Renewals"), prefixes=("example_renewal_",)),
            PluginLocaleGroup(path=("Billing", "Invoices"), prefixes=("example_invoice_",)),
        ]
```

每个键选择最长匹配前缀的分组；未匹配键进入插件的“其他文案”。`path` 定义显示标题层级，不改变键本身或翻译保存机制，分组名称由插件提供。新键使用插件前缀，例如 `example_title` 或 `admin_example_section_title`。

## 功能开关

<a id="флаги-возможностей"></a>

插件可通过 `entitlements_provider()` 返回 `EntitlementsProvider`，活动提供者实现 `has_feature(name)` 和 `features()`。

多个插件返回提供者会导致启动配置错误，权益权威来源必须唯一。没有插件返回时，核心默认提供空功能集。管理设置 API 返回排序后的 `features: string[]`；管理前端隐藏 descriptor 中所需 `feature` 不在该列表的分区。

## 管理后台分区

<a id="секции-админки"></a>

管理分区支持构建时描述符，以及签名运行时包的 ESM 模块。本节介绍前者，无需重建的包安装见后文。用户页面、教程、订单、持久任务、奖励和备份见[扩展 SDK v1](plugin-extensions.md)。

基础描述符位于 `frontend/src/admin/sections/registry.ts`。扩展构建可在 `frontend/src/admin/sections/extensions/*.ts` 添加默认导出单个描述符或数组的文件：

```ts
import ExampleSection from "./ExampleSection.svelte";
import { Sparkles } from "$components/ui/icons.js";

export default {
  id: "example",
  group: "operations",
  order: 90,
  i18nKey: "nav_example",
  fallbackLabel: "Example",
  titleI18nKey: "section_example_title",
  fallbackTitle: "Example",
  subtitleI18nKey: "section_example_subtitle",
  fallbackSubtitle: "Extension section",
  icon: Sparkles,
  component: ExampleSection,
  requiredFeature: "example.admin",
  visibleWhenLocked: true,
};
```

加载器按模块路径排序，再按 `group`、`order`、`id` 排序描述符，确保构建确定性。分区应始终可见时不设置 `requiredFeature`。

扩展模块可命名导出 `sectionGroups`，提供单个或一组新导航分组；基础分组 ID 由核心保留：

```ts
export const sectionGroups = {
  id: "reports",
  order: 35,
  i18nKey: "nav_reports",
  fallbackLabel: "Reports",
};
```

新描述符使用 `requiredFeature`，不使用旧 `feature`。`visibleWhenLocked: true` 使缺少功能的分区仍出现在导航，由扩展组件显示通用锁定状态。这些字段只控制前端发现，扩展路由／API 仍须执行服务器授权。

同一模块还可命名导出 `userDetailPanels`，添加用户卡片的一个或多个选项卡：

```ts
import ExampleTimeline from "./ExampleTimeline.svelte";

export const userDetailPanels = {
  id: "example-timeline",
  order: 90,
  i18nKey: "user_tab_example_timeline",
  fallbackLabel: "Timeline",
  requiredFeature: "example.timeline",
  component: ExampleTimeline,
};
```

### 组合发出消息

<a id="составление-исходящего-сообщения"></a>

`bot.services.message_composition` 是群发、单用户消息和插件流程共用的通用消息创作契约。插件用普通值组合按钮，无需导入管理员 HTTP 模型：

```python
from bot.services.message_composition import MessageButtonInput, resolve_message_buttons

buttons = resolve_message_buttons(
    [MessageButtonInput(kind="promo_webapp", label="Применить код", promo_code=code)],
    mini_app_url=settings.SUBSCRIPTION_MINI_APP_URL,
    bot_username=bot_username,
)
await outbound_messaging.send_text(session, user_id=uid, text=text, buttons=buttons)
```

按钮类型包括 `url`、`promo_bot`（机器人 `/start promo_<CODE>`）、`promo_webapp`（打开预填代码的 Mini App）。`promo_webapp` 自动选择 Telegram 的 `web_app` 按钮，让目标在有认证的 Mini App **内部**打开；Mini App 仅配置普通 `http` 地址时回退到 `t.me?startapp=`。创作错误通过带稳定 `code` 的 `MessageValidationError` 返回。`normalize_message_channels` 校验 `telegram`、`email` 渠道集合；`email_links_for_buttons` 为邮件提供 `(label, url)`。

命名导出 `sectionTabs` 为**已有**后台分区（自身或 `promos`、`users`、`payments` 等核心分区）添加选项卡，无需修改原分区源码。核心只知道分区可承载选项卡，不依赖其具体内容：

```ts
import ExampleCodes from "./ExampleCodes.svelte";

export const sectionTabs = {
  id: "example-codes",
  sectionId: "promos",
  order: 10,
  i18nKey: "section_tab_example_codes",
  fallbackLabel: "Issued codes",
  requiredFeature: "example.codes",
  component: ExampleCodes,
};
```

首个选项卡始终是分区自身，名称使用 `titleI18nKey`。没有扩展为分区注册选项卡时，不渲染选项卡栏，原页面保持不变。选项卡组件接收分区组件相同的 `AdminSectionComponentProps`：`at`、`featureAvailable`、`featuresResolved`、`availableFeatures`、`routePrefix`、`onNavigateSection`、`onOpenUserCard`；不传具体分区内部 props，因此不依赖内部实现。

用户卡片选项卡接收 `at`、`user`、`userDetail`、`featureAvailable`、`active` 和 `routePrefix`。完整分区扩展除后台公共 props 外，还接收 `featureAvailable`、已排序的 `availableFeatures` 和 `onNavigateSection(sectionId)`。前者反映分区自己的 `requiredFeature`，数组用于检查内部额外功能。组件也可使用 `$lib/admin/context` 类型化 stores。`requiredFeature`、`visibleWhenLocked` 的发现语义与普通分区一致；服务器路由始终是权限及功能可用性检查边界。

## 发布镜像

<a id="релизные-образы"></a>

以下为上游发布流程，本项目不会自动执行。GitLab CI 只对 `vX.Y.Z` 格式的稳定 Git 标签发布 Docker Hub 镜像。上游发布前同步 `main`，在其当前提交上创建标签：

```bash
git fetch gitlab main --tags
git tag vX.Y.Z gitlab/main
git push gitlab refs/tags/vX.Y.Z
```

推送 `refs/tags/vX.Y.Z` 触发发布任务；标签未精确指向当前 `main` 时拒绝。任务构建 backend、worker、frontend，将不含前导 `v` 的语义版本标签（例如 `v3.6.1` 对应 `3.6.1`）和用于发现的 `latest` 发布到 Docker Hub。

扩展及生产构建必须固定精确 Docker Hub digest。`latest` 仅供发现，不是可复现构建输入。

## 无需重建 Core 的签名包安装

<a id="установка-подписанного-пакета-без-пересборки-core"></a>

在标准 Compose 主机，管理员进入“插件”，预览 ZIP 或包含现成 ZIP 的公开仓库，对照发行者官方发布核对 SHA-256，确认安装后启用。首次确认自动固定发行者密钥；预览不执行代码。安装、启用、关闭和删除由标准 launcher 将 backend/worker 切换至新代次，未更新标准镜像时不支持此路径。关闭的包可以保留数据并删除；内置于镜像的包可关闭，但删除须更换镜像。

ZIP 包含 `plugin.json`、`signatures/ed25519.sig`、`backend/` 文件，以及有界面时的 `frontend/`。首次安装在 `plugin.json` 添加 `publisher_public_key`，值为 32 字节 Ed25519 公钥的 base64。`files` 列出每个载荷文件的 SHA-256。签名覆盖规范 JSON 清单：UTF-8、键排序、使用 `,` 和 `:` 分隔且无空格。`publisher_fingerprint` 是 32 字节公钥的 SHA-256。

清单包含 `schema_version: 1`、`id`、`version`、`publisher`、`plugin_api: 1`、`frontend_host_api: 1`、`core_revision`、`runtime`（`python`、`system`、`machine`）、`backend.entry_point` 和 `files`。默认 `core_revision` 必须匹配当前 Core。

纯 Python 源码包可使用 `"core_compatibility":{"mode":"capabilities","requires":{"capability_name":1}}`。此时 `core_revision` 记录已测试构建，安装器改为检查所需公开能力版本。`capability_name` 只是示例，应使用 `bot.plugins.capabilities` 发布的名称和版本。二进制 backend 包不能使用此模式；Python／系统／CPU 配置仍须匹配。核心不兼容地修改某项公开能力时会提高其版本，旧版本包将被拒绝。

兼容当前及未来 Core 的源码包也可使用 `"core_compatibility":{"mode":"minimum_version","version":"3.4.4"}`。安装器从 `.build-tag` 或最新 Git 标签比较数值 `X.Y.Z`；无法确定构建版本则停止安装。`core_revision` 仍保存已测试构建 SHA，但不用于判断提交顺序，因为缺少 Git 历史的单个 SHA 无法提供该信息。最低版本模式只支持 `.py` 源码 backend。

发行者未在 ZIP 内附公钥时，已信任的旧包可继续工作，但首次安装需要新归档。签名和密钥本身不证明作者身份，仍须与官方发布核对归档 SHA-256。

公开 GitHub/GitLab 仓库根目录可包含 `minishop-plugin.json`：

```json
{
  "schema_version": 1,
  "artifact": "dist/example-plugin.zip",
  "sha256": "<64 lowercase hex characters>",
  "version": "1.2.3"
}
```

管理器将分支／标签解析为精确提交，只下载已构建 ZIP 并校验摘要、签名，不运行仓库中的 `pip`、`npm`、编译器或构建脚本。拒绝没有内附或既有固定密钥的包、`.pth`、嵌套 wheels、ZIP 外路径，以及占用 Core 内部 Python 命名空间的包。代码以应用权限执行；签名确认来源，不提供沙箱。

包前端是独立 ESM 模块，导出 `mountView(view, target, props)` 和 `unmountView(instance)`。描述符可增加分区、选项卡和用户面板。模块使用普通 host API props，不把核心内部 Svelte 组件当契约。资源 URL 绑定包 digest，并要求管理员会话。

已有页面内的卡片和子页面使用 [UI 组合 v1](plugin-ui-composition.md)，支持用户子页面、具名用户／管理插槽、明确替换及安全回退到核心内容。

### 插件卡片与设置

<a id="карточка-и-настройки-плагина"></a>

管理器按 `id` 展示一张卡片；同一包同时安装并注册为镜像 entry point 时合并显示。点击版本标记可看来源。可选 `name`、`description` 来自签名 `plugin.json`。预览图用 `frontend.preview` 指向 `frontend/` 内相对路径，并将文件加入签名 `files`。只有打开插件页面才加载图片，没有图片时使用通用占位。建议 WebP、16:10、不超过 100 KB。

插件可声明 `frontend.settings_tabs` 数组，元素包含 `id`、`view`、`label` 及可选 `i18nKey`、`order`。`view` 传给同一个 `mountView`，多个选项卡在选中时逐个加载。本地化键须同时存在于插件字典和前端构建。

管理员通过“插件 → 卡片 → 设置”打开界面，所有操作须在服务端核验权限。没有设置时 Core 显示空状态。旧独立分区可在 `frontend.sections` 对象中使用 `"hideInNavigation": true`，保留直接路由而从侧栏隐藏。

“更新”区分来源。镜像包通过新镜像更新，不能以 ZIP 覆盖运行中容器。公开 GitHub/GitLab 仓库安装的包，每十分钟只后台读取安装时固定分支的 `minishop-plugin.json`。索引可选 `version` 为严格更新的稳定语义版本且归档 SHA-256 改变时，显示红点。索引没有版本时仍可手动检查，但不显示红点；网络错误不阻塞页面。安装仍须完整预览并验证摘要、签名、发行者及兼容性。无仓库的 ZIP 支持手工上传新版。

没有明确安全访问契约时管理器不查询私有仓库，也不会仅凭版本号提示镜像更新。镜像提供者需提供有授权和版本信息的更新渠道，否则不显示可能误导的提示。稳定更新应选择发布分支，而非开发分支。

选择的分支、标签或明确提交与已校验包 SHA 分开保存：安装下载预览的提交，后续检查使用所选 ref；ref 为空则每次读取当前默认分支。旧安装只自动保存 SHA 时无法恢复原 ref，表单保持空值并使用默认分支。若要维持原渠道或固定旧版本，更新时应明确填写分支、标签或 SHA。

插件在外部副作用前必须核验代次，并保证后台任务幂等。新代码或迁移启动失败时 Core 进入安全模式，保留数据及限制记录，不加载外部插件。已经应用不兼容迁移后的回退须检查结构并按独立操作手册恢复，不能只替换文件。
