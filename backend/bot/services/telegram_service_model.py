"""Telegram entry policy for the project's independent service runtime."""

from aiogram import types
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.middlewares.i18n import JsonI18n
from bot.utils.callback_answer import safe_answer_callback
from bot.utils.mini_app_url import subscription_mini_app_path_url
from config.settings import Settings

INDEPENDENT_SERVICES = "independent_services"

_ACCOUNT_ACTIONS = {"toggle_ban", "send_message", "view_logs", "refresh", "delete_user"}
_MAIN_ACTIONS = {
    "language",
    "bot_language",
    "info",
    "bot_info",
    "back_to_main",
    "back_to_main_keep",
    "bot_interface",
}
_ADMIN_ACTIONS = {
    "main",
    "broadcast",
    "ban_user_prompt",
    "unban_user_prompt",
    "users_list",
    "users_search_prompt",
    "view_banned",
    "view_logs_menu",
    "queue_status",
    "view_payments",
    "ads",
    "ads_create",
}
_ADMIN_SECTIONS = {"user_management", "ban_management", "system_functions"}
_CALLBACK_ACTIONS = {
    "user_action": _ACCOUNT_ACTIONS,
    "main_action": _MAIN_ACTIONS,
    "admin_action": _ADMIN_ACTIONS,
    "admin_section": _ADMIN_SECTIONS,
}
_RETIRED_MODULES = (
    "bot.handlers.user.subscription.",
    "bot.handlers.user.trial_handler",
    "bot.handlers.user.promo_user",
    "bot.handlers.user.referral",
    "bot.handlers.admin.promo.",
    "bot.handlers.admin.sync_admin",
    "bot.handlers.admin.statistics",
    "bot.handlers.inline_mode",
)
_RETIRED_STATE_HANDLERS = {
    "process_subscription_days_handler",
    "process_premium_override_bonus_handler",
    "process_hwid_device_limit_handler",
    "process_traffic_grant_gb_handler",
}


def retired_core_callback(value: str | None) -> bool:
    prefix, _, remainder = (value or "").partition(":")
    allowed = _CALLBACK_ACTIONS.get(prefix)
    return allowed is not None and remainder.split(":", 1)[0] not in allowed


def retired_core_handler(module: str, name: str, callback: str | None = None) -> bool:
    if module.startswith("bot.payment_providers."):
        return True
    if not module.startswith("bot.handlers."):
        return False
    return (
        module.startswith(_RETIRED_MODULES)
        or (
            module == "bot.handlers.admin.user_management_state" and name in _RETIRED_STATE_HANDLERS
        )
        or retired_core_callback(callback)
    )


def independent_keyboard(builder: InlineKeyboardBuilder) -> InlineKeyboardBuilder:
    buttons = [
        button for button in builder.buttons if not retired_core_callback(button.callback_data)
    ]
    filtered = InlineKeyboardBuilder()
    filtered.add(*buttons)
    filtered.adjust(2)
    return filtered


async def send_service_portal(
    event: types.Message | types.CallbackQuery,
    settings: Settings,
    i18n_data: dict,
    *,
    is_edit: bool = False,
) -> None:
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    translate = lambda key: i18n.gettext(lang, key) if i18n else key
    text = translate("independent_services_portal_hint")
    builder = InlineKeyboardBuilder()
    for path, key in [("home", "independent_services_open"), ("support", "wa_support_title")]:
        url = subscription_mini_app_path_url(settings, path)
        if url:
            builder.button(text=translate(key), url=url)
    builder.button(
        text=translate("menu_language_settings_inline"), callback_data="main_action:language"
    )
    builder.adjust(1)
    markup = builder.as_markup()
    message = event.message if isinstance(event, types.CallbackQuery) else event
    if isinstance(message, types.Message):
        if is_edit:
            try:
                await message.edit_text(text, reply_markup=markup)
            except TelegramBadRequest:
                await message.answer(text, reply_markup=markup)
        else:
            await message.answer(text, reply_markup=markup)
        if isinstance(event, types.CallbackQuery):
            await safe_answer_callback(event)
    elif isinstance(event, types.CallbackQuery):
        await safe_answer_callback(event, text, show_alert=True)
