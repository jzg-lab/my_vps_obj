<a id="миграция-из-remnashop"></a>

# 从 Remnashop 迁移

Remnashop 使用通用导入脚本 `backend/scripts/import_legacy.py`。最方便的方式是交互安装向导：

```bash
curl -fsSL https://gitlab.com/3252a8/remnawave-minishop/-/raw/main/scripts/install.sh -o install.sh
sh install.sh
```

<!-- GitHub 备用安装地址（停用）：

```bash
curl -fsSL https://raw.githubusercontent.com/3252a8/remnawave-minishop/main/scripts/install.sh -o install.sh
sh install.sh
```
-->

上游向导目前使用俄语提示，本指南将选项含义说明为中文：

- 新服务器：选择“安装新的 remnawave-minishop 并从其他机器人迁移数据”。
- Compose 目录和 `.env` 已就绪：选择“迁移到已安装的 remnawave-minishop”。

同机发现 Remnashop 时，向导默认推荐该来源，并预填发现的参数。

独立服务器选择默认 `Caddy HTTPS` 配置，自动申请证书。同机面板已由 [eGamesAPI/remnawave-reverse-proxy](https://github.com/eGamesAPI/remnawave-reverse-proxy) 安装时，选择“已由 eGames 安装 Remnawave，使用其 Nginx／TLS”。该模式使用无代理 Compose，设置 `DEPLOYMENT_PROFILE=egames`，向发现的 eGames `nginx.conf` 加入 backend／webhook 与 Mini App 的服务器配置。迁移后先 `nginx -t`，再重载或重启容器，避免 frontend 仍指向旧上游。

<a id="что-переносится"></a>

## 导入范围

- Telegram、纯邮箱账号、用户名、已验证邮箱、Google／Yandex／VK OAuth 身份、面板 UUID 和个人资料元数据。
- 旧邀请代码与关系。
- 当前 `points` 余额，作为用户余额期初记录。
- 订阅、期限、流量、HWID／设备限额、面板订阅 UUID、受管理节点组，以及个别 internal／external 节点组覆盖。
- 付款与状态。
- 源数据库存在对应表时，导入增加订阅天数或普通流量的激活码及使用记录。
- `ad_links` 广告链接与用户首次归因。
- 支持重复 `merge` 的迁移映射。
- 后台 Remnashop 兼容设置：旧邀请链接和激活码。

没有直接对应的数据，作为备注保存在迁移辅助表或消息日志，供管理员后续核对。邀请关系仍为普通推荐，不创建合作伙伴资料或申请。

不复制 Remnashop 密码，其哈希不视为兼容契约。已验证邮箱和 OAuth 身份用于映射已有账号；纯邮箱用户获得稳定技术 `user_id`。

<a id="валюта-баланса"></a>

### 余额币种

一个 `point` 作为 Remnashop `settings.default_currency` 的一个完整货币单位导入。RUB／USD 转为最小单位时乘以 100；Telegram Stars（`XTR`）精度为 0，不乘。导入器不累加 `referral_rewards`，因为总额已包含在 `users.points`。

试运行后，向导显示所选币种。存在非零余额时，将 `USER_BALANCE_CURRENCY` 写入 `.env` 并开启 `USER_BALANCE_ENABLED`。可通过 `REMNASHOP_BALANCE_CURRENCY` 或 `--balance-currency` 覆盖。币种无法确定，或重跑发现期初记录不一致时，阻止应用并回滚事务。

不自动导入群发历史、仅设备代码、无期限流量代码和永久个人／购买折扣，因为当前模型没有安全的直接对应；这些项目在摘要和配置计划中列出，供人工处理。

<a id="настройки-и-платежные-провайдеры"></a>

## 设置与支付渠道

提供旧 Remnashop `.env` 时，额外映射部分设置到后台覆盖项：

- `REMNAWAVE_HOST` → `PANEL_API_URL`。
- `REMNAWAVE_TOKEN` → `PANEL_API_KEY`。
- `REMNAWAVE_COOKIE` → `PANEL_API_COOKIE`。
- `REMNAWAVE_WEBHOOK_SECRET` → `PANEL_WEBHOOK_SECRET`。
- `BOT_SUPPORT_USERNAME` → `SUPPORT_LINK`。
- `APP_DEFAULT_LOCALE` → `DEFAULT_LANGUAGE`。

向导分别配置 API 和浏览器面板地址。API 使用 `REMNAWAVE_HOST`；`PANEL_PUBLIC_URL` 从已有 Minishop 配置、发现的面板公开地址或旧公开 API 地址取得。只有内部地址且未找到外部地址时，手动填写。导入器保留 API 地址用途，不从 Docker 服务内部名称推导公开地址。

不自动迁移 `BOT_MINI_APP`：Remnashop 用它控制订阅页／外部 Mini App 连接按钮，不代表其个人中心。Minishop `SUBSCRIPTION_MINI_APP_URL` 必须指向当前栈 frontend／Mini App，由向导依据 `WEBHOOK_HOST`／`MINIAPP_HOST` 或 `MINIAPP_PUBLIC_URL` 设置。

`change_me` 等占位值会跳过，避免模板密钥误入运行配置。

支付渠道读取 `payment_gateways`，支持自动映射 Telegram Stars、YooKassa、WATA、CryptoPay、Cryptomus、Heleket、PayKilla、FreeKassa、Platega。迁移开启标记、API 密钥／商户 ID 和必需技术参数，包括 YooKassa 收据邮箱／税率、FreeKassa 第二密钥／支付方式／服务器 IP、Platega 支付方式。

渠道币种及支持币种限制不自动迁移，Minishop 由套餐和 `DEFAULT_CURRENCY_SYMBOL` 控制币种。源渠道使用非标准币种时，JSON 摘要会警告；请手动检查 `CRYPTOPAY_ASSET`、`HELEKET_CURRENCY`、`HELEKET_SUPPORTED_CURRENCIES`、`PAYKILLA_CURRENCY`、`PAYKILLA_PAYMENT_CURRENCIES`、`PLATEGA_SUPPORTED_CURRENCIES`。

YooMoney、MulenPay、PayMaster、RoboKassa、UrlPay 当前无直接对应，存在时写入摘要与迁移备注，需人工或未来独立渠道实现处理。

源秘密值可能采用 `enc_...` 加密。解密需旧 `APP_CRYPT_KEY`，可向向导提供旧 `.env` 或传 `--source-env-file`。缺少或错误密钥时，跳过加密值并警告，其他数据继续导入。

成功后，向导最后“后续步骤”显示新 webhook。`egames` 还更新发现的面板 `.env` 中 `WEBHOOK_URL` 并重启面板后端。其他外部渠道须手动替换原 Remnashop URL：

- 面板 `WEBHOOK_URL`：`WEBHOOK_BASE_URL` + `/webhook/panel`。
- YooKassa HTTP 通知：`WEBHOOK_BASE_URL` + `/webhook/yookassa`。
- WATA 回调：`WEBHOOK_BASE_URL` + `/webhook/wata`。
- CryptoBot／Crypto Pay：`WEBHOOK_BASE_URL` + `/webhook/cryptopay`。
- Heleket：`WEBHOOK_BASE_URL` + `/webhook/heleket`。
- PayKilla：`WEBHOOK_BASE_URL` + `/webhook/paykilla`。
- FreeKassa 通知／结果：`WEBHOOK_BASE_URL` + `/webhook/freekassa`。
- Platega：`WEBHOOK_BASE_URL` + `/webhook/platega`。
- Telegram `WEBHOOK_BASE_URL` + `/tg/webhook` 由机器人启动时自动设置。

<a id="сценарий-wizard"></a>

## 向导流程

导入器根据 `plans`、`plan_durations`、`plan_prices` 自动生成 `TARIFFS_CONFIG_PATH`，将原套餐 ID／名称／标签／公开代码映射到 `tariff_key`。只有覆盖自动映射时才使用 `--tariff-map-json`。

1. 默认目录 `/opt/remnawave-minishop`。向导通过 GitLab Raw 下载所选 Compose 和导入脚本，不克隆仓库。常规流程不询问仓库与 ref；使用派生／开发版本时，预先设置 `MINISHOP_INSTALL_REPO`、`MINISHOP_INSTALL_REF`。
2. 自动发现 PostgreSQL、`.env`、`BOT_TOKEN`、`BOT_OWNER_ID`／`ADMIN_IDS`、`BOT_SECRET_TOKEN`、面板 API URL／密钥／cookie／webhook 密钥，并预填，回车保留。
3. 填写源 PostgreSQL DSN。默认 schema 为 `public`，常规不询问；自定义时设置 `REMNASHOP_SOURCE_SCHEMA=custom_schema`。
4. 可选提供旧 `.env`，用于解密密钥、面板、Telegram 和可迁移渠道配置。
5. 选择当前 Compose 数据库或手动目标 DSN。前者提示在 `backups/pre-remnashop-migration-*` 备份部署主文件、可用时的数据库逻辑备份和 `restore.sh`。
6. 可选提供套餐映射 JSON，如 `{"basic": "standard_month"}`。
7. 可选指定余额币种，留空使用源 `settings.default_currency`。
8. 执行不写入的试运行，显示简要摘要，完整 JSON／原输出保存至 `.installer/remnashop-dry-run-summary.json`。
9. 确认 `y` 后应用。应用问题默认 `Y`，成功试运行后按回车表示应用；输入 `n` 停止，不写入。
10. 保存正式摘要，eGames 更新面板 webhook，重启 backend／worker／frontend，必要时重载 eGames Nginx，通知管理员／日志群，并在最后显示新 webhook 地址。

源数据库同一 Docker 主机、DSN 主机为容器名（如 `remnashop-db`）时，向导在试运行前自动加入 `<COMPOSE_PROJECT_NAME>-network`，默认 `remnawave-minishop-network`。访问 Docker 外服务仍使用 `host.docker.internal` 或外部服务器地址。

<a id="ручной-запуск"></a>

## 手动运行

不使用向导时：

```bash
docker compose run --rm backend \
  python backend/scripts/import_legacy.py \
    --source-type remnashop \
    --source-dsn 'postgresql://old_user:old_password@old_host:5432/remnashop' \
    --source-schema public \
    --source-env-file /path/to/remnashop/.env \
    --balance-currency XTR \
    --dry-run
```

试运行成功后移除 `--dry-run` 重复。默认冲突模式为 `merge`，映射已有用户与付款，加入新记录。窄范围导入使用 `--only`，例如 `--only users,referrals,balances,promocodes,advertising`。
