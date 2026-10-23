<a id="способы-входа"></a>

# 登录方式

Minishop 支持七种登录方式：

1. **邮箱验证码**：一次性验证码或邮件中的快捷登录链接。
2. **邮箱与密码**：验证邮箱后设置的密码。
3. **Telegram**：Telegram 内使用 Mini Apps `initData`，浏览器使用 OAuth／OpenID Connect。
4. **Google**：服务器端 OAuth 2.0／OpenID Connect。
5. **Yandex ID**：Yandex OAuth 应用。
6. **Discord**：Discord OAuth2 应用。
7. **通行密钥**：WebAuthn 密钥。

后台配置入口为“系统 → 设置 → 登录方式”。用户在“设置 → 安全”管理密码、通行密钥、已绑定渠道和通知邮箱。

| 方式 | 可用条件 | 所需配置 |
| --- | --- | --- |
| [邮箱验证码](#邮箱验证码) | 开启 `EMAIL_LOGIN_ENABLED` 且 SMTP 就绪 | SMTP、发件地址、公开 Mini App URL |
| [邮箱与密码](#邮箱与密码) | 用户已验证邮箱并设置密码 | 相同 SMTP 配置，用于验证和恢复 |
| [Telegram](#telegram) | 开启 `TELEGRAM_LOGIN_ENABLED` | BotFather、`BOT_TOKEN`；浏览器另需 Telegram OAuth |
| [Google](#google) | 开启 `GOOGLE_OIDC_ENABLED` | OAuth 客户端 ID、密钥、回调 |
| [Yandex ID](#yandex-id) | 开启 `YANDEX_OIDC_ENABLED` | OAuth 客户端 ID、密钥、回调 |
| [Discord](#discord) | 开启 `DISCORD_OIDC_ENABLED` | OAuth2 应用 ID、密钥、回调 |
| [通行密钥](#通行密钥passkey) | 开启 `PASSKEY_LOGIN_ENABLED` | HTTPS、RP ID、允许的源地址 |

每个可用渠道有独立“推荐登录方式”开关。开启后，用户尚未绑定该方式时，设置显示红色提醒；关闭后仍可登录和绑定，但缺少该方式不会单独触发提醒。推荐默认开启，以保留升级前行为；管理员可只保留需要的推荐。

“外观 → 紧凑登录方式”将宽按钮换为渠道图标，默认开启，但仅在可用方式多于一种时生效；只有一种时仍显示宽按钮或表单。“登录方式”中每个渠道的“宽登录按钮”可覆盖紧凑模式。邮箱默认开启宽按钮，直接显示表单；关闭后点击邮箱图标才显示表单。标准主题中的紧凑图标没有圆形底色。推荐开关仍独立控制提醒。

后台权限取决于内部账号角色，与登录方式无关。首位所有者在验证邮箱后通过服务器命令指定。

<a id="модель-аккаунта-и-защита-от-дублей"></a>

## 账号模型与防重复

一个账号可绑定多个登录方式和多个已验证邮箱，地址用途相互独立：

- **主邮箱**用于验证码／密码登录、账号恢复和 Remnawave 面板邮箱同步。
- **通知邮箱**由用户在已验证地址中明确选择。
- Google、Yandex ID 以稳定的 `provider + subject` 识别身份，不以邮箱识别。
- OIDC 附加邮箱不会自动成为邮箱登录名，也不会自动更改面板记录。

新 Google／Yandex ID 登录返回的邮箱已被现有账号使用时，后端**不会新建重复用户，也不会只凭相同邮箱字符串绑定**。OAuth 成功后，向已有已验证邮箱发送一次性验证码。OAuth 证明渠道身份，验证码证明现有 Minishop 账号归属。两项都通过后，身份才绑定原记录并登录；主邮箱、通知邮箱和面板邮箱不变。

待绑定上下文保存在短期签名 HttpOnly cookie 中，客户端只提交验证码，不能替换 `provider`、稳定 `subject`、精确邮箱和目标用户 ID。重新发送与确认前，后端再次校验邮箱归属、已有身份和渠道启用状态。上下文过期、地址归属变化或并发绑定会失败，不创建新用户。

合并保留双方已验证邮箱，但不自动修改目标主邮箱。订阅、付款、邀请限制等继续执行已有冲突检查，不能安全合并时整体停止，不产生部分更改。

<a id="общие-требования"></a>

## 公共要求

填写公开 HTTPS Mini App URL 和固定会话密钥：

```ini
SUBSCRIPTION_MINI_APP_URL=https://app.example.com/
WEBAPP_SESSION_SECRET=<stable-random-secret>
```

`/auth/*` 必须进入网页 API。标准 Compose 通过 frontend nginx 转发。自定义反向代理不要把回调发到 `8080` webhook 服务器；网页后端使用内部 `8081`。

生产环境应使用独立 OAuth 应用和密钥，不要把客户端密钥放入前端、公开 JSON 配置或 URL。

<a id="общая-настройка-email"></a>

## 邮件公共配置

邮箱验证码与密码登录共用 SMTP。启用方式并填写所有必填项：

```ini
EMAIL_LOGIN_ENABLED=True

SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USERNAME=<smtp-login>
SMTP_PASSWORD=<smtp-password-or-api-key>
SMTP_FROM_EMAIL=no-reply@domain.com
```

任一必填 SMTP 字段为空时，后端启动数据返回 `email_auth_enabled=false`，前端隐藏邮箱登录。快捷登录链接还需要有效 `SUBSCRIPTION_MINI_APP_URL`。

常见完整配置：

```ini
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_FALLBACK_PORTS=2525,465
SMTP_TIMEOUT_SECONDS=30
SMTP_STARTTLS=True
SMTP_USE_SSL=False
SMTP_USERNAME=<smtp-login>
SMTP_PASSWORD=<smtp-password-or-api-key>
SMTP_FROM_EMAIL=no-reply@domain.com
SMTP_FROM_NAME=Remnawave Minishop

EMAIL_CODE_TTL_SECONDS=600
EMAIL_CODE_RESEND_SECONDS=60
EMAIL_CODE_MAX_ATTEMPTS=5
BRUTE_FORCE_MAX_FAILURES=5
BRUTE_FORCE_WINDOW_SECONDS=900
BRUTE_FORCE_LOCK_SECONDS=900
```

Brevo 通常使用 `587` 和 STARTTLS。主端口不可用时依次尝试 `SMTP_FALLBACK_PORTS`；`465` 自动使用 SSL。发件地址须由 SMTP 渠道验证，否则可能被拒绝或进入垃圾邮件。`SMTP_FROM_NAME` 可留空，使用网页应用名称。

HTML 邮件采用 Mini App 品牌：`WEBAPP_TITLE`、外观强调色及标志。后台上传的标志由后端作为内嵌附件 `cid:webapp-logo` 发送，接收者无需访问内部 `/webapp-uploaded-logo/...`。公开 `https://` 标志作为外部图片，邮件客户端可能在用户允许加载前隐藏。

完整变量见 [SMTP 与邮箱登录](../configuration/env-vars.md#smtp-и-вход-по-email)。

<a id="email-код"></a>

## 邮箱验证码

无需 Telegram 即可注册或登录：

1. 输入邮箱。
2. 后端校验限流并生成一次性验证码。
3. SMTP 发送邮件；`SUBSCRIPTION_MINI_APP_URL` 有效时同时包含快捷登录链接。
4. 用户输入验证码或打开快捷链接。
5. 后端创建邮箱用户或查找已有账号。
6. URL 中邀请参数应用于新记录或已有记录。
7. 用户获得网页会话。

验证码以哈希保存，按 `EMAIL_CODE_TTL_SECONDS` 过期；重发受 `EMAIL_CODE_RESEND_SECONDS` 限制，尝试次数受 `EMAIL_CODE_MAX_ATTEMPTS` 及公共防暴力尝试配置约束。

登录后，可通过验证码为 Telegram 账号绑定邮箱，也可通过 Mini Apps `initData` 或 Telegram OAuth 为邮箱账号绑定 Telegram。

<a id="проверка-email-кода"></a>

### 验证邮箱登录

1. 修改 `.env` 后重启 backend、frontend。
2. 在 Telegram 之外打开 `https://app.domain.com/`，确认邮箱入口可见。
3. 向测试邮箱请求验证码。
4. 检查邮件、快捷链接及手动输入六位验证码。
5. 未收到邮件时查看日志：

```bash
docker compose logs -f backend
```

常见原因：

- 表单隐藏：SMTP 必填项缺失或 `EMAIL_LOGIN_ENABLED` 关闭。
- 发送失败：端口、STARTTLS／SSL、SMTP 账号／API 密钥或发件人错误。
- 快捷链接错误：`SUBSCRIPTION_MINI_APP_URL` 不是公开 HTTPS Mini App 地址。
- 验证码立即过期：有效期配置或服务器时间错误。
- `rate_limited`：重发间隔未到，或触发防暴力尝试保护。

<a id="email-и-пароль"></a>

## 邮箱与密码

验证邮箱后，可在个人资料设置或修改密码。密码以带盐 PBKDF2-SHA256 哈希保存。设置后可访问：

```text
https://app.domain.com/login/password
```

登录失败时，前端提供切换验证码入口。设置、修改、恢复密码也需要邮箱验证码，因此仍要求 SMTP 正常。

## Telegram

- Telegram 内由后端校验 Mini Apps `initData`。
- 普通浏览器使用带 PKCE、`nonce` 的 OAuth／OpenID Connect 授权码流程，回调为 `/auth/telegram/callback`，服务器通过 JWKS 校验 `id_token`。

`initData` 不需要额外 OAuth 密钥，但需要有效 `BOT_TOKEN`、公开 HTTPS Mini App URL 和 BotFather Mini Apps 配置。浏览器外部登录按钮和为邮箱账号绑定 Telegram 需要 OAuth。

<a id="переменные-telegram"></a>

### Telegram 变量

```ini
WEBAPP_ENABLED=True
SUBSCRIPTION_MINI_APP_URL=https://app.domain.com/
WEBAPP_SESSION_SECRET=<stable-random-secret>
WEBAPP_AUTH_MAX_AGE_SECONDS=86400
WEBAPP_LOGIN_TOKEN_TTL_SECONDS=600

TELEGRAM_LOGIN_ENABLED=True
TELEGRAM_OAUTH_CLIENT_ID=<client-id-from-botfather>
TELEGRAM_OAUTH_CLIENT_SECRET=<client-secret-from-botfather>
TELEGRAM_OAUTH_REQUEST_ACCESS=write
TELEGRAM_OAUTH_USE_BOT_PROXY=True
```

客户端 ID 与机器人 ID 相同时，可省略 `TELEGRAM_OAUTH_CLIENT_ID`，从 `BOT_TOKEN` 前缀读取。浏览器 OAuth 必须填写 `TELEGRAM_OAUTH_CLIENT_SECRET`。

`TELEGRAM_OAUTH_REQUEST_ACCESS=write` 添加 `telegram:bot_access` 权限，以便机器人在登录后联系用户；不需要则留空。也支持 `phone`，仅在确实需要请求手机号时使用。

`WEBAPP_AUTH_MAX_AGE_SECONDS` 限制 `initData`、OAuth `id_token` 的年龄；`WEBAPP_LOGIN_TOKEN_TTL_SECONDS` 控制 OAuth state、nonce 和登录令牌有效期。

完整参考：[网页应用、外观与 Telegram 登录](../configuration/env-vars.md#веб-приложение-внешний-вид-и-telegram-login)。

<a id="настройка-telegram-в-botfather"></a>

### BotFather 配置

1. 打开 `@BotFather` → `/mybots`，选择机器人。
2. 在机器人设置的域名项（`Bot Settings → Domain`）填写不含协议和路径的域名，如 `app.domain.com`。
3. 在 Mini Apps 设置填写 `https://app.domain.com/`。
4. 网页登录（`Web Login`）提供开关时，启用 OpenID Connect Login。
5. 将客户端 ID、密钥复制到 `TELEGRAM_OAUTH_CLIENT_ID`、`TELEGRAM_OAUTH_CLIENT_SECRET`。
6. 在允许地址（`Web Login → Allowed URLs`）添加：

```text
https://app.domain.com/
https://app.domain.com/auth/telegram/callback
```

修改 `.env` 后重建 backend、frontend：

```bash
docker compose up -d --force-recreate backend frontend
```

<a id="проксирование-telegram-oauth"></a>

### Telegram OAuth 代理

`SUBSCRIPTION_MINI_APP_URL` 公开域名应进入 `frontend:80`。frontend nginx 自动将 `/api/*`、`/auth/*` 转到 `backend:8081`。Caddy、Angie、Nginx、Newt 和直接发布方案见[部署目录](../getting-started/deployment.md#готовые-папки-запуска)。

后端无法直接访问 `oauth.telegram.org` 时配置 SOCKS5：

```ini
TELEGRAM_BOT_PROXY_URL=socks5://username:password@proxy.example.com:1080
TELEGRAM_OAUTH_USE_BOT_PROXY=True
```

授权码换令牌及 JWKS 加载走代理。`/auth` 页面仍通过用户网络打开，Telegram webhook 仍进入公开 `WEBHOOK_BASE_URL`；`initData` 和旧 Login Widget 在本地校验。若只让 Bot API 走代理、OAuth 直连，设置 `TELEGRAM_OAUTH_USE_BOT_PROXY=False`。

<a id="проверка-telegram"></a>

### 验证 Telegram 登录

Telegram 内：

1. 通过机器人按钮或 BotFather URL 打开 Mini App。
2. 确认无需 OAuth 跳转即可登录。
3. 失败时检查 Mini App URL、BotFather 域名和 `initData` 年龄。

普通浏览器：

1. 打开 `https://app.domain.com/`，点击 Telegram 登录。
2. 确认跳转 Telegram OAuth 并返回 `https://app.domain.com/auth/telegram/callback`。
3. 回调后应返回带 `telegram_auth=success` 的 `/`，前端随后移除此参数。

诊断命令：

```bash
curl -i https://app.domain.com/auth/telegram/start
docker compose logs -f backend frontend
```

常见原因：

- `telegram_oauth_not_configured`：密钥缺失，或无法从配置／令牌获得客户端 ID。
- `Telegram OAuth nonce mismatch`：会话／state 过期、会话密钥变化，或回调来自另一域名。
- `Telegram OAuth ID token is stale`：最大年龄太小或服务器时间错误。
- 回调失败：允许 URL 不匹配，或 `/auth/*` 未到网页 API。
- `invalid_token`：后端无法访问令牌接口／JWKS，或代理配置错误。
- Mini App 无法打开：BotFather 域名与应用 URL 不匹配。

相关日志：[Mini App 与 Telegram OAuth 认证](../troubleshooting/logs.md#авторизация-mini-app-и-telegram-oauth)。

## Google

1. 打开 [Google Cloud Console](https://console.cloud.google.com/apis/credentials)，选择独立生产项目。
2. 配置 OAuth 同意页面：服务名、联系方式、域名、隐私政策、用户协议。
3. 创建类型为网页应用（`Web application`）的 OAuth 2.0 客户端 ID。
4. 授权 JavaScript 源地址（`Authorized JavaScript origins`）留空。Minishop 使用服务器端授权码流程和 PKCE，不加载 Google Identity Services JavaScript SDK。
5. 在授权重定向 URI 中添加精确地址：

```text
https://app.example.com/auth/google/callback
```

6. 保存并启用：

```ini
GOOGLE_OIDC_ENABLED=True
GOOGLE_OIDC_CLIENT_ID=<client-id>.apps.googleusercontent.com
GOOGLE_OIDC_CLIENT_SECRET=<client-secret>
```

只请求 `openid email profile`，验证签名及标准 OIDC 声明 `iss`、`aud`、`exp`、`nonce`，仅接受 `email_verified=true` 的邮箱。

Google 要求重定向 URI 完全一致，包括协议、大小写、端口、路径和斜杠。见[网页服务器 OAuth 2.0](https://developers.google.com/identity/protocols/oauth2/web-server)。

## Yandex ID

1. 打开 [Yandex OAuth](https://oauth.yandex.ru/)，创建用户认证应用。
2. 添加网页服务平台。
3. 填写重定向 URI：

```text
https://app.example.com/auth/yandex/callback
```

4. 只允许 `login:email`、`login:info`、`login:avatar` 所需最小权限。
5. 保存并启用：

```ini
YANDEX_OIDC_ENABLED=True
YANDEX_OIDC_CLIENT_ID=<client-id>
YANDEX_OIDC_CLIENT_SECRET=<client-secret>
```

Minishop 使用 Yandex 返回的 `default_email` 作为已验证渠道地址，但不替换已有账号主邮箱。

注册步骤见 [Yandex ID 官方文档](https://yandex.com/dev/id/doc/en/register-auth)。

## Discord

1. 打开 [Discord Developer Portal](https://discord.com/developers/applications)，创建应用。
2. 在 OAuth2 中添加回调地址：

```text
https://app.example.com/auth/discord/callback
```

3. 复制应用 ID 和客户端密钥并启用：

```ini
DISCORD_OIDC_ENABLED=True
DISCORD_OIDC_CLIENT_ID=<application-id>
DISCORD_OIDC_CLIENT_SECRET=<client-secret>
```

使用服务器端授权码流程，只请求 `identify email`。通过 Discord `/users/@me` 获取资料，邮箱仅在 `verified=true` 时视为已验证。与已有账号邮箱相同时，和 Yandex ID 一样要求验证码确认。

官方参考：[Discord OAuth2](https://docs.discord.com/developers/topics/oauth2)。

后台保存 Google、Yandex ID、Discord 设置后，后续 `/auth/{provider}/start`、`/callback` 请求立即应用，无需重启后端；登录页和缓存的个人中心数据也会刷新。如果后台提示“已保存但未应用”，则在重启前不能视为生效。

<a id="ключи-доступа-passkey"></a>

## 通行密钥（passkey）

通行密钥使用 WebAuthn，要求 HTTPS。浏览器对 `localhost` 的本地例外不能作为生产配置。

```ini
PASSKEY_LOGIN_ENABLED=True
PASSKEY_RP_ID=app.example.com
PASSKEY_RP_NAME=Example VPN
PASSKEY_ORIGINS=https://app.example.com
PASSKEY_CHALLENGE_TTL_SECONDS=300
```

- `PASSKEY_RP_ID`：不含协议、端口和路径的域名。
- `PASSKEY_RP_NAME`：设备创建密钥时显示的服务名。
- `PASSKEY_ORIGINS`：含 `https://` 的完整源地址，多个以逗号分隔。
- 更换 RP ID 后，旧密钥不能用于新域名。
- 在第二台设备验证前，不要关闭其他登录方式。

参考 [MDN 通行密钥说明](https://developer.mozilla.org/en-US/docs/Web/Security/Authentication/Passkeys)。

<a id="привязка-способов-и-адрес-для-уведомлений"></a>

## 绑定登录方式与通知邮箱

用户可在个人资料设置：

- 通过验证码为 Telegram 账号绑定邮箱。
- 通过 Mini Apps `initData` 或 OAuth 绑定 Telegram。
- 设置或修改密码。
- 绑定 Google、Yandex ID、Discord 和通行密钥。
- 从已验证地址选择通知邮箱。

绑定方式已属于其他账号时，显示统一合并对话框；Telegram、Google、Yandex ID、Discord、邮箱共用流程。新鲜授权证明第二个账号，当前账号通过已有渠道、通行密钥或邮箱验证码再次验证。渠道／通行密钥验证不强制要求 SMTP 和邮箱登录。用户明确同意后，保留当前 Minishop ID、主邮箱及设置，迁移可用登录方式及关联数据，并清理旧网页缓存。新增渠道也复用同一机制，不为渠道组合增加独立规则。

新 OAuth 身份尚未绑定、但邮箱被其他账号占用时，从设置绑定只保存已证明的渠道身份，不改动他人邮箱或账号。与邮箱所有者合并必须再用验证码证明。相同渠道的两个不同身份、第二账号的管理角色历史或其他不兼容数据会导致整体拒绝。协议见[独立账号说明](telegram-optional.md)。

主邮箱变更独立分两步：先验证旧邮箱验证码，再验证新邮箱验证码。成功后新地址成为主邮箱和通知邮箱，并同步至 Remnawave。单独绑定／解绑 OIDC 不修改面板邮箱。

可独立于邮箱登录关闭地址变更：

```ini
EMAIL_ADDRESS_CHANGE_ENABLED=True
```

关闭后按钮禁用，后端拒绝已开始流程的所有步骤，但仍允许首次绑定邮箱、验证码／密码登录，或选择另一个已验证 OIDC 通知地址。

地址变更流程：

1. 向当前主邮箱发验证码。
2. 验证后输入新地址；已占用地址在创建记录前拒绝。
3. 向新地址发送与用户及精确地址绑定的第二个验证码。
4. 确认后更新主邮箱、通知邮箱和面板邮箱；旧邮箱收到安全通知，新邮箱收到更改确认。

唯一性在发验证码前和事务中各校验一次，数据库约束阻止并发竞争。登录、恢复、主邮箱确认邮件发到对应操作地址，自动通知发到所选通知邮箱。

<a id="общая-проверка"></a>

## 整体验证

1. 检查登录页每个已启用方式。
2. 验证码登录、设置密码、退出，再用密码登录。
3. 分别检查 Telegram Mini App 内和普通浏览器登录。
4. 使用新的 Google、Yandex ID、Discord 账号登录；邮箱相同时用验证码确认，确保不产生重复账号。
5. 添加通行密钥、退出、用密钥登录；保留其他方式时验证删除密钥。
6. 在“设置 → 安全”检查身份列表、主邮箱、通知邮箱。
7. 确认单独绑定 OAuth 不改变面板订阅和邮箱。

常见问题：

- 按钮隐藏：方式关闭或必填参数缺失。
- `redirect_uri_mismatch`：协议、域名、端口、路径、斜杠不一致。
- `account_exists`：相同主邮箱尚未确认，不能自动绑定。
- OIDC 上下文过期：重新通过渠道登录。
- 通行密钥不可用：无 HTTPS、RP ID 与域名不符，或源地址不允许。
- 通知发错地址：检查明确选择的通知邮箱；最近使用的登录方式不会改变它。

客服、支付和订阅生命周期邮件共用 SMTP。另见[通知](notifications.md)、[客服](support.md)。

<a id="настройка-локального-smtp-сервера"></a>

## 本地 SMTP 服务器配置

启动前配置域名 DNS：

- A：`mail.example.com` 指向服务器 IP。
- MX：`mail.example.com`，优先级 10。
- PTR：在 VPS 提供商处设置为 `mail.example.com`。
- TXT：`v=spf1 ip4:1.2.3.4 ~all`，替换为服务器实际 IPv4。

DNS 生效可能需要数小时至一天。STARTTLS 需要 `mail.example.com` 证书，例如 Caddy：

```txt
https://mail.example.com {
    respond "Mail server"
}
```

安装步骤：

1. 准备 Compose：

```bash
mkdir -p /opt/mailserver
cd /opt/mailserver
curl -O https://gitlab.com/3252a8/remnawave-minishop/-/raw/main/deploy/examples/mail/docker-compose.yml
nano docker-compose.yml
```

<!-- GitHub 源地址（停用）：https://raw.githubusercontent.com/3252a8/remnawave-minishop/refs/heads/main/deploy/examples/mail/docker-compose.yml -->

2. 启动：

```bash
docker compose up -d
```

3. 创建用户：

```bash
docker exec -it mailserver setup email add no-reply@example.com
docker exec -it mailserver setup email list
```

创建的地址和密码可用于邮件客户端及 Minishop SMTP 设置。

<a id="рекламные-источники"></a>

## 广告来源

活动、链接、优惠与购买来源核查见[广告说明](./advertising/index.md)。
