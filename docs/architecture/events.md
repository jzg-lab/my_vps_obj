# 域事件目录

本文件由 `bot.infra.event_payloads` 生成，请勿手动编辑。
更新命令：`PYTHONPATH=backend python -m bot.infra.event_catalog`。

订阅者继续接收 `(event_name, dict)`。以下模型描述 Core 发布的扁平、JSON 兼容字典。

## `account.email_linked`

事件载荷模型：`AccountEmailLinkedPayload`

发布位置：`backend/bot/app/web/webapp/account.py`

Core 响应：`CoreEventReactions.on_account_email_linked`

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `user_id` | `int` | 必填 |
| `email` | `str` | 必填 |
| `first_link` | `bool` | 必填 |
| `telegram_id` | `int | None` | `None` |
| `username` | `str | None` | `None` |
| `first_name` | `str | None` | `None` |

## `account.external_identity_linked`

事件载荷模型：`AccountExternalIdentityLinkedPayload`

发布位置：`backend/bot/app/web/webapp/external_oauth.py`

Core 响应：`CoreEventReactions.on_account_external_identity_linked`

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `user_id` | `int` | 必填 |
| `provider` | `'discord' | 'google' | 'yandex'` | 必填 |
| `link_source` | `'settings' | 'email_confirmation' | 'provider_verified_email'` | 必填 |
| `email` | `str | None` | `None` |
| `telegram_id` | `int | None` | `None` |
| `username` | `str | None` | `None` |
| `first_name` | `str | None` | `None` |

## `account.merged`

事件载荷模型：`AccountMergedPayload`

发布位置：`backend/db/dal/user_merge_dal.py`

Core 响应：`CoreEventReactions.on_account_merged`

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `source_user_id` | `int` | 必填 |
| `target_user_id` | `int` | 必填 |
| `source_minishop_id` | `str | None` | `None` |
| `target_minishop_id` | `str | None` | `None` |
| `reason` | `str` | 必填 |
| `send_user_email` | `bool` | 必填 |
| `source_panel_user_uuid` | `str | None` | `None` |
| `target_panel_user_uuid` | `str | None` | `None` |
| `email` | `str | None` | `None` |
| `telegram_id` | `int | None` | `None` |
| `username` | `str | None` | `None` |
| `first_name` | `str | None` | `None` |
| `language` | `str | None` | `None` |
| `final_end_date` | `datetime | None` | `None` |

## `account.telegram_linked`

事件载荷模型：`AccountTelegramLinkedPayload`

发布位置：`backend/bot/app/web/webapp/account.py`, `backend/bot/app/web/webapp/account_merge.py`

Core 响应：`CoreEventReactions.on_account_telegram_linked`

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `user_id` | `int` | 必填 |
| `telegram_id` | `int | None` | `None` |
| `first_link` | `bool` | 必填 |
| `email` | `str | None` | `None` |
| `username` | `str | None` | `None` |
| `first_name` | `str | None` | `None` |

## `bot.started`

事件载荷模型：`BotStartedPayload`

发布位置：`backend/bot/services/behavior_events.py`

Core 响应：无

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `user_id` | `int` | 必填 |
| `returning` | `bool` | 必填 |
| `source` | `'direct' | 'referral' | 'promo' | 'ad' | 'ticket' | 'notifications'` | 必填 |
| `start_param` | `str | None` | `None` |

## `device.connected`

事件载荷模型：`DeviceConnectedPayload`

发布位置：`backend/bot/services/hwid_device_notifications.py`

Core 响应：无

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `user_id` | `int` | 必填 |
| `subscription_id` | `int` | 必填 |
| `panel_user_uuid` | `str | None` | `None` |
| `device_label` | `str` | 必填 |
| `platform` | `str | None` | `None` |
| `os_version` | `str | None` | `None` |
| `current_devices` | `int | None` | `None` |
| `device_limit` | `int | None` | `None` |
| `occurred_at` | `datetime` | 必填 |

## `device.limit_reached`

事件载荷模型：`DeviceLimitReachedPayload`

发布位置：`backend/bot/services/hwid_device_notifications.py`

Core 响应：无

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `user_id` | `int` | 必填 |
| `subscription_id` | `int` | 必填 |
| `tariff_key` | `str | None` | `None` |
| `current_devices` | `int` | 必填 |
| `device_limit` | `int` | 必填 |
| `device_topup_available` | `bool` | 必填 |
| `occurred_at` | `datetime` | 必填 |

## `panel.webhook_received`

事件载荷模型：`PanelWebhookReceivedPayload`

发布位置：`backend/bot/services/panel_webhook_service.py`

Core 响应：无

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `event` | `str` | 必填 |
| `panel_user_uuid` | `str | None` | `None` |
| `telegram_id` | `int | str | None` | `None` |

## `partner.application_decided`

事件载荷模型：`PartnerApplicationDecidedPayload`

发布位置：`backend/bot/services/partner_program_service.py`

Core 响应：`CoreEventReactions.on_partner_application_decided`

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `application_id` | `int` | 必填 |
| `partner_id` | `int | None` | `None` |
| `user_id` | `int | None` | `None` |
| `status` | `str` | 必填 |
| `decided_at` | `datetime` | 必填 |

## `partner.application_submitted`

事件载荷模型：`PartnerApplicationSubmittedPayload`

发布位置：`backend/bot/services/partner_program_service.py`

Core 响应：`CoreEventReactions.on_partner_application_submitted`

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `application_id` | `int` | 必填 |
| `user_id` | `int` | 必填 |
| `status` | `str` | 必填 |
| `submitted_at` | `datetime` | 必填 |

## `partner.balance_adjusted`

事件载荷模型：`PartnerBalanceAdjustedPayload`

发布位置：`backend/bot/services/partner_commission_service.py`

Core 响应：无

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `partner_id` | `int` | 必填 |
| `currency` | `str` | 必填 |
| `amount_minor` | `int` | 必填 |
| `balance_minor` | `int` | 必填 |
| `adjusted_at` | `datetime` | 必填 |

## `partner.balance_spent`

事件载荷模型：`PartnerBalanceSpentPayload`

发布位置：`backend/bot/services/partner_checkout_balance.py`, `backend/bot/services/partner_commission_service.py`

Core 响应：无

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `partner_id` | `int` | 必填 |
| `payment_db_id` | `int` | 必填 |
| `currency` | `str` | 必填 |
| `amount_minor` | `int` | 必填 |
| `spent_at` | `datetime` | 必填 |

## `partner.client_attributed`

事件载荷模型：`PartnerClientAttributedPayload`

发布位置：`backend/bot/services/partner_program_service.py`

Core 响应：无

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `partner_id` | `int` | 必填 |
| `partner_client_id` | `int` | 必填 |
| `client_user_id` | `int` | 必填 |
| `source` | `str` | 必填 |
| `attributed_at` | `datetime` | 必填 |

## `partner.commission_available`

事件载荷模型：`PartnerCommissionAvailablePayload`

发布位置：`backend/bot/services/partner_commission_service.py`

Core 响应：无

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `partner_id` | `int` | 必填 |
| `commission_id` | `int` | 必填 |
| `currency` | `str` | 必填 |
| `commission_amount_minor` | `int` | 必填 |
| `available_at` | `datetime` | 必填 |

## `partner.commission_recorded`

事件载荷模型：`PartnerCommissionRecordedPayload`

发布位置：`backend/bot/services/partner_commission_service.py`

Core 响应：无

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `partner_id` | `int` | 必填 |
| `commission_id` | `int` | 必填 |
| `payment_db_id` | `int` | 必填 |
| `status` | `str` | 必填 |
| `currency` | `str` | 必填 |
| `gross_amount_minor` | `int` | 必填 |
| `commission_amount_minor` | `int` | 必填 |
| `available_at` | `datetime` | 必填 |

## `partner.commission_reversed`

事件载荷模型：`PartnerCommissionReversedPayload`

发布位置：`backend/bot/services/partner_commission_service.py`

Core 响应：无

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `partner_id` | `int` | 必填 |
| `commission_id` | `int` | 必填 |
| `payment_db_id` | `int | None` | `None` |
| `currency` | `str` | 必填 |
| `commission_amount_minor` | `int` | 必填 |
| `reversed_at` | `datetime` | 必填 |

## `partner.status_changed`

事件载荷模型：`PartnerStatusChangedPayload`

发布位置：`backend/bot/services/partner_program_service.py`

Core 响应：`CoreEventReactions.on_partner_status_changed`

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `partner_id` | `int` | 必填 |
| `user_id` | `int | None` | `None` |
| `old_status` | `str` | 必填 |
| `status` | `str` | 必填 |
| `changed_at` | `datetime` | 必填 |

## `partner.withdrawal_requested`

事件载荷模型：`PartnerWithdrawalRequestedPayload`

发布位置：`backend/bot/services/partner_withdrawal_service.py`

Core 响应：`CoreEventReactions.on_partner_withdrawal_requested`

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `partner_id` | `int` | 必填 |
| `user_id` | `int` | 必填 |
| `withdrawal_id` | `int` | 必填 |
| `status` | `str` | 必填 |
| `currency` | `str` | 必填 |
| `currency_scale` | `int` | 必填 |
| `amount_minor` | `int` | 必填 |
| `requested_at` | `datetime` | 必填 |

## `partner.withdrawal_status_changed`

事件载荷模型：`PartnerWithdrawalStatusChangedPayload`

发布位置：`backend/bot/services/partner_withdrawal_service.py`

Core 响应：`CoreEventReactions.on_partner_withdrawal_status_changed`

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `partner_id` | `int` | 必填 |
| `user_id` | `int | None` | `None` |
| `withdrawal_id` | `int` | 必填 |
| `old_status` | `str` | 必填 |
| `status` | `str` | 必填 |
| `status_version` | `int` | 必填 |
| `currency` | `str` | 必填 |
| `currency_scale` | `int` | 必填 |
| `amount_minor` | `int` | 必填 |
| `settlement_amount` | `str | None` | `None` |
| `external_reference` | `str | None` | `None` |
| `changed_at` | `datetime` | 必填 |

## `payment.canceled`

事件载荷模型：`PaymentCanceledPayload`

发布位置：`backend/bot/app/web/webapp/billing.py`, `backend/bot/payment_providers/shared/webhooks.py`, `backend/bot/payment_providers/yookassa.py`, `backend/bot/services/yookassa_reconciliation_worker.py`, `backend/main_worker.py`

Core 响应：`CoreEventReactions.on_payment_canceled`

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `user_id` | `int` | 必填 |
| `payment_db_id` | `int | None` | `None` |
| `provider` | `str | None` | `None` |
| `provider_payment_id` | `str | None` | `None` |
| `status` | `str | None` | `None` |
| `message_key` | `str | None` | `None` |
| `cancellation_party` | `str | None` | `None` |
| `cancellation_reason` | `str | None` | `None` |
| `auto_renew_cycle_id` | `int | None` | `None` |
| `auto_renew_retry_scheduled` | `bool` | `False` |
| `retry_at` | `datetime | None` | `None` |

## `payment.succeeded`

事件载荷模型：`PaymentSucceededPayload`

发布位置：`backend/bot/app/web/admin_api_impl/gift_creation.py`, `backend/bot/infra/payment_events.py`, `backend/bot/payment_providers/shared/gift_success.py`, `backend/bot/payment_providers/shared/success.py`, `backend/bot/payment_providers/yookassa.py`

Core 响应：`CoreEventReactions.on_payment_succeeded`

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `user_id` | `int` | 必填 |
| `payment_db_id` | `int` | 必填 |
| `provider` | `str` | 必填 |
| `notification_provider` | `str` | 必填 |
| `amount` | `float` | 必填 |
| `currency` | `str` | 必填 |
| `sale_mode` | `str` | 必填 |
| `tariff_key` | `str | None` | `None` |
| `months` | `int | None` | `None` |
| `duration_days` | `int | None` | `None` |
| `traffic_gb` | `float | None` | `None` |
| `purchased_hwid_devices` | `int | None` | `None` |
| `promo_code_id` | `int | None` | `None` |
| `base_amount` | `float | None` | `None` |
| `discount_amount` | `float | None` | `None` |
| `end_date` | `datetime | None` | `None` |
| `is_auto_renew` | `bool` | 必填 |
| `renewal_subscription_id` | `int | None` | `None` |

## `plans.viewed`

事件载荷模型：`PlansViewedPayload`

发布位置：`backend/bot/app/web/webapp/billing_contracts.py`, `backend/bot/app/web/webapp/billing_options.py`, `backend/bot/app/web/webapp/payloads.py`, `backend/bot/services/behavior_events.py`

Core 响应：无

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `user_id` | `int` | 必填 |
| `source` | `'webapp' | 'bot'` | 必填 |
| `plans_count` | `int` | 必填 |
| `tariff_key` | `str | None` | `None` |

## `promo_code.applied`

事件载荷模型：`PromoCodeAppliedPayload`

发布位置：`backend/bot/services/promo_code_service.py`

Core 响应：`CoreEventReactions.on_promo_code_applied`

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `user_id` | `int` | 必填 |
| `code` | `str` | 必填 |
| `bonus_days` | `int` | 必填 |
| `regular_traffic_gb` | `float` | `0` |
| `premium_traffic_gb` | `float` | `0` |
| `new_end_date` | `datetime | None` | `None` |

## `referral.bonus_granted`

事件载荷模型：`ReferralBonusGrantedPayload`

发布位置：`backend/bot/app/web/webapp/auth.py`, `backend/bot/handlers/user/start.py`, `backend/bot/payment_providers/shared/success.py`, `backend/bot/payment_providers/yookassa.py`, `backend/bot/services/referral_accrual_worker.py`, `backend/bot/services/referral_service.py`, `backend/bot/services/subscription_service_impl/trial.py`

Core 响应：`CoreEventReactions.on_referral_bonus_granted`

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `referee_user_id` | `int` | 必填 |
| `referee_bonus_days` | `int | None` | `None` |
| `referee_new_end_date` | `datetime | None` | `None` |
| `inviter_bonus_applied` | `bool` | 必填 |
| `inviter_user_id` | `int | None` | `None` |
| `inviter_bonus_days` | `int | None` | `None` |
| `inviter_bonus_end_date` | `datetime | None` | `None` |
| `inviter_bonus_kind` | `'extended' | 'new_sub' | None` | `None` |
| `referee_name` | `str | None` | `None` |
| `payment_db_id` | `int | None` | `None` |
| `purchased_subscription_months` | `int | None` | `None` |
| `purchased_subscription_days` | `int | None` | `None` |
| `tariff_key` | `str | None` | `None` |
| `one_bonus_per_referee` | `bool | None` | `None` |
| `gift_id` | `int | None` | `None` |
| `reason` | `'payment' | 'welcome' | 'gift_activation'` | 必填 |

## `subscription.auto_renew_failed`

事件载荷模型：`SubscriptionAutoRenewFailedPayload`

发布位置：`backend/bot/payment_providers/shared/webhooks.py`, `backend/bot/services/subscription_service_impl/renewal.py`

Core 响应：无

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `user_id` | `int` | 必填 |
| `subscription_id` | `int` | 必填 |
| `provider` | `str` | 必填 |
| `reason_code` | `'provider_unavailable' | 'saved_payment_method_missing' | 'renewal_quote_unavailable' | 'provider_request_failed' | 'provider_rejected' | 'provider_webhook_failed'` | 必填 |
| `payment_db_id` | `int | None` | `None` |
| `provider_payment_id` | `str | None` | `None` |
| `renewal_cycle_end` | `datetime | None` | `None` |
| `retryable` | `bool` | 必填 |
| `occurred_at` | `datetime` | 必填 |

## `subscription.created`

事件载荷模型：`SubscriptionCreatedPayload`

发布位置：`backend/bot/payment_providers/shared/success.py`, `backend/bot/payment_providers/yookassa.py`

Core 响应：无

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `user_id` | `int` | 必填 |
| `subscription_id` | `int | None` | `None` |
| `tariff_key` | `str | None` | `None` |
| `end_date` | `datetime | None` | `None` |
| `provider` | `str | None` | `None` |
| `months` | `int | None` | `None` |
| `duration_days` | `int | None` | `None` |
| `payment_db_id` | `int | None` | `None` |

## `subscription.expired`

事件载荷模型：`SubscriptionExpiredPayload`

发布位置：`backend/bot/services/subscription_notification_worker.py`

Core 响应：无

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `user_id` | `int` | 必填 |
| `subscription_id` | `int | None` | `None` |
| `tariff_key` | `str | None` | `None` |
| `end_date` | `datetime | None` | `None` |

## `subscription.extended`

事件载荷模型：`SubscriptionExtendedPayload`

发布位置：`backend/bot/payment_providers/shared/success.py`, `backend/bot/payment_providers/yookassa.py`

Core 响应：无

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `user_id` | `int` | 必填 |
| `subscription_id` | `int | None` | `None` |
| `tariff_key` | `str | None` | `None` |
| `end_date` | `datetime | None` | `None` |
| `provider` | `str | None` | `None` |
| `months` | `int | None` | `None` |
| `duration_days` | `int | None` | `None` |
| `payment_db_id` | `int | None` | `None` |

## `subscription.lapsed`

事件载荷模型：`SubscriptionLapsedPayload`

发布位置：`backend/bot/services/subscription_notification_worker.py`

Core 响应：无

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `user_id` | `int` | 必填 |
| `subscription_id` | `int | None` | `None` |
| `tariff_key` | `str | None` | `None` |
| `end_date` | `datetime | None` | `None` |

## `support.message_created`

事件载荷模型：`SupportMessageCreatedPayload`

发布位置：`backend/bot/services/support_service.py`

Core 响应：无

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `user_id` | `int` | 必填 |
| `ticket_id` | `int` | 必填 |
| `message_id` | `int` | 必填 |
| `author_role` | `str` | 必填 |
| `is_internal_note` | `bool` | 必填 |
| `revision` | `int` | 必填 |
| `change_cursor` | `int` | 必填 |
| `source` | `str | None` | `None` |

## `support.ticket_created`

事件载荷模型：`SupportTicketCreatedPayload`

发布位置：`backend/bot/services/support_service.py`

Core 响应：无

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `user_id` | `int` | 必填 |
| `ticket_id` | `int` | 必填 |
| `category` | `str` | 必填 |
| `priority` | `str` | 必填 |

## `support.ticket_updated`

事件载荷模型：`SupportTicketUpdatedPayload`

发布位置：`backend/bot/services/support_service.py`

Core 响应：无

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `user_id` | `int` | 必填 |
| `ticket_id` | `int` | 必填 |
| `status` | `str` | 必填 |
| `revision` | `int` | 必填 |
| `change_cursor` | `int` | 必填 |
| `assigned_admin_id` | `int | None` | `None` |

## `trial.activated`

事件载荷模型：`TrialActivatedPayload`

发布位置：`backend/bot/payment_providers/shared/success.py`, `backend/bot/services/subscription_service_impl/trial.py`

Core 响应：`CoreEventReactions.on_trial_activated`

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `user_id` | `int` | 必填 |
| `end_date` | `datetime | None` | `None` |
| `days` | `int` | 必填 |
| `traffic_gb` | `float | None` | `None` |

## `user.registered`

事件载荷模型：`UserRegisteredPayload`

发布位置：`backend/bot/app/web/webapp/external_oauth.py`, `backend/db/dal/user_dal.py`

Core 响应：`CoreEventReactions.on_user_registered`

| 字段 | 类型 | 默认值 |
| --- | --- | --- |
| `user_id` | `int` | 必填 |
| `account_id` | `str | None` | `None` |
| `minishop_id` | `str | None` | `None` |
| `telegram_id` | `int | None` | `None` |
| `username` | `str | None` | `None` |
| `first_name` | `str | None` | `None` |
| `email` | `str | None` | `None` |
| `language` | `str | None` | `None` |
| `referred_by_id` | `int | None` | `None` |
| `partner_user_id` | `int | None` | `None` |
| `registered_via` | `'telegram' | 'email' | 'discord_oauth' | 'google_oauth' | 'yandex_oauth' | 'panel_sync' | 'unknown'` | 必填 |
