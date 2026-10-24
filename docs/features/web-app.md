<a id="веб-приложение--mini-app"></a>

# 网页应用与 Mini App

网站是客户查看多份独立服务的入口，也是管理员进入统一管理台的入口。普通浏览器可以独立使用，Telegram Mini App 是可选入口；两者使用同一账号与服务记录。

一期由管理员人工开通，不接在线支付，不提供自有客户端。各份服务有自己的订阅、流量和有效期，不使用上游单一“当前套餐”模型。产品范围见[需求基线](../requirements.md)，具体环境的完成状态与证据只查[实施计划 §14：本轮本地最终验收](../implementation-plan.md#本轮本地最终验收)。

<a id="что-показывает-веб-приложение"></a>

## 网页应用显示什么

| 入口 | 客户操作 |
| --- | --- |
| 首页 `/home` | 查看简洁品牌概览与已开通套餐数量，通过“查看我的套餐”进入服务页。 |
| 我的套餐 `/services` | 在“我的服务”页签查看每份已开通服务，在“套餐目录”了解管理员提供的套餐。 |
| 服务详情 | 按服务 ID 核对已用／额度、剩余流量、到期时间、用量更新时间；月度套餐另看周期提示。详情在服务页内打开，不是单独的客户详情路由。 |
| 导入订阅 | 在可交付服务内获取自己的链接，再展开“安装与配置”；不能借用其他服务的订阅。 |
| 设置 → 安全 | 管理登录方式、已验证邮箱、密码、通行密钥及通知邮箱。 |
| 设置 → 通知 | 按站点是否启用偏好设置，选择邮件／Telegram 的营销与系统通知。 |
| 客服、服务器状态 | 由相应配置控制；客服用于沟通，状态页不替代单份服务诊断。 |

“套餐目录”展示价格并不表示已接支付，也不是申请或自动开通按钮。同名套餐可有多份服务；每次连接前确认所选配置对应的服务 ID。一份受限不自动转扣另一份额度。

客户使用步骤见[中文客户端教程](../user-guide/clients-zh.md)。管理员通过“管理后台”进入 `/admin/console-overview`，沿客户与节点两条主线处理日常事务；入口表见[统一管理后台](admin-panel.md)，实际任务见[管理员操作手册](../user-guide/admin-workflows.md)。后台资格来自账号当前角色，不来自 Telegram 或登录渠道。

### 如何理解服务状态

- “等待连接配置”或“等待核验”：先由管理员完成交付，登记成功不等于可连接。
- “已暂停”“已到期”“额度已耗尽”“账号已封禁”：刷新订阅不会续期、加额度或解除限制。
- “用量尚未确认”或等待月度确认：保留最后确认量，未知不等于零。月度额度按北京时间原始开通日恢复，切换点之后的流量归新周期，核对成功后才展示新周期。
- “有效”及面板观测正常：表示相应业务或管理条件，不保证客户端当前网络可达。

## 部署与通用能力

网页应用构建为独立 `frontend` 镜像，由 nginx 提供。静态请求进入 `frontend:80`；frontend nginx 将 `/api/*`、`/auth/*` 和主题／标志资源代理至 `backend:8081` 的内部网页服务器。`backend:8080` 保留 webhook 入口；路由存在不代表旧支付业务启用。部署变更按[隔离开发环境](../development/project-local.md)及部署文档执行，本文不是生产变更授权。

<a id="настройки-env"></a>

## `.env` 配置

```env
WEBAPP_ENABLED=True
WEBAPP_SERVER_HOST=0.0.0.0
WEBAPP_SERVER_PORT=8081
SUBSCRIPTION_MINI_APP_URL=https://app.domain.com/
WEBAPP_API_BASE_URL=/api
WEBAPP_BACKEND_UPSTREAM=http://backend:8081
WEBAPP_BACKEND_UPSTREAM_HOST=backend
MINISHOP_EDGE_TOKEN=
WEBAPP_TITLE="/minishop"
WEBAPP_THEMES_DIR=data/themes
WEBAPP_DEFAULT_THEME=
WEBAPP_SESSION_SECRET=<stable-random-secret>
WEBHOOK_SECRET_TOKEN=<stable-random-secret>
WEBAPP_SESSION_TTL_SECONDS=2592000
WEBAPP_AUTH_MAX_AGE_SECONDS=86400
WEBAPP_LOGIN_TOKEN_TTL_SECONDS=600

SUPPORT_LINK=https://t.me/your_support_link
SUPPORT_TICKETS_ENABLED=True
SUPPORT_TICKET_RATE_LIMIT_PER_HOUR=5

SERVER_STATUS_ENABLED=False
SERVER_STATUS_PROVIDER=url
SERVER_STATUS_URL=
SERVER_STATUS_KUMA_URL=
SERVER_STATUS_XRAY_CHECKER_URL=
SERVER_STATUS_CACHE_TTL_SECONDS=30
SERVER_STATUS_STALE_TTL_SECONDS=300
SERVER_STATUS_TIMEOUT_SECONDS=5
```

`SUBSCRIPTION_MINI_APP_URL` 必须是公开 frontend／Mini App 的 HTTPS URL，通常使用独立域名，如 `https://app.domain.com/`。它填写在 BotFather 的 Mini Apps 中，也用于个人中心按钮、邀请链接及邮箱登录链接。不要添加 `/api`、`/webhook` 或具体页面路径。

`WEBAPP_API_BASE_URL` 是浏览器请求的基础 URL。常规 Compose 和前后端分离都应保留 `/api`。分离部署由 frontend nginx 的服务器端 `WEBAPP_BACKEND_UPSTREAM` 实现，不在 JavaScript 中公开后端源地址。

`WEBAPP_BACKEND_UPSTREAM` 是 frontend nginx 代理 `/api`、`/auth`、`/open-app` 及网页资源的私有或受保护上游，默认 `http://backend:8081`。分离部署应使用带 `MINISHOP_EDGE_TOKEN` 的受保护后端域名、私有 IP／VPN 或 Rathole 隧道。

`SERVER_STATUS_ENABLED=True` 显示用户状态页。`url` 打开 `SERVER_STATUS_URL`；`uptime-kuma`、`xray-checker` 打开 Mini App 内部页面，不使用该 URL。状态页发布、缓存、安全与排障见[服务器状态](server-status.md)。

<a id="документы-и-markdown-страницы"></a>

## 文档与 Markdown 页面

公开文档在“系统 → 文档”管理，可设置标题、slug、Markdown 正文、排序和可选分组。公开地址为 `/<slug>`，支持由小写字母、数字和短横线组成的多级路径，如 `/guides/install/ios`。系统已占用根路径时，兼容地址为 `/docs/<slug>`。空正文可保存为草稿，但地址返回 `404`。

- “在设置中显示”：把非空文档加入用户设置页。
- “在侧栏显示”：加入文档页面导航。
- 分组：在公共标题下归类链接。
- `privacy_policy`、`user_agreement` 角色：用于注册、支付和 Telegram 法律文档链接，每个角色只能分配给一份文档。

元数据和 Markdown 分开保存在持久目录 `data/docs`，原子写入。Markdown 渲染不执行原始 HTML，单文档最大 `512 KiB`。

旧 `/legal/policy`、`/legal/terms` 和 `data/pages` 中的任意文件页面保留兼容。`data/legal` 存在非空旧文件、且尚无对应角色文档时，服务安全导入新目录，不删除源文件。每种法律角色只导入一次；后台删除文档、清空正文或更改角色不会恢复旧内容。`data/legal/*.example.md` 不导入、不发布。

可视化编辑器将表格、图片、任务列表和带语言标记的代码块保留为原始 Markdown。可在“Markdown”模式中修改；切换模式或修改相邻正文不会删除它们。

手动检查文档：

```bash
curl -fsS https://app.example.com/api/documents/guides/install/ios
curl -I https://app.example.com/guides/install/ios
```

旧的任意 Markdown 页面仍可通过“系统 → 设置 → 菜单按钮”加入 Telegram 菜单。对应 `MENU_BUTTONS_JSON` 示例：

```json
[
  {
    "id": "about",
    "kind": "page",
    "target": "/company/about",
    "webapp_icon": "Info",
    "telegram_emoji": "ℹ️",
    "labels": { "zh-hans": "关于服务", "en": "About" },
    "show_in_bot": true,
    "show_in_webapp": true
  }
]
```

标准 frontend nginx 将这些无扩展名路径代理给后端，由后端确认文件存在并返回相同的带主题和 CSP 的 Mini App 页面。不要在 Markdown 中添加 HTML、JavaScript URL 或密钥：原始 HTML 按文字显示，不安全的链接和图片不渲染。

<a id="инструкции-установки"></a>

## 安装教程

**本项目独立服务模式：**在具体服务详情中，只有获取该服务已核验订阅链接后，才显示中文教程。教程配置从 `GET /api/service-guides` 读取，随 backend 镜像打包，源文件为 `deploy/examples/independent-services-guides.json`，无需额外环境变量。链接只来自当前服务，不回退到旧账号订阅。配置失败可重试；订阅刷新失败会清空旧链接并隐藏教程。见[中文客户端教程](../user-guide/clients-zh.md)。旧 `/api/subscription-guides` 仍返回 410，下面的上游流程不适用于独立服务模式。

### 上游教程格式与退役入口参考

以下保留既有配置格式和迁移参考；本项目旧 `/s/` 及账号级教程接口返回 `410 legacy_business_retired`，这些开关不能恢复旧业务。旧客户端深链、分享令牌和面板配置回退不应成为独立服务交付路径。

**上游兼容参考：**`SUBSCRIPTION_GUIDES_ENABLED=True` 时，个人中心“安装与配置”打开内部 `/install`。关闭教程、配置加载或校验失败时，旧行为是打开面板最终连接链接。

上游 `/install` 要求网页登录，通过 `/api/subscription-guides` 获取配置，依次根据 Telegram Mini Apps 平台、`navigator.userAgentData.platform`、`navigator.userAgent` 判断设备，展示 Remnawave Subscription Page v1 配置中的客户端和步骤。`happ://...` 等深层链接可在 Mini App 直接打开。模板替换 `{{SUBSCRIPTION_LINK}}`、`{{USERNAME}}`、`{{HAPP_CRYPT3_LINK}}`、`{{HAPP_CRYPT4_LINK}}`、`{{INCY_CRYPT1_LINK}}`；加密模板将原 HTTP(S) 订阅 URL 转换为相应客户端格式。

加载失败显示“重新加载”；再次打开页面也重新请求，错误不会一直缓存到应用刷新。公开 `/s/<token>` 重新加载使用相同订阅，无需登录。成功加载和明确关闭的配置仍常规缓存。

上游配置加载顺序：

1. 开启 `SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED` 时，使用后台 JSON。
2. 开启 `SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED`，且有效订阅有 `shortUuid` 时，读取该订阅已解析的面板页面配置。
3. 读取面板默认 Subscription Page 配置。
4. 使用本地 `SUBSCRIPTION_PAGE_CONFIG_PATH` 作为回退。

默认使用面板教程，避免重复配置。面板用户分配了带专属页面配置的 External Squad 时，`/install` 和 `/s/<token>` 使用该订阅已经解析的配置。本地 `data/subpage-config/multiapp.json` 不自动创建。通用回退配置在后端缓存，相关设置变化时刷新；加载错误短暂缓存，避免每次用户请求都访问面板。

私人页面显示所选客户端安全连接按钮的二维码、同一链接复制及“分享”。没有安全连接按钮时隐藏二维码。分享生成 `/s/<token>`，无需登录、没有底部导航和二维码区。`/api/subscription-guides/public/{share_token}` 只为有效本地订阅和有效分享令牌返回公开载荷。

上游 `SUBSCRIPTION_GUIDES_BOT_MENU_ENABLED=True` 使机器人连接按钮打开 `/install`，付款、试用或激活码成功后发送 `/s/<token>`；关闭则恢复最终 Remnawave 订阅页面。

配置兼容 v1 字段：`version`、`locales`、`brandingSettings`、`uiConfig`、`baseSettings`、`baseTranslations`、`svgLibrary`、`platforms`。后端校验必需翻译、平台、按钮类型及 `svgIconKey` 引用，并清洗 SVG。

教程图标和主题 SVG 采用相同静态策略：支持渐变、蒙版、滤镜、图案、标记、文字、`symbol`／`use`、`vector-effect`、`paint-order`、字体／无障碍属性，以及只包含许可样式属性的内联 `style`。`href`、`xlink:href`、`url(...)` 只能引用本地 `#id`。禁止脚本、事件处理、动画、外部图片、HTML、样式表、DTD 和实体；拒绝属性值中的 CSS 转义与注释，防止隐藏链接绕过校验。面板不支持的图标替换为中性 SVG，不停用整个教程或其他图标；JSON 编辑器和本地文件仍拒绝非法标记，便于运营者在验证时发现问题。

`brandingSettings.logoUrl` 支持 HTTP(S) 和 `data:image/…` 内嵌图片（PNG、JPEG、GIF、WebP、AVIF、BMP、ICO、SVG），包括 base64 与 URL 编码。字段为面板配置兼容保留，内置教程不显示该标志；客户端和步骤图标从 `svgLibrary` 单独读取。此许可仅限图片：`supportUrl` 必须是 HTTP(S)，按钮链接禁止 `data:`。

`WEBAPP_ENABLED=False` 时不注册用户应用与后台。恢复访问需在 `.env` 设置 `True` 并重启 backend／frontend。

后台“外观”管理标志、网站图标、强调色、主题和桌面／手机标志缩放。自定义主题从 `WEBAPP_THEMES_DIR` 读取，`WEBAPP_DEFAULT_THEME` 可按键强制选择。主题契约与制作流程见[主题与外观](webapp-themes.md)。

<a id="авторизация"></a>

## 身份认证

支持邮箱验证码、邮箱密码、Telegram Mini Apps `initData`、Telegram OAuth／OpenID Connect、Google、Yandex ID、Discord 和通行密钥。实际显示的方式取决于启用配置，各方式配置见[登录方式](login-methods.md)。登录不会自动开通服务。

SMTP 未配置时隐藏邮箱登录。未配置 Telegram OAuth 时，Telegram 内仍可通过 `initData` 登录，但外部浏览器不能启动 Telegram 登录。

工单由 `SUPPORT_TICKETS_ENABLED` 控制，备用外部联系由 `SUPPORT_LINK` 指定。完整流程见[客服与工单](support.md)。

<a id="проксирование"></a>

## 代理部署

推荐生产方案为两个公开域名、两个后端服务入口：

- `WEBHOOK_BASE_URL`，如 `https://webhooks.domain.com`，全部代理到 `backend:8080`。
- `SUBSCRIPTION_MINI_APP_URL`，如 `https://app.domain.com/`，全部代理到 `frontend:80`。

frontend 已将 `/api/*`、`/auth/*`、`/webapp-logo` 和主题／标志资源代理至 `backend:8081`，外部反向代理通常无需直接转发这些路径。

前后端分离时，浏览器仍只访问 frontend 域名：

```text
browser -> https://app.domain.com/api -> frontend nginx -> WEBAPP_BACKEND_UPSTREAM
```

支付、Telegram 和 Remnawave webhook 继续使用 `WEBHOOK_BASE_URL` 与 `8080`，不涉及 frontend 域名或 `MINISHOP_EDGE_TOKEN`。

`WEBAPP_BACKEND_UPSTREAM=https://bot.domain.com` 时，后端反向代理应将 `/api/*`、`/auth/*`、`/open-app`、标志／主题／网站图标路径转发至 `backend:8081`，并要求仅由 frontend nginx 添加的 `X-Minishop-Edge-Token`。同域 webhook 仍进入 `backend:8080`，无需该令牌。不能把令牌放进前端 JavaScript，用户可在开发者工具看到浏览器可见令牌。

现成方案见[部署](../getting-started/deployment.md#готовые-папки-запуска)：

- [Caddy](../getting-started/deployment.md#caddy-рекомендуемый-вариант)：自动 HTTPS。
- [Angie](../getting-started/deployment.md#angie)：Nginx 语法的自动 HTTPS。
- [Nginx](../getting-started/deployment.md#nginx)：证书置于相邻 `ssl/`。
- [Pangolin／Newt](../getting-started/deployment.md#pangolin--newt)：应用服务器无需开放入站端口。
- [无反向代理](../getting-started/deployment.md#без-обратного-прокси)：直接发布端口，用于检查或外部 TLS 平台。

默认 `docker-compose.yml` 向外发布 frontend 与 webhook／backend 端口；Docker 网络内部按服务 DNS 名通信：

```yaml
services:
  frontend:
    expose:
      - "80"
  backend:
    expose:
      - "8080"
```

<a id="реферальные-ссылки"></a>

## 邀请链接

本节与后面的合作伙伴、结账均为[上游兼容参考](../upstream/index.md)，不是一期客户操作路径。保留载荷格式和身份绑定说明，不据此启用奖励或付费流程。

支持两种格式：

- Telegram 深层链接：`https://t.me/<bot>?start=ref_u<code>`。
- 网页应用：`https://app.domain.com/?ref=u<code>`。

奖励页显示注册欢迎奖励与订阅付款奖励。旧模式或只有一个按时长套餐时，按周期显示详情。JSON 目录启用多个按时长套餐时，说明奖励取决于朋友的套餐和购买周期，并显示各套餐“从 N 到 N 天”的区间；问号图标展开周期详情。

应用读取 `ref`、`start`、`start_param` 和 Telegram Mini Apps 的 `start_param`，在登录前保存，随后传入 Telegram OAuth 或邮箱登录。

启用 `REGISTRATION_INVITE_ONLY_ENABLED` 后，新用户只能通过相应链接注册，没有手动输入邀请代码的字段；已有用户无需推荐参数即可登录。

新邮箱／Telegram 注册的 Remnawave 主用户使用 `minishop_id`（`ms_` 加 32 位 UUID）作为用户名。改变登录方式不更名；旧 `em_*`、`tg_*` 保留至单独确认重命名。

未占用 Telegram 身份可绑定当前账号，不改变内部 ID、订阅或角色。已属于其他账号时，不会自动合并；双账号确认流程见[不使用 Telegram](telegram-optional.md)。

<a id="партнёрские-ссылки"></a>

## 合作伙伴链接

合作伙伴使用独立代码，不替换普通邀请关系。Telegram 载荷为 `p_<partner_code>`，网页参数为 `partner=<partner_code>`。只将新用户归属于活跃合作伙伴，重复打开其他链接不转移已有客户。`REGISTRATION_INVITE_ONLY_ENABLED=True` 时，有效合作伙伴链接同样允许注册。

“合作伙伴”和 `/partner` 只在计划开启时可用。后台保存开关后，当前 Mini App 无需重启即可更新；其他会话下次加载数据时更新。完整归因、奖励、佣金与提现规则见[合作伙伴计划](partner-program.md)。

<a id="оформление-period-подписки"></a>
<a id="按时长订阅结账"></a>

## 上游按时长订阅结账参考

上游单订阅界面按时长、普通／premium 流量和设备数计算购物车，通过 `/api/subscription/quote` 获取报价，配合 `PAYMENT_METHODS_DISPLAY_MODE` 选择支付展示形式。该模型不等于本项目的一账号多份独立服务，也不是人工开通的前置流程。

保留技术说明：[价格核查](payments.md#проверка-расчёта)、[结账加购](tariffs.md#докупки-при-оформлении-подписки)、[流量加购显示时机](tariffs.md#когда-показывается-докупка-трафика)。旧“我的设备”、推荐奖励及合作伙伴余额等能力按各自兼容资料阅读，不能据配置项存在推断当前客户入口可用。
