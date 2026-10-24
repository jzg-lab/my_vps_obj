<a id="поддержкатикеты"></a>

# 客服与工单

项目提供两种客服渠道：

- 外部链接 `SUPPORT_LINK`，可指向 Telegram 群组、频道、表单或其他公开 URL。
- 内置网页应用／Mini App 工单，需启用 `SUPPORT_TICKETS_ENABLED`。

外部链接可作为备用渠道。内置工单支持在网站发起会话、查看回复历史和未读数量，管理员在同一站点的管理后台回复。客服是通用能力，不依赖旧支付或单订阅流程。

客户连接问题应先确定**具体服务 ID**；管理员沿“客户 → 用户 → 独立服务”或“全部服务”查看权益、交付、计量和资源关系，步骤见[管理员排障手册](../user-guide/admin-workflows.md#4-排查客户无法连接)。不要用账号级普通／premium 流量代替多份服务的独立记录。

<a id="пользовательский-сценарий"></a>

## 用户操作

设置 `SUPPORT_TICKETS_ENABLED=True` 后，网页应用显示“客服”入口。用户可以：

- 填写主题、类别、优先级、正文，并附上一张图片，创建工单。
- 选择类别：账单（`billing`）、技术（`technical`）、账号（`account`）或其他（`other`）。
- 选择普通（`normal`）或高（`high`）优先级。
- 查看自己的工单，筛选处理中或全部工单。
- 在未关闭的工单中发送文字、图片，查看客服回复。
- 通过 `SUPPORT_LINK` 联系外部客服。

报障请提供服务 ID、系统与客户端版本、北京时间、操作步骤及脱敏错误。不要发送密码、完整订阅链接、二维码、API 密钥或原始配置文件。账单类别是保留的通用分类，不表示本项目一期已接支付。

被封禁用户不能创建工单或回复。用户只能看到公开消息，管理员内部备注不向用户展示。

正文使用与群发相同的可视化编辑器，支持粗体、斜体、下划线、删除线、等宽文字、代码块、引用和链接。用户只能设置格式，不能编辑 HTML 源码、插入短代码或按钮。纯文本链接会在编辑器与会话中自动变成可点击链接，旧消息同样适用。字数计数和 `SUPPORT_TICKET_MAX_BODY_LENGTH` 按可见文字计算，不计格式标记。

<a id="админский-сценарий"></a>

## 管理员操作

后台入口为“客服 → 客服”（`/admin/support`），工单详情为 `/admin/support/<ticket_id>`。权限与其他 `/api/admin/*` 相同：需要有效网页会话，且账号当前具有 `owner` 或 `admin` 角色。

管理员可以：

- 查看待处理、等待回复、已关闭和未读工单概况。
- 按状态、优先级、类别和负责人筛选。
- 按主题、用户名、姓名和邮箱搜索。
- 按更新时间、创建时间或重要程度排序。
- 回复用户，修改状态、类别、优先级和负责人。
- 添加仅管理员可见的内部备注。
- 打开用户详情，选择对应独立服务，核对该服务的状态、用量、有效期、交付和执行记录。工单本身不修改服务权益。

管理员回复使用相同编辑器，另外支持：

- 切换 HTML 源码。
- 使用与群发相同的个性化短代码。短代码只在发送时替换一次，工单保存替换后的正文，管理员和用户看到的内容一致。
- “插入”菜单保留上游账号级短代码：`{config_link}`、`{install_link}` 依赖旧账号订阅，不能定位当前多服务中的某一份，不用它们交付独立服务。可使用网站入口 `{miniapp_link}`，并写明服务 ID，让客户在“我的套餐”中自行获取本服务订阅。
- 为消息添加最多四个按钮，使用普通链接或 Mini App 页面引导客户。编辑器保留的机器人／Mini App 激活码类型属于上游兼容能力，不是当前人工开通路径。按钮显示在会话内，也会加入 Telegram 回复通知。内部备注不包含按钮，因为不会发送给用户。
- 通过文件对话框或拖放添加一张图片。内部备注也可附图，但不会向用户公开。

消息保存为 Telegram 支持的 HTML 子集（`b i u s code a pre blockquote`）。其他标签保存时转为纯文本；链接只允许 `http`、`https`、`tg` 和 `mailto` 协议。

工单状态包括 `open`、`awaiting_user`、`awaiting_admin`、`resolved`、`closed`。新工单直接进入 `awaiting_admin`；用户回复使未关闭工单进入 `awaiting_admin`，管理员回复后进入 `awaiting_user`。`resolved` 和 `closed` 都属于关闭状态。

<a id="уведомления"></a>

## 通知

新工单和用户回复可以向管理员及日志群发送 Telegram 通知。客服专用话题由 `LOG_SUPPORT_THREAD_ID` 指定；留空时按日志配置使用通用 `LOG_THREAD_ID` 或日志群。

同一未读工单的重复提醒受冷却时间限制：

- `SUPPORT_ADMIN_NOTIFICATION_COOLDOWN_SECONDS`：Telegram／日志通知间隔。
- `SUPPORT_ADMIN_EMAIL_COOLDOWN_SECONDS`：邮件通知间隔。

管理员和日志群的 Telegram 通知默认开启，由 `SUPPORT_ADMIN_TELEGRAM_NOTIFICATIONS_ENABLED` 控制。邮件默认关闭，设置 `SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED=True` 后开启，发送给具有管理员角色并填写邮箱的账号。邮件需要有效 SMTP 配置，见[登录方式中的邮件公共配置](login-methods.md#общая-настройка-email)。

管理员回复和关闭工单也可通知用户，投递依赖启用的 Telegram 适配器、已绑定身份或可用 SMTP 与邮箱。通知渠道失败不等于工单消息未保存，应回到工单核对。

图片在 Telegram 中单独作为照片发送，在 HTML 邮件中内嵌。正文单独发送，以保留 Telegram 完整文字长度和正文按钮。消息可以只有图片。

<a id="настройки"></a>

## 配置项

| 变量 | 用途 |
| --- | --- |
| `SUPPORT_LINK` | 外部 HTTP(S) 客服链接。Telegram 可填写 `@username`、`t.me/username` 或完整 `https://t.me/username`；简写自动转为完整 HTTPS 链接。显示在机器人和网页应用中。 |
| `SUPPORT_TICKETS_ENABLED` | 显示 Mini App 工单页面并允许创建工单。 |
| `SUPPORT_TICKET_MAX_BODY_LENGTH` | 工单消息最大长度。 |
| `SUPPORT_TICKET_MAX_SUBJECT_LENGTH` | 工单主题最大长度。 |
| `SUPPORT_TICKET_RATE_LIMIT_PER_HOUR` | 每用户每小时最多新建工单数；`0` 表示不限。 |
| `SUPPORT_MESSAGE_RATE_LIMIT_PER_MINUTE` | 每用户每分钟最多发送消息数；`0` 表示不限，默认 `10`。 |
| `SUPPORT_IMAGE_RATE_LIMIT_PER_DAY` | 每用户每天最多发送图片数；`0` 表示不限，默认 `20`。 |
| `LOG_SUPPORT` | 开启客服工单 Telegram／日志通知。 |
| `LOG_SUPPORT_THREAD_ID` | 日志群内客服话题 ID，可选。 |
| `SUPPORT_ADMIN_TELEGRAM_NOTIFICATIONS_ENABLED` | 向管理员发送新工单和用户回复的 Telegram／日志通知，默认 `true`。 |
| `SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED` | 向管理员发送新工单和用户回复的邮件通知。 |
| `SUPPORT_ADMIN_NOTIFICATION_COOLDOWN_SECONDS` | 同一未读工单重复 Telegram／日志通知的最短间隔。 |
| `SUPPORT_ADMIN_EMAIL_COOLDOWN_SECONDS` | 同一未读工单重复邮件通知的最短间隔。 |

完整说明见 [环境变量](../configuration/env-vars.md)。建议通过“系统 → 设置 → 客服”修改；后台值作为覆盖项，优先于 `.env`。

<a id="api-и-хранение"></a>

## API 与存储

用户接口：

- `GET /api/support/tickets`：列出用户工单。
- `POST /api/support/tickets`：创建工单。
- `GET /api/support/tickets/{id}`：打开工单。
- `POST /api/support/tickets/{id}/messages`：发送回复。
- `GET /api/support/images/{image_id}`：获取用户有权访问的公开消息图片。
- `POST /api/support/tickets/{id}/read`：标记消息已读。
- `GET /api/support/unread`：获取客服回复未读数。

管理接口位于 `/api/admin/support/*`，包括列表、详情、回复、状态／优先级／类别／负责人修改、已读标记和统计。

数据保存在 `support_tickets`、`support_ticket_messages` 和 `message_images`。迁移属于部署流程，不是回复工单或接手文档时要执行的操作。

单条消息允许一张 JPEG、PNG 或 WebP 图片，最大 8 MB、1600 万像素。服务器不信任文件名和 MIME 类型：通过 Pillow 完整解码，拒绝动画、损坏或不支持的格式，移除 EXIF 等元数据，将尺寸限制为 2560 px，再生成静态 WebP。文件按 SHA-256 存放于 `data/message-images` 并进行物理去重；每个附件在数据库中仍有独立随机 ID。用户接口检查图片所属工单，并隐藏内部备注附件；响应禁止 MIME 嗅探和公开缓存。

消息字段 `body_format` 为 `text` 或 `html`，`buttons` 保存已经生成的按钮 JSON。旧编辑器出现前的消息保留为 `text`，按字面显示，不会把原有文字追溯解释为 HTML。
