"""Cancellation preserves metering evidence before removing the remote identity."""

from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from bot.services.service_period_sync import prepare_service_cycle
from bot.services.service_revocation import revoke_service_identity
from config.service_periods import monthly_period
from db.dal.service_delivery_dal import request_service_revocation
from db.service_models import ServiceConnection, ServiceUsagePeriod, UserService
from tests.unit.test_service_changes import ServiceChangeTestCase


class ServiceRevocationEntitlementTests(ServiceChangeTestCase):
    async def test_pending_cutover_preserves_both_sides_before_destructive_delete(self) -> None:
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
        await revoke_service_identity(cast(sessionmaker, self.sessions), service.id, panel)
        async with self.sessions() as session:
            saved = await session.get(UserService, service.id)
            connection = await session.get(ServiceConnection, service.id)
            period = await session.scalar(
                select(ServiceUsagePeriod).where(ServiceUsagePeriod.service_id == service.id)
            )
            assert saved and saved.desired_status == "cancelled" and saved.used_bytes == 900
            assert (
                connection
                and connection.usage_total_bytes == 1100
                and connection.usage_raw_bytes == 1100
            )
            assert connection.cycle_cutover_bytes == 900 and connection.usage_attempted_at
            assert (
                connection.sync_pending and connection.sync_error == "service_revoke_cycle_pending"
            )
            assert period and period.used_bytes == 900 and period.cutover_bytes == 900
            assert period.confirmed_at is None
        assert remote["status"] == "DISABLED"
        panel.delete_user_from_panel.assert_not_awaited()
