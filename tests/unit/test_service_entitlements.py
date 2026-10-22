"""Fixed cutovers converge with traffic and survive remote/local commit uncertainty."""

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.services.service_change_sync import ServiceChangeWorker, synchronize_service_change
from bot.services.service_panel_state import matches_service_terms, panel_traffic_limit
from bot.services.service_period_sync import prepare_service_cycle, settle_cancelled_service_period
from bot.services.service_reconciliation import reconcile_service_usage
from bot.services.service_usage_sync import record_service_usage, synchronize_service_usage
from config.service_changes import ServiceChange
from config.service_periods import as_utc, monthly_period
from db.service_models import ServiceConnection, ServiceOrder, ServiceUsagePeriod, UserService
from tests.unit.test_service_changes import ServiceChangeTestCase


class ServiceEntitlementTests(ServiceChangeTestCase):
    async def cancelled_cutover(self) -> tuple[UserService, dict[str, Any]]:
        service, remote = await self.monthly()
        await prepare_service_cycle(cast(sessionmaker, self.sessions), service.id, self.panel)
        async with self.sessions.begin() as session:
            saved = await session.get(UserService, service.id)
            assert saved
            saved.desired_status = "cancelled"
            saved.revision += 1
        remote["status"] = "DISABLED"
        remote["userTraffic"] = {"usedTrafficBytes": 1200, "lifetimeUsedTrafficBytes": 1200}
        self.panel.reset_mock()
        return service, remote

    async def test_terminal_settlement_survives_rollback_without_confirming_or_granting_quota(
        self,
    ) -> None:
        from bot.app.web.service_schemas import UserServiceOut
        from bot.services.service_panel_state import locked_service

        service, remote = await self.cancelled_cutover()
        for commit in (False, True, True):
            async with self.sessions() as session:
                locked = await locked_service(session, service.id)
                assert locked
                _, saved, connection = locked
                assert await settle_cancelled_service_period(
                    session, saved, connection, remote, actor_id=1
                )
                if commit:
                    await session.commit()
                else:
                    await session.rollback()
            async with self.sessions() as session:
                saved = await session.get(UserService, service.id)
                connection = await session.get(ServiceConnection, service.id)
                period = await session.scalar(select(ServiceUsagePeriod))
                orders = list(
                    await session.scalars(
                        select(ServiceOrder).where(ServiceOrder.kind == "settle_usage")
                    )
                )
                assert saved and connection and period
                assert saved.desired_status == "cancelled" and connection.state == "ready"
                assert period.confirmed_at is None and period.cutover_bytes == 900
                assert period.used_bytes == 900 and period.quota_bytes == 10000
                if not commit:
                    assert not orders and saved.used_bytes == 900
                    assert connection.cycle_cutover_bytes == 900
                    continue
                assert saved.used_bytes == 300 and connection.usage_total_bytes == 1200
                assert connection.cycle_cutover_bytes is None and connection.sync_pending
                assert as_utc(saved.cycle_started_at) == as_utc(period.next_started_at)
                assert as_utc(saved.cycle_ends_at) == as_utc(period.next_ends_at)
                assert connection.panel_user_uuid == remote["uuid"]
                assert not UserServiceOut.from_orm_service(saved, connection, None).cycle_pending
                assert len(orders) == 1
                snapshot = orders[0].snapshot
                assert orders[0].actor_id == 1
                assert snapshot["before"]["used_bytes"] == 900
                assert (
                    snapshot["before"]["desired_status"]
                    == snapshot["desired_status"]
                    == "cancelled"
                )
                assert snapshot["cutover_bytes"] == 900 and snapshot["used_bytes"] == 300
                assert snapshot["usage_total_bytes"] == snapshot["usage_raw_bytes"] == 1200
                assert snapshot["allowance_confirmed"] is False
                assert snapshot["panel_user_uuid"] == remote["uuid"]
        await synchronize_service_change(cast(sessionmaker, self.sessions), service.id, self.panel)
        assert remote["trafficLimitBytes"] == 10000 and remote["status"] == "DISABLED"
        self.panel.create_panel_user.assert_not_awaited()
        self.panel.update_user_details_on_panel.assert_not_awaited()
        self.panel.update_user_status_on_panel.assert_not_awaited()

    async def test_terminal_settlement_requires_cancelled_stopped_owned_and_verified_identity(
        self,
    ) -> None:
        from bot.services.service_panel_state import locked_service

        service, remote = await self.cancelled_cutover()
        for invalid in (
            "active",
            "paused",
            "remote_active",
            "foreign",
            "unbound",
            "anomaly",
            "stale",
            "reset",
            "missing_period",
            "confirmed_period",
            "wrong_cutover",
        ):
            async with self.sessions() as session:
                locked = await locked_service(session, service.id)
                assert locked
                _, saved, connection = locked
                observed = dict(remote)
                if invalid in {"active", "paused"}:
                    saved.desired_status = invalid
                elif invalid == "remote_active":
                    observed["status"] = "ACTIVE"
                elif invalid == "foreign":
                    observed["uuid"] = "another-identity"
                elif invalid == "unbound":
                    connection.panel_user_uuid = None
                elif invalid == "anomaly":
                    connection.usage_error = "panel_usage_regressed"
                elif invalid == "stale":
                    observed["userTraffic"] = {
                        "usedTrafficBytes": 850,
                        "lifetimeUsedTrafficBytes": 850,
                    }
                elif invalid == "reset":
                    observed["trafficLimitStrategy"] = "MONTH"
                else:
                    period = await session.scalar(select(ServiceUsagePeriod))
                    assert period
                    if invalid == "missing_period":
                        await session.delete(period)
                        await session.flush()
                    elif invalid == "confirmed_period":
                        period.confirmed_at = datetime.now(UTC)
                    else:
                        period.cutover_bytes = 899
                assert not await settle_cancelled_service_period(
                    session, saved, connection, observed, actor_id=1
                )
                assert saved.used_bytes == 900 and connection.cycle_cutover_bytes == 900
                assert not await session.scalar(
                    select(ServiceOrder).where(ServiceOrder.kind == "settle_usage")
                )
                await session.rollback()

    async def test_terminal_retries_count_late_bytes_once_and_block_late_counter_anomalies(
        self,
    ) -> None:
        from bot.services.service_panel_state import locked_service

        service, remote = await self.cancelled_cutover()
        for total, record_first in (
            (1200, False),
            (1225, False),
            (1225, True),
            (1250, True),
            (1250, False),
        ):
            remote["userTraffic"] = {
                "usedTrafficBytes": total,
                "lifetimeUsedTrafficBytes": total,
            }
            async with self.sessions.begin() as session:
                locked = await locked_service(session, service.id)
                assert locked
                _, saved, connection = locked
                if record_first:
                    record_service_usage(saved, connection, remote)
                assert await settle_cancelled_service_period(
                    session, saved, connection, remote, actor_id=1
                )
            async with self.sessions() as session:
                saved = await session.get(UserService, service.id)
                connection = await session.get(ServiceConnection, service.id)
                period = await session.scalar(select(ServiceUsagePeriod))
                orders = list(
                    await session.scalars(
                        select(ServiceOrder).where(ServiceOrder.kind == "settle_usage")
                    )
                )
                assert saved and connection and period
                assert saved.used_bytes == total - period.cutover_bytes == total - 900
                assert connection.usage_total_bytes == connection.usage_raw_bytes == total
                assert connection.cycle_cutover_bytes is None and connection.usage_error is None
                assert saved.desired_status == "cancelled"
                assert connection.panel_user_uuid == remote["uuid"]
                assert period.used_bytes == 900 and period.confirmed_at is None
                assert len(orders) == 1
                assert orders[0].snapshot["usage_total_bytes"] == 1200
                assert orders[0].snapshot["used_bytes"] == 300
                assert orders[0].snapshot["cutover_bytes"] == 900
                assert orders[0].snapshot["allowance_confirmed"] is False
        # A later larger counter cannot clear the anomaly or silently forgive lost bytes.
        for total in (1100, 1275):
            remote["userTraffic"] = {
                "usedTrafficBytes": total,
                "lifetimeUsedTrafficBytes": total,
            }
            async with self.sessions.begin() as session:
                locked = await locked_service(session, service.id)
                assert locked
                _, saved, connection = locked
                assert not await settle_cancelled_service_period(
                    session, saved, connection, remote, actor_id=1
                )
                assert connection.usage_error == "panel_usage_regressed"
                assert connection.usage_total_bytes == 1250 and saved.used_bytes == 350
                assert saved.desired_status == "cancelled" and connection.state != "revoked"
        assert remote["trafficLimitBytes"] == 10000 and remote["status"] == "DISABLED"
        self.panel.create_panel_user.assert_not_awaited()
        self.panel.update_user_details_on_panel.assert_not_awaited()
        self.panel.update_user_status_on_panel.assert_not_awaited()

    async def test_cancelled_pending_period_settles_only_after_exact_anomaly_reconciliation(
        self,
    ) -> None:
        from bot.services.service_panel_state import locked_service

        service, remote = await self.cancelled_cutover()
        remote["userTraffic"] = {"usedTrafficBytes": 100, "lifetimeUsedTrafficBytes": 100}
        await synchronize_service_usage(cast(sessionmaker, self.sessions), service.id, self.panel)
        async with self.sessions.begin() as session:
            fixed, _, _ = await reconcile_service_usage(
                session,
                service_id=service.id,
                user_id=1,
                actor_id=1,
                expected_revision=2,
                idempotency_key="cancelled-recovery",
                change=ServiceChange(
                    action="reconcile_usage",
                    verified_total_bytes=1200,
                    expected_raw_bytes=100,
                    evidence="Exact final incident ledger",
                ),
                panel=self.panel,
            )
            assert fixed.used_bytes == 900 and fixed.desired_status == "cancelled"
        async with self.sessions.begin() as session:
            locked = await locked_service(session, service.id)
            assert locked
            _, saved, connection = locked
            assert await settle_cancelled_service_period(
                session, saved, connection, remote, actor_id=1
            )
            assert saved.used_bytes == 300 and saved.desired_status == "cancelled"
            assert connection.usage_total_bytes == 1200 and connection.usage_raw_bytes == 100
            assert connection.cycle_cutover_bytes is None
            period = await session.scalar(select(ServiceUsagePeriod))
            assert period and period.used_bytes == 900 and period.confirmed_at is None

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
