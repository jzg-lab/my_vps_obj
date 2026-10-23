<a id="платежи"></a>

# 支付

后台付款表支持按用户 ID、Telegram ID、`@username`、姓名和邮箱搜索。服务器先搜索，再排序分页，计数为全部匹配付款。清空后点击“搜索”恢复全部；“刷新”更新当前筛选。

渠道可通过 `.env` 或许可设置中的后台项启用。Mini App 默认使用紧凑下拉，`PAYMENT_METHODS_DISPLAY_MODE=buttons` 恢复独立按钮；Telegram 仍使用按钮。

> 本页保留上游支付集成参考。本项目一期不接在线收款或自动扣费，中文翻译不会启用这些功能。

<a id="общий-порядок-настройки"></a>

## 通用配置顺序

1. 开启所需渠道。
2. 填写公开参数、密钥和返回 URL。
3. 在渠道平台配置 webhook（如适用）。
4. 检查 `PAYMENT_METHODS_ORDER`。
5. 在“支付 → 结账外观”选择下拉或独立按钮。
6. 检查名称和图标。
7. 执行测试付款。
8. 检查后端日志。

> 未明确设置返回 URL 时，默认使用 Telegram 机器人链接。

<a id="выбор-способа-оплаты-в-mini-app"></a>

## Mini App 支付方式选择

默认 `dropdown`，可改 `buttons`。两种模式都保留配置顺序、名称及图标。

币种支持但购物车低于渠道最低金额时，方式仍显示但禁用；悬停、焦点或点击显示精确最低额。可用性按完整订阅及加购、激活码百分比折扣后的价格计算。后端独立复查，过期或篡改金额返回 `payment_amount_below_minimum`。

加购支持与最低金额分开检查。外部控制价格或无法把加购加入首付款的循环方式，可卖普通订阅，但会阻止带设备或弹性限额的结账。

<a id="сверка-оплаченных-заказов-yookassa"></a>

## YooKassa 已付款订单核对

渠道付款成功与 Core 发放购买是两个阶段，即使 webhook 未送达，worker 也会核对未完成订单。

| Core 状态 | 含义 |
| --- | --- |
| `pending_yookassa` | 核对及发放未完成，不能据此断定未付款。 |
| `succeeded_pending_finalization` | 已收款待发放，临时失败后至少五分钟再重试。 |
| `succeeded_pending_review` | 已收款，但保存的报价或订阅上下文无法安全应用，需人工核对。 |
| `succeeded` | 购买已发放，处理完成。 |

待人工核对订单不再自动重试。重复 webhook、迟到取消和自动续费不会重复扣款或抹去收款事实。旧卡住订单若固定上下文已变化，下次核对进入待审。

对照渠道付款 ID、金额、保存的购买及订阅历史。只看到到期日变化不能证明该订单已发放。无法交付时，应在渠道退款并记录结果，不因订单年久而删除或取消；冲突不会自动退款或补发。Mini App 明确提示已收款并引导客服。

## Anore

开启 `ANORE_ENABLED`，填写 `ANORE_API_KEY`、收银台密钥 `ANORE_WEBHOOK_SECRET`；账号级密钥另需 `ANORE_SHOP_ID`。webhook 为 `<WEBHOOK_BASE_URL>/webhook/anore`，必须验证 HMAC-SHA256。用户跳回商店不能证明付款。

账单支持 RUB、USD，USD 按原美元金额校验，不按换算 `rubAmount`。`ANORE_METHODS` 可限制为公开支持的 `sbp,yoomoney,crypto`，留空使用收银台配置。`ANORE_RETURN_URL` 为返回地址，`ANORE_BASE_URL` 默认 `https://api.anore.cc/v1`。链接有效四小时，worker 核对已付款账单，重复通知不重复发放。

公开 API 未说明循环扣款，本渠道只支持单次购买。[Anore 文档](https://anore.cc/docs)。

## Cryptomus

开启 `CRYPTOMUS_ENABLED`，填写商户 ID 和收款 API 密钥（不是提现密钥）。webhook 为 `<WEBHOOK_BASE_URL>/webhook/cryptomus`。账单以 RUB／USD 定价，用户用加密货币支付，可用 `CRYPTOMUS_TO_CURRENCY`、`CRYPTOMUS_NETWORK` 限制币种和网络。后台可设返回地址、有效期 `300–43200` 秒（默认 `3600`）、API 地址（默认 `https://api.cryptomus.com/v1`）。必须校验 `MD5(base64(JSON) + 密钥)`，编码遵循公开 PHP 的 UTF-8／斜杠方式。少付不发放，多付不增加期限；公开商户 API 无 P2P 快速支付方式，因此不提供。

`CRYPTOMUS_SUBSCRIPTION_ENABLED` 增加 7 天／1 月／3 月自动付款。用户在 Cryptomus 确认计划，由渠道排程，本地 worker 不发起扣款。礼品、单独加购、结账附加项及激活码不进入循环。取消调用 `recurrence/cancel`，隐藏方式不阻止旧计划处理／取消。可先用 `CRYPTOMUS_SUBSCRIPTION_ADMIN_ONLY_ENABLED` 仅管理员验证。

发放依据 `recurrence/info` 和唯一 `last_pay_off`，不将未公开的循环 webhook 格式作为付款证明。该 API 只有最近扣款，没有完整周期历史；停机跨过多个扣款时，漏掉的旧周期须人工核对，不能按经过时间猜测次数。访问时长取原购买，日历排程由渠道决定。见[账单与签名](https://doc.cryptomus.com/merchant-api/payments/creating-invoice)、[循环计划](https://doc.cryptomus.com/merchant-api/recurring/creating)。

## CisPay

开启 `CISPAY_ENABLED`，填写店铺 ID、API 密钥，平台配置 `<WEBHOOK_BASE_URL>/webhook/cispay`。按原始正文、API 密钥和店铺 ID 校验 HMAC-SHA256。`CISPAY_RETURN_URL` 为返回地址，API 默认 `https://api.cispay.app`。

单次表单提供店铺可用银行卡、快速支付、加密货币。支持 RUB、USD；USD 仅加密货币。API 金额用戈比／美分。客户手续费不增加期限，转换加密货币账单时核查原订单币种与金额。有效期 30 分钟，成功还通过付款状态 API 确认。测试交易不发放，除非为测试店铺明确开启 `CISPAY_ALLOW_SANDBOX_PAYMENTS`。

`CISPAY_SUBSCRIPTION_CARD_ENABLED`、`CISPAY_SUBSCRIPTION_SBP_ENABLED` 分别开启 RUB 7–360 天循环，卡支付最低 50 RUB。店铺需渠道授权循环支付，否则 API 403。相应 `*_ADMIN_ONLY_ENABLED` 可限制管理员测试。用户在渠道同意，礼品、附加项、加购和激活码不进入循环。

渠道自行扣款，worker 只核对已付款周期历史，不重复扣。每交易 ID 只发放一次，原所有者、金额、币种、周期固定。取消通过 `/subscriptions/{id}/cancel` 确认，隐藏方式不妨碍旧计划。暂停和失败不发放，三次失败后渠道结束计划。已付款退款需运营者单独调整。

见 [CisPay 文档](https://cispay.app/developers)、[公开 OpenAPI](https://cispay.app/api/merchant/v1/openapi.json)。

<a id="общие-ссылки"></a>

## 相关文档

- [环境变量](../configuration/env-vars.md)：全部渠道参数。
- [管理后台](admin-panel.md)：支付设置。
- [套餐](tariffs.md)：价格、Stars、购买流程。
- [激活码](promocodes.md)：折扣、倍数、结账激活。
- [合作伙伴](partner-program.md)：佣金与余额支付。
- [用户余额](user-balance.md)：充值、扣款、转换、退款。
- [日志](../troubleshooting/logs.md)：webhook 和支付链接排查。

<a id="проверка-расчёта"></a>

## 价格核查

按时长套餐可在结账加入设备、普通／premium 弹性总限额。弹性限额适用于已付款时长的每个重置周期，不充值到永久加购流量余额。拖滑块时本地计算，结束后请求完整服务器报价，创建付款时再次重算。百分比折扣作用于全部小计，包括基础订阅、加购及立即提升当前订阅的按比例差价，再计算伙伴余额后的外部金额。

提前续费同套餐时，为新期限支付完整所选组合，对超过已有设备／限额的提升按当前窗口剩余比例补差。降低不退款，从下一订阅边界生效。报价绑定当前订阅 ID 和到期日，并发续费使旧账单失效，防止重复发放。切换套餐走独立流程，不伪装成续费。

只在已认证成功确认且币种一致后发放。确认金额等于或高于账单时，只发放原固定订单一次，多付不增加时长、流量或设备。少付或币种不同不激活，webhook 拒绝；渠道已扣款时，应在渠道退款或另收差额，不以少付发完整订单。

普通／伙伴余额可全额或部分付款。混合时渠道只收余额后余款，`Payment` 同时保存总额与内部扣款，现金收入只计外部余款。全额余额创建内部审计付款并走共同发放，不增加现金收入、不产生新佣金或推荐奖励。同一操作只扣一个明确选择的来源。见[用户余额](user-balance.md#оплата-из-баланса)、[伙伴余额](partner-program.md#оплата-из-баланса)。

<a id="webhook-url-провайдеров"></a>

## 渠道 webhook 地址

> 完整地址显示在后台各渠道区域顶部。

全部地址基于公开 HTTPS `WEBHOOK_BASE_URL`，必须路由到 `backend:8080`，而非 frontend／Mini App。例 `https://bot.example.com` 加下表路径。

启用渠道 IP 过滤时，反向代理必须传 `X-Forwarded-For`，且自身 IP／CIDR 在 `TRUSTED_PROXIES`，否则后端可能看到 Docker 网关而拒绝有效请求（403）。相关项包括 `FREEKASSA_TRUSTED_IPS`、`WATA_TRUSTED_IPS`、`HELEKET_TRUSTED_IPS`、`OXAPAY_TRUSTED_IPS`、`PAYKILLA_TRUSTED_IPS`、YooKassa 内置许可列表。Cloudflare 下，先验证最近外部代理属于官方网段，再使用 `CF-Connecting-IP`。

| 渠道 | 路径 | 配置说明 |
| --- | --- | --- |
| YooKassa | `/webhook/yookassa` | 填写 HTTP 通知地址。 |
| FreeKassa | `/webhook/freekassa` | 通知地址；可配置可信 IP。 |
| Platega | `/webhook/platega` | 单次和循环共用。 |
| RollyPay | `/webhook/rollypay` | 单次与循环共用签名地址。 |
| SeverPay | `/webhook/severpay` | 平台提供字段时填写。 |
| Wata | `/webhook/wata` | 按需设置 `WATA_WEBHOOK_VERIFY_SIGNATURE`、`WATA_PUBLIC_KEY`。 |
| CryptoPay | `/webhook/cryptopay` | Crypto Bot／CryptoPay 通知设置。 |
| Heleket | `/webhook/heleket` | 可开启签名和可信 IP。 |
| OxaPay | `/webhook/oxapay` | 创建账单自动传入 `callback_url`，始终校验原正文 HMAC-SHA512。 |
| PayKilla | `/webhook/paykilla` | 设置中的 Webhooks，启用账单支付事件。 |
| LAVA | `/webhook/lava` | 创建账单自动传 `hookUrl`，也可后台配置。 |
| Pally | `/webhook/pally` | Result URL，表单编码回传。 |
| CloudPayments | `/webhook/cloudpayments` | Pay、Fail 通知，可配置可信 IP。 |
| Overpay | `/webhook/overpay` | JSON POST，HTTP Basic 使用店铺 ID／密钥。 |
| Stripe | `/webhook/stripe` | 开启 `checkout.session.completed`、`checkout.session.expired`、`payment_intent.succeeded`、`payment_intent.payment_failed`、`payment_intent.canceled`。 |
| Tribute | `/webhook/tribute` | API 设置，按原正文和 API 密钥验签。 |
| Telegram Stars | `/tg/webhook` | 共用机器人 webhook，无独立支付通知地址。 |

测试后确认后端收到正确路径的 POST。渠道报告不可用时，先查 DNS／HTTPS／反向代理，再查路径是否准确 `/webhook/...`，不应带 `/api`、`/auth` 或 frontend 域名。

<a id="платёжные-провайдеры"></a>

## 支付渠道

以下列出各方式参数、通知和限制。

## YooKassa

用于 RUB，也可自动续费按时长订阅。

<a id="настройка"></a>

### 配置

1. 开启 `YOOKASSA_ENABLED`。
2. 填写 `YOOKASSA_SHOP_ID`、`YOOKASSA_SECRET_KEY`、`YOOKASSA_RETURN_URL`。
3. 复制后台 webhook 到渠道平台。

<a id="безопасные-повторы-автопродления"></a>

### 自动续费安全重试

每周期固定金额、币种、卡、用户同意版本和请求体。网络结果不确定时，仅在 30 分钟窗口用相同 `Idempotence-Key`、相同正文重试。只有渠道明确 `canceled`，且原因是 `insufficient_funds`、`issuer_unavailable`、`internal_timeout`，才允许最多一次新键。撤销授权、关闭续费、换卡或删卡永久停止该周期。

首次开启 `AUTO_RENEW_RETRY_ENABLED=True`，保持 `AUTO_RENEW_RETRY_DRY_RUN=True` 检查日志，再单独关试运行。备用 `AUTO_RENEW_SCHEDULER_ENABLED` 独立且默认关闭。

<a id="справочник"></a>

### 参考

- [YooKassa 变量](../configuration/env-vars.md#yookassa)。

## FreeKassa

独立渠道，通知由后端处理。

<a id="настройка-1"></a>

### 配置

1. 开启 `FREEKASSA_ENABLED`。
2. 填写商户 ID、第一／第二密钥、API 密钥。
3. `FREEKASSA_PAYMENT_METHOD_ID` 填平台已启用方式 ID。
4. 从后端容器确认公开出站 IPv4：

   ```bash
   docker compose exec backend sh -lc 'curl -4fsS https://api.ipify.org; echo'
   ```

5. 写入 `FREEKASSA_PAYMENT_IP`；改 `.env` 后重建 backend，后台覆盖按常规机制应用。
6. 检查签名。
7. 复制 webhook 到平台。
8. 按需填 `FREEKASSA_TRUSTED_IPS`。

<a id="зачем-нужен-freekassapaymentip"></a>

### `FREEKASSA_PAYMENT_IP` 的用途

`POST /v1/orders/create` 要求 `ip`，定义为买家 IP。Telegram Bot API 不提供用户 IP，因此 Minishop 回退使用后端稳定公开出站 IP。它不是可信通知 IP，也不一定等于域名或代理地址。

必须在容器内获取：NAT、VPN、独立网关、Kubernetes 出站会使主机与容器不同。不能填私网地址，动态地址改变后需更新。所有 Telegram 付款共用服务器 IP 是否允许，应向 FreeKassa 确认。

见[官方文档](https://docs.freekassa.net/)。缺少付款 IP 或方式 ID 时不允许创建新付款，但旧 webhook 和核对继续。

<a id="справочник-1"></a>

### 参考

- [FreeKassa 变量](../configuration/env-vars.md#freekassa)。

## Platega

可提供快速支付、银行卡、加密货币、国际卡、统一选择页和循环快速支付独立按钮。新增方式默认关闭，不改变升级前按钮。

<a id="настройка-2"></a>

### 配置

1. 开启 `PLATEGA_ENABLED`。
2. 填写 `PLATEGA_MERCHANT_ID`、`PLATEGA_SECRET`。
3. 按需开启 `PLATEGA_SBP_ENABLED`、`PLATEGA_CARD_ENABLED`、`PLATEGA_CRYPTO_ENABLED`、`PLATEGA_INTERNATIONAL_ENABLED`、`PLATEGA_ALL_METHODS_ENABLED`、`PLATEGA_SUBSCRIPTION_ENABLED`。
4. 平台填写可信证书的公开 HTTPS webhook，不能使用 HTTP、localhost、私网或自签名证书。单次与循环共用。
5. 向渠道确认店铺类别是否要求 `metadata.userId`；Minishop 所有单次结账自动传付款人标识。

<a id="разовые-способы-оплаты"></a>

### 单次方式

- 银行卡按钮位于快速支付之后，默认 `paymentMethod: 11`，可用 `PLATEGA_CARD_METHOD` 覆盖。
- 国际卡默认 `12`，可用 `PLATEGA_INTERNATIONAL_METHOD` 覆盖。
- 统一选择页调用 `POST /v2/transaction/process`，不传 `paymentMethod`，由用户选商户可用方式。
- 共用返回、失败地址、通知和 `PLATEGA_SUPPORTED_CURRENCIES`。国际卡／统一页币种不同时，列出真实币种并在套餐限制不适用按钮。

<a id="рекуррентные-сбп-подписки"></a>

### 循环快速支付订阅

循环按钮出售 `paymentMethod: 6` 授权，不是单次付款。Platega 自行排程扣款并发送每次结果，本地 worker 不主动扣款；渠道无保存方式扣款 API，故不声明 `supports_recurring`。

- 首次带 `SubscriptionId` 回调确认原结账，`provider_payment_id` 保存订阅 ID，作为未来唯一长期关联。
- 后续各扣款生成 `platega-sub:<subscription>:<charge>` 幂等付款，金额与期限取授权快照，不取回调。
- 本地自动续费镜像渠道状态，用户只能关闭；调用 `POST /subscription/{id}/cancel`，未确认则保持开启并报错。重新授权需新购买。
- 失败且无 `NextChargeAt` 为终态，取消授权并关续费；有下次时间则保留 `past_due`，等待渠道重试。

<a id="ограничения"></a>

### 限制

- 只支持 **1、12 个月**，其他时长隐藏。
- 仅周期订阅；流量、设备、切换仍单次。
- 有激活码时隐藏循环按钮，避免一次折扣变成永久固定价。
- 授权金额下单时固定，套餐改价不改变旧授权，需重新购买。

<a id="справочник-2"></a>

### 参考

- [Platega 变量](../configuration/env-vars.md#platega)。
- [不指定方式的支付链接](https://docs.platega.io/создание-платежной-ссылки-без-заданного-метода-33845703e0)。
- [指定方式的支付链接](https://docs.platega.io/создание-платежной-ссылки-с-заданным-методом-29203843e0)。

## RollyPay

提供快速支付、俄罗斯卡、海外卡、加密货币、统一托管页及循环快速支付。

<a id="настройка-3"></a>

### 配置

1. 开启 `ROLLYPAY_ENABLED`，填写 API 密钥、签名密钥。
2. 按需开启全部方式、快速支付、卡、国际卡、加密货币、订阅对应开关。
3. 绑定特定终端或订阅需 `ROLLYPAY_TERMINAL_ID`。
4. 终端配置 `/webhook/rollypay`，将该通知密钥填入 `ROLLYPAY_SIGNING_SECRET`。

每请求生成新 UUID `X-Nonce`。通知按 `<X-Timestamp>.<body>` 原文验 HMAC-SHA256，拒绝超窗事件。签名后仍调用 `GET /payments/{id}` 核对订单 ID、金额、币种、状态。因此迟到 `expired → paid` 可正常激活，旧事件不能覆盖新状态。

<a id="разовые-платежи"></a>

### 单次付款

- 统一页不传 `payment_method`。
- 快速支付、卡、海外卡、加密货币分别为 `sbp`、`card`、`intl_card`、`crypto`。
- 快速支付、俄罗斯卡、加密货币支持 RUB，海外卡支持 RUB／EUR。
- worker 核对 `created`、`processing`；`canceled`、`expired` 释放本地预留；即使曾过期，后续 `paid` 仍是最终成功。
- 退款／拒付映射本地状态。提现及退款请求完成事件安全确认，但商户余额／提现不属于用户结账。

<a id="регулярные-сбп-подписки"></a>

### 循环快速支付

渠道排程，Minishop 从 `GET /subscription-plans` 选择符合时长的最新版本并检查 `cap_amount_rub`。支持 **1、3、12 月**（`month`、`quarter`、`year`），不使用日计划，因为 Core 时长以整月表示。

创建调用 `POST /subscriptions`，使用固定幂等键，仅传许可字段；返回链接前持久化授权。首笔及续扣均为 `payment.paid`，读取付款和 `subscription_id`、核对金额，为各次生成独立幂等本地付款，重复通知不重复续期。

无独立授权状态 webhook，worker 定期核对 `provider_state`、`billing_status`。关闭调用幂等 `POST /subscriptions/{id}/stop`；`stopped` 关本地开关，`review` 等待渠道决定。拒付会停止对应授权。完全关闭渠道前先停活跃授权；只关订阅按钮不妨碍旧计划核对／取消。

循环不支持激活码和结账加购，避免一次优惠或可变权益偷偷影响后续。套餐改价不改旧授权。

<a id="sandbox-и-sdk"></a>

### 测试与 SDK

`ROLLYPAY_TEST_MODE=True` 添加 `test: true`，隐藏公开按钮，只让管理员使用单次测试；测试通知不能激活普通用户购买。公开文档未保证循环测试环境，因此测试模式关闭订阅。

集成时官方 Python SDK 为同步，缺必需 nonce 和订阅接口；Core 使用共用异步 HTTP 客户端调用相同公开 REST，补齐 nonce、幂等及循环。

<a id="справочник-3"></a>

### 参考

- [RollyPay 变量](../configuration/env-vars.md#rollypay)。
- [官方文档](https://docs.rollypay.io/)。

## SeverPay

独立渠道，使用自身 MID、令牌和支付链接有效期。

<a id="настройка-4"></a>

### 配置

1. 开启 `SEVERPAY_ENABLED`。
2. 填写 `SEVERPAY_BASE_URL`。
3. 填写 `SEVERPAY_MID`、`SEVERPAY_TOKEN`。
4. 复制 webhook 至平台。
5. 按需设置 `SEVERPAY_LIFETIME_MINUTES`。

<a id="справочник-4"></a>

### 参考

- [SeverPay 变量](../configuration/env-vars.md#severpay)。

## Wata

使用 bearer 令牌、支付链接、循环计划和可选签名。循环由渠道排程，首付后自行定期扣固定金额，向相同 webhook 发新交易。

<a id="настройка-5"></a>

### 配置

1. 开启 `WATA_ENABLED`。
2. 填 API 地址和令牌。
3. 设置链接有效分钟。
4. 复制 webhook 至平台。
5. 按需开启签名校验。
6. 签名模式填写 `WATA_PUBLIC_KEY`。
7. IP 过滤填 `WATA_TRUSTED_IPS`。
8. 向渠道申请终端订阅授权，开启 `WATA_SUBSCRIPTION_ENABLED`。
9. 按需用 `WATA_SUBSCRIPTION_MAX_PERIODS` 限次数。

<a id="ограничения-1"></a>

### 限制

- 链接有效期 `15–43200` 分钟。
- 自动付款仅订阅，单独流量、premium、设备仍单次。
- 新订阅弹性限额进入每次固定价，不支持首周期按比例补差，避免首付与续扣不同。
- 同意时固定套餐、基础／弹性限额和价格；后改不影响旧计划，新条件需新订阅。
- 替换时先确认新计划再结束旧计划；人工换套餐先确认旧计划结束，否则不换。
- 创建链接需用户输入邮箱和电话，传给 Wata，但不存本地。
- 不支持激活码、内部余额和旧仅设备限额循环续费。

<a id="справочник-5"></a>

### 参考

- [Wata 变量](../configuration/env-vars.md#wata)。

## CryptoPay

通过 Crypto Bot API 令牌和网络提供加密货币支付。

<a id="настройка-6"></a>

### 配置

1. 开启 `CRYPTOPAY_ENABLED`。
2. 填令牌。
3. 选 `mainnet`／`testnet`。
4. 选 `CRYPTOPAY_CURRENCY_TYPE=fiat`／`crypto`。
5. 检查 `CRYPTOPAY_ASSET`，如 RUB、USDT、BTC。
6. 复制 webhook 到 CryptoPay。

<a id="проверка"></a>

### 核查

测试令牌只配测试网，主网令牌只配主网。金额或资产不对时，核对币种类型与资产组合。

<a id="справочник-6"></a>

### 参考

- [CryptoPay 变量](../configuration/env-vars.md#cryptopay)。

## Tribute

两种模式。开启 `TRIBUTE_ENABLED`、`TRIBUTE_SHOP_ENABLED` 且填写店铺 ID 时，优先使用 [Shop API](https://wiki.tribute.tg/for-shops/api/methods) 动态订单，金额币种精确对应本地报价。Creator 已发布订阅和数字商品作为不支持场景回退；关闭 Shop 时完全使用 Creator。

<a id="настройка-7"></a>

### 配置

1. 创建 Shop、允许循环付款、获取 API 密钥及数值店铺 ID。
2. 在后台支付设置开启渠道，填密钥、店铺 ID 并开 Shop。
3. 配置 `/webhook/tribute`，同地址接受 [Shop](https://wiki.tribute.tg/for-shops/api/webhooks) 和 [Creator](https://wiki.tribute.tg/for-content-creators/api-documentation/webhooks) 事件；`trbt-signature` 以 API 密钥对原正文验 HMAC-SHA256。
4. 需 Creator 回退时，预建订阅／数字商品，在套餐编辑填链接与 ID。
5. 测试 `shop_order`、`shop_order_charge_success`、`shop_order_cancelled`；回退另测 `new_subscription`、`renewed_subscription`、`cancelled_subscription`、`new_digital_product`。

<a id="основной-режим-shop-api"></a>

### 主要模式：Shop API

- 周期订阅只创建 1、3、6、12 月循环订单，对应 `monthly`、`quarterly`、`halfyearly`、`yearly`。渠道虽有 `weekly`，本集成不创建。
- 单次支持普通／premium 流量及加购、独立 HWID、换套餐差价；传精确 RUB／EUR／USD。通知金额、币种或用户不符时隔离，不发放。
- 严格绑定 `TRIBUTE_SHOP_ID`，缺失／其他店铺通知拒绝。金额 `100–300000` 戈比／美分。
- 未填店铺 ID 时，即使开关开启也只卖 Creator 已配置项目；设备和差价不可用，因为只有 Shop 能传其金额。
- Shop 不需套餐 `tribute` 字段，仅回退使用。
- 循环价格折扣将完整续扣价放 `amount`，首付折扣价放 `firstPeriodAmount`，首付通知必须确认两者。只允许价格折扣码，不支持奖励天数、时长／流量倍数，因为排程与权威到期由渠道管理。单次不受此限制。`hwid_renewal` 订阅加设备组合仍不支持，可单独买设备。
- 循环价创建时固定，本地改价不影响旧授权；取消重订前维持旧价。仍有循环订单时不要停用、删除、更名套餐，也不要换店铺 ID；先取消并等 `shop_order_cancelled`，否则旧通知无法通过店铺验证。

不使用 Shop Stars、`paymentToken`／令牌扣款或 Tribute 预付余额。Creator 数字商品外部页面的支付选择由渠道管理。

<a id="резервный-режим-creator-subscriptions-и-digital-products"></a>

### 备用模式：Creator 订阅与数字商品

- 每个本地周期单独填写链接、`subscription_id`、`period_id`。`https://t.me/tribute/app?startapp=ep_...` 须指向真实出售该周期的订阅；同订阅涵盖全部周期时可逐行重复链接与 ID。
- 平台和分享链接没有数值 ID，只由 Creator API 提供。“从 Tribute 获取”用同密钥读取 [Subscriptions API](https://wiki.tribute.tg/for-content-creators/api-documentation/subscriptions) 和 [Products API](https://wiki.tribute.tg/for-content-creators/info-products-and-content/api-integration)。选择订阅映射 1／3／6／12 月，缺失周期留空并提示差异。分享链接仍需人工复制，API 不返回。
- 固定普通／premium 包可配数字商品 ID 和链接；加载目录后 ID 变为列表，商品 API 也返回链接。
- Creator 价格及周期由渠道决定，本地仅展示，不随链接传入，管理员须保持一致。编辑器比较金额、币种、已消失 ID 和周期差异。
- 仍可能收到迟到通知或退款时，不删除／复用 ID。先停止新结账链接，等待渠道结算／退款窗口结束，再删映射。

捐赠不用于销售，因为金额由捐赠者决定，无法稳定关联内部订单；`new_donation`、`recurrent_donation` 不发放套餐、流量或设备。

<a id="lifecycle-отмена-и-возвраты"></a>

### 生命周期、取消与退款

- 只接受有效签名通知，去重，旧事件不回滚已处理续费。
- `new_subscription`／`renewed_subscription`、`shop_order`／`shop_order_charge_success` 发放。中间 `shop_order_payment_received`、`shop_order_prepaid` 只确认不发放，等待最终事件。Creator `expires_at` 为权威日期，试用／赠送可处理，但免费期不发本地推荐奖励。
- 活跃循环时，用户不能自行换套餐或另买周期订阅。管理员可立即指定，但 Shop 先通过 API 取消，Creator 因无取消 API 需先在平台取消。指定后关本地自动续费，已付访问保留至到期。
- Creator 关闭按钮引导用户到 `@tribute` 取消，再在 Mini App 单独确认；确认后无需等通知即关本地开关，不改已付期。Shop 仍调用 API。
- 首通知前并发付了两个循环订单时，取消第二个并申请首付退款，不发放。退款未确认前隔离待人工。
- `shop_order_charge_failed` 不发新期限，等待渠道重试，第三次失败关本地开关；迟到成功重新同步。
- `digital_product_refunded` 标记关联付款退款；`shop_order_refunded` 对已完成单次标退款，循环退款需人工核查账务和权益。不自动收回已用流量或已发／已用设备。

<a id="справочник-7"></a>

### 参考

- [Shop API](https://wiki.tribute.tg/for-shops/api)。
- [Shop 方法](https://wiki.tribute.tg/for-shops/api/methods)。
- [Shop 通知](https://wiki.tribute.tg/for-shops/api/webhooks)。
- [Creator API](https://wiki.tribute.tg/for-content-creators/api-documentation)。
- [Creator 通知](https://wiki.tribute.tg/for-content-creators/api-documentation/webhooks)。
- [Tribute 变量](../configuration/env-vars.md#tribute)。

## Heleket

加密货币账单使用商户 ID、支付 API 密钥、账单币种和通知验证。

<a id="настройка-8"></a>

### 配置

1. 开启 `HELEKET_ENABLED`。
2. 填 API 地址、商户 ID、API 密钥。
3. 设置 `HELEKET_CURRENCY`。
4. 按需设目标币种和网络。
5. 核对返回及成功 URL。
6. 设置有效秒数。
7. 复制通知地址至平台。
8. 按需开签名验证。
9. 按需设可信 IP。

<a id="ограничения-2"></a>

### 限制

有效期 `300–43200` 秒。`paid`、`paid_over` 只在 `is_final=true` 发放，多付仍只发原固定订单。

<a id="справочник-8"></a>

### 参考

- [Heleket 变量](../configuration/env-vars.md#heleket)。

## OxaPay

使用 Merchant API v1 的 `Generate Invoice` 生成托管链接。金额币种取本地订单，`order_id` 为 Minishop 付款 ID，回调从 `WEBHOOK_BASE_URL` 生成。

<a id="настройка-9"></a>

### 配置

1. 在平台创建 Merchant API 密钥。
2. 开启渠道并保存 `OXAPAY_MERCHANT_API_KEY`。
3. 确认公开回调以 `/webhook/oxapay` 结尾。
4. 按需填返回 URL，有效期 `15–2880` 分钟。
5. 测试时临时开启 `OXAPAY_SANDBOX`。

<a id="комиссия-недоплата-и-расчёты"></a>

### 手续费、少付与结算

- 费用承担、少付容差、自动提现、混合支付项留空时，沿用 OxaPay 商户服务设置。
- 自动换币只支持 `OXAPAY_TO_CURRENCY=USDT`，其他目标 API 不接受。
- 支持法币与加密货币账单，本地不写死名单，最终由商户账号 API 校验。

<a id="webhook-и-восстановление"></a>

### 通知与恢复

- 使用商户密钥对精确原始 JSON 字节验 `HMAC` 头 HMAC-SHA512，不能关闭。
- `Paying` 只表示交易已发送；`Paid` 才发放，`manual_accept` 也为完成态。
- 激活前核对 `type=invoice`、`track_id`、`order_id`、金额、币种。重复通知幂等并返回必需 `200 ok`。
- 通知丢失时，公共核对 worker 读取 `GET /v1/payment/{track_id}`，完成已付账单或关闭过期账单。
- 可信 IP 是可选附加保护，最新名单向支持获取；无名单仍强制 HMAC。

<a id="справочник-9"></a>

### 参考

- [创建账单](https://docs.oxapay.com/api-reference/payment/generate-invoice)。
- [付款信息](https://docs.oxapay.com/api-reference/payment/payment-information)。
- [通知](https://docs.oxapay.com/webhook)。
- [状态](https://docs.oxapay.com/api-reference/payment/payment-status-table)。
- [OxaPay 变量](../configuration/env-vars.md#oxapay)。

## PayKilla

V2 加密货币账单托管页为 `https://gopay.paykilla.com/{invoice_id}`。API 使用 HMAC-SHA256，通知按 `X-API-SIGN` 和原正文验签。

<a id="особенности"></a>

### 特点

- 严格校验文本字段，`purpose`、`description` 传 ASCII 英文模板 `<WEBAPP_TITLE> payment <id>`；中文说明只保留本地。
- 清洗只允许 ASCII 字母、数字、空格、`_`、`.`、`,`。
- 最低金额由配置决定，默认 10 USD。转换后仍低于最低时，机器人隐藏，网页禁用，API 返回最低额错误。

<a id="валюта-invoice"></a>

### 账单币种

币种必须是 API `currency` 可接受值。法币保留两位小数，加密资产保留精确十进制；成功通知后先核对认证账单金额币种。

套餐币种在 `PAYKILLA_INVOICE_CURRENCIES` 中则原样传；否则换为 `PAYKILLA_CURRENCY`。默认 RUB 经 ExchangeRate-API 换 USD，并按 `PAYKILLA_EXCHANGE_RATE_CACHE_SECONDS` 缓存。

创建前读取 `GET /api/v2/currency`，检查 `invoiceMin`／`invoiceMax` 及当前商户的币种／方式限制。

<a id="данные-счёта"></a>

### 账单字段

必需 `type`、`purpose`、`currency`、`totalPrice`、`paymentCurrencies`；另传 `clientOrderId`、`description`、`expiredAt`、`userPaysServiceFee`、`userPaysNetworkFee`。不传重定向 URL，依赖通知完成。

<a id="ключ-api"></a>

### API 密钥

1. 平台设置打开 API 密钥。
2. 创建 HMAC 类型。
3. 收款开启 `INVOICE`。
4. 不需要 `WITHDRAWAL`。
5. `publicKey` 填 `PAYKILLA_API_KEY`。
6. `secretKey` 填 `PAYKILLA_SECRET_KEY`。

<a id="вебхук"></a>

### webhook

1. 平台设置打开 Webhooks。
2. 填后台完整地址。
3. 最少开启 `INVOICE_PAID`、`INVOICE_EXPIRED`。
4. 生产另开 `PAYMENT_COMPLETED`、`PAYMENT_FAILED`、`PAYMENT_OVERPAID`、`PAYMENT_UNDERPAID`、`PAYMENT_PARTIAL`、`COMPLIANCE_FAILED`。
5. 如需中间日志，加 `INVOICE_CREATED`、`PAYMENT_PENDING`、`TRANSACTION_CONFIRMED`、`TRANSACTION_FINAL`。
6. 保持 `PAYKILLA_VERIFY_WEBHOOK_SIGNATURE=True`。

<a id="настройка-10"></a>

### 配置

1. 开启渠道。
2. 填公私密钥。
3. 套餐币种不可直接开账时保留 `PAYKILLA_CURRENCY=USD`；`PAYKILLA_INVOICE_CURRENCIES` 填商户真实支持值，如 `USD,EUR`。
4. 支付资产默认 `USDTTRC,BTC,ETH,USDTBSC,USDTTON`，也可替换为平台可用列表，`USDTTRC` 应首位。
5. 最低账单为 10 USD 时保留对应默认。
6. 确认通知地址，因为不传重定向。
7. 需要明确排序时将 `paykilla` 加入顺序。

<a id="справочник-10"></a>

### 参考

- [PayKilla 变量](../configuration/env-vars.md#paykilla)。

## LAVA

LAVA Business 通过 `https://api.lava.ru` 提供 RUB 银行卡和快速支付。请求对原正文验 HMAC-SHA256，传 `Signature`；通知以 `Authorization` 接受原正文或旧 PHP SDK 排序键 JSON 的签名。

<a id="особенности-1"></a>

### 特点

只开 RUB 账单，配置公开后端地址时自动传 `hookUrl`。`LAVA_INCLUDE_SERVICES` 可限制 `card,sbp` 等方式。成功通知金额必须匹配，否则拒绝。

<a id="настройка-11"></a>

### 配置

1. 开启渠道。
2. 填店铺 ID、密钥。
3. 有独立通知密钥时填 `LAVA_WEBHOOK_SECRET`，留空使用主密钥。
4. 按需设置有效期 `1..7200` 分钟和返回地址。
5. 按需将通知地址填平台。

<a id="справочник-11"></a>

### 参考

- [LAVA 变量](../configuration/env-vars.md#lava)。

## Pally

Pally／PayPalych 托管页 `https://pally.info`。通过 `POST /api/v1/bill/create` 创建，保存 `bill_id`，由 `/webhook/pally` 处理 Result URL。

<a id="особенности-2"></a>

### 特点

- 支持 RUB、USD、EUR。
- 请求为表单编码，`Authorization: Bearer <PALLY_API_TOKEN>`。
- 签名为 `strtoupper(md5(OutSum:InvId:token))`，优先用 `PALLY_SIGNATURE_TOKEN`，留空用 API 令牌。
- `OutSum` 纳入签名并严格匹配；付款人承担手续费时可接受签名金额大于账单，但只发原订单。
- `SUCCESS`、`OVERPAID` 激活，`FAIL` 失败，其余 `NEW`、`PROCESS`、`UNDERPAID` 待处理。

<a id="настройка-12"></a>

### 配置

1. 开启渠道。
2. 填令牌、店铺 ID 和可选独立签名令牌。
3. 平台填写 Result URL。
4. 按需设返回／成功／失败、有效秒数、手续费承担。RUB 最低外部金额默认 30，伙伴混合支付至少保留该值；USD／EUR 有独立最低额设置。
5. 固定方式可选 `PALLY_PAYMENT_METHOD=BANK_CARD` 或 `SBP`。

<a id="справочник-12"></a>

### 参考

- [Pally 变量](../configuration/env-vars.md#pally)。

## CloudPayments

通过 Orders API `https://api.cloudpayments.ru/orders/create` 收卡支付。请求 Basic 登录为公开 ID、密码为 API 密钥。Pay／Fail 表单通知以密钥对原正文验 base64 HMAC-SHA256，头为 `Content-HMAC`，旧版为 `X-Content-HMAC`。

<a id="особенности-3"></a>

### 特点

- 创建 order 并返回托管链接，`InvoiceId` 为内部付款 ID。
- 支持 RUB、USD、EUR、GBP、KZT、UAH、BYN、AZN、AMD、KGS。
- 成功金额不符返回 `12`。
- 开循环后，Pay 保存 `Token`，商户通过 `/payments/tokens/charge`、`TrInitiatorCode=0`、`PaymentScheduled=1` 续扣。
- 不使用渠道内置 subscriptions；期限、HWID 续费、取消和恢复由通用逻辑管理。
- 成功响应为 `{"code": 0}`。

<a id="настройка-13"></a>

### 配置

1. 开启渠道。
2. 填公开 ID、API 密钥。
3. 按需设置返回／失败地址。
4. 相同 webhook 用于 Pay、Fail。
5. 渠道允许 Pay 返回令牌，并开启 `CLOUDPAYMENTS_RECURRING_ENABLED=true`。
6. 按需设可信 IP。

<a id="справочник-13"></a>

### 参考

- [CloudPayments 变量](../configuration/env-vars.md#cloudpayments)。

## Overpay

基于 BeGateway，`POST https://checkout.overpay.io/ctp/api/checkouts` 创建托管付款，跳转 `redirect_url`，通过 `/webhook/overpay` 完成。

API 与 JSON POST 通知都用 Basic 店铺 ID／密钥，金额为最小货币单位，`tracking_id` 为内部付款 ID。

<a id="особенности-4"></a>

### 特点

- `transaction_type=payment`，保存返回 `token` 并展示链接。
- 支持 USD、EUR、RUB、GBP 等，依商户合同。
- 成功最小单位金额须覆盖账单，少付 400，多付只发原固定订单。
- 循环创建带 `additional_data.contract=["recurring"]`，成功保存 `credit_card.token`，续扣调用 `POST https://gateway.overpay.io/transactions/payments`。
- 不使用渠道内置订阅，期限、HWID、取消和恢复由通用逻辑管理。

<a id="настройка-14"></a>

### 配置

1. 开启渠道。
2. 填店铺 ID、密钥。
3. 按需填返回／成功／拒绝／失败地址。
4. 平台设置通知 URL。
5. 按需开 `OVERPAY_RECURRING_ENABLED=true`。
6. 按需设可信 IP。

<a id="справочник-14"></a>

### 参考

- [Overpay 变量](../configuration/env-vars.md#overpay)。

## Stripe

托管付款使用 Checkout Sessions，应用管理的自动续费使用 PaymentIntents。

<a id="особенности-5"></a>

### 特点

- 内部付款 ID 放 `client_reference_id`、metadata `payment_db_id`。
- 循环开启时传 `payment_intent_data[setup_future_usage]=off_session`，成功保存客户及方式，续费创建会话外 PaymentIntent。
- 不使用 Stripe Billing Subscriptions，期限、设备续费、取消和重试由通用逻辑管理。
- 支持币种配置只列商户及已启用方式真实可用值。

<a id="настройка-15"></a>

### 配置

1. 开启渠道。
2. 填 `STRIPE_SECRET_KEY`。
3. 平台添加通知地址。
4. 开启前表所列五个 Checkout／PaymentIntent 事件。
5. 将该端点 `whsec_...` 签名密钥填 `STRIPE_WEBHOOK_SECRET`。
6. 按需设返回／取消地址。
7. 按需开 `STRIPE_RECURRING_ENABLED=true`。

<a id="справочник-15"></a>

### 参考

- [Stripe 变量](../configuration/env-vars.md#stripe)。

## Telegram Stars

直接使用 Stars，兼容旧价格和 JSON 套餐目录。

<a id="где-используются"></a>

### 适用场景

按时长订阅、流量包、premium 加购，以及目录开启的 HWID 加购。

<a id="настройка-16"></a>

### 配置

1. 开启 `STARS_ENABLED`。
2. 核对旧设置或 JSON 中 Stars 价格。
3. 确认价格取整。
4. 检查切换套餐。

<a id="ограничения-3"></a>

### 限制

无独立通知地址，事件通过 `/tg/webhook`。没有明确汇率时，不自动转换 XTR／Stars 加购。

<a id="справочник-16"></a>

### 参考

- [支付变量](../configuration/env-vars.md#платежи)。
- [套餐](tariffs.md)。

<a id="рекламные-источники"></a>

## 广告来源

活动、链接、优惠与购买来源核查见[广告说明](./advertising/index.md)。
