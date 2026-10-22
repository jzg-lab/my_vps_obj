"""Independent changes preserve usage and survive retries and panel outages."""

from datetime import datetime, timedelta
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from bot.services.account_access_sync import set_account_ban, synchronize_account_access
from bot.services.service_change_sync import ServiceChangeWorker, synchronize_service_change
from bot.services.service_provisioning import provision_service_identity
from config.service_changes import ServiceChange
from config.service_periods import as_utc, monthly_period
from db.dal.service_changes_dal import change_service
from db.dal.user_services_dal import ServiceConflict
from db.models import User
from db.service_models import ServiceConnection, ServiceOrder, UserService
from tests.unit.test_service_provisioning import panel_fixture
from tests.unit.test_user_services import ServiceDatabaseTestCase


@pytest.mark.parametrize(
    "values",
    [
        {"action": "renew"},
        {"action": "pause", "days": 1},
        {"action": "renew", "days": True, "price": "1", "currency": "CNY"},
        {"action": "renew", "days": 1, "price": "-1", "currency": "CNY"},
        {"action": "renew", "days": 1, "price": "1.001", "currency": "CNY"},
        {"action": "renew", "days": 1, "price": "NaN", "currency": "CNY"},
    ],
)
def test_change_rejects_ambiguous_terms(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ServiceChange.model_validate(values)


class ServiceChangeTestCase(ServiceDatabaseTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.panel, self.remote_users = panel_fixture()

    async def change(
        self, service: UserService, action: str = "renew", *, key: str = "change"
    ) -> tuple[UserService, ServiceOrder, bool]:
        change = ServiceChange.model_validate(
            {
                "action": action,
                **({"days": 31, "price": "9.90", "currency": "CNY"} if action == "renew" else {}),
            }
        )
        async with self.sessions.begin() as session:
            service, order, duplicate = await change_service(
                session,
                service_id=service.id,
                user_id=1,
                actor_id=1,
                expected_revision=service.revision,
                idempotency_key=key,
                change=change,
            )
            return service, order, duplicate

    async def prepare(
        self, service: UserService, *, ready: bool = False
    ) -> tuple[AsyncMock, dict[str, Any]]:
        panel, users = self.panel, self.remote_users
        await provision_service_identity(cast(sessionmaker, self.sessions), service.id, panel)
        remote = users[f"svc_{service.id}"]
        if ready:
            async with self.sessions.begin() as session:
                connection = await session.get(ServiceConnection, service.id)
                assert connection
                connection.state = "ready"
            remote["status"] = "ACTIVE"

        async def update(_reference: str, values: dict[str, Any]) -> dict[str, Any]:
            remote.update(values)
            return dict(remote)

        async def status(_reference: str, enable: bool, **_kwargs: object) -> bool:
            remote["status"] = "ACTIVE" if enable else "DISABLED"
            return True

        panel.update_user_details_on_panel.side_effect = update
        panel.update_user_status_on_panel.side_effect = status
        return panel, remote

    async def sync(self, service: UserService, panel: AsyncMock) -> ServiceConnection:
        await synchronize_service_change(cast(sessionmaker, self.sessions), service.id, panel)
        async with self.sessions() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection
            return connection


class ServiceChangeTests(ServiceChangeTestCase):
    async def test_renewal_is_once_preserves_usage_anchor_and_other_service(self) -> None:
        service, _, _ = await self.activate()
        other, _, _ = await self.activate("other")
        async with self.sessions.begin() as session:
            saved = await session.get(UserService, service.id)
            assert saved
            saved.terms = {**saved.terms, "traffic_rule": "monthly"}
            saved.used_bytes = 9000
            saved.cycle_started_at, saved.cycle_ends_at = monthly_period(
                saved.starts_at, saved.starts_at
            )
            original_period = (saved.cycle_started_at, saved.cycle_ends_at)
        result, order, duplicate = await self.change(service)
        assert not duplicate and result.revision == 2
        assert result.used_bytes == 9000 and result.quota_bytes == 10000
        assert (as_utc(result.cycle_started_at), as_utc(result.cycle_ends_at)) == original_period
        assert as_utc(result.expires_at) == as_utc(service.expires_at) + timedelta(days=31)
        replay, same, duplicate = await self.change(service)
        assert (
            duplicate
            and same.id == order.id
            and as_utc(replay.expires_at) == as_utc(result.expires_at)
        )
        assert order.snapshot["change"] == {
            "action": "renew",
            "days": 31,
            "price": "9.90",
            "currency": "CNY",
        }
        async with self.sessions() as session:
            unchanged = await session.get(UserService, other.id)
            assert unchanged and unchanged.revision == 1 and unchanged.used_bytes == 0
            assert as_utc(unchanged.expires_at) == as_utc(other.expires_at)
            assert await session.scalar(select(func.count()).select_from(ServiceOrder)) == 3

    async def test_expired_renewal_uses_now_and_does_not_resume_paused_service(self) -> None:
        service, _, _ = await self.activate()
        now = as_utc(service.expires_at) + timedelta(days=5)
        async with self.sessions.begin() as session:
            saved = await session.get(UserService, service.id)
            assert saved
            saved.desired_status = "paused"
            saved.used_bytes = 11000
            await session.flush()
            renewed, _, _ = await change_service(
                session,
                service_id=service.id,
                user_id=1,
                actor_id=1,
                expected_revision=1,
                idempotency_key="renew",
                change=ServiceChange(action="renew", days=3, price="0", currency="CNY"),
                now=now,
            )
            assert renewed.expires_at == now + timedelta(days=3)
            assert renewed.desired_status == "paused" and renewed.used_bytes == 11000

    async def test_version_owner_and_reused_key_cannot_change_another_service(self) -> None:
        service, _, _ = await self.activate()
        other, _, _ = await self.activate("other", user_id=2)
        await self.change(service, "pause")
        with pytest.raises(ServiceConflict, match="idempotency_conflict"):
            await self.change(service, "renew")
        with pytest.raises(ServiceConflict, match="service_revision_changed"):
            await self.change(service, "renew", key="stale")
        with pytest.raises(ServiceConflict, match="service_not_found"):
            await self.change(other, key="wrong-owner")
        async with self.sessions() as session:
            saved = await session.get(UserService, service.id)
            assert saved and saved.desired_status == "paused" and saved.revision == 2

    async def test_pending_identity_renewal_changes_expiry_but_cannot_enable(self) -> None:
        service, _, _ = await self.activate()
        panel, remote = await self.prepare(service)
        renewed, _, _ = await self.change(service)
        connection = await self.sync(service, panel)
        assert not connection.sync_pending and connection.sync_confirmed_at
        assert connection.state == "pending" and remote["status"] == "DISABLED"
        assert datetime.fromisoformat(remote["expireAt"]) == as_utc(renewed.expires_at).replace(
            microsecond=(renewed.expires_at.microsecond // 1000) * 1000
        )
        assert set(panel.update_user_details_on_panel.await_args.args[1]) == {
            "expireAt",
            "trafficLimitBytes",
            "status",
        }
        panel.update_user_status_on_panel.assert_not_awaited()
        panel.create_panel_user.assert_awaited_once()

    async def test_failed_patch_retries_without_refilling_or_claiming_confirmation(self) -> None:
        service, _, _ = await self.activate()
        panel, remote = await self.prepare(service, ready=True)
        renewed, _, _ = await self.change(service)
        update = panel.update_user_details_on_panel.side_effect
        panel.update_user_details_on_panel.side_effect = TimeoutError("panel unavailable")
        connection = await self.sync(service, panel)
        assert (
            connection.sync_pending and connection.sync_error and not connection.sync_confirmed_at
        )
        assert remote["status"] == "ACTIVE"
        panel.update_user_details_on_panel.side_effect = update
        connection = await self.sync(service, panel)
        assert not connection.sync_pending and remote["status"] == "ACTIVE"
        again, _, duplicate = await self.change(service)
        assert (
            duplicate
            and as_utc(again.expires_at) == as_utc(renewed.expires_at)
            and again.used_bytes == 0
        )

    async def test_pause_and_resume_require_actual_state_not_success_acknowledgment(self) -> None:
        service, _, _ = await self.activate()
        panel, remote = await self.prepare(service, ready=True)
        paused, _, _ = await self.change(service, "pause")
        # Both mocked mutations claim success while leaving the remote untouched.
        update = panel.update_user_details_on_panel.side_effect
        status = panel.update_user_status_on_panel.side_effect
        panel.update_user_status_on_panel.side_effect = None
        panel.update_user_status_on_panel.return_value = True
        panel.update_user_details_on_panel.side_effect = None
        panel.update_user_details_on_panel.return_value = dict(remote)
        assert (await self.sync(service, panel)).sync_pending
        assert remote["status"] == "ACTIVE"
        panel.update_user_details_on_panel.side_effect = update
        panel.update_user_status_on_panel.side_effect = status
        assert not (await self.sync(service, panel)).sync_pending
        assert remote["status"] == "DISABLED"
        await self.change(paused, "resume", key="resume")
        assert not (await self.sync(service, panel)).sync_pending
        assert remote["status"] == "ACTIVE"

    async def test_conflicting_or_missing_identity_is_not_mutated_or_recreated(self) -> None:
        service, _, _ = await self.activate()
        panel, remote = await self.prepare(service)
        await self.change(service)
        remote["description"] = "someone else"
        assert (await self.sync(service, panel)).sync_error == "panel_identity_conflict"
        panel.update_user_details_on_panel.assert_not_awaited()
        panel.update_user_status_on_panel.assert_not_awaited()
        panel.get_user_by_uuid_lookup.side_effect = None
        panel.get_user_by_uuid_lookup.return_value = {"not_found": True}
        assert (await self.sync(service, panel)).sync_error == "panel_identity_missing"
        panel.create_panel_user.assert_awaited_once()

    async def test_unban_cannot_enable_before_pending_terms_are_verified(self) -> None:
        service, _, _ = await self.activate()
        panel, remote = await self.prepare(service, ready=True)
        await self.change(service)
        remote["status"] = "DISABLED"
        async with self.sessions.begin() as session:
            await set_account_ban(session, user_id=1, actor_id=1, banned=False)
        async with self.sessions() as session:
            job = await synchronize_account_access(session, 1, panel)
            assert job and job.pending and job.last_error == "service_change_pending"
        assert remote["status"] == "DISABLED"
        panel.update_user_status_on_panel.assert_not_awaited()
        assert not (await self.sync(service, panel)).sync_pending
        assert remote["status"] == "ACTIVE"

    async def test_ban_and_exhaustion_win_over_resume_and_renewal(self) -> None:
        for condition in ("ban", "exhaustion"):
            with self.subTest(condition=condition):
                service, _, _ = await self.activate(condition)
                panel, remote = await self.prepare(service, ready=True)
                await self.change(service, key=condition + "-renew")
                async with self.sessions.begin() as session:
                    saved = await session.get(UserService, service.id)
                    user = await session.get(User, 1)
                    assert saved and user
                    if condition == "ban":
                        user.is_banned = True
                    else:
                        saved.used_bytes = saved.quota_bytes
                        remote["userTraffic"] = {
                            "usedTrafficBytes": saved.used_bytes,
                            "lifetimeUsedTrafficBytes": saved.used_bytes,
                        }
                assert not (await self.sync(service, panel)).sync_pending
                assert remote["status"] == "DISABLED"
                async with self.sessions.begin() as session:
                    user = await session.get(User, 1)
                    assert user
                    user.is_banned = False

    async def test_worker_preserves_uncertain_creation_and_settles_unsubmitted_change(
        self,
    ) -> None:
        first, _, _ = await self.activate()
        second, _, _ = await self.activate("uncertain")
        await self.change(first, "pause", key="first")
        await self.change(second, "pause", key="second")
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, second.id)
            assert connection
            connection.state = "error"
        panel, _ = panel_fixture()
        await ServiceChangeWorker(cast(sessionmaker, self.sessions), panel).tick()
        async with self.sessions() as session:
            one = await session.get(ServiceConnection, first.id)
            two = await session.get(ServiceConnection, second.id)
            assert one and two
            assert not one.sync_pending and one.sync_confirmed_at is None
            assert two.sync_pending and two.sync_error
        assert not panel.mock_calls
