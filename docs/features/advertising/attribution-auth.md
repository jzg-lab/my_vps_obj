<a id="источник-через-авторизацию-и-оплату"></a>

# 登录与付款来源

访问广告链接时，保存接触时间、渠道、链接代码和实际 UTM。网页访客获得随机安全 cookie，有效期 30 天。公开请求不接受任意用户 ID，也不授予产品权限。

登录成功后，将访问关联到已验证账号，复用邮箱验证码、密码、快捷链接、OAuth 和 Telegram 验证。邮箱验证码／快捷链接的上下文绑定服务器验证操作，因此链接可以在另一浏览器打开。邀请注册仍保留自身限制。已属于其他账号的访问，不会因切换用户而转移。

创建订单时保存购买来源快照。默认选择过去 30 天内最近一次已知活动接触，窗口可设置为 1–365 天。窗口调整只影响新订单。下单后的接触、重复 webhook、CSV 修正或人工 UTM 匹配都不改写既有快照。

合并账号会迁移接触与购买，历史保留原 ID。首次来源选更早记录；合并前双方的首购不会都变成合并账号的首购。

未知代码不影响正常流程，也不虚构来源。只有 UTM、没有代码的访问进入“未匹配接触”。管理员可为精确 UTM 参数组创建规则，依据标为人工匹配。

相关文档：[登录方式](../login-methods.md)、[不使用 Telegram](../telegram-optional.md)、[来源与报表](./reporting.md)。

<a id="публичный-контракт-аудитории"></a>

## 公开受众契约

`bot.services.advertising.audience` 提供版本化契约 `AUDIENCE_CONTRACT_VERSION = 1`，供需要广告来源的扩展使用。`audience_query(filters, now=..., namespace=...)` 返回选择用户 ID 的参数化 SQL，扩展不应自行复制广告表结构。`customer_contexts(session, user_ids)` 批量返回来源，`audience_options(session)` 返回包含历史项的活动／链接选项。

`ad_model` 可选 `first_touch`、`last_touch`、`last_purchase`。首次／末次接触指保存的广告／UTM 记录，不是任意用户活动。旧首次来源标为 `legacy_first_start`。最近购买必须是成功产品订单，待付款和余额充值不能替代；退款保留来源历史。

`ad_campaign_id`、`ad_link_id`、`utm_source`、`utm_medium`、`utm_campaign`、`utm_content`、`utm_term` 在选出单条记录后应用，不会把一次访问的 UTM 与另一次活动拼在一起。UTM 精确区分大小写，按参数传递。组合多个查询时，`namespace` 隔离参数。匿名未匹配访问不进入受众。

广告归因与后续沟通归因独立，同一订单可进入两个报表，不能将其收入当作不同订单相加。
