import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.handlers.admin import user_management_subscription as bans
from db.dal.user_services_dal import ServiceConflict


class TelegramAdminBanTests(unittest.IsolatedAsyncioTestCase):
    async def test_checks_account_identity_before_mutating_database_or_panel(self):
        for banned, allowed in ((False, False), (False, True), (True, False)):
            with self.subTest(banned=banned, allowed=allowed):
                user = SimpleNamespace(user_id=42, is_banned=banned, panel_user_uuid="panel")
                callback = SimpleNamespace(from_user=SimpleNamespace(id=1001), answer=AsyncMock())
                session = SimpleNamespace(
                    commit=AsyncMock(), rollback=AsyncMock(), refresh=AsyncMock()
                )
                panel = SimpleNamespace(update_user_status_on_panel=AsyncMock())
                i18n = SimpleNamespace(gettext=lambda lang, key, **kwargs: key)
                with (
                    patch.object(
                        bans,
                        "set_account_ban",
                        AsyncMock(
                            return_value=user,
                            side_effect=ServiceConflict("forbidden", 403)
                            if not banned and not allowed
                            else None,
                        ),
                    ) as change,
                    patch.object(
                        bans, "synchronize_access_after_commit", AsyncMock(return_value=True)
                    ) as sync,
                    patch.object(
                        bans, "require_telegram_account_id", AsyncMock(return_value=71)
                    ) as identity,
                    patch.object(bans, "handle_refresh_user_card", AsyncMock()),
                ):
                    await bans.handle_toggle_ban(
                        callback,
                        user,
                        panel,
                        SimpleNamespace(),
                        session,
                        SimpleNamespace(),
                        i18n,
                        "ru",
                    )
                    identity.assert_awaited_once_with(session, 1001)
                    change.assert_awaited_once_with(
                        session, user_id=42, actor_id=71, banned=not banned
                    )
                    if not banned and not allowed:
                        sync.assert_not_awaited()
                        session.commit.assert_not_awaited()
                        session.rollback.assert_awaited_once()
                        callback.answer.assert_awaited_once_with(
                            "wa_auth_access_denied", show_alert=True
                        )
                        self.assertFalse(user.is_banned)
                    else:
                        session.commit.assert_awaited_once()
                        sync.assert_awaited_once_with(session, 42, panel)
                        callback.answer.assert_awaited_once_with(
                            "admin_account_access_saved_pending", show_alert=True
                        )
                    panel.update_user_status_on_panel.assert_not_awaited()
