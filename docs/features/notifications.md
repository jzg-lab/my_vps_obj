<a id="уведомления"></a>

# 通知

Minishop 通过 Telegram 和邮件发送通知。Telegram 可指向具有已验证绑定的用户、具有管理员角色的账号或 `LOG_CHAT_ID`，取决于事件。邮件要求 SMTP 正常且接收者有邮箱。

自动用户通知在“系统 → 设置 → 通知 → 用户投递”按类别配置，每类有独立 Telegram／邮件开关。两者都关表示完全禁止该类通知。

备用渠道开关允许在所选渠道未绑定时，通过唯一已绑定渠道投递。例如只选 Telegram，但用户只有邮箱，可改发邮件。所选渠道可用时，不使用关闭的渠道；临时发送故障也不触发备用渠道。

封禁用户不会收到任何自动通知，包括备用渠道；跳过不记为成功投递。

所有 HTML 邮件使用统一网页品牌模板，包含标题、强调色与标志。后台“外观”上传的标志作为内嵌图片，公开 HTTPS 标志仍为外部图片。

> 本页包含上游通知能力，不代表本项目一期启用了旧支付、礼品、推荐或营销流程。

<a id="сводная-таблица"></a>

## 通知总表

| 事件 | 接收者 | Telegram | 邮件 | 条件与限制 |
| --- | --- | :---: | :---: | --- |
| 邮箱登录验证码与快捷链接 | 用户 | - | ✓ | 需要 `SMTP_*`、`EMAIL_*`；快捷链接还需要有效 `SUBSCRIPTION_MINI_APP_URL`。 |
| 设置／修改密码验证码 | 用户 | - | ✓ | 需要 SMTP 与邮箱配置。 |
| 订阅付款成功 | 用户 | ✓ | ✓ | `subscription`；邮件需 SMTP 和用户邮箱。 |
| 购买赠送订阅 | 购买者／管理日志群 | ✓ | - | 购买者收到链接，日志群只记礼品标记与付款编号；链接保存在“奖励”。 |
| 礼品投递 | 购买者指定邮箱 | - | ✓ | 用户选择后由 SMTP worker 有限重试，失败不取消礼品，见[赠送订阅](gifts.md)。 |
| 独立流量包购买成功 | 用户 | ✓ | ✓ | `traffic`／`traffic_package`；邮件需 SMTP 和邮箱。 |
| 普通流量加购成功 | 用户 | ✓ | ✓ | `topup`；邮件需 SMTP 和邮箱。 |
| Premium 流量加购成功 | 用户 | ✓ | ✓ | `premium_topup`；邮件需 SMTP 和邮箱。 |
| HWID 设备购买成功 | 用户 | ✓ | ✓ | 单独支付 `hwid_devices` 后发送；随订阅续费设备时，附在订阅付款通知中。邮件需 SMTP 和邮箱。 |
| 新 HWID 设备连接 | 用户 | ✓ | ✓ | 需 Remnawave 2.8.1+ 签名 `user_hwid_devices.added`；不保存或显示原 HWID、IP、User-Agent。 |
| HWID 设备限额用尽 | 用户 | ✓ | ✓ | 新设备数达到有限上限时随新设备事件发送；仅有效套餐且有 HWID 包时推荐加购。 |
| 付费升级套餐 | 用户 | ✓ | ✓ | `tariff_upgrade`；邮件需 SMTP 和邮箱。 |
| 绑定 YooKassa 支付方式 | 用户 | ✓ | ✓ | webhook 成功保存方式后发送；邮件需 SMTP 和邮箱。 |
| 渠道 webhook 报告付款失败 | 用户 | ✓ | ✓ | 渠道报告失败时发送；邮件需 SMTP 和邮箱。 |
| 推荐奖励延长邀请者有效订阅 | 邀请者 | ✓ | ✓ | 被邀请者付款，且奖励延长了邀请者有效订阅。 |
| 推荐奖励为邀请者创建奖励订阅 | 邀请者 | ✓ | ✓ | 被邀请者付款，但邀请者没有可延长的有效订阅。 |
| 到期前 3 天提醒 | 用户 | ✓ | ✓ | `SUBSCRIPTION_NOTIFY_DAYS_BEFORE >= 3`；邮件另需 `SUBSCRIPTION_EMAIL_NOTIFICATIONS_ENABLED=True`。 |
| 到期前 2 天提醒 | 用户 | ✓ | ✓ | `SUBSCRIPTION_NOTIFY_DAYS_BEFORE >= 2`；邮件另需订阅邮件开关。 |
| 自动续费前 48 小时扣款提醒 | 用户 | ✓ | ✓ | 替代已开启自动续费 YooKassa 订阅的普通 48 小时提醒；邮件另需订阅邮件开关。 |
| 到期前 1 天提醒 | 用户 | ✓ | ✓ | `SUBSCRIPTION_NOTIFY_DAYS_BEFORE >= 1`；邮件另需订阅邮件开关。YooKassa 自动续费 24 小时 webhook 会先尝试扣款，可能不再提醒。 |
| 到期前数小时提醒 | 用户 | ✓ | ✓ | 本地 worker 发送，`SUBSCRIPTION_NOTIFY_HOURS_BEFORE` 为 1–23；邮件另需订阅邮件开关。 |
| 到期当天通知 | 用户 | ✓ | ✓ | `SUBSCRIPTION_NOTIFY_ON_EXPIRE`；邮件另需订阅邮件开关。 |
| 到期后一天通知 | 用户 | ✓ | ✓ | `SUBSCRIPTION_NOTIFY_AFTER_EXPIRE`；邮件另需订阅邮件开关。 |
| 试用流量用尽 | 用户 | ✓ | ✓ | 本地 worker 对试用订阅发送；邮件需 SMTP 和邮箱。 |
| 普通套餐流量接近限额 | 用户 | ✓ | ✓ | `TariffTrafficWorker` 按 `TARIFF_TRAFFIC_WARNING_LEVELS` 发送；邮件需 SMTP 和邮箱。 |
| 普通套餐流量用尽 | 用户 | ✓ | ✓ | `TariffTrafficWorker` 在周期限额达到时发送；邮件需 SMTP 和邮箱。 |
| Premium 流量接近限额 | 用户 | ✓ | ✓ | `TariffTrafficWorker` 按相同阈值检查 premium 配额；邮件需 SMTP 和邮箱。 |
| Premium 流量用尽 | 用户 | ✓ | ✓ | `TariffTrafficWorker` 在 premium 配额达到时发送；邮件需 SMTP 和邮箱。 |
| Torrent Blocker 临时封禁 IP | 用户 | ✓ | ✓ | 需面板 2.7+ 及签名 `torrent_blocker.report`，由 `TORRENT_BLOCKER_NOTIFICATIONS_ENABLED` 开启；渠道、冷却和 IP 显示独立配置。 |
| 管理员回复工单 | 用户 | ✓ | ✓ | Telegram 发给已绑定用户，邮件发给有邮箱用户。 |
| 关闭工单 | 用户 | ✓ | ✓ | 按绑定渠道发送。 |
| 邮箱与 Telegram 账号合并 | 用户 | - | ✓ | 网页绑定表单合并后发到最终邮箱；Telegram OAuth 绑定合并只记管理日志，不发用户邮件。 |
| 伙伴申请决定 | 伙伴用户 | ✓ | - | `approved`／`rejected`；批准另记日志群，重复读取同一待审申请不重复通知。 |
| 伙伴资料状态变化 | 伙伴用户 | ✓ | - | 激活、恢复、暂停、关闭时发送。 |
| 伙伴提现状态变化 | 伙伴用户 | ✓ | - | `processing`、`paid`、`rejected`、`failed`、`canceled`，说明预留是否返还。 |
| 管理员群发 | 选定受众 | ✓ | ✓ | 从机器人／网页后台入队，受众 `all`、`active`、`inactive`；各渠道遵守全局设置与用户偏好。 |
| 管理员直接私信 | 已绑定 Telegram 用户 | ✓ | - | 从机器人／网页后台用户详情发送，无邮件渠道。 |
| 新客服工单 | 管理员 | ✓ | ✓ | Telegram／日志由 `LOG_SUPPORT`、`SUPPORT_ADMIN_TELEGRAM_NOTIFICATIONS_ENABLED` 控制；邮件由 `SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED` 开启。 |
| 用户回复工单 | 管理员 | ✓ | ✓ | 使用相同客服通知开关。 |
| Telegram 新注册 | 管理员／日志群 | ✓ | - | `LOG_NEW_USERS`。 |
| 邮箱新注册 | 管理员／日志群 | ✓ | - | `LOG_NEW_USERS`。 |
| Telegram 账号绑定邮箱 | 管理员／日志群 | ✓ | - | `LOG_NEW_USERS`。 |
| 邮箱账号绑定 Telegram | 管理员／日志群 | ✓ | - | `LOG_NEW_USERS`。 |
| 邮箱与 Telegram 账号合并 | 管理员／日志群 | ✓ | - | `LOG_NEW_USERS`。 |
| 付款成功 | 管理员／日志群 | ✓ | - | `LOG_PAYMENTS`。 |
| 试用激活 | 管理员／日志群 | ✓ | - | `LOG_TRIAL_ACTIVATIONS`。 |
| 激活码成功 | 管理员／日志群 | ✓ | - | `LOG_PROMO_ACTIVATIONS`。 |
| 可疑激活码尝试 | 管理员／日志群 | ✓ | - | `LOG_SUSPICIOUS_ACTIVITY`。 |
| 新伙伴申请 | 管理员／日志群 | ✓ | - | 发到 `LOG_CHAT_ID`／`LOG_THREAD_ID`，含用户跳转。 |
| 新伙伴提现 | 管理员／日志群 | ✓ | - | 包含金额、币种和内部编号，不含完整收款信息。 |
| 手动面板同步结果 | 发起管理员 | ✓ | - | 通过队列执行时，worker 向 `target_chat_id` 发简要结果。 |
| 创建面板用户失败 | 管理员 | ✓ | ✓ | 按当前账号角色和可用渠道选接收者。 |
| 备份归档已创建 | 管理员／备份群 | ✓ | - | 发到 `BACKUP_CHAT_ID`，留空则使用 `LOG_CHAT_ID`。 |
| 备份失败 | 管理员／备份群 | ✓ | - | 同上。 |

<a id="важно-про-окончание-подписки"></a>

## 订阅到期通知规则

类别同时开启两渠道且用户绑定 Telegram、已验证通知邮箱时，会收到两条。只有一个可用时，只向该渠道发。两渠道都关时，不论备用设置都不发。

到期邮件按钮通过邮箱验证码打开网页应用：立即发送代码，验证后进入续费。曾付费订阅选择原套餐，试用选择标准、默认或首个可用套餐。

成功／失败付款、流量／HWID 加购、付费升级、推荐奖励、流量提醒和支付方式绑定等，也会在 SMTP 可用时发到所选通知邮箱。管理邮件群发使用同一地址；Telegram 私信是独立渠道。

<a id="пользовательские-предпочтения"></a>

## 用户偏好

“个人中心 → 设置 → 通知”提供四个独立开关：邮件营销、邮件系统、Telegram 营销、Telegram 系统。新旧用户默认都开。管理员全局设置是上限，用户同意不能开启全站关闭渠道。

营销包括管理员手动群发及使用公开 Core 受众数据访问层的自动活动。系统包括付款、订阅到期／续费、流量、设备、限额和推荐入账。用户详情私信、登录与账号安全、客服会话不视为群发，仍正常工作。

管理员可在用户详情查看、修改四项。关闭或实际不可用渠道视为正常跳过，不是群发失败，worker 继续处理其他人。自动活动必须通过公开 Core 群发数据访问层获取受众，它已过滤关闭对应营销渠道的用户。

营销和系统邮件底部有签名偏好管理链接，无需登录，但绑定用户及当前通知邮箱。更换邮箱后旧链接失效，偏好保留并应用新地址。合并账号时，关闭优先于开启，合并不会重新启用已关闭渠道。

<a id="кнопка-перехода-к-настройкам"></a>

### 通知设置按钮

在群发／私信按钮编辑器选择“网页应用页面 → 通知设置”，生成本地化按钮，直接打开 `/settings/notifications`；Telegram 深层链接使用安全 `startapp=notifications`。“系统 → 设置 → 菜单按钮”也提供同目标，每个自定义按钮分别设置机器人、Mini App、普通浏览器可见性。

用户邮件需 SMTP 和已验证通知地址，在“设置 → 安全 → 通知邮箱”选择，不随最近登录方式变化。订阅生命周期另需 `SUBSCRIPTION_EMAIL_NOTIFICATIONS_ENABLED=True`，管理客服邮件另由 `SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED` 控制。见[登录方式与邮箱](login-methods.md)。

`USER_NOTIFICATION_PREFERENCES_ENABLED=False` 可完全隐藏偏好：个人中心入口消失，新邮件不添加管理链接，公开偏好接口返回 `404`。

<a id="hwid-устройства"></a>

## HWID 设备

新设备通知使用独立 `user_hwid_devices.added`，不在后台轮询全部用户设备。相同 webhook 按不透明 HMAC 设备指纹去重，原 HWID、请求 IP、User-Agent 不进入队列、日志、域事件或正文。

“新设备”和“设备限额”各有独立 Telegram／邮件开关。新增设备占用最后名额、且同渠道都允许时，合并成一条通知。设备列表不可用时，只发送安全新设备通知，不猜测限额耗尽。无限或未知限额不发限额提醒。

按钮进入“我的设备”。只有订阅有效、当前套餐支持周期付款且配置至少一个付费 HWID 包时才推荐加购。试用、无限套餐、设备页面关闭或无加购包时，只建议释放名额。删除设备通常由用户自行发起，不单独通知，避免重复。

<a id="синхронизация-каналов"></a>

## 渠道同步

面板 webhook 与本地 `SubscriptionNotificationWorker` 共用发送服务和 `subscription_notifications` 去重表。

去重按渠道独立，例如 `before_3d:telegram`、`before_3d:email`。单渠道故障不阻塞另一个；webhook／worker 重复事件不会重复发送已送达通知。

旧无渠道记录如 `before_3d` 视为 Telegram 历史，只阻止重复 Telegram，不阻止升级后邮件。

上游兼容回退：面板 webhook 用户没有本地订阅时，只向载荷 `telegram_id` 发 Telegram，不发邮件、不做渠道去重；不应据此推断独立服务模式会启用旧订阅流程。

<a id="блокировка-торрентов-torrent-blocker"></a>

## Torrent Blocker 限制通知

处理面板 2.7+ 签名 `torrent_blocker.report`，只在 `actionReport.blocked=true` 时发。未实际封禁的报告忽略。用户看到限制原因和自动解封时间，不保存或显示节点名、目标地址、入站／出站及其他 `xrayReport` 技术字段。

开启前检查：

- 面板、Node 为 2.7.0+，Xray-Core 为 26.3.27+。
- Node 容器具备 `NET_ADMIN`，主机有 nftables、Linux 内核 5.7+。
- 入站启用所需 `destOverride` 的流量嗅探，Node Plugin 开启 Torrent Blocker。
- 面板 `WEBHOOK_URL` 为 `WEBHOOK_BASE_URL` + `/webhook/panel`，双方密钥一致。
- 面板通知配置未关闭 `torrent_blocker.report`。

完整要求及事件结构见 [Remnawave Node Plugins 官方文档](https://docs.rw/docs/learn/node-plugins/)。

配置入口“系统 → 设置 → 通知 → Torrent Blocker”：

- `TORRENT_BLOCKER_NOTIFICATIONS_ENABLED`：总开关，需主动开启。
- `TORRENT_BLOCKER_TELEGRAM_NOTIFICATIONS_ENABLED`：Telegram 渠道。
- `TORRENT_BLOCKER_EMAIL_NOTIFICATIONS_ENABLED`：SMTP 邮件渠道。
- `TORRENT_BLOCKER_NOTIFICATION_COOLDOWN_SECONDS`：同一用户同渠道最短间隔；`0` 关闭冷却，不关闭精确去重。
- `TORRENT_BLOCKER_NOTIFICATION_INCLUDE_IP`：正文是否包含被封 IP，隐私原因默认关闭。

模板在“系统 → 翻译 → Torrent Blocker 通知”。Minishop 不调用 `DELETE /api/node-plugins/torrent-blocker/truncate`，保留面板报告供管理统计和其他集成使用。

按官方 `scope=torrent_blocker` 和类型化结构校验。晚于 `willUnblockAt` 送达视为过期，不通知用户。渠道成功独立记录：Telegram 已送达但 SMTP 暂不可用时，只重试邮件。worker 指标 `torrent_blocker_notification_total` 包含渠道与结果，不包含原 IP。
