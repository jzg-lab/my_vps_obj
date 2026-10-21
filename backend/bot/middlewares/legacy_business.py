"""Stop old core entitlement handlers after normal routing and authorization."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, types
from aiogram.dispatcher.event.handler import HandlerObject
from aiogram.fsm.context import FSMContext

from bot.infra.webhook_queue import enqueue_webhook_event
from bot.services.telegram_service_model import (
    INDEPENDENT_SERVICES,
    retired_core_handler,
    send_service_portal,
)
from config.settings import Settings


class LegacyBusinessMiddleware(BaseMiddleware):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[types.TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: types.TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        i18n_data = {**data.get("i18n_data", {}), INDEPENDENT_SERVICES: True}
        data["i18n_data"] = i18n_data
        matched = data.get("handler")
        if isinstance(matched, HandlerObject) and retired_core_handler(
            getattr(matched.callback, "__module__", ""),
            getattr(matched.callback, "__name__", ""),
            event.data if isinstance(event, types.CallbackQuery) else None,
        ):
            state = data.get("state")
            if isinstance(state, FSMContext):
                await state.clear()
            if isinstance(event, types.InlineQuery):
                await event.answer(results=[], cache_time=0, is_personal=True)
            elif isinstance(event, types.PreCheckoutQuery):
                i18n = i18n_data.get("i18n_instance")
                text = (
                    i18n.gettext(
                        i18n_data.get("current_language", self.settings.DEFAULT_LANGUAGE),
                        "independent_services_payment_disabled",
                    )
                    if i18n
                    else "Payments are unavailable. Contact the administrator."
                )
                await event.answer(ok=False, error_message=text)
            elif isinstance(event, (types.Message, types.CallbackQuery)):
                if isinstance(event, types.Message) and event.successful_payment:
                    saved = await enqueue_webhook_event(
                        self.settings,
                        "retired_telegram_payment",
                        {
                            "telegram_user_id": event.from_user.id if event.from_user else None,
                            "chat_id": event.chat.id,
                            "message_id": event.message_id,
                            "payment": event.successful_payment.model_dump(mode="json"),
                        },
                        event_id=event.successful_payment.telegram_payment_charge_id,
                    )
                    if not saved:
                        raise RuntimeError("Cannot retain retired Telegram payment receipt")
                await send_service_portal(event, self.settings, i18n_data)
            return None
        return await handler(event, data)
