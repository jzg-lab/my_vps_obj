"""Quota edits and evidence-based counter recovery retain paid history and usage."""

from typing import cast

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from bot.services.service_change_sync import ServiceChangeWorker, synchronize_service_change
from bot.services.service_reconciliation import reconcile_service_usage
from bot.services.service_usage_sync import synchronize_service_usage
from config.service_changes import ServiceChange
from db.dal.user_services_dal import ServiceConflict, save_plan
from db.service_models import ServiceConnection, ServiceOrder, UserService
from tests.unit.test_service_changes import ServiceChangeTestCase
from tests.unit.test_user_services import sample_terms


class ServiceAdjustmentTests(ServiceChangeTestCase):
    async def test_cancelled_service_can_reconcile_without_restoring_or_replacing_identity(
        self,
    ) -> None:
        for anomaly, lifetime in [("panel_usage_reset", 300), ("panel_usage_regressed", 100)]:
            with self.subTest(anomaly=anomaly):
                service, _, _ = await self.activate(anomaly)
                _, remote = await self.prepare(service, ready=True)
                remote["userTraffic"] = {"usedTrafficBytes": 500, "lifetimeUsedTrafficBytes": 500}
                await synchronize_service_usage(
                    cast(sessionmaker, self.sessions), service.id, self.panel
                )
                async with self.sessions.begin() as session:
                    saved = await session.get(UserService, service.id)
                    assert saved
                    # B persists this cancellation before trying to revoke the identity.
                    saved.desired_status = "cancelled"
                    saved.revision += 1
                remote["userTraffic"] = {
                    "usedTrafficBytes": 100,
                    "lifetimeUsedTrafficBytes": lifetime,
                }
                await synchronize_service_change(
                    cast(sessionmaker, self.sessions), service.id, self.panel
                )
                async with self.sessions() as session:
                    connection = await session.get(ServiceConnection, service.id)
                    assert connection and connection.usage_error == anomaly
                    identity = (connection.panel_user_uuid, connection.username, connection.state)
                change = ServiceChange(
                    action="reconcile_usage",
                    verified_total_bytes=600,
                    expected_raw_bytes=100,
                    evidence="Exact cancellation incident ledger",
                )
                remote["status"] = "ACTIVE"
                async with self.sessions() as session:
                    with self.assertRaisesRegex(
                        ServiceConflict, "usage_reconciliation_pause_required"
                    ):
                        await reconcile_service_usage(
                            session,
                            service_id=service.id,
                            user_id=1,
                            actor_id=1,
                            expected_revision=2,
                            idempotency_key=f"recover:{anomaly}",
                            change=change,
                            panel=self.panel,
                        )
                remote["status"] = "DISABLED"
                self.panel.reset_mock()
                async with self.sessions.begin() as session:
                    fixed, order, duplicate = await reconcile_service_usage(
                        session,
                        service_id=service.id,
                        user_id=1,
                        actor_id=1,
                        expected_revision=2,
                        idempotency_key=f"recover:{anomaly}",
                        change=change,
                        panel=self.panel,
                    )
                    assert not duplicate and fixed.used_bytes == 600
                    assert fixed.desired_status == "cancelled"
                    assert order.snapshot["before"]["desired_status"] == "cancelled"
                    assert order.snapshot["desired_status"] == "cancelled"
                async with self.sessions.begin() as session:
                    _, replay, duplicate = await reconcile_service_usage(
                        session,
                        service_id=service.id,
                        user_id=1,
                        actor_id=1,
                        expected_revision=2,
                        idempotency_key=f"recover:{anomaly}",
                        change=change,
                        panel=None,
                    )
                    assert duplicate and replay.id == order.id
                for action in ("resume", "renew", "pause"):
                    with self.assertRaisesRegex(ServiceConflict, "service_not_editable"):
                        await self.change(fixed, action, key=f"blocked:{anomaly}:{action}")
                await synchronize_service_change(
                    cast(sessionmaker, self.sessions), service.id, self.panel
                )
                async with self.sessions() as session:
                    saved = await session.get(UserService, service.id)
                    connection = await session.get(ServiceConnection, service.id)
                    assert saved and connection
                    assert saved.desired_status == "cancelled" and saved.used_bytes == 600
                    assert saved.quota_bytes == service.quota_bytes
                    assert connection.usage_error is None and connection.usage_total_bytes == 600
                    assert (
                        connection.panel_user_uuid,
                        connection.username,
                        connection.state,
                    ) == identity
                self.panel.create_panel_user.assert_not_awaited()
                self.panel.update_user_details_on_panel.assert_not_awaited()
                self.panel.update_user_status_on_panel.assert_not_awaited()
                assert remote["status"] == "DISABLED"
                # The successful recovery response can be lost before revocation completes.
                async with self.sessions.begin() as session:
                    connection = await session.get(ServiceConnection, service.id)
                    assert connection
                    connection.state = "revoked"
                self.panel.reset_mock()
                async with self.sessions.begin() as session:
                    replayed, replay, duplicate = await reconcile_service_usage(
                        session,
                        service_id=service.id,
                        user_id=1,
                        actor_id=1,
                        expected_revision=2,
                        idempotency_key=f"recover:{anomaly}",
                        change=change,
                        panel=None,
                    )
                    assert duplicate and replay.id == order.id and replayed.used_bytes == 600
                    assert replayed.desired_status == "cancelled" and replayed.revision == 3
                for owner, key, revision, error in [
                    (1, f"new:{anomaly}", 3, "service_not_found"),
                    (1, f"recover:{anomaly}", 3, "idempotency_conflict"),
                    (2, f"recover:{anomaly}", 2, "service_not_found"),
                ]:
                    with self.subTest(owner=owner, key=key):
                        async with self.sessions() as session:
                            with self.assertRaisesRegex(ServiceConflict, error):
                                await reconcile_service_usage(
                                    session,
                                    service_id=service.id,
                                    user_id=owner,
                                    actor_id=1,
                                    expected_revision=revision,
                                    idempotency_key=key,
                                    change=change,
                                    panel=self.panel,
                                )
                self.panel.get_user_by_uuid_lookup.assert_not_awaited()

    async def test_template_quota_applies_to_existing_services_once_without_rewriting_snapshot(
        self,
    ) -> None:
        first, activation, _ = await self.activate()
        second, _, _ = await self.activate("second", user_id=2)
        async with self.sessions.begin() as session:
            saved = await session.get(UserService, first.id)
            assert saved
            saved.used_bytes = 8000
            saved.desired_status = "paused"
            await save_plan(
                session,
                plan_id=self.plan.id,
                expected_revision=1,
                terms=sample_terms(quota_bytes=7000, name="New name", price="8"),
                enabled=True,
                actor_id=1,
                quota_change_reason="New allowance for every subscriber",
            )
        for _ in range(2):
            await ServiceChangeWorker(cast(sessionmaker, self.sessions), self.panel).tick()
        async with self.sessions() as session:
            a, b = (
                await session.get(UserService, first.id),
                await session.get(UserService, second.id),
            )
            assert a and b and a.quota_bytes == b.quota_bytes == 7000
            assert a.used_bytes == 8000 and b.used_bytes == 0 and a.desired_status == "paused"
            assert a.terms["quota_bytes"] == b.terms["quota_bytes"] == 10000
            assert a.terms["name"] == first.terms["name"]
            old = await session.get(ServiceOrder, activation.id)
            assert old and old.snapshot == activation.snapshot
            changes = list(
                await session.scalars(select(ServiceOrder).where(ServiceOrder.kind == "quota"))
            )
            assert len(changes) == 2 and {row.actor_id for row in changes} == {1}
            assert changes[0].snapshot["before"] == {"quota_bytes": 10000}
        # A service opened after editing already has the new quota and no duplicate adjustment.
        async with self.sessions.begin() as session:
            from db.dal.user_services_dal import activate_service

            opened, _, _ = await activate_service(
                session,
                user_id=1,
                actor_id=1,
                plan_id=self.plan.id,
                expected_revision=2,
                idempotency_key="after-edit",
            )
        await ServiceChangeWorker(cast(sessionmaker, self.sessions), self.panel).tick()
        async with self.sessions() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ServiceOrder)
                    .where(ServiceOrder.kind == "quota")
                )
                == 2
            )
            saved = await session.get(UserService, opened.id)
            assert saved and saved.quota_bytes == 7000 and saved.quota_revision == 2

    async def test_unexplained_quota_edit_is_rejected(self) -> None:
        async with self.sessions() as session:
            with self.assertRaisesRegex(ServiceConflict, "quota_change_reason_required"):
                await save_plan(
                    session,
                    plan_id=self.plan.id,
                    expected_revision=1,
                    terms=sample_terms(quota_bytes=8000),
                    enabled=True,
                    actor_id=1,
                )

    async def test_accurate_recovery_records_offset_without_clearing_previous_usage(self) -> None:
        service, _, _ = await self.activate()
        _, remote = await self.prepare(service, ready=True)
        remote["userTraffic"] = {"usedTrafficBytes": 500, "lifetimeUsedTrafficBytes": 500}
        await synchronize_service_usage(cast(sessionmaker, self.sessions), service.id, self.panel)
        remote["userTraffic"] = {"usedTrafficBytes": 100, "lifetimeUsedTrafficBytes": 300}
        await synchronize_service_usage(cast(sessionmaker, self.sessions), service.id, self.panel)
        paused, _, _ = await self.change(service, "pause")
        await synchronize_service_change(cast(sessionmaker, self.sessions), service.id, self.panel)
        change = ServiceChange(
            action="reconcile_usage",
            verified_total_bytes=600,
            expected_raw_bytes=100,
            evidence="Exact per-identity byte ledger, incident 2026-10-23",
        )
        async with self.sessions.begin() as session:
            fixed, order, duplicate = await reconcile_service_usage(
                session,
                service_id=service.id,
                user_id=1,
                actor_id=1,
                expected_revision=paused.revision,
                idempotency_key="recover",
                change=change,
                panel=self.panel,
            )
            assert not duplicate and fixed.used_bytes == 600
            assert order.snapshot["before"]["used_bytes"] == 500
        # Idempotency works even if the panel becomes unavailable after committing.
        async with self.sessions.begin() as session:
            fixed, same, duplicate = await reconcile_service_usage(
                session,
                service_id=service.id,
                user_id=1,
                actor_id=1,
                expected_revision=paused.revision,
                idempotency_key="recover",
                change=change,
                panel=None,
            )
            assert duplicate and same.id == order.id and fixed.used_bytes == 600
        await synchronize_service_change(cast(sessionmaker, self.sessions), service.id, self.panel)
        assert remote["trafficLimitBytes"] == 9500 and remote["status"] == "DISABLED"
        remote["userTraffic"] = {"usedTrafficBytes": 150, "lifetimeUsedTrafficBytes": 350}
        await synchronize_service_usage(cast(sessionmaker, self.sessions), service.id, self.panel)
        async with self.sessions() as session:
            saved = await session.get(UserService, service.id)
            connection = await session.get(ServiceConnection, service.id)
            assert saved and connection and saved.used_bytes == 650
            assert connection.usage_total_bytes == 650 and connection.usage_error is None
            assert connection.usage_raw_bytes == 150 and connection.usage_lifetime_offset == 200
        self.panel.create_panel_user.assert_awaited_once()

    async def test_recovery_rejects_active_identity_wrong_counter_and_lost_history_forgiveness(
        self,
    ) -> None:
        service, _, _ = await self.activate()
        _, remote = await self.prepare(service, ready=True)
        async with self.sessions.begin() as session:
            saved = await session.get(UserService, service.id)
            connection = await session.get(ServiceConnection, service.id)
            assert saved and connection
            saved.used_bytes = 500
            connection.usage_total_bytes = 500
            connection.usage_error = "panel_usage_regressed"
        for paused, verified, raw, code in [
            (False, 500, 0, "usage_reconciliation_pause_required"),
            (True, 499, 0, "usage_reconciliation_changed"),
            (True, 500, 1, "usage_reconciliation_changed"),
        ]:
            async with self.sessions.begin() as session:
                saved = await session.get(UserService, service.id)
                assert saved
                saved.desired_status = "paused" if paused else "active"
            remote["status"] = "DISABLED" if paused else "ACTIVE"
            async with self.sessions() as session:
                with self.assertRaisesRegex(ServiceConflict, code):
                    await reconcile_service_usage(
                        session,
                        service_id=service.id,
                        user_id=1,
                        actor_id=1,
                        expected_revision=1,
                        idempotency_key="bad",
                        change=ServiceChange(
                            action="reconcile_usage",
                            verified_total_bytes=verified,
                            expected_raw_bytes=raw,
                            evidence="Checked ledger",
                        ),
                        panel=self.panel,
                    )
        async with self.sessions() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection and connection.usage_error == "panel_usage_regressed"
