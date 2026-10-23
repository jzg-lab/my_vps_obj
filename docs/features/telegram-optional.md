<a id="работа-без-telegram"></a>

# 不使用 Telegram

Core 可以作为通过邮箱注册的浏览器商店运行；Telegram 是可选的登录和通知渠道。数值 `user_id` 是数据库内部主键，`telegram_id` 是单独验证的绑定身份。公开的 `minishop_id` 由 `ms_` 加 32 位十六进制 UUID 组成，新建 Remnawave 主记录使用它作为用户名。

<a id="новая-установка"></a>

## 全新安装

在 `.env` 中至少设置：

```dotenv
TELEGRAM_ENABLED=False
BOT_TOKEN=
ADMIN_IDS=
WEBAPP_ENABLED=True
EMAIL_LOGIN_ENABLED=True
EMAIL_AUTH_SECRET=<固定的随机密钥>
WEBAPP_SESSION_SECRET=<另一个固定的随机密钥>
PUBLIC_APP_URL=https://shop.example.com/
WEBHOOK_BASE_URL=https://api.example.com
POSTGRES_USER=<数据库用户>
POSTGRES_PASSWORD=<数据库密码>
POSTGRES_DB=<数据库名>
SMTP_HOST=<SMTP服务器>
SMTP_PORT=587
SMTP_FROM_EMAIL=shop@example.com
```

另行填写自己的 Remnawave 和支付渠道凭据。`EMAIL_AUTH_SECRET`、`WEBAPP_SESSION_SECRET` 在重启后必须保持不变，所有副本必须一致。分别独立生成，例如 `openssl rand -hex 32`，并保存在 Git 之外。`PUBLIC_APP_URL` 是浏览器个人中心和邮件链接地址；`WEBHOOK_BASE_URL` 是接收 API webhook 的地址。即使 `EMAIL_LOGIN_ENABLED=False`，SMTP 仍可用于通知邮件。

启动 backend、worker 和 frontend 后，在浏览器个人中心注册。个人资料中可查看 `ms_…` 格式的 ID。首位所有者只能从可信服务器终端指定：

```bash
docker compose exec backend python backend/scripts/bootstrap_owner.py --minishop-id ms_<id>
```

也可使用已验证邮箱：`--email owner@example.com`。已有所有者时命令会拒绝执行。系统不会向首位随机注册用户自动授予权限。所有者在后台“设置 → 通用 → 管理员”中管理 `owner`、`admin` 角色，不能撤销最后一位所有者；服务器命令用于初始化时恢复访问。

<a id="обновление-существующей-установки"></a>

## 升级已有安装

1. 备份 PostgreSQL 和当前配置，记录待付款项、循环订阅和面板用户关联。
2. 部署新版 backend、worker 并应用常规迁移。迁移 `0090`、`0091`、`0092` 添加 UUID、`minishop_id`、角色、实际用户名、面板指纹和新内部主键序列，不会重新编号旧账号或改写其支付记录。
3. 面板仍能通过保存的原生 ID 响应时，在可信终端先执行 `python backend/scripts/capture_panel_usernames.py`，再执行 `python backend/scripts/capture_panel_usernames.py --apply`。该命令只依据已验证 Telegram 身份、已验证邮箱或精确保存的用户名读取实际用户名，不修改面板。找不到的关联保留在报告中，需人工核对。必须连接**创建这些关联的同一面板**；另一面板恰好相同的数值原生 ID 不能证明账号归属。必须在面板从 2.8 升级至 3.x **之前**执行，因为跨代后旧 UUID 可能无法通过 API 读取。核对 `account_id`、`minishop_id` 的唯一性及 `panel_user_uuid` 完整性。数据库迁移不会根据邮箱或 Telegram ID 猜测 `panel_username`。旧 `ADMIN_IDS` 只有存在明确 `telegram_id` 时才导入为角色；未解析 ID 会写入迁移日志，需人工处理。
4. 验证所有者邮箱；如果角色尚未导入，使用上述命令指定。确认后台登录正常后，再设置 `TELEGRAM_ENABLED=False`。
5. 与备份核对付款金额与状态、余额、礼品、循环付款状态、订阅和面板关联。重复 webhook 必须保持幂等。

新面板用户名使用 `minishop_id`。历史 `tg_*`、`em_*` 保留原名，直到在支持重命名的 Remnawave 版本中单独验证并执行更名。代码通过保存的 `panel_username` 和原生 ID 查找旧记录，不会声称已完成更名。如果已有面板关联无法确认，Core 保留关联供人工核对，不自动新建身份。单独升级 Minishop 不会改变面板用户名、订阅链接或连接密钥。

Telegram 身份可绑定到现有账号，而不改变 `user_id`、`account_id`、`minishop_id`、订阅或角色。如果该身份已属于另一个账号（包括通过 `/start` 创建的账号），普通绑定会提示显式合并。同一流程适用于已有 Google、Yandex ID、Discord 和邮箱账号，不为不同渠道组合制定独立规则。

重新登录第二个账号后，后端保存有效期 10 分钟的签名归属证明。`GET /api/account/merge/status` 返回当前保留账号可用的再次验证方式。带 `purpose=merge` 的 OAuth 只确认该账号已经绑定的身份；通行密钥使用 `/api/account/merge/passkey/options` 和 `/api/account/merge/passkey/verify`。启用邮箱登录时，也可通过 `POST /api/account/merge/request` 请求验证码。使用第三方身份或通行密钥验证时，不强制要求 SMTP 或已验证邮箱。

用户明确同意后，`POST /api/account/merge/confirm` 完成合并：提交 `email_code`，或在重新登录后提交空请求体。`POST /api/account/merge/cancel` 撤销已保存的确认。证明与参与账号及本次操作绑定；服务器在锁定两个账号后重新验证身份归属。保留当前账号、Minishop ID、权限和主要设置，通过既有机制迁移另一账号的登录方式及关联数据。同一渠道的不同身份、不兼容权限及其他冲突会整体拒绝，不进行部分迁移。

具有管理员角色历史的账号需要单独人工处理。删除的数值 ID 作为历史别名保留，用于旧业务记录，不赋予旧会话访问权限。两个面板记录尚未核对完成时，响应标记 `panel_reconciliation_pending`；运营者需在关闭问题前核对关联与访问权限。旧 `/api/account/telegram/merge/request` 和 `/confirm` 继续兼容邮箱验证码加新签名 Telegram 数据的流程。

另外，上游同步逻辑会在主记录已绑定 Minishop 账号时，自动合并具有相同 Telegram ID 的**面板记录**。例如，将 Telegram ID 添加至唯一一条先前手动创建的记录时，会保留该记录的 UUID、用户名和原生连接链接。Minishop 订阅保留自身 ID、套餐、已购限额、历史和续费同意；有效期限合并，已有 Minishop 公开链接重新关联到保留记录而不更换令牌。商店创建的重复记录只有在保留记录成功更新后才删除。失败重试不会重复增加天数，并会考虑后续购买、限额变更或订阅取消。存在多条外部记录或来源不明时，需人工处理；重复记录关联另一个本地账号时，使用上述双账号确认流程。

> 本节说明上游兼容行为。本项目独立多服务模式的账号合并与历史保留，以[独立服务说明](../development/independent-services.md)及当前接口为准；不能把上游“合并有效期”理解为将多个独立服务合成一份。

<a id="откат"></a>

## 回滚

创建内部 ID 与 Telegram ID 不同的账号后，旧应用镜像会再次把数值主键当作 Telegram 地址，不能安全使用。应使用理解新标识与角色的兼容版本，或把数据库和外部操作恢复至一致检查点。只回滚镜像不会回滚付款或 Remnawave 状态。恢复前先停止处理新 webhook，并保存队列以便重放。

<a id="рекламные-источники"></a>

## 广告来源

活动、链接、优惠与购买来源核查见[广告说明](./advertising/index.md)。
