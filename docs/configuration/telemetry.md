<a id="анонимная-телеметрия-установок"></a>

# 安装实例匿名遥测

为了了解活跃安装数量和使用中的版本，机器人可以每天发送一次匿名心跳。该功能面向自托管场景设计，可以关闭；遥测载荷不包含用户个人数据，也不参与机器人的业务处理。

<a id="что-отправляется"></a>

## 发送哪些信息

每次心跳包含一个随机安装标识和概括性的环境信息：

| 字段 | 示例 | 用途 |
| --- | --- | --- |
| `installation_id` | `f47ac10b-...`（UUIDv4） | 随机安装标识，只生成一次并保存在数据库中，不由令牌、域名或管理员 ID 推导。 |
| `app_version` | `v3.4.6+gabc1234` | 完整构建版本。 |
| `app_version_tag` | `v3.4.6` | 用于按版本汇总的发布标签。 |
| `build_provenance` | `official` / `custom` | 镜像来源。只有项目官方构建设置 `official`；本地构建和派生项目为 `custom`。 |
| `image_modified` | `false` / `true` | 便于汇总的布尔标记：官方镜像为 `false`，本地或派生构建为 `true`。 |
| `os` / `arch` | `linux` / `x86_64` | 运行平台。 |
| `python_version` | `3.12.7` | Python 运行时版本。 |
| `locale` | `zh-hans` | 默认语言。 |
| `payment_providers` | `["stars", "yookassa"]` | 已启用支付渠道的标识，不含密钥。 |
| `users_bucket` | `51-200` | 用户数量所在区间，不发送精确数量。 |
| `webapp_enabled` / `panel_configured` | `true` | 配置状态标记。 |

接收时间 `last_seen` 由采集端设置。“活跃安装”指最近约 48 小时内发送过心跳的不同 `installation_id`；版本分布按每个安装的最近一次版本计算。

<a id="чего-там-нет"></a>

## 不发送哪些信息

载荷不发送机器人令牌、域名、webhook URL、支付系统或 Remnawave 密钥、用户 ID 或用户资料、精确用户数量、内容、镜像仓库地址或派生仓库 URL。

<a id="как-выключить"></a>

## 关闭方式

任选一种方式：

- **`.env`：**设置 `TELEMETRY_ENABLED=False`，然后重启。
- **网页后台：**进入“管理 → 系统 → 安装匿名统计”。开关在每次调度时从数据库读取，无需重启。
- **构建或镜像：**将 `TELEMETRY_ENDPOINT` 或 `TELEMETRY_API_KEY` 留空。没有接收地址或项目密钥时，不启动发送。

<a id="доставка"></a>

## 发送行为

心跳以 PostHog 格式向 `POST {TELEMETRY_ENDPOINT}/capture/` 发送 `{api_key, event, distinct_id, properties}`。发送不等待业务确认，超时为 10 秒；错误仅记入 `debug` 日志，不因遥测失败而中断 worker。存在多个 worker 副本时，每个间隔只由一个副本通过 Redis 锁发送。

<a id="переменные-окружения"></a>

## 环境变量

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `TELEMETRY_ENABLED` | `True` | 总开关，默认启用；也可在后台关闭。 |
| `TELEMETRY_ENDPOINT` | `https://eu.i.posthog.com` | PostHog 接收地址，留空即关闭。 |
| `TELEMETRY_API_KEY` | 空 | PostHog 项目写入密钥（`phc_...`），仅用于接收事件，不是读取数据或管理项目的密钥。留空即关闭。 |
| `TELEMETRY_INTERVAL_HOURS` | `24` | 心跳发送间隔，单位为小时。 |
