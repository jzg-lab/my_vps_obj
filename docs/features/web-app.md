<a id="веб-приложение--mini-app"></a>

# 网页应用与 Mini App

网页应用构建为独立 `frontend` 镜像，由 nginx 提供。Mini App 静态请求进入 `frontend:80`；frontend nginx 将 `/api/*`、`/auth/*` 和主题／标志资源代理至 `backend:8081` 的内部网页服务器。Telegram、支付和面板 webhook 仍由 `backend:8080` 处理。

> 本页包含上游功能参考。本项目一期以独立多服务、人工开通及中文教程为准，不开放旧支付与营销购买入口。旧教程接口已退役；当前服务教程路径见本页“安装教程”。

<a id="что-показывает-веб-приложение"></a>

## 网页应用显示什么

- 当前连接链接、订阅状态和到期日、已用与可用流量。
- 当前套餐配置 premium 节点组及限额时，显示独立 premium 流量卡片。
- 可用套餐、支付方式和付款状态。
- 按时长套餐的权益卡片；管理员启用后，可在结账时通过滑块选择总设备数和普通／premium 周期限额。
- 配置套餐目录后，可切换套餐、加购普通与 premium 流量。默认使用对应额度超过 80% 后才推荐加购；套餐开启“始终允许加购”时例外，见[流量加购显示时机](tariffs.md#когда-показывается-докупка-трафика)。
- 内置安装教程：平台、客户端列表、深层链接按钮、二维码和订阅链接操作。
- `MY_DEVICES_SECTION_ENABLED=True` 时显示“我的设备”。
- `SUPPORT_TICKETS_ENABLED` 开启时显示客服工单与外部 `SUPPORT_LINK`。
- `SERVER_STATUS_ENABLED=True` 时显示外部状态页，或内置 Uptime Kuma／xray-checker 数据。
- “设置 → 通知”管理邮件、Telegram 营销和系统通知；消息按钮与菜单可使用 `/settings/notifications` 或 `startapp=notifications`。
- 邀请链接与推荐统计。
- 合作伙伴计划开启时显示“合作伙伴”，包括申请、专属链接、客户、佣金、独立余额、提现和余额全额／部分付款。
- 将邮箱与 Telegram 绑定到同一账号。

具有 `owner` 或 `admin` 角色的账号还可进入管理后台，查看统计、用户搜索／筛选／premium 流量、合作伙伴、客服、群发、激活码、日志、设置和套餐编辑器。见[管理后台](admin-panel.md)。

<a id="оформление-period-подписки"></a>

## 按时长订阅结账

选择时长前，Mini App 展示紧凑套餐卡片，包括名称、说明、设备、普通及 premium 流量。无限资源显示“不限量”，不额外显示重置周期。存在可用结账滑块时，点击卡片或修改按钮可展开；未启用滑块的参数仅显示信息。

切换购买时长会保留所选设备数和限额。总按钮、所有周期卡片和月均价格随选择动态更新。连续拖动时本地计算，松开滑块后调用 `/api/subscription/quote` 获取服务器权威报价。百分比折扣按整个购物车计算。

支付方式默认显示为带图标的下拉列表；`PAYMENT_METHODS_DISPLAY_MODE=buttons` 可恢复独立按钮。低于最低金额的渠道仍显示但禁用，悬停、聚焦或点击时提示最低值。见[价格核查](payments.md#проверка-расчёта)及[结账加购](tariffs.md#докупки-при-оформлении-подписки)。

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
SUBSCRIPTION_GUIDES_ENABLED=True
SUBSCRIPTION_GUIDES_BOT_MENU_ENABLED=True
SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED=True
SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED=False
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

支持邮箱验证码、邮箱密码、Telegram Mini Apps `initData`、Telegram OAuth／OpenID Connect、Google、Yandex ID 和通行密钥。各方式配置见[登录方式](login-methods.md)。

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
