"""Independent traffic observations are monotonic, repeatable and never issue rights."""

from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy.orm import sessionmaker

from bot.app.web.service_schemas import UserServiceOut
from bot.services.service_provisioning import provision_service_identity
from bot.services.service_usage_sync import ServiceUsageWorker, synchronize_service_usage
from config.service_periods import as_utc, monthly_period
from db.models import User
from db.service_models import ServiceConnection, UserService
from tests.unit.test_service_provisioning import panel_fixture
from tests.unit.test_user_services import ServiceDatabaseTestCase


class ServiceUsageTests(ServiceDatabaseTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.panel, self.remote_users = panel_fixture()

    async def prepare(self, key: str = "one") -> UserService:
        service, _, _ = await self.activate(key)
        await provision_service_identity(cast(sessionmaker, self.sessions), service.id, self.panel)
        self.sample(service, 0)
        return service

    def sample(self, service: UserService, total: object) -> None:
        self.remote_users[f"svc_{service.id}"]["userTraffic"] = {
            "usedTrafficBytes": total,
            "lifetimeUsedTrafficBytes": total,
        }

    async def sync(self, service: UserService) -> tuple[UserService, ServiceConnection]:
        await synchronize_service_usage(cast(sessionmaker, self.sessions), service.id, self.panel)
        async with self.sessions() as session:
            saved = await session.get(UserService, service.id)
            connection = await session.get(ServiceConnection, service.id)
            assert saved and connection
            return saved, connection

    async def test_repeated_samples_and_two_services_have_separate_totals(self) -> None:
        first, second = await self.prepare(), await self.prepare("two")
        self.sample(first, 321)
        self.sample(second, 654)
        for _ in range(2):
            await ServiceUsageWorker(cast(sessionmaker, self.sessions), self.panel).tick()
        saved, connection = await self.sync(first)
        other, _ = await self.sync(second)
        assert saved.used_bytes == connection.usage_total_bytes == 321
        assert other.used_bytes == 654
        assert saved.quota_bytes == 10000 and saved.revision == 1
        assert as_utc(saved.expires_at) == as_utc(first.expires_at)
        assert connection.state == "pending" and not connection.sync_pending
        assert saved.last_usage_sync_at and not connection.usage_error
        assert UserServiceOut.from_orm_service(saved, connection, None).usage_error is None
        self.panel.update_user_status_on_panel.assert_not_awaited()
        self.panel.update_user_details_on_panel.assert_not_awaited()

    async def test_overage_is_visible_and_counter_rollback_cannot_restore_allowance(self) -> None:
        service = await self.prepare()
        self.sample(service, 12000)
        saved, _ = await self.sync(service)
        assert saved.used_bytes == 12000
        last_sync = saved.last_usage_sync_at
        self.sample(service, 100)
        saved, connection = await self.sync(service)
        assert saved.used_bytes == connection.usage_total_bytes == 12000
        assert saved.last_usage_sync_at == last_sync
        assert connection.usage_error == "panel_usage_regressed"
        output = UserServiceOut.from_orm_service(saved, connection, None)
        assert output.status == "exhausted" and output.usage_error == "panel_usage_regressed"
        self.sample(service, 12500)
        saved, connection = await self.sync(service)
        assert saved.used_bytes == 12000 and connection.usage_error == "panel_usage_regressed"
        assert saved.last_usage_sync_at == last_sync

    async def test_missing_invalid_and_reset_counters_preserve_last_confirmed_sample(self) -> None:
        service = await self.prepare()
        self.sample(service, 100)
        saved, _ = await self.sync(service)
        confirmed = saved.last_usage_sync_at
        remote = self.remote_users[f"svc_{service.id}"]
        for bad in (None, True, -1, 1.5, "101", 2**53):
            with self.subTest(bad=bad):
                self.sample(service, bad)
                saved, connection = await self.sync(service)
                assert saved.used_bytes == 100 and saved.last_usage_sync_at == confirmed
                assert connection.usage_error == "panel_usage_invalid"
        invalid_traffic: tuple[object, ...] = ({}, {"usedTrafficBytes": 101}, [], None)
        for traffic in invalid_traffic:
            with self.subTest(traffic=traffic):
                remote["userTraffic"] = traffic
                saved, connection = await self.sync(service)
                assert saved.used_bytes == 100 and connection.usage_error == "panel_usage_invalid"
        remote["userTraffic"] = {"usedTrafficBytes": 1, "lifetimeUsedTrafficBytes": 101}
        saved, connection = await self.sync(service)
        assert saved.used_bytes == 100 and connection.usage_error == "panel_usage_reset"
        assert saved.last_usage_sync_at == confirmed

    async def test_changed_reset_strategy_remains_unconfirmed_after_strategy_is_restored(
        self,
    ) -> None:
        service = await self.prepare()
        self.sample(service, 100)
        saved, _ = await self.sync(service)
        confirmed = saved.last_usage_sync_at
        remote = self.remote_users[f"svc_{service.id}"]
        remote["trafficLimitStrategy"] = "MONTH"
        self.sample(service, 200)
        saved, connection = await self.sync(service)
        assert saved.used_bytes == 100 and connection.usage_error == "panel_usage_reset"
        remote["trafficLimitStrategy"] = "NO_RESET"
        saved, connection = await self.sync(service)
        assert saved.used_bytes == 100 and connection.usage_error == "panel_usage_reset"
        assert saved.last_usage_sync_at == confirmed

    async def test_first_sample_keeps_existing_confirmed_usage_without_counting_it_twice(
        self,
    ) -> None:
        service = await self.prepare()
        async with self.sessions.begin() as session:
            saved = await session.get(UserService, service.id)
            assert saved
            saved.used_bytes = 100
        self.sample(service, 150)
        saved, connection = await self.sync(service)
        assert saved.used_bytes == connection.usage_total_bytes == 150

    async def test_temporary_outage_recovers_without_recounting_previous_usage(self) -> None:
        service = await self.prepare()
        self.sample(service, 200)
        await self.sync(service)
        lookup = self.panel.get_user_by_uuid_lookup.side_effect
        self.panel.get_user_by_uuid_lookup.side_effect = TimeoutError("unavailable")
        saved, connection = await self.sync(service)
        assert saved.used_bytes == 200 and connection.usage_error == "panel_usage_unavailable"
        self.panel.get_user_by_uuid_lookup.side_effect = lookup
        self.sample(service, 300)
        saved, connection = await self.sync(service)
        assert saved.used_bytes == connection.usage_total_bytes == 300
        assert connection.usage_error is None

    async def test_panel_failure_missing_identity_and_conflict_do_not_erase_usage(self) -> None:
        service = await self.prepare()
        self.sample(service, 200)
        saved, _ = await self.sync(service)
        confirmed = saved.last_usage_sync_at
        lookup = self.panel.get_user_by_uuid_lookup.side_effect
        self.panel.get_user_by_uuid_lookup.side_effect = TimeoutError("unavailable")
        saved, connection = await self.sync(service)
        assert connection.usage_error == "panel_usage_unavailable"
        assert saved.used_bytes == 200 and saved.last_usage_sync_at == confirmed
        self.panel.get_user_by_uuid_lookup.side_effect = None
        self.panel.get_user_by_uuid_lookup.return_value = {"not_found": True}
        _, connection = await self.sync(service)
        assert connection.usage_error == "panel_identity_missing"
        self.panel.get_user_by_uuid_lookup.side_effect = lookup
        self.remote_users[f"svc_{service.id}"]["description"] = "another owner"
        self.sample(service, 9000)
        saved, connection = await self.sync(service)
        assert connection.usage_error == "panel_identity_conflict"
        assert saved.used_bytes == 200 and saved.last_usage_sync_at == confirmed
        self.panel.create_panel_user.assert_awaited_once()

    async def test_month_boundary_and_ban_still_observe_traffic_without_resetting(self) -> None:
        service = await self.prepare()
        async with self.sessions.begin() as session:
            saved = await session.get(UserService, service.id)
            user = await session.get(User, 1)
            assert saved and user
            saved.terms = {**saved.terms, "traffic_rule": "monthly"}
            saved.starts_at = datetime.now(UTC) - timedelta(days=90)
            saved.cycle_started_at, saved.cycle_ends_at = monthly_period(
                saved.starts_at, saved.starts_at
            )
            old_period = (saved.cycle_started_at, saved.cycle_ends_at)
            saved.desired_status = "paused"
            user.is_banned = True
        self.sample(service, 500)
        saved, connection = await self.sync(service)
        assert saved.used_bytes == 500 and connection.usage_total_bytes == 500
        assert (as_utc(saved.cycle_started_at), as_utc(saved.cycle_ends_at)) == old_period
        assert saved.desired_status == "paused" and saved.revision == 1
        assert self.remote_users[f"svc_{service.id}"]["status"] == "DISABLED"

    async def test_worker_skips_unbound_and_revoked_and_recovers_other_services(self) -> None:
        await self.activate("unbound")
        revoked, good = await self.prepare("revoked"), await self.prepare("good")
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, revoked.id)
            assert connection
            connection.state = "revoked"
        self.panel.get_user_by_uuid_lookup.reset_mock()
        self.sample(good, 88)
        await ServiceUsageWorker(cast(sessionmaker, self.sessions), self.panel).tick()
        self.panel.get_user_by_uuid_lookup.assert_awaited_once()
        saved, _ = await self.sync(good)
        assert saved.used_bytes == 88


def test_usage_worker_does_not_treat_dry_run_counters_as_real_usage() -> None:
    from main_worker import _core_worker_tasks

    from tests.unit.test_telegram_business_retirement import settings

    spec = next(task for task in _core_worker_tasks() if task.name == "ServiceUsage")
    assert spec.enabled is not None
    cfg = settings()
    cfg.PANEL_WRITE_MODE = "dry_run"
    assert spec.enabled(cfg) is False
    cfg.PANEL_WRITE_MODE = "live"
    assert spec.enabled(cfg) is True
