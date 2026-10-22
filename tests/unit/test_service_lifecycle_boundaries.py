"""Account lifecycle actions cannot bypass terminal service accounting."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock, patch

from aiogram import types
from aiogram.fsm.context import FSMContext
from sqlalchemy.orm import sessionmaker

from bot.app.web.admin_api_impl import users_actions
from bot.handlers.admin import user_management_info
from bot.services.account_access_sync import set_account_ban, synchronize_account_access
from bot.services.service_change_sync import synchronize_service_change
from bot.services.service_revocation import revoke_service_identity
from bot.services.service_usage_sync import synchronize_service_usage
from config.settings import Settings
from db.dal.service_delivery_dal import request_service_revocation
from db.models import User
from db.service_models import ServiceConnection, UserService
from tests.unit.test_service_changes import ServiceChangeTestCase


class ServiceLifecycleBoundaryTests(ServiceChangeTestCase):
    async def cancel(self, service: UserService) -> None:
        assert service.user_id is not None
        async with self.sessions.begin() as session:
            await request_service_revocation(
                session,
                service_id=service.id,
                user_id=service.user_id,
                actor_id=1,
                expected_revision=1,
                idempotency_key=f"cancel:{service.id}",
                reason="Terminal accounting regression",
            )

    async def test_every_owned_revocation_read_latches_anomalies_before_larger_samples(
        self,
    ) -> None:
        lookup = self.panel.get_user_by_uuid_lookup.side_effect
        for position in range(3):
            for anomaly, lifetime in [("panel_usage_regressed", 100), ("panel_usage_reset", 300)]:
                with self.subTest(position=position, anomaly=anomaly):
                    self.panel.get_user_by_uuid_lookup.side_effect = lookup
                    service, _, _ = await self.activate(f"{position}:{anomaly}")
                    panel, remote = await self.prepare(service, ready=True)
                    remote["userTraffic"] = {
                        "usedTrafficBytes": 500,
                        "lifetimeUsedTrafficBytes": 500,
                    }
                    await synchronize_service_usage(
                        cast(sessionmaker, self.sessions), service.id, panel
                    )
                    await self.cancel(service)
                    samples = [
                        {
                            **remote,
                            "status": "ACTIVE" if index == position else "DISABLED",
                            "userTraffic": {
                                "usedTrafficBytes": 100 if index == position else 500,
                                "lifetimeUsedTrafficBytes": lifetime if index == position else 500,
                            },
                        }
                        for index in range(3)
                    ]
                    recovered = {
                        **remote,
                        "status": "DISABLED",
                        "userTraffic": {"usedTrafficBytes": 600, "lifetimeUsedTrafficBytes": 600},
                    }
                    panel.get_user_by_uuid_lookup.side_effect = [
                        *({"ok": True, "user": sample} for sample in samples[: position + 1]),
                        *({"ok": True, "user": recovered} for _ in range(3 - position)),
                        {"not_found": True},
                    ]
                    panel.delete_user_from_panel.reset_mock()
                    await revoke_service_identity(
                        cast(sessionmaker, self.sessions), service.id, panel
                    )
                    panel.get_user_by_uuid_lookup.side_effect = None
                    panel.get_user_by_uuid_lookup.return_value = {"ok": True, "user": recovered}
                    await revoke_service_identity(
                        cast(sessionmaker, self.sessions), service.id, panel
                    )
                    async with self.sessions() as session:
                        saved = await session.get(UserService, service.id)
                        connection = await session.get(ServiceConnection, service.id)
                        assert saved and saved.used_bytes == 500
                        assert connection and connection.usage_error == anomaly
                        assert connection.state != "revoked" and connection.sync_pending
                        assert connection.revoke_delete_requested_at is None
                    panel.delete_user_from_panel.assert_not_awaited()

    async def test_ban_and_unban_ignore_revoked_history_but_sync_remaining_service(self) -> None:
        ended, _, _ = await self.activate("ended", user_id=2)
        other, _, _ = await self.activate("other", user_id=2)
        panel, ended_remote = await self.prepare(ended, ready=True)
        _, other_remote = await self.prepare(other, ready=True)
        await synchronize_service_change(cast(sessionmaker, self.sessions), other.id, panel)

        async def status(reference: str, enable: bool) -> bool:
            for remote in self.remote_users.values():
                if remote["uuid"] == reference:
                    remote["status"] = "ACTIVE" if enable else "DISABLED"
            return True

        panel.update_user_status_on_panel.side_effect = status
        await self.cancel(ended)
        panel.delete_user_from_panel.side_effect = lambda _reference: self.remote_users.pop(
            str(ended_remote["username"]), None
        )
        await revoke_service_identity(cast(sessionmaker, self.sessions), ended.id, panel)
        async with self.sessions() as session:
            connection = await session.get(ServiceConnection, ended.id)
            assert connection and connection.state == "revoked"
            confirmed_at = connection.sync_confirmed_at
        panel.get_user_by_uuid_lookup.reset_mock()
        for banned in (True, False):
            async with self.sessions.begin() as session:
                with patch(
                    "bot.services.account_access_sync.can_ban_account", AsyncMock(return_value=True)
                ):
                    await set_account_ban(session, user_id=2, actor_id=1, banned=banned)
            async with self.sessions() as session:
                job = await synchronize_account_access(session, 2, panel)
                assert job and not job.pending and job.last_error is None
                connection = await session.get(ServiceConnection, ended.id)
                assert connection and connection.state == "revoked"
                assert not connection.sync_pending and connection.usage_error is None
                assert connection.sync_confirmed_at == confirmed_at
            assert other_remote["status"] == ("DISABLED" if banned else "ACTIVE")
        assert all(
            call.args[0] != ended_remote["uuid"]
            for call in panel.get_user_by_uuid_lookup.await_args_list
        )

    async def test_web_delete_cannot_skip_pending_terminal_accounting(self) -> None:
        service, _, _ = await self.activate(user_id=2)
        panel, _ = await self.prepare(service, ready=True)
        panel.get_user_by_uuid_lookup.side_effect = None
        panel.get_user_by_uuid_lookup.return_value = {"not_found": True}
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection
            connection.usage_error = "panel_usage_regressed"
            connection.cycle_cutover_bytes = 500
        request = SimpleNamespace(
            app={
                "settings": SimpleNamespace(),
                "async_session_factory": self.sessions,
                "panel_service": panel,
            },
            match_info={"user_id": "2"},
        )
        with (
            patch.object(users_actions, "_require_admin_user_id", return_value=1),
            patch.object(users_actions, "_invalidate_after_admin_user_mutation", AsyncMock()),
        ):
            response = await users_actions.admin_user_delete_route(request)
        assert response.status == 409
        panel.delete_user_from_panel.assert_not_awaited()
        async with self.sessions() as session:
            assert await session.get(User, 2) is not None
            connection = await session.get(ServiceConnection, service.id)
            assert connection and connection.usage_error == "panel_usage_regressed"
            assert connection.cycle_cutover_bytes == 500

    async def test_telegram_delete_cannot_skip_pending_terminal_accounting(self) -> None:
        service, _, _ = await self.activate(user_id=2)
        panel, _ = await self.prepare(service, ready=True)
        panel.get_user_by_uuid_lookup.side_effect = None
        panel.get_user_by_uuid_lookup.return_value = {"not_found": True}
        message = SimpleNamespace(
            text="2",
            from_user=SimpleNamespace(id=1, username=None, full_name="Admin"),
            answer=AsyncMock(),
        )
        state = SimpleNamespace(
            get_data=AsyncMock(return_value={"target_user_id": 2}), clear=AsyncMock()
        )
        i18n = SimpleNamespace(gettext=Mock(side_effect=lambda _lang, key, **_kwargs: key))
        async with self.sessions() as session:
            admin = await session.get(User, 1)
            with patch.object(
                user_management_info.user_dal,
                "get_user_by_telegram_id",
                AsyncMock(return_value=admin),
            ):
                await user_management_info.process_delete_user_confirmation_handler(
                    cast(types.Message, message),
                    cast(FSMContext, state),
                    cast(Settings, SimpleNamespace(DEFAULT_LANGUAGE="en")),
                    {"i18n_instance": i18n},
                    panel,
                    session,
                )
        panel.delete_user_from_panel.assert_not_awaited()
        message.answer.assert_awaited_once_with("admin_error_service_connection_revoke_required")
        async with self.sessions() as session:
            assert await session.get(User, 2) is not None
