"""Core Telegram routing cannot revive the retired single-subscription business."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from aiogram import Bot, Dispatcher, F, Router, types

from bot.handlers.admin.user_management_cards import format_user_card, get_user_card_keyboard
from bot.handlers.user import start_flow, start_menus
from bot.keyboards.inline.admin_keyboards import (
    get_admin_panel_keyboard,
    get_system_functions_keyboard,
    get_user_management_keyboard,
)
from bot.middlewares.i18n import JsonI18n
from bot.routers import build_root_router
from bot.services.telegram_service_model import (
    INDEPENDENT_SERVICES,
    retired_core_callback,
    retired_core_handler,
    send_service_portal,
)
from config.settings import Settings
from db.models import User
from tests.unit.test_user_services import ServiceDatabaseTestCase


def settings() -> Settings:
    return Settings(
        POSTGRES_USER="test",
        POSTGRES_PASSWORD="test",
        _env_file=None,
        SUBSCRIPTION_MINI_APP_URL="https://example.test/shop/",
        DEFAULT_LANGUAGE="en",
        REFERRAL_WELCOME_BONUS_DAYS=3,
        PARTNER_AUTO_ENROLLMENT_ENABLED=True,
    )


def message(bot: Bot, text: str = "/start") -> types.Message:
    return types.Message(
        message_id=1,
        date=datetime.now(UTC),
        text=text,
        chat=types.Chat(id=42, type="private"),
        from_user=types.User(id=42, is_bot=False, first_name="Test"),
    ).as_(bot)


class TelegramRetirementTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.settings = settings()
        self.i18n = JsonI18n("locales")
        self.data = {
            "current_language": "en",
            "i18n_instance": self.i18n,
            INDEPENDENT_SERVICES: True,
        }

    async def test_real_router_stops_old_buttons_and_stale_state_but_preserves_plugin_handler(
        self,
    ) -> None:
        public = Router()
        called = AsyncMock()

        async def old_callback(callback: types.CallbackQuery) -> None:
            await called(callback)

        async def process_traffic_grant_gb_handler(message: types.Message) -> None:
            await called(message)

        async def plugin_callback(callback: types.CallbackQuery, i18n_data: dict) -> None:
            await called(callback, i18n_data)

        old_callback.__module__ = "bot.handlers.user.start_callbacks"
        process_traffic_grant_gb_handler.__module__ = "bot.handlers.admin.user_management_state"
        plugin_callback.__module__ = "test_plugin.handlers"
        public.callback_query.register(old_callback, F.data == "main_action:request_trial")
        public.message.register(process_traffic_grant_gb_handler, F.text == "100")
        public.callback_query.register(plugin_callback, F.data == "main_action:subscribe")
        portal = AsyncMock()
        bot = Bot("12345:TEST", session=AsyncMock())
        dp = Dispatcher()
        with (
            patch("bot.routers.user_router_aggregate", public),
            patch("bot.routers.admin_router_aggregate", Router()),
            patch("bot.routers.inline_mode.router", Router()),
            patch("bot.middlewares.legacy_business.send_service_portal", portal),
        ):
            dp.include_router(build_root_router(self.settings))
            context = dp.fsm.get_context(bot=bot, chat_id=42, user_id=42)
            await context.set_state("old_traffic_grant")
            await context.update_data(target_user_id=99)
            incoming = types.CallbackQuery(
                id="trial",
                from_user=types.User(id=42, is_bot=False, first_name="Test"),
                chat_instance="test",
                message=message(bot),
                data="main_action:request_trial",
            )
            await dp.feed_update(
                bot, types.Update(update_id=1, callback_query=incoming), i18n_data=self.data
            )
            await dp.feed_update(
                bot, types.Update(update_id=2, message=message(bot, "100")), i18n_data=self.data
            )
            called.assert_not_awaited()
            assert portal.await_count == 2
            assert await context.get_state() is None
            assert await context.get_data() == {}
            incoming = incoming.model_copy(update={"data": "main_action:subscribe"})
            await dp.feed_update(
                bot, types.Update(update_id=3, callback_query=incoming), i18n_data=self.data
            )
            called.assert_awaited_once()
        await dp.storage.close()

    async def test_payment_and_inline_updates_cannot_apply_old_entitlements(self) -> None:
        public, inline = Router(), Router()
        called = AsyncMock()

        async def payment_handler(event: types.TelegramObject) -> None:
            await called(event)

        async def inline_handler(event: types.InlineQuery) -> None:
            await called(event)

        payment_handler.__module__ = "bot.payment_providers.stars.service"
        inline_handler.__module__ = "bot.handlers.inline_mode"
        public.callback_query.register(payment_handler)
        public.pre_checkout_query.register(payment_handler)
        public.message.register(payment_handler, F.successful_payment)
        inline.inline_query.register(inline_handler)
        bot_session = AsyncMock(return_value=True)
        bot = Bot("12345:TEST", session=bot_session)
        dp = Dispatcher()
        portal, enqueue = AsyncMock(), AsyncMock(return_value=True)
        actor = types.User(id=42, is_bot=False, first_name="Test")
        receipt = types.SuccessfulPayment(
            currency="XTR",
            total_amount=100,
            invoice_payload="old-invoice",
            telegram_payment_charge_id="telegram-charge",
            provider_payment_charge_id="provider-charge",
        )
        with (
            patch("bot.routers.user_router_aggregate", public),
            patch("bot.routers.admin_router_aggregate", Router()),
            patch("bot.routers.inline_mode.router", inline),
            patch("bot.middlewares.legacy_business.send_service_portal", portal),
            patch("bot.middlewares.legacy_business.enqueue_webhook_event", enqueue),
        ):
            dp.include_router(build_root_router(self.settings))
            await dp.feed_update(
                bot,
                types.Update(
                    update_id=1,
                    callback_query=types.CallbackQuery(
                        id="pay",
                        from_user=actor,
                        chat_instance="test",
                        message=message(bot),
                        data="pay_stars:old-invoice",
                    ),
                ),
                i18n_data=self.data,
            )
            portal.assert_awaited_once()
            await dp.feed_update(
                bot,
                types.Update(
                    update_id=2,
                    pre_checkout_query=types.PreCheckoutQuery(
                        id="checkout",
                        from_user=actor,
                        currency="XTR",
                        total_amount=100,
                        invoice_payload="old-invoice",
                    ),
                ),
                i18n_data=self.data,
            )
            answer = bot_session.call_args.args[1]
            assert answer.ok is False
            assert answer.error_message == self.i18n.gettext(
                "en", "independent_services_payment_disabled"
            )
            paid = message(bot).model_copy(update={"successful_payment": receipt})
            await dp.feed_update(bot, types.Update(update_id=3, message=paid), i18n_data=self.data)
            enqueue.assert_awaited_once_with(
                self.settings,
                "retired_telegram_payment",
                {
                    "telegram_user_id": 42,
                    "chat_id": 42,
                    "message_id": 1,
                    "payment": receipt.model_dump(mode="json"),
                },
                event_id="telegram-charge",
            )
            assert portal.await_count == 2
            enqueue.return_value = False
            with self.assertRaisesRegex(RuntimeError, "Cannot retain"):
                await dp.feed_update(
                    bot, types.Update(update_id=4, message=paid), i18n_data=self.data
                )
            assert portal.await_count == 2
            await dp.feed_update(
                bot,
                types.Update(
                    update_id=5,
                    inline_query=types.InlineQuery(
                        id="inline", from_user=actor, query="gift", offset=""
                    ),
                ),
                i18n_data=self.data,
            )
            answer = bot_session.call_args.args[1]
            assert answer.results == []
            assert answer.cache_time == 0
            assert answer.is_personal is True
            called.assert_not_awaited()
        await dp.storage.close()

    async def test_admin_authorization_precedes_retirement(self) -> None:
        admin = Router()
        called = AsyncMock()

        async def old_admin(callback: types.CallbackQuery) -> None:
            await called(callback)

        old_admin.__module__ = "bot.handlers.admin.common"
        admin.callback_query.register(old_admin)
        bot = Bot("12345:TEST", session=AsyncMock())
        dp = Dispatcher()
        portal = AsyncMock()
        with (
            patch("bot.routers.user_router_aggregate", Router()),
            patch("bot.routers.admin_router_aggregate", admin),
            patch("bot.routers.inline_mode.router", Router()),
            patch("bot.middlewares.legacy_business.send_service_portal", portal),
            patch(
                "bot.filters.admin_filter.get_user_by_telegram_id",
                AsyncMock(return_value=User(user_id=42)),
            ) as lookup,
            patch("bot.filters.admin_filter.is_admin", AsyncMock(return_value=False)) as allowed,
        ):
            dp.include_router(build_root_router(self.settings))
            await dp.feed_update(
                bot,
                types.Update(
                    update_id=1,
                    callback_query=types.CallbackQuery(
                        id="admin",
                        from_user=types.User(id=42, is_bot=False, first_name="Test"),
                        chat_instance="test",
                        message=message(bot),
                        data="admin_action:sync_panel",
                    ),
                ),
                i18n_data=self.data,
                session=AsyncMock(),
            )
            lookup.assert_awaited_once()
            allowed.assert_awaited_once()
            called.assert_not_awaited()
            portal.assert_not_awaited()
        await dp.storage.close()

    async def test_policy_covers_old_entitlement_handlers_and_retains_account_actions(self) -> None:
        for module, name, callback in [
            ("bot.handlers.user.subscription.core_purchase", "purchase", None),
            ("bot.handlers.user.trial_handler", "trial", None),
            ("bot.handlers.user.promo_user", "promo", None),
            ("bot.handlers.user.referral", "referral", None),
            ("bot.handlers.admin.promo.create", "create", None),
            ("bot.handlers.admin.sync_admin_commands", "sync", None),
            ("bot.handlers.inline_mode", "inline_query_handler", None),
            ("bot.handlers.admin.common", "dispatch", "admin_action:sync_panel"),
            (
                "bot.handlers.admin.user_management_browser",
                "dispatch",
                "user_action:traffic_grant:42",
            ),
            (
                "bot.handlers.admin.user_management_browser",
                "dispatch",
                "user_action:set_tariff:42:plan",
            ),
        ]:
            with self.subTest(module=module, callback=callback):
                assert retired_core_handler(module, name, callback)
        for callback in [
            "user_action:toggle_ban:42",
            "user_action:delete_user:42",
            "user_action:send_message:42",
            "main_action:language",
            "admin_action:users_list:0",
        ]:
            assert not retired_core_handler("bot.handlers.admin.common", "dispatch", callback)
        assert not retired_core_handler("example_plugin", "dispatch", "main_action:subscribe")

    async def test_portal_and_menus_do_not_query_old_subscriptions(self) -> None:
        bot_session = AsyncMock(return_value=True)
        bot = Bot("12345:TEST", session=bot_session)
        subscription = AsyncMock()
        for menu in (start_menus.send_main_menu, start_menus.send_bot_interface_menu):
            await menu(message(bot), self.settings, self.data, subscription, AsyncMock())
        assert not subscription.mock_calls
        request = bot_session.call_args.args[1]
        urls = [b.url for row in request.reply_markup.inline_keyboard for b in row if b.url]
        assert urls == ["https://example.test/shop/home", "https://example.test/shop/support"]
        callbacks = [
            b.callback_data
            for row in request.reply_markup.inline_keyboard
            for b in row
            if b.callback_data
        ]
        assert callbacks == ["main_action:language"]
        assert "own allowance" in request.text
        no_message = types.CallbackQuery(
            id="old",
            from_user=types.User(id=42, is_bot=False, first_name="Test"),
            chat_instance="test",
        ).as_(bot)
        await send_service_portal(no_message, self.settings, self.data)
        assert bot_session.call_args.args[1].show_alert is True

    async def test_account_cards_and_menus_keep_lifecycle_without_legacy_links(self) -> None:
        user = User(user_id=42, minishop_id="ms_test", first_name="Test", is_banned=False)
        subscription = AsyncMock()
        session = AsyncMock()
        text = await format_user_card(
            user, session, subscription, self.i18n, "en", independent_services=True
        )
        assert "separate services" in text
        assert not subscription.mock_calls
        assert not session.mock_calls
        keyboard = get_user_card_keyboard(42, self.i18n, "en", independent_services=True)
        callbacks = {b.callback_data for b in keyboard.buttons}
        assert {
            "user_action:toggle_ban:42",
            "user_action:delete_user:42",
            "user_action:send_message:42",
        } <= callbacks
        for markup in [
            keyboard.as_markup(),
            get_admin_panel_keyboard(self.i18n, "en", self.settings, independent_services=True),
            get_user_management_keyboard(self.i18n, "en", independent_services=True),
            get_system_functions_keyboard(self.i18n, "en", independent_services=True),
        ]:
            assert all(
                not retired_core_callback(b.callback_data)
                for row in markup.inline_keyboard
                for b in row
            )

    def test_portal_copy_exists_in_both_base_locales(self) -> None:
        for language in ("en", "ru"):
            locale = json.loads(Path(f"locales/{language}.json").read_text())
            for key in (
                "independent_services_portal_hint",
                "independent_services_open",
                "admin_independent_services_open",
                "admin_independent_services_hint",
                "independent_services_payment_disabled",
            ):
                assert locale[key]


class TelegramRegistrationRetirementTests(ServiceDatabaseTestCase):
    async def test_registration_survives_without_implicit_bonus_promo_or_partner_enrollment(
        self,
    ) -> None:
        cfg = settings()
        i18n = JsonI18n("locales")
        bot_session = AsyncMock(return_value=True)
        bot = Bot("12345:TEST", session=bot_session)
        subscription = AsyncMock()
        promo = AsyncMock()
        partner = AsyncMock()
        data = {"current_language": "en", "i18n_instance": i18n, INDEPENDENT_SERVICES: True}
        async with self.sessions() as session:
            with (
                patch.object(
                    start_flow.user_dal, "generate_account_user_id", AsyncMock(return_value=42)
                ),
                patch.object(
                    start_flow,
                    "evaluate_registration_invite",
                    AsyncMock(
                        return_value=SimpleNamespace(
                            requires_invite=False,
                            referrer_user_id=1,
                            partner_code="partner",
                            partner_user_id=1,
                        )
                    ),
                ),
                patch.object(
                    start_flow, "ensure_required_channel_subscription", AsyncMock(return_value=True)
                ),
                patch.object(start_flow, "emit_bot_started", AsyncMock()),
                patch.object(start_flow.PartnerProgramService, "auto_enroll_user", partner),
                patch.object(start_flow.PartnerProgramService, "attribute_user", partner),
                patch("bot.services.promo_code_service.PromoCodeService.apply_promo_code", promo),
                patch("bot.services.advertising.capture.capture_contact", AsyncMock()),
            ):
                await start_flow.start_command_handler(
                    message(bot, "/start promo_BONUS"),
                    AsyncMock(),
                    cfg,
                    data,
                    subscription,
                    AsyncMock(),
                    session,
                    promo_match=re.match(r"promo_(.+)", "promo_BONUS"),
                )
            created = await start_flow.user_dal.get_user_by_telegram_id(session, 42)
            assert created is not None
            assert created.referred_by_id == 1
            assert not subscription.mock_calls
            promo.assert_not_awaited()
            partner.assert_not_awaited()
            assert "own allowance" in bot_session.call_args.args[1].text
