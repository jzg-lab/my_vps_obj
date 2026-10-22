"""Delivery commits intent before enabling through the shared entitlement synchronizer."""

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from bot.services.service_change_sync import ServiceChangeWorker
from bot.services.service_delivery import deliver_service_identity, service_subscription
from bot.services.service_provisioning import ServiceProvisioningWorker
from db.dal.service_delivery_dal import request_service_delivery
from db.dal.user_services_dal import ServiceConflict
from db.models import User
from db.service_models import ServiceConnection, ServiceOrder, UserService
from tests.unit.test_service_changes import ServiceChangeTestCase


class ServiceActivationDeliveryTests(ServiceChangeTestCase):
    async def request(self, service: UserService) -> tuple[UserService, ServiceOrder, bool]:
        async with self.sessions.begin() as session:
            service, order, duplicate = await request_service_delivery(
                session,
                service_id=service.id,
                user_id=1,
                actor_id=1,
                expected_revision=service.revision,
                idempotency_key=f"deliver:{service.id}",
            )
            return service, order, duplicate

    async def test_no_delivery_without_metering_and_explicit_request(self) -> None:
        service, _, _ = await self.activate()
        panel, remote = await self.prepare(service)
        with pytest.raises(ServiceConflict, match="service_not_deliverable"):
            await self.request(service)
        await self.sync(service, panel)
        await deliver_service_identity(cast(sessionmaker, self.sessions), service.id, panel)
        assert remote["status"] == "DISABLED"
        async with self.sessions() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection and connection.state == "pending"
            assert not list(
                await session.scalars(select(ServiceOrder).where(ServiceOrder.kind == "deliver"))
            )
        panel.update_user_status_on_panel.assert_not_awaited()

    async def test_worker_delivers_once_without_replacing_identity_or_allowance(self) -> None:
        service, _, _ = await self.activate()
        other, _, _ = await self.activate("other")
        panel, remote = await self.prepare(service)
        remote["userTraffic"] = {"usedTrafficBytes": 123, "lifetimeUsedTrafficBytes": 123}
        await self.sync(service, panel)
        updated, order, duplicate = await self.request(service)
        assert not duplicate and updated.revision == 2 and order.kind == "deliver"
        worker = ServiceProvisioningWorker(cast(sessionmaker, self.sessions), panel)
        await worker.tick()
        await worker.tick()
        _, repeated, duplicate = await self.request(service)
        assert duplicate and repeated.id == order.id
        assert remote["status"] == "ACTIVE" and remote["trafficLimitBytes"] == 10_000
        assert panel.create_panel_user.await_count == 2  # Other service is only prepared.
        async with self.sessions() as session:
            row = await session.get(UserService, service.id)
            connection = await session.get(ServiceConnection, service.id)
            second = await session.get(ServiceConnection, other.id)
            assert row and row.used_bytes == 123 and row.quota_bytes == 10_000
            assert connection and connection.state == "ready" and not connection.sync_pending
            assert second and second.state == "pending"
            remote["subscriptionUrl"] = "https://subscription.example.test/one"
            assert (
                await service_subscription(session, user_id=1, service_id=service.id, panel=panel)
                == remote["subscriptionUrl"]
            )

    async def test_safe_disabled_result_with_unrepaired_terms_is_not_ready(self) -> None:
        service, _, _ = await self.activate()
        panel, remote = await self.prepare(service)
        await self.sync(service, panel)
        await self.request(service)
        remote["userTraffic"] = {"usedTrafficBytes": -1, "lifetimeUsedTrafficBytes": 0}
        await deliver_service_identity(cast(sessionmaker, self.sessions), service.id, panel)
        async with self.sessions() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection and connection.state == "pending" and connection.sync_pending
            assert connection.usage_error == "panel_usage_invalid"
        assert remote["status"] == "DISABLED"
        panel.update_user_status_on_panel.assert_not_awaited()

    async def test_restrictions_after_request_prevent_enable(self) -> None:
        for restriction in ("ban", "pause", "expiry", "exhaustion"):
            with self.subTest(restriction=restriction):
                service, _, _ = await self.activate(restriction)
                panel, remote = await self.prepare(service)
                await self.sync(service, panel)
                await self.request(service)
                async with self.sessions.begin() as session:
                    row = await session.get(UserService, service.id)
                    user = await session.get(User, 1)
                    assert row and user
                    if restriction == "ban":
                        user.is_banned = True
                    elif restriction == "pause":
                        row.desired_status = "paused"
                    elif restriction == "expiry":
                        row.starts_at = datetime.now(UTC) - timedelta(days=2)
                        row.expires_at = datetime.now(UTC) - timedelta(days=1)
                    else:
                        remote["userTraffic"] = {
                            "usedTrafficBytes": 10_001,
                            "lifetimeUsedTrafficBytes": 10_001,
                        }
                await deliver_service_identity(cast(sessionmaker, self.sessions), service.id, panel)
                assert remote["status"] == "DISABLED"
                async with self.sessions.begin() as session:
                    connection = await session.get(ServiceConnection, service.id)
                    user = await session.get(User, 1)
                    assert connection and connection.state == "pending"
                    assert user
                    user.is_banned = False

    async def test_crash_after_ready_marker_retries_and_honors_new_ban(self) -> None:
        for banned in (False, True):
            with self.subTest(banned=banned):
                service, _, _ = await self.activate(str(banned))
                panel, remote = await self.prepare(service)
                await self.sync(service, panel)
                await self.request(service)
                with (
                    patch(
                        "bot.services.service_delivery.synchronize_service_change",
                        side_effect=RuntimeError("crash"),
                    ),
                    pytest.raises(RuntimeError, match="crash"),
                ):
                    await deliver_service_identity(
                        cast(sessionmaker, self.sessions), service.id, panel
                    )
                async with self.sessions.begin() as session:
                    connection = await session.get(ServiceConnection, service.id)
                    assert connection and connection.state == "ready" and connection.sync_pending
                    if banned:
                        user = await session.get(User, 1)
                        assert user
                        user.is_banned = True
                assert remote["status"] == "DISABLED"
                # Use this service's entry to keep the fake remote scoped to its identity.
                await self.sync(service, panel)
                assert remote["status"] == ("DISABLED" if banned else "ACTIVE")
                async with self.sessions() as session:
                    connection = await session.get(ServiceConnection, service.id)
                    assert connection and not connection.sync_pending

    async def test_delivery_request_worker_recovers_after_panel_outage(self) -> None:
        service, _, _ = await self.activate()
        panel, remote = await self.prepare(service)
        await self.sync(service, panel)
        await self.request(service)
        lookup = panel.get_user_by_uuid_lookup.side_effect
        panel.get_user_by_uuid_lookup.side_effect = TimeoutError("unavailable")
        await deliver_service_identity(cast(sessionmaker, self.sessions), service.id, panel)
        assert remote["status"] == "DISABLED"
        panel.get_user_by_uuid_lookup.side_effect = lookup
        await ServiceChangeWorker(cast(sessionmaker, self.sessions), panel).tick()
        await ServiceProvisioningWorker(cast(sessionmaker, self.sessions), panel).tick()
        assert remote["status"] == "ACTIVE"
