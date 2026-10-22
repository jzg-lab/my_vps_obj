"""Fixed cutovers converge with traffic and survive remote/local commit uncertainty."""

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.services.service_change_sync import ServiceChangeWorker, synchronize_service_change
from bot.services.service_panel_state import matches_service_terms, panel_traffic_limit
from bot.services.service_usage_sync import synchronize_service_usage
from config.service_periods import as_utc, monthly_period
from db.service_models import ServiceConnection, ServiceUsagePeriod, UserService
from tests.unit.test_service_changes import ServiceChangeTestCase


class ServiceEntitlementTests(ServiceChangeTestCase):
    async def monthly(self, key: str = "monthly") -> tuple[UserService, dict[str, Any]]:
        service, _, _ = await self.activate(key)
        _, remote = await self.prepare(service, ready=True)
        async with self.sessions.begin() as session:
            saved = await session.get(UserService, service.id)
            assert saved
            saved.terms = {**saved.terms, "traffic_rule": "monthly"}
            saved.starts_at = datetime(2024, 1, 31, 4, tzinfo=UTC)
            saved.expires_at = datetime.now(UTC) + timedelta(days=365)
            saved.cycle_started_at, saved.cycle_ends_at = monthly_period(
                saved.starts_at, saved.starts_at
            )
            remote["expireAt"] = saved.expires_at.isoformat()
        remote["userTraffic"] = {"usedTrafficBytes": 900, "lifetimeUsedTrafficBytes": 900}
        return service, remote

    async def saved(self, service: UserService) -> tuple[UserService, ServiceConnection]:
        async with self.sessions() as session:
            saved = await session.get(UserService, service.id)
            connection = await session.get(ServiceConnection, service.id)
            assert saved and connection
            return saved, connection

    async def test_continuously_growing_counter_finishes_once_without_pause_or_carry(self) -> None:
        service, remote = await self.monthly()
        lookup = self.panel.get_user_by_uuid_lookup.side_effect
        assert callable(lookup)

        async def moving(reference: str) -> dict[str, Any]:
            traffic = remote["userTraffic"]
            traffic["usedTrafficBytes"] += 10
            traffic["lifetimeUsedTrafficBytes"] += 10
            result = await lookup(reference)
            assert isinstance(result, dict)
            return result

        self.panel.get_user_by_uuid_lookup.side_effect = moving
        await synchronize_service_change(cast(sessionmaker, self.sessions), service.id, self.panel)
        saved, connection = await self.saved(service)
        assert not connection.sync_pending and connection.cycle_cutover_bytes is None
        assert saved.used_bytes > 0
        assert (
            as_utc(saved.cycle_started_at) == monthly_period(saved.starts_at, datetime.now(UTC))[0]
        )
        assert remote["trafficLimitBytes"] == 910 + 10000
        assert panel_traffic_limit(saved, connection) == 10910
        self.panel.update_user_status_on_panel.assert_not_awaited()
        before = remote["trafficLimitBytes"]
        for _ in range(3):
            await synchronize_service_change(
                cast(sessionmaker, self.sessions), service.id, self.panel
            )
        assert remote["trafficLimitBytes"] == before
        async with self.sessions() as session:
            periods = list(await session.scalars(select(ServiceUsagePeriod)))
            assert len(periods) == 1 and periods[0].used_bytes == 910 and periods[0].confirmed_at
        self.panel.update_user_details_on_panel.assert_awaited_once()

    async def test_remote_write_then_process_crash_recovers_the_original_cutover(self) -> None:
        service, remote = await self.monthly()
        update = self.panel.update_user_details_on_panel.side_effect
        assert callable(update)

        async def crash(reference: str, payload: dict[str, Any]) -> None:
            await update(reference, payload)
            raise SystemExit("process stopped")

        self.panel.update_user_details_on_panel.side_effect = crash
        with self.assertRaises(SystemExit):
            await synchronize_service_change(
                cast(sessionmaker, self.sessions), service.id, self.panel
            )
        saved, connection = await self.saved(service)
        assert connection.cycle_cutover_bytes == 900 and saved.used_bytes == 900
        assert remote["trafficLimitBytes"] == 10900
        remote["userTraffic"] = {"usedTrafficBytes": 1200, "lifetimeUsedTrafficBytes": 1200}
        self.panel.update_user_details_on_panel.side_effect = update
        await synchronize_service_change(cast(sessionmaker, self.sessions), service.id, self.panel)
        saved, connection = await self.saved(service)
        assert saved.used_bytes == 300 and connection.cycle_cutover_bytes is None
        assert remote["trafficLimitBytes"] == 10900
        self.panel.update_user_details_on_panel.assert_awaited_once()

    async def test_failed_local_confirmation_commit_does_not_issue_a_second_allowance(self) -> None:
        service, remote = await self.monthly()
        original = AsyncSession.commit
        failed = False

        async def commit(session: AsyncSession) -> None:
            nonlocal failed
            if self.panel.update_user_details_on_panel.await_count and not failed:
                failed = True
                raise RuntimeError("database commit unavailable")
            await original(session)

        with patch.object(AsyncSession, "commit", commit), self.assertRaises(RuntimeError):
            await synchronize_service_change(
                cast(sessionmaker, self.sessions), service.id, self.panel
            )
        saved, connection = await self.saved(service)
        assert saved.used_bytes == 900 and connection.cycle_cutover_bytes == 900
        remote["userTraffic"] = {"usedTrafficBytes": 11500, "lifetimeUsedTrafficBytes": 11500}
        await synchronize_service_change(cast(sessionmaker, self.sessions), service.id, self.panel)
        saved, connection = await self.saved(service)
        assert saved.used_bytes == 10600 and remote["trafficLimitBytes"] == 10900
        assert remote["status"] == "DISABLED" and not connection.sync_pending
        async with self.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(ServiceUsagePeriod)) == 1

    async def test_monthly_outage_retains_old_display_and_pending_identity_stays_disabled(
        self,
    ) -> None:
        service, remote = await self.monthly()
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection
            connection.state = "pending"
        remote["status"] = "DISABLED"
        update = self.panel.update_user_details_on_panel.side_effect
        self.panel.update_user_details_on_panel.side_effect = TimeoutError("unavailable")
        await synchronize_service_change(cast(sessionmaker, self.sessions), service.id, self.panel)
        saved, connection = await self.saved(service)
        assert saved.used_bytes == 900 and connection.cycle_cutover_bytes == 900
        remote["userTraffic"] = {"usedTrafficBytes": 1000, "lifetimeUsedTrafficBytes": 1000}
        await synchronize_service_usage(cast(sessionmaker, self.sessions), service.id, self.panel)
        saved, _ = await self.saved(service)
        assert saved.used_bytes == 900
        self.panel.update_user_details_on_panel.side_effect = update
        await synchronize_service_change(cast(sessionmaker, self.sessions), service.id, self.panel)
        saved, connection = await self.saved(service)
        assert saved.used_bytes == 100 and connection.state == "pending"
        assert remote["status"] == "DISABLED"

    async def test_worker_enforces_expiry_and_overage_without_an_admin_action(self) -> None:
        first, _, _ = await self.activate("expires")
        second, _, _ = await self.activate("exhausts")
        # One panel fixture must mutate the requested reference, not the last prepared user.
        await self.prepare(first, ready=True)
        await self.prepare(second, ready=True)

        async def status(reference: str, enabled: bool, **_kwargs: object) -> bool:
            next(user for user in self.remote_users.values() if user["uuid"] == reference)[
                "status"
            ] = "ACTIVE" if enabled else "DISABLED"
            return True

        async def update(reference: str, payload: dict[str, Any]) -> dict[str, Any]:
            remote = next(user for user in self.remote_users.values() if user["uuid"] == reference)
            remote.update(payload)
            return remote

        self.panel.update_user_status_on_panel.side_effect = status
        self.panel.update_user_details_on_panel.side_effect = update
        async with self.sessions.begin() as session:
            service = await session.get(UserService, first.id)
            assert service
            service.starts_at = datetime.now(UTC) - timedelta(days=2)
            service.expires_at = datetime.now(UTC) - timedelta(days=1)
        self.remote_users[f"svc_{second.id}"]["userTraffic"] = {
            "usedTrafficBytes": 10200,
            "lifetimeUsedTrafficBytes": 10200,
        }
        await ServiceChangeWorker(cast(sessionmaker, self.sessions), self.panel).tick()
        assert all(user["status"] == "DISABLED" for user in self.remote_users.values())
        assert (await self.saved(second))[0].used_bytes == 10200
        assert (await self.saved(first))[0].used_bytes == 0

    async def test_anomaly_and_unknown_data_do_not_refill_or_cut_healthy_active_access(
        self,
    ) -> None:
        service, _, _ = await self.activate()
        _, remote = await self.prepare(service, ready=True)
        remote["userTraffic"] = None
        await synchronize_service_change(cast(sessionmaker, self.sessions), service.id, self.panel)
        saved, connection = await self.saved(service)
        assert remote["status"] == "ACTIVE" and saved.used_bytes == 0
        assert connection.sync_pending and connection.usage_error == "panel_usage_invalid"
        self.panel.update_user_status_on_panel.assert_not_awaited()
        remote["status"] = "DISABLED"
        await synchronize_service_change(cast(sessionmaker, self.sessions), service.id, self.panel)
        assert remote["status"] == "DISABLED"
        self.panel.update_user_status_on_panel.assert_not_awaited()

    async def test_absolute_limit_matches_after_previous_month_and_keeps_two_services_separate(
        self,
    ) -> None:
        service, remote = await self.monthly()
        await synchronize_service_change(cast(sessionmaker, self.sessions), service.id, self.panel)
        saved, connection = await self.saved(service)
        assert matches_service_terms(
            remote,
            saved,
            [str(value) for value in saved.terms["squad_uuids"]],
            connection=connection,
        )
        other, _, _ = await self.activate("untouched")
        assert (await self.saved(other))[0].used_bytes == 0
        assert not matches_service_terms(
            {**remote, "trafficLimitBytes": saved.quota_bytes},
            saved,
            [str(value) for value in saved.terms["squad_uuids"]],
            connection=connection,
        )

    async def test_period_switch_respects_pause_ban_and_expiry(self) -> None:
        from db.models import User

        for restriction in ("paused", "banned", "expired"):
            with self.subTest(restriction=restriction):
                service, remote = await self.monthly(restriction)
                async with self.sessions.begin() as session:
                    saved = await session.get(UserService, service.id)
                    user = await session.get(User, 1)
                    assert saved and user
                    if restriction == "paused":
                        saved.desired_status = "paused"
                    elif restriction == "banned":
                        user.is_banned = True
                    else:
                        saved.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                await synchronize_service_change(
                    cast(sessionmaker, self.sessions), service.id, self.panel
                )
                saved, connection = await self.saved(service)
                assert remote["status"] == "DISABLED"
                assert saved.used_bytes == (900 if restriction == "expired" else 0)
                assert saved.desired_status == ("paused" if restriction == "paused" else "active")
                assert connection.state == "ready"
                async with self.sessions.begin() as session:
                    user = await session.get(User, 1)
                    assert user
                    user.is_banned = False

    async def test_exhaustion_observed_while_enabling_is_immediately_restricted(self) -> None:
        service, _, _ = await self.activate()
        _, remote = await self.prepare(service, ready=True)
        remote["status"] = "DISABLED"

        async def status(_reference: str, enabled: bool, **_kwargs: object) -> bool:
            remote["status"] = "ACTIVE" if enabled else "DISABLED"
            if enabled:
                remote["userTraffic"] = {
                    "usedTrafficBytes": 11000,
                    "lifetimeUsedTrafficBytes": 11000,
                }
            return True

        self.panel.update_user_status_on_panel.side_effect = status
        await synchronize_service_change(cast(sessionmaker, self.sessions), service.id, self.panel)
        saved, connection = await self.saved(service)
        assert saved.used_bytes == 11000 and not connection.sync_pending
        assert remote["status"] == "DISABLED"
        assert [
            call.args[1] for call in self.panel.update_user_status_on_panel.await_args_list
        ] == [True, False]
