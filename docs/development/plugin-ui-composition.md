# 插件页面与卡片：UI 组合 v1

<a id="разделы-и-карточки-плагинов-ui-composition-v1"></a>

在能力模式下，将 `"ui_composition": 1` 加入 `core_compatibility.requires`；用户中心还需要 `"user_ui": 1`。Plugin API、前端 host API 和 schema version 仍为 1，新增字段向后兼容。原有页面、插槽、分区和面板继续工作。

> 本文描述上游扩展界面。旧账号订阅、余额和营销目标的存在不表示本项目 MVP 开放这些流程；当前独立服务界面及可用入口以[产品设计](../product-design.md)和实际运行状态为准。

## 用户中心：已有页面内的卡片与子页面

<a id="лк-карточка-и-подраздел-в-существующем-разделе"></a>

`frontend.user.pages` 添加页面，`frontend.user.slots` 嵌入视图。例如，工具卡片位于“奖励”页面，其完整视图也从该页面打开，不额外占用底部导航位置：

```json
{
  "frontend": {
    "user": {
      "entry": "customer/index.js",
      "pages": [
        {"id": "tool", "view": "tool", "label": "Дополнительный инструмент", "parent": "invite", "navigation": "section", "order": 20},
        {"id": "resources", "view": "resources", "label": "Материалы", "parent": "support", "navigation": "section", "order": 10}
      ],
      "slots": [
        {"id": "tool-card", "view": "tool-card", "label": "Дополнительный инструмент", "target": "user.invite.codes", "placement": "after", "order": 20},
        {"id": "help-card", "view": "help-card", "label": "Материалы", "target": "user.support.cards", "order": 10}
      ]
    }
  }
}
```

所有 entry/styles/assets 仍须列在签名的 `files` 中。插件实现卡片和子页面内容，Core 提供布局位置和导航。`id` 与 `view` 不同：路由使用 `id`，`mountView` 接收 `view`。

- `navigation: "primary"`：在公共导航增加独立项目，也是原来的默认值。
- `navigation: "section"` 加必填 `parent`：在父页面内放置按钮；完整视图中仍选中父页面，并提供返回入口。
- `navigation: "hidden"`：仅通过直接链接或卡片进入；可选 `parent` 保留返回父页面的行为。
- 直接链接为 `/extensions/<owner>/<page-id>`，保留安装路径前缀。名称和图标由插件提供，不覆盖 Core 路由。
- `host.navigate("tool")` 打开插件自己的页面；`host.navigateSection("support")` 返回 Core 页面。该方法不允许 `admin` 或任意 URL。
- 只要插件在“奖励”或“客服”中提供内容，即使内置推荐计划或工单关闭，对应页面仍保留在导航中。

## 消息按钮中的页面与消息数据

<a id="экраны-в-кнопках-и-данные-в-сообщениях"></a>

包可在 `core_compatibility.requires` 中声明 `"message_composition": 1`。活跃包的 `frontend.user.pages` 页面会出现在全部消息／菜单按钮编辑器的页面选择器中。`GET /api/admin/message/targets` 返回本地化名称和所有者；在视图设置中关闭的页面不会出现。管理分区和插槽不会成为客户按钮的目标。具体接收者能否访问仍由页面策略决定。

保存的目标为 `/extensions/<owner>/<page-id>`。Telegram Mini App 使用 `startapp=ext_<owner>__<page-id>`，从右侧解析分隔符，因为 `page-id` 不包含下划线。删除或关闭插件不会把目标替换成其他页面：编辑器将它保留为不可用目标，发送时拒绝。

通过 `ExtensionContributions.message_shortcodes` 声明消息数据：

```python
from bot.plugins.extensions import (
    ExtensionContributions,
    MessageShortcode,
    MessageShortcodeContext,
)


async def remaining(context: MessageShortcodeContext) -> dict[int, str | None]:
    # Query the plugin's own data once for this recipient batch.
    return {user_id: "10" for user_id in context.user_ids}


def extensions(self, ctx):
    return ExtensionContributions(
        message_shortcodes=(
            MessageShortcode("remaining", "sample_remaining_description", remaining),
        )
    )
```

所有者为 `sample` 时，占位符是 `{sample.remaining}`。插件通过 `description_key` 本地化名称；`cost` 可为 `db` 或 `panel`。Core 只加载实际使用的占位符和存在的接收者，每批调用一次处理器，检查返回值属于对应接收者，并转义 HTML。文本值最长 8192 个字符。处理器不能提交或结束会话事务；失败时回滚至保存点，缺失值显示为 `—`。`db` 超时为 5 秒，`panel` 为 15 秒。未知占位符原样保留。群发、私信及其他公共消息组合功能共用注册表和替换逻辑。

## 用户中心的稳定目标

<a id="стабильные-цели-лк"></a>

各页面 `home`、`invite`、`support`、`settings`、`install`、`devices`、`partner`、`notifications`、`security`、`status`、`trial` 可使用以下目标：

| 目标 | 用途 |
| --- | --- |
| `user.<section>.content` | 整个页面内容周围，允许替换 |
| `user.<section>.cards` | 页面内容之后的附加卡片 |
| `user.invite.gifts`, `.codes`, `.referrals` | “奖励”中的独立内置区块 |
| `user.home.summary` | 紧凑模式的汇总卡片 |
| `user.home.balance`, `.subscription`, `.traffic` | 普通首页模式的卡片 |
| `user.home.status` | 服务器状态卡片 |
| `user.settings.profile`, `.codes` | 设置中的个人资料与代码激活 |

旧 `user.home.cards`、`user.profile.actions`、`user.subscription.actions`、`user.install.blocks` 保留原来在对应页面之后追加内容的行为。卡片目标仅在内置容器实际渲染时存在；例如 `user.home.traffic` 属于有效订阅的普通模式。如果扩展内容应独立于模式或订阅显示，使用 `.cards` 或 `.content`。安装时会拒绝未知用户中心目标。

## 后台：卡片、选项卡与内容替换

<a id="админка-карточки-вкладки-и-замена-содержимого"></a>

管理端描述符位于 `frontend` 中，与 `entry` 同级。已有页面支持扩展选项卡；仅提供选项卡的包不需要独立分区：

```json
{
  "frontend": {
    "entry": "admin/index.js",
    "section_tabs": [
      {"id": "resources", "view": "resources-editor", "sectionId": "support", "label": "Материалы", "order": 10}
    ],
    "slots": [
      {"id": "help-summary", "view": "help-summary", "label": "Материалы", "target": "admin.support.content", "placement": "before", "order": 0},
      {"id": "tariff-card", "view": "tariff-editor", "label": "Тариф", "target": "admin.users.detail.tariff", "placement": "replace"}
    ]
  }
}
```

`admin.<section-id>.content` 对全部分区可用，包括插件注册的分区。未知分区不会渲染扩展，也不会将其 slug 重定向到其他页面。内部选项卡（设置、工单筛选等）仍由所属分区管理，`section_tabs` 扩展的是外层选项卡。

直接链接为 `/admin/support?extensionTab=<owner>:resources`。切换时保留其他参数和 hash，支持浏览器前进／后退与键盘操作。删除或屏蔽插件后，不可用选项卡会返回基础页面。

用户卡片的“操作”选项卡提供 `admin.users.detail.tariff`、`.balance`、`.traffic-strategy`、`.premium-traffic`、`.regular-traffic`、`.hwid`、`.traffic-grant`、`.squads`。`admin.users.detail.actions` 在基础操作之后增加独立卡片。条件卡片只在对应数据／订阅存在时显示。

随构建提供的扩展，应从 `admin/sections/extensions/*.ts` 导出类型为 `AdminUiSlotDescriptor[]` 的 `uiSlots`，使用相同的 `target`、`placement`、`order`、功能字段和 Svelte 组件。新增内置边界通过公共 `AdminExtensionPoint` / `UserExtensionPoint` 添加。DOM 选择器和内部类名不是插件 API。

## 顺序、冲突、故障与权限

<a id="порядок-конфликты-отказ-и-права"></a>

- `placement` 支持 `before`、`after`（默认）和 `replace`。组内先按 −10000～10000 的整数 `order`，再按 `<owner>:<id>` 排序，零值保留。`before`/`after` 在 Core 内容周围追加视图，`replace` 替换指定边界内容。修改文案使用本地化；修改卡片使用明确替换。插件自行负责视图操作和数据保存。
- 同一目标存在两个活跃替换时，不按随机包顺序选择；Core 显示冲突信息和原始区块，追加内容保留。
- 替换内容加载期间原始区块仍可用。包视图导入、挂载或更新失败时恢复 Core 内容，一个视图故障不影响相邻视图。内置 Svelte 视图的同步错误由错误边界处理；自有组件的异步操作须自行处理错误。
- `.cards`、旧追加目标、`user.security.content`、`admin.plugins.content` 和 `admin.users.detail.actions` 不允许 `replace`，以保留卡片追加、账号恢复及故障包管理入口。
- 运行时选项卡、面板和插槽标识加入所有者命名空间，因此两个包可以使用同一个本地 `resources`。现有 section ids 和 aliases 不覆盖 Core；重新注册时删除旧运行时描述符、别名和样式。只有描述符的包可以不提供 `sections`。
- 用户中心可见性通过 `view_policy` 和已保存的 `view:<id>` 偏好决定，策略出错时隐藏视图。管理端功能字段与普通选项卡一致；被锁定的替换不会隐藏 Core。隐藏界面不等于禁止服务端操作，每个端点都必须检查用户、数据所有者、管理员权限和当前代次。
- 用户端 `props.context` 包含 screen、subscription、ticketId，以及视图元数据 `target`、`viewId`、`parent`。管理插槽取得 `context.sectionId`、`context.target`，操作卡片取得 `context.user` 与 `context.userDetail` 快照。它们只是输入快照，不是 ORM、store 或修改套餐的命令。
- 用户端和管理端 bundles/assets 保持分离，要求对应会话。受信任 JavaScript 不等于沙箱。CSS 应限制在自身容器内，并在 `unmountView` 清理定时器、监听器和门户节点。
