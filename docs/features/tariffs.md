# 套餐配置

<a id="настройка-тарифов"></a>

机器人支持两种销售配置方式：

- `TARIFFS_CONFIG_PATH` 指定的 JSON 套餐目录，默认 `data/tariffs.json`。
- JSON 文件不存在时，使用 `.env` 变量配置。

> 本页保留 Minishop 上游套餐、支付、试用和营销流程，不表示本项目 MVP 已启用这些能力。当前项目采用一个账号管理多个独立服务、管理员手动激活及无支付。项目独立服务的计量与切换规则以[额度与计量契约](../development/entitlement-metering-contract.md)为准；本页不是生产节点、限流断连或真实出口的验收证据。

<!-- GitHub 源文件链接（未启用）：[data/tariffs.example.json](https://github.com/3252a8/remnawave-minishop/blob/main/data/tariffs.example.json) -->
JSON 目录可包含多种模式的套餐：按时长订阅、无到期时间的流量包、不同 Internal Squads、设备上限和加购包。格式示例见 [data/tariffs.example.json](https://gitlab.com/3252a8/remnawave-minishop/-/blob/main/data/tariffs.example.json)。

Docker 中，`TARIFFS_CONFIG_PATH` 通常指向 `/app/data` 内文件，`migrate`、`backend` 和 `worker` 都必须可访问该目录。迁移器为没有 `tariff_key` 的现有有效订阅绑定默认套餐、填充套餐限额时，也会读取目录。标准 Compose 已配置：根目录方案为三个服务共用 `shop-data:/app/data`，生产示例共用 `./data:/app/data`。具体绑定条件见文末的安全核对规则。

模式概览：

- `period`：按时长订阅，带周期流量限额、可配置重置策略，以及可选的限额外 GB 加购。
- `traffic`：没有用户可见到期时间的 GB 套餐包，重复购买将流量加到当前余额。
- 高级 squad：任意套餐内附加的 Internal Squads，拥有独立名称、计量器、可配置额度周期和独立加购包。

## 通过管理后台配置

<a id="управление-через-админку"></a>

Web App 管理后台的**系统 → 套餐**可编辑目录。后台读取并保存 `TARIFFS_CONFIG_PATH`，通过与机器人相同的 `TariffsConfig` 模型验证，仅验证成功后才原子覆盖 JSON。

界面支持：

- 添加、编辑和删除套餐。
- 开启或关闭套餐在商店中的显示。
- 选择默认套餐。
- 配置按时长套餐（`period`）：基础限额、重置策略、周期、支付币种／Stars 价格、邀请奖励和流量加购包。
- 配置按流量套餐（`traffic`）：GB 套餐包、支付币种／Stars 价格和换算比例。
- 从 Remnawave 列表选择基础 Internal Squads。
- 配置高级区域：RU/EN 名称、高级 Internal Squads、限额／不限量、独立重置策略，以及支付币种／Stars 的高级流量加购包。
- 配置基础 HWID 上限和设备加购包。
- 独立配置下单时设备、普通流量及高级流量滑块的开关、步长、最大值和价格。

可通过拖动行调整销售选项顺序，适用于订阅周期、流量包、普通流量加购、高级加购及 HWID 包。顺序保存到 JSON，供 Web App 和 Telegram 机器人使用。

套餐配置在请求时从 JSON 加载，因此保存后立即作用于新的 Web App 请求。已有订阅保留自己的 `tariff_key`；删除或禁用套餐时，应检查引用该键的有效订阅是否仍需要续订或切换。

权限、设置保存和页面列表详见[管理后台](admin-panel.md)。

## 模式选择

<a id="как-выбирается-режим"></a>

`TARIFFS_CONFIG_PATH` 文件存在且验证通过时，使用套餐目录。此时 `.env` 中的 `TRAFFIC_PACKAGES` 和订阅价格不参与商店展示，价格和套餐包均从 JSON 读取。

JSON 文件不存在时，机器人使用 `.env`：

- `RUB_PRICE_*`、`STARS_PRICE_*` 和 `*_MONTHS_ENABLED` 配置按时长订阅。
- `TRAFFIC_PACKAGES` 和 `STARS_TRAFFIC_PACKAGES` 配置流量包销售。
- `USER_TRAFFIC_LIMIT_GB`、`USER_TRAFFIC_STRATEGY`、`USER_SQUAD_UUIDS`、`USER_HWID_DEVICE_LIMIT` 配置 Remnawave 用户。

无 JSON 目录时，只要存在 `TRAFFIC_PACKAGES` 或 `STARS_TRAFFIC_PACKAGES`，商店就改为销售流量，而非按时长订阅。

## 目录币种与渠道限制

<a id="валюта-каталога-и-ограничения-провайдеров"></a>

JSON 目录支持 `default_currency`，默认 `rub`，因此已有 `prices_rub`、`rub` 套餐包及 `.env` 价格保持兼容。其他币种使用小写代码，例如 `usd`、`eur` 或 `usdt`，并在通用字段中设置价格：

- `prices`：`{ "usd": { "1": 4.99, "3": 12.99 } }`。
- `traffic_packages`、`topup_packages`、`premium_topup_packages`、`hwid_device_packages`：用币种键替代 `rub`，例如 `{ "usd": [{ "gb": 50, "price": 2.5 }] }`。
- `conversion_rate_per_gb`：所选币种的已付价值兑换为 GB 的比例。

旧字段保留为别名：`prices_rub`、`conversion_rate_rub_per_gb` 和 `rub` 键自动映射到通用模型。Telegram Stars 仍为独立币种 `stars`/`XTR`，不能作为 `default_currency`。上述价格键按目录版本解释：旧版为月数，v2 为天数。

支付渠道对币种的支持不同。当前目录币种不被渠道支持时，机器人过滤该支付方式，并阻止创建付款：

| 渠道 | 默认币种 |
| --- | --- |
| YooKassa | `RUB` |
| WATA | `RUB`、`USD`、`EUR` |
| FreeKassa | `RUB`、`USD`、`EUR`、`UAH`、`KZT` |
| CryptoPay | 法币：`USD`、`EUR`、`RUB`、`BYN`、`UAH`、`GBP`、`CNY`、`KZT`、`UZS`、`GEL`、`TRY`、`AMD`、`THB`、`INR`、`BRL`、`IDR`、`AZN`、`AED`、`PLN`、`ILS`；加密货币：`USDT`、`TON`、`BTC`、`ETH`、`LTC`、`BNB`、`TRX`、`USDC` |
| Heleket | 可配置列表 `HELEKET_SUPPORTED_CURRENCIES`。 |
| OxaPay | 不做本地过滤，法币／加密货币账单币种由 OxaPay 按具体商户账号验证。 |
| Platega | 可配置列表 `PLATEGA_SUPPORTED_CURRENCIES`。 |
| RollyPay | `RUB`；境外银行卡按钮还支持 `EUR`；周期性 SBP 订阅只支持 `RUB`。 |
| SeverPay | 可配置列表 `SEVERPAY_SUPPORTED_CURRENCIES`。 |
| LAVA | `RUB` |
| Pally | `RUB`、`USD`、`EUR` |
| Stripe | 默认不做本地过滤，可按 Stripe 账号通过 `STRIPE_SUPPORTED_CURRENCIES` 限制。 |
| Telegram Stars | `XTR`，使用独立 Stars 价格。 |

后台**系统 → 套餐**显示当前支付币种和渠道矩阵，包括方式是否启用、服务是否配置及所选币种下是否可用。Platega、SeverPay 和 Heleket 的币种列表应与商户条件一致。RollyPay 仅境外银行卡按钮支持 `EUR`。

## 以天数表示订阅时长

<a id="срок-подписки-в-днях"></a>

v2 目录设置 `schema_version: 2` 和 `period_unit: "day"`。
`enabled_periods`、周期价格、邀请奖励表和设备周期价格的键均为正整数天数。
例如 7、30、45、360、365 是五种不同方案。编辑器接受任意天数，并显示相应名称。

365 的倍数显示为年，否则 30 的倍数显示为月，其余显示为天。
因此 365 天显示“1 年”、730 天“2 年”、360 天“12 个月”、366 天“366 天”。
一年始终等于 365 天，包括闰年。名称只是固定时长的显示方式，实际增加 UTC 天数而非日历月。
付款前显示精确时长、奖励天数及预计到期日期，方案仍可拖动排序。

无版本号的目录按 v1（月）读取，按 `(months // 12) * 365 + (months % 12) * 30`
自动转换：1 → 30、12 → 365、13 → 395、24 → 730。
首次保存旧文件时，在旁边创建不可变 `.v1.bak` 副本。
重复读取或保存 v2 不会再次换算天数，旧编辑器不能用月份格式覆盖已保存的 v2 目录。

价格和邀请奖励的**数值**保留，只改时长键。试用、欢迎礼品、优惠奖励天数和邀请奖励天数
不乘以 30。旧年度附加项保留完整价格和 `addon_period_factors`（例如 `"365": 12`），
防止原来的 12 个月单价变成 365/30 份单价。
新时长没有覆盖系数时，采用每 30 天价格 × `duration_days / 30`。
`monthly_gb` 及 `MONTH`、`MONTH_ROLLING`、`DAY`、`WEEK`、`NO_RESET`
描述额度更新方式，不随访问时长变化。

升级不改变已有订阅日期。此前已创建的日历账单按旧周期履行，新订单创建时固定天数。
新账单还固定套餐参数和邀请奖励天数，创建后修改或删除目录不改变其条件。
编辑器禁用某周期时，保留其非活跃价格和外部绑定。
新本地自动扣款使用已保存的精确周期；方案删除或禁用后不创建新扣款。
已开始的重试周期继续使用保存快照，奖励天数不成为下一次扣款的周期。

外部订阅的日历月或年不能自动等同于 30/365 天。
当前外部周期性 Tribute、Platega SBP subscription 和 RollyPay recurring 适配器
不支持新的固定天数订单，应使用可用的一次性支付。
已有扣款授权和 webhook 的权威日期继续有效。

## JSON 目录结构

<a id="структура-json-каталога"></a>

最小结构（语言示例值保持其原语言）：

```json
{
  "default_tariff": "standard",
  "referral_welcome_bonus_tariff": "standard",
  "default_currency": "rub",
  "tariffs": [
    {
      "key": "standard",
      "names": {
        "ru": "Стандарт",
        "en": "Standard"
      },
      "descriptions": {
        "ru": "Базовый набор серверов"
      },
      "premium_names": {
        "ru": "Premium-серверы",
        "en": "Premium servers"
      },
      "squad_uuids": [
        "uuid-1"
      ],
      "premium_squad_uuids": [
        "premium-uuid-1"
      ],
      "billing_model": "period",
      "monthly_gb": 500,
      "traffic_limit_strategy": "MONTH",
      "flexible_traffic_limit": {
        "step_gb": 100,
        "max_total_gb": 1000,
        "price_per_step": 79,
        "stars_price_per_step": 40
      },
      "premium_monthly_gb": 50,
      "premium_traffic_limit_strategy": "MONTH",
      "premium_flexible_traffic_limit": {
        "step_gb": 25,
        "max_total_gb": 150,
        "price_per_step": 129,
        "stars_price_per_step": 65
      },
      "prices_rub": {
        "30": 200,
        "90": 600
      },
      "referral_bonus_days_inviter": {
        "30": 3,
        "90": 7
      },
      "referral_bonus_days_referee": {
        "30": 1,
        "90": 3
      },
      "enabled_periods": [
        30,
        90
      ],
      "hwid_device_limit": 5,
      "topup_packages": {
        "rub": [
          {
            "gb": 10,
            "price": 99
          }
        ],
        "stars": [
          {
            "gb": 10,
            "price": 2500
          }
        ]
      },
      "hwid_device_packages": {
        "rub": [
          {
            "count": 1,
            "price": 99,
            "prices": {
              "30": 99,
              "90": 249
            },
            "min_price": 20,
            "traffic_bonus_gb": 15,
            "period_unit": "day"
          }
        ],
        "stars": [
          {
            "count": 1,
            "price": 50,
            "prices": {
              "30": 50,
              "90": 130
            },
            "traffic_bonus_gb": 15,
            "period_unit": "day"
          }
        ]
      },
      "checkout_addons": {
        "devices": {
          "enabled": true,
          "max_extra_devices": 5,
          "price_per_device": 79,
          "stars_price_per_device": 40
        },
        "traffic": {
          "enabled": true
        },
        "premium_traffic": {
          "enabled": true
        }
      },
      "enabled": true,
      "period_unit": "day",
      "addon_period_factors": {
        "30": 1,
        "90": 3
      }
    }
  ],
  "schema_version": 2,
  "period_unit": "day"
}
```

主要字段：

| 字段 | 用途 |
| --- | --- |
| `default_tariff` | 首次选择及为没有 `tariff_key` 的有效订阅绑定时使用的默认套餐。 |
| `referral_welcome_bonus_tariff` | 被邀请用户欢迎订阅使用的可选 period 套餐，必须引用已启用的 period 套餐；未设置时使用 `default_tariff`。流量限额、Internal Squads、重置策略和设备上限继承该套餐。 |
| `default_currency` | JSON 目录默认价格币种，默认 `rub`；禁止 `stars`，Stars 使用独立价格。 |
| `tariffs[].key` | 稳定套餐键，用于支付、订阅和套餐切换。 |
| `tariffs[].legacy_keys` | 该套餐的旧键，让重命名后仍可处理已保存付款和订阅。每个旧键必须在整个目录中唯一。 |
| `tariffs[].names` | 按语言划分的套餐名称。 |
| `tariffs[].descriptions` | 按语言划分的套餐说明。 |
| `tariffs[].enabled` | 是否在公开商店可见。隐藏套餐（`false`）可由后台指定，或通过 `access_code` 私有链接开放首次购买；已指定套餐仍可供该用户续订。切换后不再提供原隐藏套餐。选项数量按可见套餐加当前已指定隐藏套餐计算，因此仅有一个可见套餐时，普通用户直接进入其条件页。 |
| `tariffs[].access_code` | 隐藏套餐的可选私有码，必须为全目录唯一的 32 位十六进制字符。后台以密码学安全随机源生成，并创建 `/checkout/<access_code>` URL。启用套餐禁止此字段。删除或重建代码立即撤销旧链接，套餐仍不出现在商店和切换列表。 |
| `tariffs[].squad_uuids` | 套餐用户使用的 Remnawave Internal Squads。 |
| `tariffs[].premium_names` | 按语言划分的高级区域名称，用于限额卡片、高级加购弹窗及预警。未设置时，俄语／英语默认值分别为 `Premium-серверы` / `Premium servers`。 |
| `tariffs[].premium_squad_uuids` | 具有独立高级限额的 Internal Squads。计量节点通过面板 API 自动取自这些 squad 的可访问节点。 |
| `tariffs[].premium_monthly_gb` | 每个高级周期的独立流量限额。字段名为兼容保留，周期频率由 `premium_traffic_limit_strategy` 决定。`0` 或缺省表示基础额度为零，只有加购或发放额外高级流量后才可访问高级 squad。 |
| `tariffs[].premium_unlimited` | 显式启用高级 squad 无限量访问，默认 `false`；设为 `true` 时忽略 `premium_monthly_gb`。 |
| `tariffs[].premium_traffic_limit_strategy` | 可选的独立高级计量策略：`NO_RESET`、`DAY`、`WEEK`、`MONTH`、`MONTH_ROLLING`（从订阅开始计算的月周期）。缺省继承普通流量的实际策略。 |
| `tariffs[].premium_topup_packages` | 高级加购包，格式为 `{ "rub": [{ "gb": 10, "price": 99 }], "stars": [...] }`，要求 `premium_squad_uuids`。行顺序决定商店顺序，可在后台拖动调整。 |
| `tariffs[].premium_flexible_traffic_limit` | 灵活高级限额参数：`step_gb`、`max_total_gb`、月单价 `price_per_step` 和 `stars_price_per_step`。与高级计量器一同重置，不增加可结转加购余额。要求 `premium_squad_uuids`。 |
| `tariffs[].premium_topup_always_available` | 不论高级流量使用比例始终显示加购，默认 `false`，达到高级限额 80% 后才显示；见[加购显示条件](#когда-показывается-докупка-трафика)。 |
| `tariffs[].billing_model` | 套餐模式：`period` 或 `traffic`。 |
| `tariffs[].hwid_device_limit` | 基础 HWID 设备上限，`0` 表示不限；缺省使用 `USER_HWID_DEVICE_LIMIT`。 |
| `tariffs[].hwid_device_packages` | 设备加购包。`traffic_bonus_gb` 是整个包每月赠送流量，默认 `0`，同一行各币种必须一致。`price` 为 30 天单价，`prices` 为套餐按天周期（`"30"`、`"90"`、`"180"`、`"365"`）的完整价格，`min_price` 是按比例加购的最低价格。行顺序决定 HWID 加购顺序，可在后台拖动调整。 |
| `tariffs[].flexible_traffic_limit` | 普通流量灵活限额：滑块步长 `step_gb`、最终最大值 `max_total_gb`、每步月单价 `price_per_step` 和可选 `stars_price_per_step`。与不过期的 `topup_packages` 是不同模式。 |
| `tariffs[].checkout_addons` | period 套餐下单时加购设置。`devices` 使用 `enabled`、额外设备上限 `max_extra_devices` 和每设备月单价 `price_per_device`/`stars_price_per_device`。`traffic`/`premium_traffic` 在此只存 `enabled` 开关，步长、最大值和价格来自对应灵活限额。 |

## 下单时加购

<a id="докупки-при-оформлении-подписки"></a>

period 套餐下单时，可在创建付款前调整设备最终数量及普通／高级流量周期限额。
这与购买后的不过期加购是不同模式：

| 资源 | 最小值 | 设置与显示条件 | 订阅获得的权益 |
| --- | --- | --- | --- |
| 设备 | 实际基础 HWID 上限 | `MY_DEVICES_SECTION_ENABLED=True`、有限且为正的基础上限、`checkout_addons.devices.enabled`、`max_extra_devices`、`price_per_device`；步长固定 `1`。 | 付费时长内的临时额外设备。下单载荷的 `device_count` 是基础数量**之外**的设备数。 |
| 普通流量 | `monthly_gb` | 有限正数基础额度、`checkout_addons.traffic.enabled` 及有效 `flexible_traffic_limit`。 | 每次重置周期选择的**最终**限额 `regular_limit_gb`。 |
| 高级流量 | `premium_monthly_gb`，允许 `0` | 高级 squad、`premium_unlimited=false`、`checkout_addons.premium_traffic.enabled` 和有效 `premium_flexible_traffic_limit`。 | 每个高级周期选择的**最终**限额 `premium_limit_gb`。 |

`flexible_traffic_limit` 和 `premium_flexible_traffic_limit` 包含：

- `step_gb`：每个等距步长的容量。
- `max_total_gb`：最终最大值，必须等于基础额度加整数个步长。
- `price_per_step`：每 30 个付费日的每步价格，以 `default_currency` 计价。
- `stars_price_per_step`：可选的每 30 天每步整数 ⭐ Stars 价格。

例如基础 `100 GB`、步长 `50 GB`、最大 `300 GB`，产生 `100/150/200/250/300 GB` 刻度。
选择 `250 GB` 时，付费步数为 `(250 - 100) / 50 = 3`。
`D` 天价格为 `3 × price_per_step × addon_period_factor(D)`，系数默认 `D / 30`。
额度重置频率不改变价格单位：`DAY`、`WEEK`、`MONTH`、`MONTH_ROLLING` 甚至 `NO_RESET`
仍按订阅付费天数计算补价。最大值很大时不要设置过小步长，因为每个刻度都会成为 API 和界面中的独立选项。

设备采用同一线性公式，步长为 `1`：`额外设备数 × price_per_device × addon_period_factor(D)`。
某资源 Stars 价格缺失或为零时，Stars 付款不提供该资源的扩展刻度。
目录币种允许零价，对应步长免费。

`topup_packages`、`premium_topup_packages` 和 `hwid_device_packages` 不参与这些滑块。
它们仍为购买后的独立流程：流量包增加可结转、可消耗余额，HWID 包有自己的价格、
有效期和可选 `traffic_bonus_gb`。

### 续订与有效权益调整

<a id="продление-и-изменение-активных-прав"></a>

| 场景 | 计算与结果 |
| --- | --- |
| 首次购买 | 基础周期价格，加所选资源整个时长的完整价格。 |
| 提前续订同一套餐 | 新时长全额付费，所选方案比已付费有效方案增加的正差额，再按当前剩余窗口比例付费。计算以 30 天作为月价格单位。 |
| 降低限额 | 当前剩余时长不退款，较低值从新的付费窗口边界生效。因此即使补价为零，快照仍可能保留基础选择。 |
| 多次提前续订 | backend 将流量剩余时长分成已付费窗口，每个窗口只计算正差额。重叠的更高限额不会被更低值覆盖。 |
| 已安排未来 HWID 窗口 | 新的额外设备下单被视为计划冲突而拒绝，防止重叠权益重复累加。 |
| 当前为其他有效套餐 | 普通续订返回 `tariff_switch_required`，使用独立套餐切换及其兑换／补价规则。 |

有效灵活限额以时间窗口保存在 `flexible_traffic_limits`。
套餐 worker 应用同类资源当前有效的最高限额，最后一个窗口结束后恢复当前套餐基础额度。
自动续订将订阅边界时有效的方案及其固定月单价延续到下个时长。
可结转加购余额不会重新购买，也不会清零。

### 报价、优惠码与付款快照

<a id="котировка-промокод-и-платёжный-снимок"></a>

滑块移动时，Mini App 在本地更新周期卡片和付款按钮价格，不为每个指针事件请求服务器。
操作结束后，`POST /api/subscription/quote` 返回权威报价，创建付款时再次完整重算购物车。
请求中的 `regular_limit_gb` 和 `premium_limit_gb` 是最终限额，`device_count` 仅为额外设备数。

优惠码百分比折扣作用于完整小计：基础订阅、新时长资源价格和立即提高权益的按比例补价。
折扣后再结合伙伴余额计算外部付款部分。Stars 使用同一规则，正数最终金额不能低于 `1` Star。

v2 `Payment.checkout_bundle_snapshot` 保存套餐、有效订阅边界、周期、基础价格、所选最终限额
及价格组成；`checkout_bundle_hash` 用于安全复用 pending 付款。
激活前订阅 ID 或到期时间改变时，快照视为过期，不重复发放权益。
创建账单后编辑目录不会改变已固定的交付内容。

外部定价或自主管理周期订阅的渠道可能不支持首笔付款附加项。
此类方式下滑块不可用，但仍可不带附加项购买基础订阅。
backend 在报价和创建付款时重复检查。

套餐重命名时，将旧 `key` 移到 `legacy_keys`，不要直接移除。
付款和订阅保存创建时的套餐键；后续激活通过别名解析旧键，再使用当前规范 `key`。
当前键不能同时出现在 `legacy_keys` 中，同一旧键也不能分配给多个套餐。

别名解析和验证位于 [`TariffsConfig`](../../backend/config/tariffs_config.py)，
[`activate_subscription`](../../backend/bot/services/subscription_service_impl/lifecycle_activation.py)
在处理付款前规范化已保存键。回归用例见 [`test_tariffs_config.py`](../../tests/unit/test_tariffs_config.py)。

`period` 套餐还使用以下字段；周期键在 v1 中为月数，在 v2 中为天数：

| 字段 | 用途 |
| --- | --- |
| `monthly_gb` | 每个 `traffic_limit_strategy` 周期的基础流量限额，字段名为兼容保留；`0` 表示不限。 |
| `traffic_limit_strategy` | Remnawave 流量重置策略：`NO_RESET`、`DAY`、`WEEK`、`MONTH`、`MONTH_ROLLING`（从订阅开始计算的月周期）；缺省使用旧配置 `USER_TRAFFIC_STRATEGY`。 |
| `prices` | 按币种划分的通用周期价格，例如 `{ "usd": { "1": 4.99 } }`。 |
| `prices_rub` | 旧版 RUB 周期价格字段，等价于 `prices.rub`，键按目录版本解释。 |
| `prices_stars` | Telegram Stars 周期价格。 |
| `referral_bonus_days_inviter` | 各周期给邀请人的奖励天数，键与 `enabled_periods` 使用同一时长单位。 |
| `referral_bonus_days_referee` | 各周期给被邀请人的奖励天数，键与 `enabled_periods` 使用同一时长单位。 |
| `enabled_periods` | 可购买周期。数组顺序决定 Telegram 和 Web App 商店的显示顺序，可在后台拖动周期行调整。 |
| `tribute` | 可选 Creator 备用配置：订阅使用 `link`、`subscription_id`、`period_ids`，固定 Digital Products 使用 `traffic_products`/`premium_traffic_products`。主 Shop API 模式采用本地金额，不要求这些字段；见 [Tribute 配置](payments.md#tribute)。 |
| `topup_packages` | 当前套餐的流量加购包。未设置或列表为空时，Web App 和 Telegram 不显示加购。行顺序决定商店顺序，可在后台拖动。 |
| `flexible_traffic_limit` | 下单／续订滑块的步长、最终最大值及每步月单价。所选限额按 `traffic_limit_strategy` 重置。 |
| `topup_always_available` | 不论使用比例始终显示流量加购，默认 `false`，消耗达到限额 80% 时才显示；见[加购显示条件](#когда-показывается-докупка-трафика)。 |

`traffic` 套餐使用：

| 字段 | 用途 |
| --- | --- |
| `traffic_packages` | 按目录币种及 Telegram Stars 划分的 GB 流量包。列表顺序决定 Telegram 和 Web App 商店顺序：先显示目录币种包，再显示仅 Stars 可用的包，可在后台拖动调整。 |
| `conversion_rate_per_gb` | 切换到流量套餐时，以目录币种将 period 套餐剩余天数换算为 GB 的比例。 |
| `conversion_rate_rub_per_gb` | RUB 目录的旧版别名。 |
| `tribute` | 流量包可选 Creator 备用配置：`traffic_products` 将容量映射到固定 `product_id` 及 Digital Product HTTPS 链接。启用 Shop API 时，常规购买按本地金额创建动态订单。 |

流量套餐没有 `default_currency` 对应套餐包时，必须设置 `conversion_rate_per_gb`。

## 按时长套餐（`period`）

<a id="тарифы-на-срок-period"></a>

`period` 销售指定时长的访问权限，带按配置策略更新的流量限额。

购买或续订时：

- 现有订阅仍有效时，使用其当前开始日期，否则使用当前时间。
- 新固定天数订单增加精确天数；保留的旧日历订单通过 `add_months` 计算日历月，适用范围见前文“以天数表示订阅时长”。
- 优惠码可向计算后的时长添加奖励天数。
- `tier_baseline_bytes` 取 `monthly_gb` 对应值。
- 从当前有效订阅保留 `topup_balance_bytes`。
- `traffic_limit_bytes` 为 `tier_baseline_bytes + topup_balance_bytes`。
- 向 Remnawave 发送套餐的 `trafficLimitStrategy`，缺省回退 `USER_TRAFFIC_STRATEGY`。
- 向 Remnawave 发送套餐的 Internal Squads。
- 向 Remnawave 发送套餐实际 HWID 上限。

Core 还从规范 `tariff_key` 生成 Remnawave 用户 `tag`，遵循面板限制：
仅 `A-Z`、数字及 `_`，不超过 16 字符。过长或具有相同可读形式的键添加稳定哈希后缀。
激活、续订及切换后，单独读取面板确认结果。后台核对为已有有效订阅补充标签，
在订阅到期、变为试用或指向未知／已删除套餐时，移除此前管理的套餐标签。
由规范键和 `legacy_keys` 生成的值属于 Core 保留标签。
操作员或外部系统在 Remnawave 手动设置的任意非空标签不会被覆盖；
冲突时 Core 保留原所有者的标签，并记录警告。

`traffic_limit_strategy` 按 period 套餐独立设置，新建 Remnawave 用户时的 CREATE，以及激活、续订和切换时都会应用。旧 `tariffs.json` 缺少该字段时，保留 `USER_TRAFFIC_STRATEGY` 的原行为，编辑器显示继承模式，直到管理员明确选择。`NO_RESET` 不做日历重置；`DAY`、`WEEK`、`MONTH` 和 `MONTH_ROLLING` 指定对应周期。traffic 套餐禁止该字段，普通流量包始终使用 `NO_RESET`。

编辑器将 `MONTH_ROLLING` 显示为**“从订阅开始计算的月周期”**。它不同于从每月一日开始的 `MONTH`，而是绑定订阅开始日期：

| 策略 | 周期边界 | 普通计量器的维护方 |
| --- | --- | --- |
| `NO_RESET` | 不重置 | Remnawave |
| `DAY` | 每日开始 | Remnawave |
| `WEEK` | 每周开始 | Remnawave |
| `MONTH` | 日历月第一天 | Remnawave |
| `MONTH_ROLLING` | 从订阅开始日期起每个日历月 | Remnawave，实际当前边界通过 `lastTrafficResetAt` 返回。 |

Core 只向 Remnawave 传递 `trafficLimitStrategy`，普通计量器的实际重置由面板控制。因此已有用户仍以面板返回的 `lastTrafficResetAt` 为权威；单纯改变策略不会清除已计流量。本地 `period_start_at` 是供预警使用的当前周期缓存，不是独立计量器或可配置基准。

用户详情显示 Remnawave 的实际策略，手动用户级覆盖可立即看见。后台同步不会用套餐值替换该覆盖；下一次权益变更（激活、续订或套餐切换）会重新应用当前套餐策略。

period 套餐流量加购增加 `topup_balance_bytes` 和总 `traffic_limit_bytes`。余额保存在订阅中，续订时继续计入。向面板发送最新限额，并将访问状态设为 `ACTIVE`。

## 何时显示流量加购

<a id="когда-показывается-докупка-трафика"></a>

购买订阅后不会立即显示加购，默认消耗达到相应限额的 **80%** 才解锁。Web App 和 Telegram 使用同一规则：未解锁时隐藏机器人菜单的加购按钮，点击旧按钮会提示剩余流量并刷新菜单。

- 普通和高级流量**独立**解锁，分别计算自己的已用比例。
- `topup_always_available` 和 `premium_topup_always_available` 分别取消普通／高级流量阈值，对应套餐编辑器“流量”和“高级流量”标签的**“始终允许加购”**。
- `traffic` 套餐不适用阈值，流量包本身就是商品，始终可加购。
- 限额为无限量（`0`）或订阅启用无限量覆盖时，不提供加购。

## 高级 squad 与独立限额

<a id="premium-сквады-и-отдельный-лимит"></a>

套餐可包含具有独立流量限额的附加 Internal Squads，适用于普通服务器权限保持不变、高级服务器单独限额的场景。

```json
{
  "billing_model": "period",
  "monthly_gb": 0,
  "traffic_limit_strategy": "NO_RESET",
  "squad_uuids": ["standard-squad-uuid"],
  "premium_names": { "ru": "Premium-серверы", "en": "Premium servers" },
  "premium_squad_uuids": ["premium-squad-uuid"],
  "premium_monthly_gb": 32,
  "premium_traffic_limit_strategy": "MONTH",
  "premium_topup_packages": {
    "rub": [{ "gb": 10, "price": 99 }],
    "stars": [{ "gb": 10, "price": 2500 }]
  }
}
```

规则：

- 普通套餐限额继续通过 Remnawave `trafficLimitBytes` 生效。
- 高级流量按 `premium_squad_uuids` 可访问节点独立计量。Remnawave 3.x 使用一次 `POST /api/bandwidth-stats/nodes/usage` 获取全部节点；2.8.1 使用兼容聚合接口 `POST /api/bandwidth-stats/nodes/users`。逐节点查询仅用于备用处理，或定位限制后仍持续的流量。
- 套餐不保存节点 UUID 列表，机器人向 Remnawave 查询每个高级 squad 的可访问节点并缓存。
- 聚合统计快照最多复用 115 秒，短于 Remnawave 约两分钟的聚合间隔，避免频繁高级检查重复发起结果相同的高开销请求。
- 高级限额未耗尽时，用户拥有 `squad_uuids + premium_squad_uuids`。
- 同一套餐的 `squad_uuids` 与 `premium_squad_uuids` 不得包含相同 UUID，否则高级额度耗尽后该 squad 仍留在基础权限中。backend 和编辑器均拒绝此冲突。
- 高级额度耗尽时，只移除高级 squad，保留普通访问。最终非空 squad 集合相同的变更合并为 `POST /api/users/bulk/update-squads`，每次最多 500 用户；选择器从 2.8.1 的 `uuids` 自动切换到 3.x 的 `userIds`。最终集合为空时，使用逐用户 `PATCH /api/users`，因为 Remnawave 3.0.0 通过批量接口删除最后一个 squad 会返回 `A088/500`。不支持批量接口的面板也使用该已验证 PATCH 备用路径。
- 高级限额检查不等待 worker 完整周期：已使用至少 `TARIFF_PREMIUM_FAST_WATCH_PERCENT` 百分比的订阅，以及所有临时受限订阅，每 `TARIFF_PREMIUM_FAST_TICK_SECONDS` 秒复查。因此检查延迟造成的超额窗口按分钟计算，而非完整 `TARIFF_WORKER_TICK_SECONDS`；这不是零超额保证。
- 某个高级节点统计缺失时，不降低当前周期高级已用量，避免不完整数据向超额用户重新开放访问。
- 移除 squad 只阻止新连接，因此限制后立即请求面板断开高级节点上已有会话。节点集合相同的用户合并为一请求：2.8.1 使用带 `userUuids` 的 `POST /api/ip-control/drop-connections`，3.x 使用带 `userIds` 的 `POST /api/connections/drop`。不影响普通访问和其他用户会话。`TARIFF_PREMIUM_DROP_CONNECTIONS` 可关闭此行为，重复请求受 `TARIFF_PREMIUM_DROP_CONNECTIONS_COOLDOWN_SECONDS` 限制。**Remnawave 节点必须具有 `CAP_NET_ADMIN`**，见下文。
- 已受限订阅的高级流量仍增长时，机器人记录含节点列表的警告，并在管理后台诊断页提示。
- 加购高级流量后，只要新限额再次高于已用量，就恢复高级 squad。
- 加购高级流量不过期：先消耗 `premium_monthly_gb`，只对超出基础高级额度的流量扣减加购余额。
- `premium_traffic_limit_strategy` 缺省或为 `null` 时，继承普通策略。period 套餐依次采用面板实际 `trafficLimitStrategy`、套餐 `traffic_limit_strategy`、`USER_TRAFFIC_STRATEGY`；traffic 套餐继承其必需的 `NO_RESET`。旧 period 套餐因此保持原行为，旧 traffic 套餐也一致继承普通包不重置的策略。
- 显式设置 `premium_traffic_limit_strategy` 后，高级周期独立于普通计量器及面板用户级覆盖。例如 `monthly_gb: 0`、`traffic_limit_strategy: "NO_RESET"`、`premium_monthly_gb: 32`、`premium_traffic_limit_strategy: "MONTH"` 表示普通流量无限量且不重置，高级流量每个日历月独立提供 32 GB。
- `NO_RESET` 的高级周期从订阅 `start_date` 开始，不重置 `premium_topup_used_bytes`。`DAY`、`WEEK`、`MONTH`、`MONTH_ROLLING` 在相应边界重置高级计量器和 `premium_topup_used_bytes`，保留 `premium_topup_balance_bytes`。显式 `DAY`、`WEEK`、`MONTH` 即使刚切换策略，也立即对齐日历边界。显式 `MONTH_ROLLING` 每次从不可变 `start_date` 重新计算，不将 Remnawave 重置时间或旧 `premium_period_start_at` 用作新基准。
- `premium_period_start_at` 保存已计算的当前高级周期起点，是 `premium_used_bytes` 和 `premium_topup_used_bytes` 所属窗口的缓存，不是高级访问开通日期或独立套餐设置。
- 现有订阅切换至显式高级 `MONTH_ROLLING` 后，下次高级检查从 `start_date` 重建窗口。旧记录缺少有效 `start_date` 时，安全回退到保存的 `premium_period_start_at`；二者均无时，使用当前日历月月初。
- 月份通过 `add_months` 计算；下月没有对应日时，使用该月最后一天。高级节点统计按 `YYYY-MM-DD` 日期查询，因此边界时间戳中的时分不会在一天内缩小统计窗口。
- 试用订阅不采用套餐高级策略，仍使用 `TRIAL_TRAFFIC_STRATEGY`。

设置了 `premium_squad_uuids`，但 `premium_monthly_gb` 为空或 `0` 时，在获得正高级余额前不发放高级 squad。这可用于纯加购模式：有 `premium_topup_packages` 时，立即允许加购，无需等待使用阈值。无限量高级访问需设置 `premium_unlimited: true`。存在 `premium_topup_packages` 或正 `premium_monthly_gb` 时，必须提供 `premium_squad_uuids`。

订阅保存以下状态：

- `premium_baseline_bytes`：套餐基础高级限额。
- `premium_topup_balance_bytes`：剩余加购高级流量。
- `premium_topup_used_bytes`：当前高级周期已使用的加购部分。
- `premium_used_bytes`：当前高级周期已用总量。
- `premium_period_start_at`：`premium_used_bytes` 所属高级周期起点。
- `premium_is_limited`：高级 squad 是否临时移除。

用户 Web App 以独立卡片显示高级已用量、限额、剩余量、可结转加购余量及受独立限制的服务器／squad 列表。Telegram 的“我的订阅”显示同样区域。

普通和高级加购分别显示。普通加购使用 period 的 `topup_packages` 或 traffic 的 `traffic_packages`；高级加购只使用 `premium_topup_packages`，标记 `sale_mode=premium_topup`，标题使用 `premium_names`。

高级限额预警独立于普通流量，使用相同 `TARIFF_TRAFFIC_WARNING_LEVELS` 百分比。消息使用 `premium_names`，列出服务器／squad 并引导高级流量加购。

后台套餐编辑器的**高级流量**标签配置高级 squad 及策略。默认选择**“继承普通流量策略”**，显式值使高级重置独立。列表来自 Remnawave API（`/api/admin/panel/internal-squads`），通常无需手动复制 UUID。

### 节点要求：CAP_NET_ADMIN

<a id="требование-к-нодам-cap_net_admin"></a>

高级限额耗尽后，机器人从面板用户移除高级 squad，节点不再接受**新连接**，但 xray 不会自动断开现有会话。断开由 Remnawave 节点执行，且要求容器具有 `CAP_NET_ADMIN`；缺少此能力时无法获取用户在线 IP 列表并关闭套接字，因此限制后客户端仍可能通过旧连接下载。

可查看节点启动日志：

```bash
docker logs remnawave-node 2>&1 | grep CAP_NET_ADMIN
```

`[OK] CAP_NET_ADMIN is available` 表示能力可用；`CAP_NET_ADMIN is not available.` 表示无法断开会话。需要时在节点 `docker-compose.yml` 添加该能力并重启节点。以下为配置说明，本项目验证必须使用独立测试资源，不对现有生产节点操作：

```yaml
services:
  remnawave-node:
    image: remnawave/node:latest
    cap_add:
      - NET_ADMIN
```

受限订阅的高级流量仍增长时，机器人记录警告，并在后台诊断页显示含问题节点的提示。除缺少 `CAP_NET_ADMIN` 外，还可能是节点与面板失联（移除未下发，重连后才应用）、普通 squad 没有入站配置，或普通与高级 squad 共用入站。最后一种情况下，高级节点流量仍合法，需在面板侧将 squad 分配到不同入站。

## 按流量套餐（`traffic`）

<a id="тарифы-по-трафику-traffic"></a>

`traffic` 销售没有用户可见到期时间的流量额度。

购买时：

- 有效订阅没有更晚日期时，将 `end_date` 设为远期 `2099-01-01 UTC`。
- `duration_months = 0`。
- `period_start_at = NULL`。
- `tier_baseline_bytes = 0`。
- `topup_balance_bytes` 保存可用流量余额。
- 向 Remnawave 发送 `trafficLimitStrategy = NO_RESET`。
- 禁用该订阅的自动续订及临近到期通知。

再次购买将 GB 添加到实际余额：

```text
remaining = max(0, current_limit - current_used)
balance_after = remaining + purchased
limit_after = current_used + balance_after
```

这样用户不会损失已付费余量，Remnawave 继续以当前已用量为基础计算总限额。

对 traffic 套餐发起流量加购时，按购买该套餐的下一个流量包处理。

## HWID 设备

<a id="hwid-устройства"></a>

套餐可配置基础设备上限和加购包。以下保留旧版月份价格示例；v2 按天价格见前文完整 JSON 示例：

```json
{
  "hwid_device_limit": 5,
  "hwid_device_packages": {
    "rub": [
      {
        "count": 1,
        "price": 99,
        "prices": { "1": 99, "3": 249, "6": 449, "12": 799 },
        "min_price": 20,
        "traffic_bonus_gb": 15
      }
    ],
    "stars": [
      {
        "count": 1,
        "price": 50,
        "prices": { "1": 50, "3": 130 },
        "traffic_bonus_gb": 15
      }
    ]
  }
}
```

规则：

- 用户设备区域及所有新 HWID 账单要求 `MY_DEVICES_SECTION_ENABLED=True`。
- 用户须有有效订阅，规范 `tariff_key` 在当前目录中存在、已启用且属于 `period`。
- 套餐须有有限基础上限，并至少有一个目录币种或 Telegram Stars 正价设备包。
- Web App 和 Telegram 共用可用性检查，显示准确的禁用原因。创建账单前重新检查区域开关、当前套餐和设备包，旧按钮或回调不能绕过限制。
- `hwid_device_limit` 保存基础套餐上限。
- `extra_hwid_devices` 只保存当前有效的加购设备总数。
- 每次加购有效期保存在 `hwid_device_purchases.valid_from` / `valid_until`。
- 实际上限为 `hwid_device_limit + active extra_hwid_devices`。
- `traffic_bonus_gb` 是整个包每月增加的普通流量限额，不是每台设备的赠送量；`0` 关闭奖励。
- 奖励固定在付款及加购记录中，后续编辑套餐不改变已购买权益。
- 有效加购奖励累加，从 `valid_from` 生效，在 `valid_until` 后消失。
- 基础上限 `0` 表示不限，向 Remnawave 发送 `hwidDeviceLimit = 0`。
- 基础设备不限量时，不应用设备加购。
- 旧月份价格的完整 HWID 包价取 `prices[duration_months]`，缺省回退 `price * duration_months`；v2 使用前文按天周期价格及系数，不能将天数直接代入旧月份公式。
- 实际加购价按 `valid_from -> valid_until` 付费窗口相对订阅周期的比例计算，并固定在付款中。
- Telegram Stars 向上取整，支付币种向上取到分；`min_price` 防止周期末尾产生极小付款。
- 设备加购按钮只为当前有效订阅购买设备，且仅持续到其当前到期时间。
- 续订时提供独立的“续订已加购设备”复选框，默认勾选，按当前套餐计价并加入同一笔订阅付款。
- 续订订阅但不续订设备时，旧加购持续到自己的 `valid_until`；Web App 提示可能暂时回到基础上限。
- 管理员续期、优惠码和邀请奖励分别为订阅及有效设备加购增加固定天数，不合并各自到期时间。
- `traffic` 套餐没有订阅期限，不显示或接受 HWID 设备加购。
- 套餐切换后基础上限来自目标套餐，支付币种的未使用 HWID 加购价值换算为新 period 套餐天数或 traffic 套餐 GB。XTR/Stars 加购没有明确汇率时不兑换，继续有效至原 `valid_until`。
- 加购历史保存在 `hwid_device_purchases`。
- 付款通过 `payments.purchased_hwid_devices` 保存设备数，通过 `payments.hwid_traffic_bonus_bytes` 保存奖励快照。

Web App 通过 `/api/devices/topup-options` 和 `/api/payments` 提供设备加购，
Telegram 在设备区域提供入口。基础上限中的空闲名额（例如只用了 5 台中的 1 台）
不影响按钮显示；购买增加最大设备上限，不是解锁当前五个名额。

## 套餐切换

<a id="смена-тарифа"></a>

带有 `tariff_key` 的有效订阅可切换套餐，记录保存在 `tariff_changes`。

计算方式：

| 切换 | 行为 |
| --- | --- |
| `period -> period` | 根据旧字段 `effective_monthly_price_rub` 中保存的目录支付币种月价，评估剩余已付天数价值，再按目标月价换算为天数。支付币种中未使用的 HWID 加购价值作为额外天数加入，天数向下取整。 |
| `period -> period` 补价 | 目标套餐更贵时，可创建 `tariff_upgrade` 付款；未使用 HWID 加购的支付币种价值抵减补价。付款后应用目标套餐，并关闭已兑换的 HWID 窗口。 |
| `period -> traffic` | 剩余已付天数及支付币种中未使用的 HWID 加购价值，按 `conversion_rate_per_gb` 或目标套餐包的最低 GB 单价兑换为流量。 |
| `traffic -> period` | 用户选择并支付目标套餐周期；剩余 GB 保留为 `topup_balance_bytes`，叠加于 period 限额。 |

切换时，机器人修改：

- `tariff_key`。
- Remnawave Internal Squads。
- `trafficLimitBytes`。
- `trafficLimitStrategy`。
- 基础 HWID 上限。
- period 套餐的 `effective_monthly_price_rub`。
- traffic 套餐的 `auto_renew_enabled` 和通知。

## 支付

<a id="платежи"></a>

付款使用以下字段；名称含月份的字段为保留的兼容字段，新固定天数订单还使用按天字段，见前文按天升级规则：

| 字段 | 用途 |
| --- | --- |
| `sale_mode` | 销售类型：`subscription`、`traffic_package`、`topup`、`premium_topup`、`tariff_upgrade`、`hwid_devices`。 |
| `tariff_key` | 付款所属套餐键。 |
| `purchased_gb` | 流量包和流量加购购买的 GB 数。 |
| `purchased_hwid_devices` | HWID 加购设备数。 |
| `hwid_valid_from`, `hwid_valid_until` | 付款创建时固定的 HWID 加购有效窗口。 |
| `hwid_pricing_period_months`, `hwid_proration_ratio`, `hwid_full_price` | HWID 加购价格计算元数据：旧月份周期字段、按比例系数及周期完整包价。 |
| `subscription_duration_months` | 旧按时长订阅的月数字段，也供支付处理器保留为数字购买字段；新固定天数订单以其已保存天数为准。 |
| `checkout_bundle_snapshot`, `checkout_bundle_hash` | 下单附加项的不可变组成及其 SHA-256，用于匹配 pending 付款。 |

支付渠道回调和元数据中的 `sale_mode` 可带套餐后缀，例如 `subscription@standard` 或 `topup@standard`。激活付款时，套餐单独保存在 `tariff_key`。

## 流量预警与耗尽

<a id="предупреждения-и-исчерпание-трафика"></a>

达到 `trafficLimitBytes` 时，Remnawave 将用户设为 `LIMITED` 并限制访问。普通流量达到 100% 时，机器人不会将用户从 Internal Squads 移除。

启用 JSON 套餐目录时运行 `TariffTrafficWorker`，每 300 秒：

- 从面板同步 `status`、`trafficLimitBytes`、`usedTrafficBytes`、`trafficLimitStrategy`。
- period 套餐使用 Remnawave 的 `trafficLimitStrategy`；面板没有返回策略时，依次回退套餐策略及 `USER_TRAFFIC_STRATEGY`。
- 在 `TARIFF_TRAFFIC_WARNING_LEVELS` 指定阈值发送预警，默认 `85,90,95`。
- 通过 `traffic_warnings` 去重。

period 套餐的预警去重绑定当前周期起点，策略取自 Remnawave，缺省回退套餐及 `USER_TRAFFIC_STRATEGY`；仅实际策略非 `NO_RESET` 时发送重置通知。traffic 套餐去重考虑当前 `trafficLimitBytes`，让购买新包后可再次收到一组预警。

以前机器人运行逻辑限制的订阅（`is_throttled=True`），只有限额再次高于已用量时，worker 才恢复访问。

## 自动续订、试用与奖励

<a id="автопродление-пробный-период-и-бонусы"></a>

YooKassa 自动续订适用于按时长订阅。无 JSON 目录的流量销售模式跳过自动续订；JSON 目录中的 traffic 购买是流量包，不是周期订阅。

试用使用 `TRIAL_DURATION_DAYS`、`TRIAL_TRAFFIC_LIMIT_GB`、`TRIAL_HWID_DEVICE_LIMIT`、
`TRIAL_TRAFFIC_STRATEGY` 和 `TRIAL_SQUAD_UUIDS`。它不选择 JSON 套餐，但可在
**系统 → 套餐**的销售目录旁配置。
`TRIAL_DAYS_STRATEGY` 决定试用有效期内购买的行为：`add_remaining` 将剩余试用天数
加入付费时长，`start_from_payment` 从付款日期计算。由管理员决定，用户下单不能选择。

`TRIAL_PAYMENT_ENABLED` 开启付费激活：Web App 打开独立收银台，无时长选择或优惠码，
仅成功 webhook 后发放访问。`TRIAL_PAYMENT_PRICE` 使用默认支付币种，
`TRIAL_PAYMENT_STARS_PRICE` 为独立 Stars 价格；Stars 为 `0` 时隐藏该方式。
试用付款不适用优惠码、个人或伙伴余额，也不支持下单附加项。
`TRIAL_HWID_DEVICE_LIMIT` 留空保留面板或默认值，`0` 表示不限。
试用期间不允许设备加购；有限设备额度耗尽后，只有至少一个可用套餐配置设备包时，
Web App 才提示转为套餐。

`TRIAL_SQUAD_UUIDS` 为空时使用 `USER_SQUAD_UUIDS`；套餐目录中的高级 squad 不会作为
普通权限加入试用列表。试用高级权限通过 `TRIAL_PREMIUM_SQUAD_UUIDS` 单独开启，
列表为空则不发放。独立限额为 `TRIAL_PREMIUM_TRAFFIC_LIMIT_GB`，`0` 表示无独立高级限制，
周期遵循 `TRIAL_TRAFFIC_STRATEGY`。试用首页高级区域标题通过 `TRIAL_PREMIUM_TITLE` 设置，
留空保留本地化默认名称。
默认开启的 `TRIAL_WITHOUT_OAUTH_ENABLED` 允许未绑定提供方时激活试用；关闭后需绑定
Telegram 或可用的外部 OAuth 身份。`DISPOSABLE_EMAIL_DOMAINS` 域名仍必须绑定 Telegram。
旧名称 `TRIAL_WITHOUT_TELEGRAM_ENABLED` 仅作为已弃用环境别名接受。

从试用转为按周期付费套餐时，商店重置 Remnawave 普通流量计量器，将已购买额度与试用消耗分开。
试用未到期、已过期或流量已耗尽时都适用；剩余天数按 `TRIAL_DAYS_STRATEGY` 处理，
面板 lifetime 总计数保留。商店通过独立无缓存请求确认重置，再检查已保存的限额、时长、
squad 和 `ACTIVE` 状态。面板拒绝或重置未确认时，激活保持未完成，供标准付款流程重试。
已付费套餐的普通续订不会重置周期已用流量。

`DISPOSABLE_EMAIL_DOMAINS` 默认包含两个公开列表的内置快照：主要核验列表
[disposable-email-domains](https://github.com/disposable-email-domains/disposable-email-domains)
和 [Castle](https://github.com/castle/disposable-email-domains) 的活跃临时域名列表。
已确认补充项（包括 `prorises.com`）独立保存，不随来源轮换消失。
注册时应用不访问外部服务，快照由独立脚本更新，每周自动化通过 PR 提议修改供审查，
因此来源不可用或错误更新不会破坏用户登录。

优惠码支持即时奖励天数、付款后奖励天数、下单折扣、订阅时长倍数和发放流量倍数。
奖励天数和时长倍数用于 period 订阅，流量倍数用于 traffic 包和加购；
折扣可用于订阅、traffic 和 HWID 购买。详情见[优惠码](promocodes.md)。

JSON 目录的付款邀请奖励直接配置于 period 套餐周期价格旁：邀请人为 `referral_bonus_days_inviter`，被邀请人为 `referral_bonus_days_referee`。字典键是周期天数，如 `"7"`、`"30"`、`"90"`、`"180"`、`"365"` 或其他精确时长；值本身就是奖励天数。traffic 套餐不适用。

**设置 → 营销计划 → 邀请计划**顶部的 `REFERRAL_PROGRAM_ENABLED` 是总开关。关闭后停止普通邀请归因、欢迎奖励及付款奖励，隐藏 Telegram 和 Web App 的邀请元素；“奖励”区域仍提供优惠码输入。保存配置不删除，推广伙伴计划独立运行。

被邀请人的欢迎奖励 `REFERRAL_WELCOME_BONUS_DAYS` 在同一区域设置。
目录 `referral_welcome_bonus_tariff` 为新奖励订阅选择已启用 period 套餐，缺省使用
`default_tariff`，继承普通／高级限额、Internal Squads、重置策略和 HWID 上限。
奖励不替代试用：奖励订阅有效时不提供试用，结束后可激活普通试用。
“欢迎奖励”组中的“将欢迎奖励加入试用”（`REFERRAL_WELCOME_BONUS_ADDS_TO_TRIAL`）
开启且免费试用可用时，不创建独立奖励订阅，而向试用加入奖励天数，此时不使用欢迎奖励套餐。
`REFERRAL_WEBAPP_LINK_ENABLED` 和 `REFERRAL_TELEGRAM_LINK_ENABLED`
控制 Web App 奖励区显示哪些邀请链接，至少开启一个。
`REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED` 控制未绑定 Telegram 的账号是否能获得
欢迎奖励；`DISPOSABLE_EMAIL_DOMAINS` 中的一次性邮箱始终需要先绑定 Telegram。

`REFERRAL_ONE_BONUS_PER_REFEREE` 将时长奖励限制为被邀请人的首次成功事件：个人购买或符合条件的礼品激活。`REFERRAL_GIFT_ACTIVATION_ENABLED` 默认开启，决定是否计入礼品激活。购买礼品不算个人购买，礼品链接不建立邀请关系。启用首次事件限制后，重复购买或礼品不再为双方增加时长；注册欢迎奖励单独控制。

被邀请人与邀请人套餐不同时，奖励取被邀请人购买的套餐及周期。邀请人订阅仅增加奖励天数，其限额、Internal Squads 等仍按自己的套餐，不改为被邀请人套餐。

Web App 和 Telegram 仅在旧版模式或只有一个启用 period 套餐时显示详细周期行。多个 period 套餐启用时，Web App 提示奖励取决于朋友付款的套餐及周期，再列出各套餐“从 N 到 N 天”的范围，可点问号展开详情。Telegram 此时仅显示每套餐范围。

无 JSON 目录的旧版模式使用 `REFERRAL_BONUS_DAYS_*` 和 `REFEREE_BONUS_DAYS_*`；无 JSON 的流量销售模式下，Web App 不显示逐月奖励详情。`LEGACY_REFS` 接受 `/start ref_<telegram_id>` 旧链接，其载荷包含邀请人 Telegram/用户 ID；后台位置为**旧版套餐兼容**。

## 绑定现有订阅

<a id="привязка-существующих-подписок"></a>

启用 JSON 目录启动时，机器人对有效付费订阅执行安全核对。
不会盲目指定 `default_tariff`，只应用确定性匹配：

- 将 `legacy_keys` 中的旧键转为规范键。
- 使用订阅或套餐切换最近一次成功付款的套餐。
- 无键订阅仅在恰好一个 period 套餐启用时自动绑定。

候选套餐多个、键不在目录中，或用户同时有多个有效订阅时，保持记录不变并加入人工检查列表。
绑定结果、来源和时间保存在 `tariff_binding_source`、`tariff_bound_at` 和 `tariff_binding_note`。

后台**系统 → 套餐 → 订阅套餐绑定**支持 dry-run，显示正常、可安全匹配及有歧义记录数。
**应用安全匹配**仅修改确定性记录；有歧义情况通过用户详情修正，切换前预览流量、squad 和 HWID 上限。
保存目录也会触发核对，未完成时明确返回错误。

目录启用时，新付费激活必须含规范 `tariff_key`，避免再次创建无法使用套餐功能和 HWID 加购的订阅。
