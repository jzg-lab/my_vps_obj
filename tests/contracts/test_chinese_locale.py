"""Keep the independent-service UI Chinese as new screens and states are added.

The upstream payment/marketing editors are not the phase-one surface. Their
English/Russian catalogs remain unchanged; this guard follows the open routes.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import cast

from bot.app.web.admin_settings_manifest import manifest_payload
from bot.middlewares.i18n import resolve_locale_key

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend/src"
# Direct and computed service/status keys; new A/B states must not silently fall back.
PREFIXES = (
    "wa_services_",
    "admin_services_",
    "admin_account_access_",
    "admin_independent_",
    "wa_auth_",
    "wa_security_",
    "wa_password_",
    "wa_qr_",
    "wa_support_",
    "wa_install_",
    "wa_app_launch_",
    "admin_user_merge_",
)
SOURCES = (
    "webapp/auth",
    "webapp/security",
    "webapp/screens/ServicesScreen.svelte",
    "webapp/screens/SettingsScreen.svelte",
    "webapp/screens/SecurityScreen.svelte",
    "webapp/screens/NotificationSettingsScreen.svelte",
    "webapp/screens/StatusScreen.svelte",
    "webapp/screens/SupportScreen.svelte",
    "webapp/screens/SupportTicketScreen.svelte",
    "admin/sections/services",
    "admin/sections/ServicePlansSection.svelte",
    "admin/sections/DedicatedExitsSection.svelte",
    "admin/sections/ServiceHistorySection.svelte",
    "admin/sections/users",
    "lib/components/patterns/admin",
)
# These calls sit in legacy-only branches of the shared Settings/Security screens.
RETIRED_KEYS = {
    "wa_nav_partner",
    "wa_payment_history_open",
    "wa_payment_history_title",
    "wa_balance_title",
    "wa_balance_topup",
    "wa_activate_promo_title",
    "wa_subscription_reissue_action",
    "wa_settings_subscription_reissue_hint",
    "wa_security_subscription_access",
    "wa_subscription_reissue_title",
    "wa_subscription_reissue_warning",
    "wa_subscription_reissue_confirm",
    "wa_subscription_reissue_done",
    "wa_subscription_reissue_done_telegram",
    "wa_subscription_reissue_done_app",
    "wa_subscription_reissue_requires_subscription",
    "wa_subscription_reissue_failed",
}


def _locale(code: str) -> dict[str, str]:
    return cast(dict[str, str], json.loads((ROOT / f"locales/{code}.json").read_text()))


def _surface_keys() -> set[str]:
    english = _locale("en")
    keys = {key for key in english if key.startswith(PREFIXES)}
    for name in SOURCES:
        path = SRC / name
        assert path.exists(), name
        for source in path.rglob("*") if path.is_dir() else [path]:
            if source.suffix not in {".svelte", ".ts"} or ".test." in source.name:
                continue
            content = source.read_text()
            keys.update(re.findall(r'\bt\(\s*"([a-z0-9_]+)"', content))
            keys.update("admin_" + key for key in re.findall(r'\bat\(\s*"([a-z0-9_]+)"', content))
    for field in manifest_payload():
        if field["section"] in {"pricing", "payments", "trial", "referral", "devices"}:
            continue
        if field["key"] in {
            "GIFTS_ENABLED",
            "USER_TRAFFIC_STRATEGY",
            "PANEL_WEBHOOK_SECRET",
            "USER_SQUAD_UUIDS",
            "USER_EXTERNAL_SQUAD_UUID",
        }:
            continue
        for part in ("label", "description", "placeholder", "subsection"):
            key = field.get(f"i18n_{part}_key")
            if isinstance(key, str) and key in english:
                keys.add(key)
    return {resolve_locale_key(key) for key in keys - RETIRED_KEYS}


def test_phase_one_chinese_keys_are_present() -> None:
    chinese = _locale("zh-hans")
    missing = sorted(key for key in _surface_keys() if not chinese.get(key, "").strip())
    assert not missing, f"Phase-one Chinese translations missing: {missing}"


def test_chinese_preserves_placeholders_and_rich_text_contracts() -> None:
    english = _locale("en")
    russian = _locale("ru")
    for key, translation in _locale("zh-hans").items():
        assert key in english and key in russian, f"Missing base key: {key}"
        assert translation.strip(), key
        tokens = r"\{[A-Za-z_]\w*(?::[^}]+)?\}"
        assert Counter(re.findall(tokens, translation)) == Counter(
            re.findall(tokens, english[key])
        ), key
        tags = r"</?(?:b|i|u|s|a|code|pre|strong|em|span|tg-emoji)\b[^>]*>"
        assert Counter(re.findall(tags, translation)) == Counter(re.findall(tags, english[key])), (
            key
        )
