"""Cancellation preserves metering evidence before removing the remote identity."""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from bot.services.service_period_sync import prepare_service_cycle
from bot.services.service_reconciliation import reconcile_service_usage
from bot.services.service_revocation import revoke_service_identity
from bot.services.service_usage_sync import synchronize_service_usage
from config.service_changes import ServiceChange
from config.service_periods import monthly_period
from db.dal.service_delivery_dal import request_service_revocation
from db.service_models import ServiceConnection, ServiceOrder, ServiceUsagePeriod, UserService
from tests.unit.test_service_changes import ServiceChangeTestCase


class ServiceRevocationEntitlementTests(ServiceChangeTestCase):
    async def test_cancelled_counter_recovery_allows_revocation_without_restoring_access(
        self,
    ) -> None:
        service, _, _ = await self.activate()
        other, _, _ = await self.activate("unaffected")
        panel, remote = await self.prepare(service, ready=True)
        remote["userTraffic"] = {"usedTrafficBytes": 500, "lifetimeUsedTrafficBytes": 500}
        await synchronize_service_usage(cast(sessionmaker, self.sessions), service.id, panel)
        async with self.sessions.begin() as session:
            await request_service_revocation(
                session,
                service_id=service.id,
                user_id=1,
                actor_id=1,
                expected_revision=1,
                idempotency_key="cancel-before-reset",
                reason="End only this service",
            )
        remote["userTraffic"] = {"usedTrafficBytes": 0, "lifetimeUsedTrafficBytes": 0}
        await revoke_service_identity(cast(sessionmaker, self.sessions), service.id, panel)
        panel.delete_user_from_panel.assert_not_awaited()
        async with self.sessions.begin() as session:
            saved, audit, duplicate = await reconcile_service_usage(
                session,
                service_id=service.id,
                user_id=1,
                actor_id=1,
                expected_revision=2,
                idempotency_key="exact-cancelled-recovery",
                change=ServiceChange(
                    action="reconcile_usage",
                    verified_total_bytes=600,
                    expected_raw_bytes=0,
                    evidence="Exact isolated ledger: 500 before reset plus 100 missing bytes",
                ),
                panel=panel,
            )
            assert not duplicate and saved.desired_status == "cancelled" and saved.used_bytes == 600
            assert audit.kind == "reconcile_usage"
        remote["userTraffic"] = {"usedTrafficBytes": 25, "lifetimeUsedTrafficBytes": 25}

        async def delete(_reference: str) -> None:
            self.remote_users.clear()
            raise TimeoutError("DELETE succeeded but its response was lost")

        panel.delete_user_from_panel.side_effect = delete
        await revoke_service_identity(cast(sessionmaker, self.sessions), service.id, panel)
        async with self.sessions() as session:
            saved = await session.get(UserService, service.id)
            connection = await session.get(ServiceConnection, service.id)
            assert saved and saved.used_bytes == 625
            assert connection and connection.usage_total_bytes == 625 and connection.sync_pending
        await revoke_service_identity(cast(sessionmaker, self.sessions), service.id, panel)
        async with self.sessions() as session:
            connection = await session.get(ServiceConnection, service.id)
            unaffected = await session.get(UserService, other.id)
            assert connection and connection.state == "revoked" and connection.revoked_at
            assert (
                unaffected and unaffected.desired_status == "active" and unaffected.used_bytes == 0
            )
        panel.delete_user_from_panel.assert_awaited_once()
        assert all(
            call.args[1] is False for call in panel.update_user_status_on_panel.await_args_list
        )
        panel.create_panel_user.assert_awaited_once()

    async def pending_monthly_cancellation(self) -> tuple[UserService, dict[str, Any]]:
        service, _, _ = await self.activate()
        panel, remote = await self.prepare(service, ready=True)
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
        await prepare_service_cycle(cast(sessionmaker, self.sessions), service.id, panel)
        async with self.sessions.begin() as session:
            await request_service_revocation(
                session,
                service_id=service.id,
                user_id=1,
                actor_id=1,
                expected_revision=1,
                idempotency_key="cancel-pending-cutover",
                reason="Cancellation during a lost cap confirmation",
            )
        remote["userTraffic"] = {"usedTrafficBytes": 1100, "lifetimeUsedTrafficBytes": 1100}
        return service, remote

    async def test_pending_cutover_and_late_bytes_are_committed_before_lost_delete_reply(
        self,
    ) -> None:
        service, remote = await self.pending_monthly_cancellation()
        lookup = self.panel.get_user_by_uuid_lookup.side_effect
        assert callable(lookup)
        reads = 0

        async def growing(reference: str) -> dict[str, Any]:
            nonlocal reads
            reads += 1
            if reads == 3:
                remote["userTraffic"] = {"usedTrafficBytes": 1250, "lifetimeUsedTrafficBytes": 1250}
            result = await lookup(reference)
            assert isinstance(result, dict)
            return result

        async def delete(_reference: str) -> None:
            # A separate transaction proves persistence before the irreversible side effect.
            async with self.sessions() as session:
                saved = await session.get(UserService, service.id)
                connection = await session.get(ServiceConnection, service.id)
                assert saved and saved.used_bytes == 350
                assert connection and connection.usage_total_bytes == 1250
                assert connection.cycle_cutover_bytes is None
            self.remote_users.clear()
            raise TimeoutError("DELETE completed; response lost")

        self.panel.get_user_by_uuid_lookup.side_effect = growing
        self.panel.delete_user_from_panel.side_effect = delete
        await revoke_service_identity(cast(sessionmaker, self.sessions), service.id, self.panel)
        async with self.sessions() as session:
            saved = await session.get(UserService, service.id)
            connection = await session.get(ServiceConnection, service.id)
            period = await session.scalar(
                select(ServiceUsagePeriod).where(ServiceUsagePeriod.service_id == service.id)
            )
            settlements = list(
                await session.scalars(
                    select(ServiceOrder).where(ServiceOrder.kind == "settle_usage")
                )
            )
            assert saved and saved.desired_status == "cancelled" and saved.used_bytes == 350
            assert (
                connection
                and connection.usage_total_bytes == 1250
                and connection.usage_raw_bytes == 1250
            )
            assert connection.cycle_cutover_bytes is None and connection.sync_pending
            assert period and period.used_bytes == 900 and period.cutover_bytes == 900
            assert period.confirmed_at is None
            assert len(settlements) == 1
            assert settlements[0].actor_id == 1
            assert settlements[0].snapshot["allowance_confirmed"] is False
            assert settlements[0].snapshot["usage_total_bytes"] == 1100
            assert settlements[0].snapshot["used_bytes"] == 200
        await revoke_service_identity(cast(sessionmaker, self.sessions), service.id, self.panel)
        async with self.sessions() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection and connection.state == "revoked" and not connection.sync_pending
        assert remote["status"] == "DISABLED"
        self.panel.delete_user_from_panel.assert_awaited_once()
        self.panel.update_user_details_on_panel.assert_not_awaited()

    async def test_missing_identity_does_not_claim_pending_period_accounting_complete(self) -> None:
        service, _ = await self.pending_monthly_cancellation()
        self.remote_users.clear()
        await revoke_service_identity(cast(sessionmaker, self.sessions), service.id, self.panel)
        async with self.sessions() as session:
            connection = await session.get(ServiceConnection, service.id)
            saved = await session.get(UserService, service.id)
            assert connection and connection.cycle_cutover_bytes == 900 and connection.sync_pending
            assert connection.revoked_at is None
            assert saved and saved.used_bytes == 900
        self.panel.delete_user_from_panel.assert_not_awaited()

    async def test_anomaly_in_final_read_blocks_delete_after_terminal_settlement(self) -> None:
        service, remote = await self.pending_monthly_cancellation()
        lookup = self.panel.get_user_by_uuid_lookup.side_effect
        assert callable(lookup)
        reads = 0

        async def regressing(reference: str) -> dict[str, Any]:
            nonlocal reads
            reads += 1
            if reads == 3:
                remote["userTraffic"] = {"usedTrafficBytes": 10, "lifetimeUsedTrafficBytes": 10}
            result = await lookup(reference)
            assert isinstance(result, dict)
            return result

        self.panel.get_user_by_uuid_lookup.side_effect = regressing
        await revoke_service_identity(cast(sessionmaker, self.sessions), service.id, self.panel)
        async with self.sessions() as session:
            connection = await session.get(ServiceConnection, service.id)
            saved = await session.get(UserService, service.id)
            assert connection and connection.usage_error == "panel_usage_regressed"
            assert connection.usage_total_bytes == 1100 and connection.cycle_cutover_bytes is None
            assert connection.revoked_at is None and connection.sync_pending
            assert saved and saved.used_bytes == 200 and saved.desired_status == "cancelled"
        self.panel.delete_user_from_panel.assert_not_awaited()
