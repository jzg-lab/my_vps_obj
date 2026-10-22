"""Keep independent services and the currently open operations UI Chinese."""

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
    "email_login_code_",
    "email_set_password_code_",
    "email_change_",
    "email_support_",
    "email_user_notification_",
    "email_broadcast_",
    "admin_health_",
    "admin_ads_",
    "admin_broadcast_",
    "admin_telegram_emoji_",
    "admin_tg_menu_",
    "admin_error_theme_",
    "admin_documents_",
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
    "admin/sections/BackupsSection.svelte",
    "admin/sections/DocumentsSection.svelte",
    "admin/sections/documents",
    "admin/sections/PluginsSection.svelte",
    "admin/sections/PluginApplyDialog.svelte",
    "admin/sections/PluginImportDialog.svelte",
    "admin/sections/PluginRemoveDialog.svelte",
    "admin/sections/PluginOperations.svelte",
    "admin/sections/AppearanceSection.svelte",
    "admin/sections/appearance",
    "admin/sections/TranslationsSection.svelte",
    "admin/sections/SupportSection.svelte",
    "admin/sections/LogsSection.svelte",
    "admin/sections/BroadcastSection.svelte",
    "admin/sections/BroadcastHistory.svelte",
    "admin/sections/BroadcastFailuresDialog.svelte",
    "admin/sections/AdsSection.svelte",
    "admin/sections/advertising",
    "admin/sections/settings/SettingsContent.svelte",
    "admin/sections/settings/SettingsIconPicker.svelte",
    "admin/sections/settings/AdministratorsSubsection.svelte",
    "admin/sections/settings/RoleManagement.svelte",
    "admin/sections/settings/TelegramMenuAppearance.svelte",
    "admin/sections/settings/TelegramMenuPreview.svelte",
    "admin/sections/settings/MenuButtonsField.svelte",
    "admin/sections/settings/NotificationDeliveryMatrix.svelte",
    "lib/admin/richTextLabels.ts",
    "lib/admin/components",
    "lib/admin/stores/backupsStore.svelte.ts",
    "lib/admin/stores/documentsStore.svelte.ts",
    "lib/admin/stores/logsStore.svelte.ts",
    "lib/admin/stores/settingsStore.svelte.ts",
    "lib/admin/stores/supportStore.svelte.ts",
    "lib/admin/stores/themeLibraryStore.svelte.ts",
    "lib/admin/stores/themesStore.svelte.ts",
    "lib/admin/stores/translationsStore.svelte.ts",
    "lib/admin/stores/usersStoreAccess.ts",
    "lib/admin/stores/usersStoreNotificationPreferences.ts",
    "lib/telegramEmoji",
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
            keys.update(re.findall(r'\bt\(\s*"([a-z0-9_-]+)"', content))
            keys.update("admin_" + key for key in re.findall(r'\bat\(\s*"([a-z0-9_-]+)"', content))
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


def test_chinese_client_guide_example_uses_existing_schema() -> None:
    from config.subscription_guides_config import validate_subscription_guides_config_text

    example = ROOT / "deploy/examples/independent-services-guides.json"
    config = validate_subscription_guides_config_text(example.read_text())
    assert set(config["locales"]) == {"zh", "en", "ru"}
    assert {key: len(value["apps"]) for key, value in config["platforms"].items()} == {
        "android": 3,
        "ios": 3,
        "windows": 4,
        "macos": 4,
        "linux": 4,
        "androidTV": 1,
        "appleTV": 2,
    }
    for content in config["platforms"].values():
        for app in content["apps"]:
            assert not app["featured"]
            assert len(app["blocks"]) == 4
            assert "尚未完成" in app["blocks"][0]["description"]["zh"]
            buttons = [button for block in app["blocks"] for button in block["buttons"]]
            assert any(button["link"] == "{{SUBSCRIPTION_LINK}}" for button in buttons)
            assert all(
                button["link"].startswith("https://") or button["link"] == "{{SUBSCRIPTION_LINK}}"
                for button in buttons
            )
