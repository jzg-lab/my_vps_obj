import base64
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from bot.services import email_templates as email_templates_module  # noqa: E402
from bot.services.email_templates import (  # noqa: E402
    render_account_merged,
    render_login_code,
    render_payment_success,
    render_subscription_expiring,
    render_subscription_lifecycle_notification,
    render_support_admin_reply_user,
    render_support_new_ticket_admin,
    render_support_ticket_closed_user,
    render_support_user_reply_admin,
    render_user_notification,
)

LANGUAGE = "zh-hans"
PREVIEW_LOGO_FILE = (
    REPO_ROOT
    / "backend"
    / "bot"
    / "app"
    / "web"
    / "templates"
    / "default-brand"
    / "favicons"
    / "19b2a242e5b7bc2d"
    / "icon-180.png"
)
PREVIEW_LOGO_TEMP_DIR = tempfile.TemporaryDirectory()


def prepare_preview_logo_url() -> str:
    if not PREVIEW_LOGO_FILE.exists():
        return ""
    body = PREVIEW_LOGO_FILE.read_bytes()
    digest = hashlib.sha256(body).hexdigest()[:16]
    filename = f"logo-{digest}.png"
    logo_dir = Path(PREVIEW_LOGO_TEMP_DIR.name)
    (logo_dir / filename).write_bytes(body)
    email_templates_module._WEBAPP_UPLOADED_LOGO_DIR = logo_dir
    return f"/webapp-uploaded-logo/{filename}"


PREVIEW_LOGO_URL = prepare_preview_logo_url()


class PreviewI18n:
    def __init__(self, path: Path, default: str = "zh-hans"):
        self.default_lang = default
        self.locales_data = {}
        for item in path.glob("*.json"):
            try:
                data = json.loads(item.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                self.locales_data[item.stem] = {
                    str(key): str(value) for key, value in data.items() if isinstance(value, str)
                }

    def gettext(self, lang_code: str | None, key: str, **kwargs) -> str:
        requested = str(lang_code or "").strip().lower().replace("_", "-")
        requested_base = requested.split("-", 1)[0]
        if requested in self.locales_data:
            messages = self.locales_data[requested]
        elif requested_base in self.locales_data:
            messages = self.locales_data[requested_base]
        else:
            messages = self.locales_data.get(self.default_lang) or self.locales_data.get("en", {})
        template = messages.get(key)
        if template is None and self.default_lang in self.locales_data:
            template = self.locales_data[self.default_lang].get(key)
        if template is None:
            template = key
        try:
            return template.format(**kwargs) if kwargs else template
        except Exception:
            return template


def settings():
    return SimpleNamespace(
        DEFAULT_LANGUAGE=LANGUAGE,
        EMAIL_CODE_TTL_SECONDS=600,
        WEBAPP_LOGO_URL=PREVIEW_LOGO_URL,
        WEBAPP_PRIMARY_COLOR="#00fe7a",
        WEBAPP_TITLE="remnawave-minishop",
    )


I18N = PreviewI18n(REPO_ROOT / "locales", default=LANGUAGE)
SETTINGS = settings()
SAMPLE = {
    "amount": 390,
    "code": "483921",
    "currency": "RUB",
    "dashboard_url": "https://mini.example.com/app",
    "end_date": "21.06.2026, 18:00",
    "magic_url": "https://mini.example.com/app/auth/magic/preview",
    "premium_traffic": 25,
    "regular_traffic": 100,
    "ticket_url": "https://mini.example.com/app/support/42",
}


def t(key: str, **kwargs) -> str:
    return I18N.gettext(LANGUAGE, key, **kwargs)


def preview(item_id: str, category: str, title: str, content):
    return {
        "id": item_id,
        "category": category,
        "title": title,
        "subject": content.subject,
        "html": preview_html(content),
    }


def preview_html(content):
    rendered = content.html
    for image in content.inline_images:
        data_url = (
            f"data:{image.content_type};base64,{base64.b64encode(image.data).decode('ascii')}"
        )
        rendered = rendered.replace(f"cid:{image.content_id}", data_url)
    return rendered


def payment_preview(
    item_id: str,
    title: str,
    sale_mode: str,
    *,
    months: int = 0,
    traffic_gb: float | None = None,
):
    return preview(
        item_id,
        "付款",
        title,
        render_payment_success(
            SETTINGS,
            language_code=LANGUAGE,
            sale_mode=sale_mode,
            months=months,
            traffic_gb=traffic_gb,
            amount=SAMPLE["amount"],
            currency=SAMPLE["currency"],
            end_date_text=SAMPLE["end_date"],
            dashboard_url=SAMPLE["dashboard_url"],
            provider_label="YooKassa",
            i18n=I18N,
        ),
    )


def user_notification_preview(
    item_id: str,
    title: str,
    subject_key: str,
    message_text: str,
    *,
    cta_label_key: str = "email_user_notification_cta",
):
    subject = t(subject_key)
    return preview(
        item_id,
        "通知",
        title,
        render_user_notification(
            SETTINGS,
            language_code=LANGUAGE,
            subject=subject,
            heading=subject,
            intro=t("email_user_notification_intro"),
            message_text=message_text,
            dashboard_url=SAMPLE["dashboard_url"],
            cta_label=t(cta_label_key),
            i18n=I18N,
        ),
    )


def expiring_preview(item_id: str, title: str, days_left: int):
    return preview(
        item_id,
        "订阅",
        title,
        render_subscription_expiring(
            SETTINGS,
            language_code=LANGUAGE,
            days_left=days_left,
            end_date_text=SAMPLE["end_date"],
            dashboard_url=SAMPLE["dashboard_url"],
            i18n=I18N,
        ),
    )


def lifecycle_preview(
    item_id: str,
    title: str,
    notification_key: str,
    message_text: str,
    *,
    mirrored_from_telegram: bool = False,
    days_left: int | None = None,
    hours_before: int | None = None,
):
    return preview(
        item_id,
        "订阅",
        title,
        render_subscription_lifecycle_notification(
            SETTINGS,
            language_code=LANGUAGE,
            notification_key=notification_key,
            message_text=message_text,
            end_date_text=SAMPLE["end_date"],
            dashboard_url=SAMPLE["dashboard_url"],
            mirrored_from_telegram=mirrored_from_telegram,
            days_left=days_left,
            hours_before=hours_before,
            i18n=I18N,
        ),
    )


def support_snapshot_rows():
    return [
        ("email_support_row_tariff", "Premium"),
        ("email_support_row_remaining", "3 天 4 小时"),
    ]


EMAIL_PREVIEWS = [
    preview(
        "login-code",
        "访问",
        "登录验证码",
        render_login_code(
            SETTINGS,
            code=SAMPLE["code"],
            language_code=LANGUAGE,
            magic_link=SAMPLE["magic_url"],
            purpose="login",
            i18n=I18N,
        ),
    ),
    preview(
        "set-password-code",
        "访问",
        "创建密码验证码",
        render_login_code(
            SETTINGS,
            code=SAMPLE["code"],
            language_code=LANGUAGE,
            purpose="set_password",
            i18n=I18N,
        ),
    ),
    preview(
        "account-merged",
        "账号",
        "账号已合并",
        render_account_merged(
            SETTINGS,
            language_code=LANGUAGE,
            primary_user_id=100200300,
            removed_user_id=-42,
            final_end_date_text=SAMPLE["end_date"],
            i18n=I18N,
        ),
    ),
    payment_preview(
        "payment-subscription",
        "订阅付款",
        "subscription",
        months=1,
    ),
    payment_preview(
        "payment-traffic",
        "购买流量",
        "traffic",
        traffic_gb=SAMPLE["regular_traffic"],
    ),
    payment_preview(
        "payment-premium-traffic",
        "购买高级流量",
        "premium_topup",
        traffic_gb=SAMPLE["premium_traffic"],
    ),
    payment_preview("payment-hwid", "增加 HWID 设备", "hwid_device", months=2),
    payment_preview("payment-tariff-upgrade", "付费升级套餐", "tariff_upgrade"),
    user_notification_preview(
        "payment-failed",
        "付款失败",
        "email_payment_failed_subject",
        "付款未完成，可从个人中心重试。",
    ),
    user_notification_preview(
        "payment-method-bound",
        "支付方式已绑定",
        "email_payment_method_bound_subject",
        "已开启自动续期，下次将自动付款。",
    ),
    user_notification_preview(
        "referral-bonus",
        "邀请奖励",
        "email_referral_bonus_subject",
        "好友已激活订阅，奖励天数已加到您的账号。",
    ),
    user_notification_preview(
        "trial-traffic-depleted",
        "试用流量已耗尽",
        "email_trial_traffic_depleted_subject",
        "试用流量已用完，请开通订阅继续使用。",
    ),
    user_notification_preview(
        "regular-traffic-almost",
        "普通流量即将耗尽",
        "email_traffic_warning_regular_almost_subject",
        "套餐流量已使用超过 85%，可提前加购流量包。",
        cta_label_key="email_traffic_warning_regular_cta",
    ),
    user_notification_preview(
        "regular-traffic-depleted",
        "普通流量已耗尽",
        "email_traffic_warning_regular_depleted_subject",
        "套餐流量已用完，请加购流量包恢复访问。",
        cta_label_key="email_traffic_warning_regular_cta",
    ),
    user_notification_preview(
        "premium-traffic-almost",
        "高级流量即将耗尽",
        "email_traffic_warning_premium_almost_subject",
        "高级流量剩余较少，可在耗尽前加购。",
        cta_label_key="email_traffic_warning_premium_cta",
    ),
    user_notification_preview(
        "premium-traffic-depleted",
        "高级流量已耗尽",
        "email_traffic_warning_premium_depleted_subject",
        ("高级流量已用完，请加购流量包，以继续使用高级线路。"),
        cta_label_key="email_traffic_warning_premium_cta",
    ),
    expiring_preview(
        "subscription-expiring-today",
        "订阅今天到期",
        0,
    ),
    expiring_preview(
        "subscription-expiring-tomorrow",
        "订阅明天到期",
        1,
    ),
    expiring_preview(
        "subscription-expiring-days",
        "订阅即将到期",
        3,
    ),
    lifecycle_preview(
        "lifecycle-before-days",
        "生命周期：还剩几天",
        "before_days",
        "订阅即将到期，请提前续期以避免中断。",
        days_left=3,
    ),
    lifecycle_preview(
        "lifecycle-before-hours",
        "生命周期：还剩几小时",
        "before_hours",
        "距离订阅到期只剩几小时。",
        hours_before=6,
    ),
    lifecycle_preview(
        "lifecycle-expired",
        "生命周期：订阅已到期",
        "expired",
        "订阅已到期，请在个人中心续期。",
    ),
    lifecycle_preview(
        "lifecycle-expired-after",
        "生命周期：订阅昨天到期",
        "expired_24h_after",
        "订阅昨天已停用，可续期恢复访问。",
    ),
    lifecycle_preview(
        "lifecycle-autorenew",
        "生命周期：明天自动续期",
        "before_2d_autorenew",
        "订阅将在明天自动续期。",
    ),
    lifecycle_preview(
        "lifecycle-mirrored",
        "生命周期：Telegram 通知副本",
        "before_days",
        "此邮件是 Telegram 重要通知的副本。",
        mirrored_from_telegram=True,
        days_left=2,
    ),
    preview(
        "support-new-ticket-admin",
        "支持",
        "管理员新工单通知",
        render_support_new_ticket_admin(
            SETTINGS,
            I18N,
            LANGUAGE,
            ticket_id=42,
            user_display="alex@example.com",
            subject="无法连接",
            body_preview="用户续期后无法连接。",
            snapshot_rows=support_snapshot_rows(),
            ticket_url="https://mini.example.com/app/admin/support/42",
        ),
    ),
    preview(
        "support-user-reply-admin",
        "支持",
        "管理员收到用户回复",
        render_support_user_reply_admin(
            SETTINGS,
            I18N,
            LANGUAGE,
            ticket_id=42,
            user_display="alex@example.com",
            subject="无法连接",
            body_preview="手机和笔记本上都出现相同问题。",
            snapshot_rows=support_snapshot_rows(),
            ticket_url="https://mini.example.com/app/admin/support/42",
        ),
    ),
    preview(
        "support-admin-reply-user",
        "支持",
        "用户收到客服回复",
        render_support_admin_reply_user(
            SETTINGS,
            I18N,
            LANGUAGE,
            ticket_id=42,
            subject="无法连接",
            body_preview="配置已更新，请重新尝试连接。",
            ticket_url=SAMPLE["ticket_url"],
        ),
    ),
    preview(
        "support-ticket-closed-user",
        "支持",
        "工单已关闭",
        render_support_ticket_closed_user(
            SETTINGS,
            I18N,
            LANGUAGE,
            ticket_id=42,
            subject="无法连接",
            ticket_url=SAMPLE["ticket_url"],
        ),
    ),
]

print(json.dumps(EMAIL_PREVIEWS, ensure_ascii=False))
