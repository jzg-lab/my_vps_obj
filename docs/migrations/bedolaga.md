<a id="миграция-из-bedolaga"></a>

# 从 Bedolaga 迁移

Minishop 通过通用导入器读取 [Bedolaga](https://docs.bedolagam.ru/) PostgreSQL。已验证支持 Alembic `0110`、`0118`；未知版本只允许清点和试运行，禁止正式应用。

<a id="что-переносится"></a>

## 导入范围

- Telegram、邮箱账号，已验证邮箱和 OAuth 身份。
- 邀请关系与代码。
- 套餐的精确天数、价格、流量、设备和节点组。
- 全部订阅，包括已过期、已停用和已使用试用。
- 交易历史及以整数最小货币单位表示的余额。
- 已付款、已投递礼品；未付款记录归档，不授予权益。
- 兼容激活码及使用记录。
- 客服工单与消息。
- 广告活动与归因。
- 合作伙伴资料和申请。
- 可安全映射的设置及支付方式排序。

不迁移密码、刷新／会话令牌、验证码、临时 OAuth 状态等用户有效密钥；秘密设置值不会出现在 JSON 报告中。

<a id="безопасность"></a>

## 安全边界

向导分别询问 backend／worker 使用的 `PANEL_API_URL` 和管理员浏览器使用的 `PANEL_PUBLIC_URL`。API 地址从 `REMNAWAVE_API_URL` 发现，公开地址从面板配置或旧机器人公开 API 地址发现。Minishop `.env` 中已有 `PANEL_PUBLIC_URL` 会保留。旧 API 为内部地址且找不到公开地址时，必须手动填写浏览器地址。

源与目标必须为不同数据库。源连接使用只读事务。`--dry-run` 不运行目标结构迁移，并阻止全部目标 ORM／SQL 写入。重复应用通过 `legacy_import_mappings`、付款渠道／幂等键及账本保持幂等。

正式应用前，向导提示备份 Minishop。清点、试运行和导入均不修改源栈。应用成功后，单独确认才执行自动切换；Minishop 启动或健康检查失败时，向导恢复旧 `.env` 并尝试恢复 Bedolaga。

<a id="ручной-запуск"></a>

## 手动运行

先试运行：

```bash
python backend/scripts/import_legacy.py \
  --source-type bedolaga \
  --source-dsn 'postgresql://source_user:source_password@source-db:5432/bedolaga' \
  --target-dsn 'postgresql://target_user:target_password@target-db:5432/minishop' \
  --source-env-file /opt/bedolaga/.env \
  --dry-run \
  --inventory-output .installer/bedolaga-inventory.json \
  --config-plan-output .installer/bedolaga-config-plan.json \
  --summary-output .installer/bedolaga-dry-run-summary.json \
  --reconciliation-output .installer/bedolaga-dry-run-reconciliation.json
```

确认 `blockers` 为空、`balance_total_matches=true`，并处理 `identity_conflicts`、`unresolved_panel_subscriptions`。再移除 `--dry-run` 重复执行，正式报告使用独立文件名。

使用向导时，运行 `scripts/install.sh`，选择迁移及 Bedolaga 来源。向导发现本地 `.env`、PostgreSQL 容器和 Compose 项目，创建迁移前备份、试运行并请求确认应用。写入前显示脱敏计划，可自动将兼容启动设置迁入 Minishop `.env`：

- `BOT_TOKEN`、`ADMIN_IDS` 和 Telegram webhook 密钥。
- Remnawave 面板 URL／API 密钥。
- Telegram、Google OAuth／OIDC 客户端凭据。
- Bedolaga webhook／个人中心 URL 中的公开主机名。
- 语言、日志级别、时区和兼容的本地备份参数。

不复制 PostgreSQL／Redis 密码、Bedolaga 会话／JWT 密钥及不兼容运行参数。已有 Minishop `.env` 就地备份。清点、配置计划、摘要与核对报告保存在 `.installer/`，应用后另生成 `bedolaga-post-migration.md`。

<a id="сопоставление-учетных-записей"></a>

## 账号映射

只依据稳定身份合并：Telegram、已验证邮箱、OAuth subject 或面板 ID。不同证据指向不同 Minishop 账号时，进入 `identity_conflicts`，不自动合并。纯邮箱账号使用独立区间的稳定负数内部 ID，不复制旧密码哈希和会话。

<a id="финансовая-сверка"></a>

## 财务核对

已完成充值、推荐入账、订阅与礼品扣款，以戈比为单位导入只追加账本。每个账号创建幂等期初余额调整，使账本与源 `balance_kopeks` 一致。历史 `new`、`change`、`renew` 仅保存为付款历史，不再次影响余额。

应用后，核对用户／订阅／付款数量及最小单位总额。另行检查带 `bedolaga-unresolved:*` 的有效订阅：记录保留，但启动运行时同步前，必须人工关联当前 Remnawave 用户。

<a id="настройки-и-cutover"></a>

## 配置与切换

配置计划只显示许可映射，秘密值标为 `<redacted>`。成功应用后，明确确认切换，向导将：

1. 检查 Bedolaga 没有通过 cron 启动。
2. 停止整个源 Compose 项目，不删除容器、卷或数据库。
3. 将源容器重启策略设为 `no`，停用已确认的 Bedolaga systemd 单元，检查旧栈已停止。
4. 启动 Minishop，等待 backend／worker／frontend 就绪，执行常规栈和面板 API 检查。
5. eGames 配置切换面板 webhook。
6. 再次确认 Bedolaga 未重新启动。

手动目标 DSN 不执行自动切换，因为向导不能安全管理远程 Minishop。支付凭据及 webhook、强制频道、法律页面和自定义菜单仍需人工核对，没有通用安全映射。

<a id="внешние-кабинеты-после-миграции"></a>

## 迁移后的外部平台

向导最后显示新 Minishop 地址，但不能替你修改第三方平台回调或 webhook，必须逐一更新已启用集成。

OIDC 回调基于 frontend `MINIAPP_PUBLIC_URL`：

- Telegram BotFather 网页登录／OIDC：`/auth/telegram/callback`。
- Google Cloud 授权重定向 URI：`/auth/google/callback`。
- Yandex OAuth 重定向 URI：`/auth/yandex/callback`。

支付 webhook 基于 backend `WEBHOOK_BASE_URL`：

| 渠道 | webhook 路径 |
| --- | --- |
| YooKassa | `/webhook/yookassa` |
| FreeKassa | `/webhook/freekassa` |
| Platega | `/webhook/platega` |
| RollyPay | `/webhook/rollypay` |
| SeverPay | `/webhook/severpay` |
| WATA | `/webhook/wata` |
| Crypto Pay | `/webhook/cryptopay` |
| Heleket | `/webhook/heleket` |
| OxaPay | `/webhook/oxapay` |
| PayKilla | `/webhook/paykilla` |
| LAVA | `/webhook/lava` |
| Pally／PayPalych | `/webhook/pally` |
| CloudPayments | `/webhook/cloudpayments` |
| Overpay | `/webhook/overpay` |
| Stripe | `/webhook/stripe` |
| Tribute | `/webhook/tribute` |

OxaPay 创建账单时自动传递回调，LAVA 传递 `hookUrl`，更换域名后仍应检查。Telegram Stars 使用机器人共用 `/tg/webhook`，无需单独支付 webhook。

更新地址后，逐一测试已启用 OIDC 登录和支付渠道。事件、签名与许可名单要求见[登录方式](../features/login-methods.md)、[支付渠道](../features/payments.md)。
