"""A committed attempt belongs to one owner and revision across transaction boundaries."""

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.services.service_change_sync import synchronize_service_change
from bot.services.service_delivery import deliver_service_identity
from bot.services.service_provisioning import provision_service_identity
from bot.services.service_revocation import revoke_service_identity
from bot.services.service_usage_sync import synchronize_service_usage
from config.service_changes import ServiceChange
from config.service_periods import monthly_period
from db.dal.service_accounts_dal import merge_history
from db.dal.service_changes_dal import change_service
from db.dal.service_delivery_dal import request_service_delivery, request_service_revocation
from db.service_models import (
    ServiceConnection,
    ServiceOperationExecution,
    ServiceUsagePeriod,
    UserService,
)
from tests.unit.test_service_changes import ServiceChangeTestCase


class ServiceOperationRaceTests(ServiceChangeTestCase):
    async def execution(self, order_id: str) -> ServiceOperationExecution:
        async with self.sessions() as session:
            row = await session.scalar(
                select(ServiceOperationExecution).where(
                    ServiceOperationExecution.order_id == order_id
                )
            )
            assert row
            return row

    async def test_new_revision_waits_for_its_own_committed_marker(self) -> None:
        service, _, _ = await self.activate()
        panel, remote = await self.prepare(service, ready=True)
        renewed, renewal, _ = await self.change(service)
        commit = AsyncSession.commit
        replacement_order: str | None = None

        async def pause_after_marker(session: AsyncSession) -> None:
            nonlocal replacement_order
            marked = any(
                isinstance(row, ServiceOperationExecution)
                and row.order_id == renewal.id
                and row.status == "unknown"
                for row in session.identity_map.values()
            )
            await commit(session)
            if marked and replacement_order is None:
                async with self.sessions.begin() as other:
                    _, order, _ = await change_service(
                        other,
                        service_id=service.id,
                        user_id=1,
                        actor_id=1,
                        expected_revision=renewed.revision,
                        idempotency_key="race-pause",
                        change=ServiceChange(action="pause"),
                    )
                    replacement_order = order.id

        panel.reset_mock()
        with patch.object(AsyncSession, "commit", pause_after_marker):
            await self.sync(service, panel)
        assert replacement_order is not None
        queued = await self.execution(replacement_order)
        assert queued.status == "pending" and queued.attempt_count == 0
        assert not panel.mock_calls
        lookup = panel.get_user_by_uuid_lookup.side_effect
        assert callable(lookup)

        async def observe(reference: str):
            row = await self.execution(replacement_order)
            assert row.status == "unknown" and row.attempt_count == 1
            return await lookup(reference)

        panel.get_user_by_uuid_lookup.side_effect = observe
        await self.sync(service, panel)
        assert (await self.execution(replacement_order)).status == "succeeded"
        assert remote["status"] == "DISABLED"
        panel.create_panel_user.assert_not_awaited()

    async def test_owner_change_fences_every_worker_after_its_marker_commit(self) -> None:
        commit = AsyncSession.commit
        workers = {
            "prepare": provision_service_identity,
            "delivery": deliver_service_identity,
            "usage": synchronize_service_usage,
            "revocation": revoke_service_identity,
        }
        for phase, worker in workers.items():
            with self.subTest(phase=phase):
                service, _, _ = await self.activate(phase)
                if phase != "prepare":
                    await self.prepare(service, ready=phase != "delivery")
                if phase == "delivery":
                    await synchronize_service_usage(
                        cast(sessionmaker, self.sessions), service.id, self.panel
                    )
                    async with self.sessions.begin() as session:
                        await request_service_delivery(
                            session,
                            service_id=service.id,
                            user_id=1,
                            actor_id=1,
                            expected_revision=1,
                            idempotency_key="deliver",
                        )
                if phase == "revocation":
                    async with self.sessions.begin() as session:
                        await request_service_revocation(
                            session,
                            service_id=service.id,
                            user_id=1,
                            actor_id=1,
                            expected_revision=1,
                            idempotency_key="revoke",
                            reason="test",
                        )
                moved = False

                async def merge_after_marker(session: AsyncSession) -> None:
                    nonlocal moved
                    await commit(session)
                    if not moved:
                        moved = True
                        async with self.sessions.begin() as other:
                            await merge_history(other, 1, 2)

                self.panel.reset_mock()
                with patch.object(AsyncSession, "commit", merge_after_marker):
                    await worker(cast(sessionmaker, self.sessions), service.id, self.panel)
                assert moved and not self.panel.mock_calls
                async with self.sessions() as session:
                    saved = await session.get(UserService, service.id)
                    assert saved and saved.user_id == 2

    async def test_monthly_second_pass_defers_a_new_pending_pause(self) -> None:
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
        commit = AsyncSession.commit
        pause_order: str | None = None
        calls_after_pause: list[str] = []

        async def pause_after_cutover(session: AsyncSession) -> None:
            nonlocal pause_order
            confirmed = any(
                isinstance(row, ServiceConnection)
                and row.cycle_cutover_bytes is None
                and row.sync_error == "panel_cycle_unconfirmed"
                for row in session.identity_map.values()
            )
            await commit(session)
            if confirmed and pause_order is None:
                async with self.sessions.begin() as other:
                    _, order, _ = await change_service(
                        other,
                        service_id=service.id,
                        user_id=1,
                        actor_id=1,
                        expected_revision=1,
                        idempotency_key="pause-after-cutover",
                        change=ServiceChange(action="pause"),
                    )
                    pause_order = order.id

        lookup = panel.get_user_by_uuid_lookup.side_effect
        assert callable(lookup)

        async def observe(reference: str):
            if pause_order is not None:
                calls_after_pause.append((await self.execution(pause_order)).status)
            return await lookup(reference)

        panel.get_user_by_uuid_lookup.side_effect = observe
        with patch.object(AsyncSession, "commit", pause_after_cutover):
            await synchronize_service_change(cast(sessionmaker, self.sessions), service.id, panel)
        assert pause_order is not None and calls_after_pause == []
        assert (await self.execution(pause_order)).status == "pending"
        await self.sync(service, panel)
        assert calls_after_pause and set(calls_after_pause) == {"unknown"}
        assert (await self.execution(pause_order)).status == "succeeded"
        assert remote["status"] == "DISABLED" and remote["trafficLimitBytes"] == 10900
        async with self.sessions() as session:
            periods = list(await session.scalars(select(ServiceUsagePeriod)))
            assert len(periods) == 1 and periods[0].used_bytes == 900

    async def test_revocation_rechecks_owner_after_each_accounting_commit(self) -> None:
        commit = AsyncSession.commit
        for boundary in ("usage", "delete_intent"):
            with self.subTest(boundary=boundary):
                service, _, _ = await self.activate(boundary)
                panel, _ = await self.prepare(service, ready=True)
                async with self.sessions.begin() as session:
                    await request_service_revocation(
                        session,
                        service_id=service.id,
                        user_id=1,
                        actor_id=1,
                        expected_revision=1,
                        idempotency_key=f"revoke:{boundary}",
                        reason="test",
                    )
                moved = False
                calls_at_merge: int | None = None

                async def merge_after_accounting(
                    session: AsyncSession, expected_boundary: str = boundary
                ) -> None:
                    nonlocal moved, calls_at_merge
                    reached = any(
                        isinstance(row, ServiceConnection)
                        and row.usage_total_bytes is not None
                        and (
                            expected_boundary == "usage"
                            or row.revoke_delete_requested_at is not None
                        )
                        for row in session.identity_map.values()
                    )
                    await commit(session)
                    if reached and not moved:
                        moved = True
                        async with self.sessions.begin() as other:
                            await merge_history(other, 1, 2)
                        calls_at_merge = self.panel.get_user_by_uuid_lookup.await_count

                panel.reset_mock()
                with patch.object(AsyncSession, "commit", merge_after_accounting):
                    await revoke_service_identity(
                        cast(sessionmaker, self.sessions), service.id, panel
                    )
                assert moved and panel.get_user_by_uuid_lookup.await_count == calls_at_merge
                panel.delete_user_from_panel.assert_not_awaited()
