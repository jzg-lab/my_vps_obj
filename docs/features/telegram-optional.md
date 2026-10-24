<a id="работа-без-telegram"></a>

# 不使用 Telegram

本项目可以通过普通浏览器与邮箱等方式使用，Telegram 是可选的登录和通知渠道。用户登录后从“我的套餐”选择独立服务；管理员使用同一账号的角色进入[统一管理后台](admin-panel.md)。一期人工开通、不接支付，不要求先创建 Telegram 账号。

数值 `user_id` 是数据库内部主键，`telegram_id` 是单独验证的绑定身份；公开的 `minishop_id` 由 `ms_` 加 32 位十六进制 UUID 组成。上游账号主面板记录使用的用户名不能替代独立服务身份：每份服务通过自己的 `service_connections` 保存连接关联，不共用账号级 `panel_user_uuid` 授予权益。

本页区分全新安装、日常绑定和上游升级参考。已有项目接手先读[接手指南](../handoff.md)，环境与验证范围只查[实施计划 §14：本轮本地最终验收](../implementation-plan.md#本轮本地最终验收)，不要重复初始化、迁移或重建现有账号。

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

另行配置 Remnawave 对接；一期不填写或启用支付渠道。`EMAIL_AUTH_SECRET`、`WEBAPP_SESSION_SECRET` 在重启后必须保持不变，所有副本必须一致。分别独立生成，例如 `openssl rand -hex 32`，并保存在 Git 之外。`PUBLIC_APP_URL` 是浏览器个人中心和邮件链接地址；`WEBHOOK_BASE_URL` 是接收 API webhook 的地址。即使 `EMAIL_LOGIN_ENABLED=False`，SMTP 仍可用于通知邮件。

启动 backend、worker 和 frontend 后，在浏览器个人中心注册。个人资料中可查看 `ms_…` 格式的 ID。首位所有者只能从可信服务器终端指定：

```bash
docker compose exec backend python backend/scripts/bootstrap_owner.py --minishop-id ms_<id>
```

也可使用已验证邮箱：`--email owner@example.com`。已有所有者时命令会拒绝执行。系统不会向首位随机注册用户自动授予权限。所有者在后台“系统 → 设置 → 常规 → 管理员”中管理 `owner`、`admin` 角色，不能撤销最后一位所有者；服务器命令只用于没有所有者时的引导，不是日常重复执行的恢复办法。

<a id="обновление-существующей-установки"></a>

## 升级已有安装

**仅供确有相应旧版本数据的升级参考。** 下列历史迁移编号与脚本不是当前接手待办；先核对目标版本、已应用迁移和备份，按[上游兼容参考](../upstream/index.md)处理。保留支付、礼品等历史数据不等于恢复这些业务入口。

1. 备份 PostgreSQL 和当前配置，记录待付款项、循环订阅和面板用户关联。
2. 部署新版 backend、worker 并应用常规迁移。迁移 `0090`、`0091`、`0092` 添加 UUID、`minishop_id`、角色、实际用户名、面板指纹和新内部主键序列，不会重新编号旧账号或改写其支付记录。
3. 面板仍能通过保存的原生 ID 响应时，在可信终端先执行 `python backend/scripts/capture_panel_usernames.py`，再执行 `python backend/scripts/capture_panel_usernames.py --apply`。该命令只依据已验证 Telegram 身份、已验证邮箱或精确保存的用户名读取实际用户名，不修改面板。找不到的关联保留在报告中，需人工核对。必须连接**创建这些关联的同一面板**；另一面板恰好相同的数值原生 ID 不能证明账号归属。必须在面板从 2.8 升级至 3.x **之前**执行，因为跨代后旧 UUID 可能无法通过 API 读取。核对 `account_id`、`minishop_id` 的唯一性及 `panel_user_uuid` 完整性。数据库迁移不会根据邮箱或 Telegram ID 猜测 `panel_username`。旧 `ADMIN_IDS` 只有存在明确 `telegram_id` 时才导入为角色；未解析 ID 会写入迁移日志，需人工处理。
4. 验证所有者邮箱；如果角色尚未导入，使用上述命令指定。确认后台登录正常后，再设置 `TELEGRAM_ENABLED=False`。
5. 与备份核对付款金额与状态、余额、礼品、循环付款状态、订阅和面板关联。重复 webhook 必须保持幂等。

新面板用户名使用 `minishop_id`。历史 `tg_*`、`em_*` 保留原名，直到在支持重命名的 Remnawave 版本中单独验证并执行更名。代码通过保存的 `panel_username` 和原生 ID 查找旧记录，不会声称已完成更名。如果已有面板关联无法确认，Core 保留关联供人工核对，不自动新建身份。单独升级 Minishop 不会改变面板用户名、订阅链接或连接密钥。

## 日常绑定与账号合并

在“设置 → 安全”绑定登录方式。未被占用的 Telegram 身份可绑定到现有账号，而不改变 `user_id`、`account_id`、`minishop_id`、独立服务或角色。如果该身份已属于另一个账号（包括通过 `/start` 创建的账号），普通绑定会提示显式合并。同一流程适用于已有 Google、Yandex ID、Discord 和邮箱账号，不为不同渠道组合制定独立规则。

合并的是登录账号归属，不是服务权益。各份服务保留原 ID、连接身份、额度、用量和日期；同模板的两份服务仍是两份。开通请求保留原始账号作用域，不能因请求编号相同丢弃历史。服务归属与历史规则见[独立服务说明](../development/independent-services.md)。

重新登录第二个账号后，后端保存有效期 10 分钟的签名归属证明。`GET /api/account/merge/status` 返回当前保留账号可用的再次验证方式。带 `purpose=merge` 的 OAuth 只确认该账号已经绑定的身份；通行密钥使用 `/api/account/merge/passkey/options` 和 `/api/account/merge/passkey/verify`。启用邮箱登录时，也可通过 `POST /api/account/merge/request` 请求验证码。使用第三方身份或通行密钥验证时，不强制要求 SMTP 或已验证邮箱。

用户明确同意后，`POST /api/account/merge/confirm` 完成合并：提交 `email_code`，或在重新登录后提交空请求体。`POST /api/account/merge/cancel` 撤销已保存的确认。证明与参与账号及本次操作绑定；服务器在锁定两个账号后重新验证身份归属。保留当前账号、Minishop ID、权限和主要设置，通过既有机制迁移另一账号的登录方式及关联数据。同一渠道的不同身份、不兼容权限及其他冲突会整体拒绝，不进行部分迁移。

具有管理员角色历史的账号需要单独人工处理。删除的数值 ID 作为历史别名保留，用于旧业务记录，不赋予旧会话访问权限。两个面板记录尚未核对完成时，响应标记 `panel_reconciliation_pending`；运营者需在关闭问题前核对关联与访问权限。旧 `/api/account/telegram/merge/request` 和 `/confirm` 继续兼容邮箱验证码加新签名 Telegram 数据的流程。

### 上游单订阅面板记录合并参考

上游同步逻辑在主记录已绑定 Minishop 账号时，可合并具有相同 Telegram ID 的**面板记录**：保留主记录 UUID、用户名和原生连接链接，合并有效期，主记录成功更新后再删除重复记录，失败重试避免重复加天数。存在多个来源不明的外部记录或其他本地账号归属时需人工核对。这是旧单订阅数据的兼容语义，不是独立服务的操作步骤；当前核心队列将旧 `panel_sync` 事件作为 `legacy_business_retired` 处理，不能照此重新同步账号级权益。

> 本节说明上游兼容行为。本项目独立多服务模式的账号合并与历史保留，以[独立服务说明](../development/independent-services.md)及当前接口为准；不能把上游“合并有效期”理解为将多个独立服务合成一份。

<a id="откат"></a>

## 回滚

创建内部 ID 与 Telegram ID 不同的账号后，旧应用镜像会再次把数值主键当作 Telegram 地址，不能安全使用。应使用理解新标识与角色的兼容版本，或把数据库和外部操作恢复至一致检查点。只回滚镜像不会回滚付款或 Remnawave 状态。恢复前先停止处理新 webhook，并保存队列以便重放。

<a id="рекламные-источники"></a>

## 广告来源

活动、链接、优惠与购买来源核查见[广告说明](./advertising/index.md)。
