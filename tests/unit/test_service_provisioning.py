"""Preparing a service identity cannot leak legacy quotas or orphan remote access."""

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import AsyncMock, patch
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from bot.services.panel_api_service import PanelApiService
from bot.services.service_provisioning import ServiceProvisioningWorker, provision_service_identity
from db.dal.service_accounts_dal import deletion_connections
from db.dal.user_services_dal import ServiceConflict, activate_service, create_exit, save_plan
from db.models import User
from db.service_models import DedicatedExit, ServiceConnection, UserService
from tests.unit.test_user_services import ServiceDatabaseTestCase, sample_terms


def panel_fixture() -> tuple[AsyncMock, dict[str, dict[str, Any]]]:
    panel = AsyncMock(spec=PanelApiService)
    users: dict[str, dict[str, Any]] = {}

    async def lookup(*, username: str) -> list[dict[str, Any]]:
        return [dict(users[username])] if username in users else []

    async def lookup_id(reference: str) -> dict[str, Any]:
        found = next((user for user in users.values() if user["uuid"] == reference), None)
        return {"ok": found is not None, "not_found": found is None, "user": found}

    async def create(username: str, **kwargs: Any) -> dict[str, Any]:
        users[username] = {
            "uuid": str(len(users) + 1),
            "username": username,
            "status": kwargs["status"],
            "description": kwargs["description"],
            "expireAt": kwargs["expire_at"].replace(tzinfo=UTC).isoformat(),
            "activeInternalSquads": [{"uuid": value} for value in kwargs["specific_squad_uuids"]],
            "trafficLimitBytes": kwargs["default_traffic_limit_bytes"],
            "trafficLimitStrategy": kwargs["default_traffic_limit_strategy"],
            "userTraffic": {"usedTrafficBytes": 0, "lifetimeUsedTrafficBytes": 0},
        }
        return {"response": users[username]}

    panel.get_users_by_filter.side_effect = lookup
    panel.get_user_by_uuid_lookup.side_effect = lookup_id
    panel.create_panel_user.side_effect = create
    return panel, users


class ServiceProvisioningTests(ServiceDatabaseTestCase):
    async def test_local_refusals_cannot_starve_the_next_remote_candidate(self) -> None:
        with patch(
            "db.dal.user_services_dal.uuid4",
            side_effect=[UUID(int=index) for index in range(1, 107)],
        ):
            for index in range(51):
                await self.activate(f"blocked:{index}", user_id=2)
            service, _, _ = await self.activate("eligible")
        async with self.sessions.begin() as session:
            user = await session.get(User, 2)
            assert user
            user.is_banned = True
        panel, users = panel_fixture()
        worker = ServiceProvisioningWorker(cast(sessionmaker, self.sessions), panel)
        await worker.tick()
        assert list(users) == [f"svc_{service.id}"]
        panel.create_panel_user.assert_awaited_once()
        async with self.sessions() as session:
            blocked = list(
                await session.scalars(
                    select(ServiceConnection)
                    .join(UserService, UserService.id == ServiceConnection.service_id)
                    .where(UserService.user_id == 2)
                )
            )
            assert len(blocked) == 51 and all(row.attempted_at is None for row in blocked)

    async def provision(self, service_id: str, panel: AsyncMock) -> ServiceConnection:
        await provision_service_identity(cast(sessionmaker, self.sessions), service_id, panel)
        async with self.sessions() as session:
            connection = await session.get(ServiceConnection, service_id)
            assert connection is not None
            return connection

    async def test_separate_identities_remain_disabled_and_retries_do_not_duplicate(self) -> None:
        first, _, _ = await self.activate()
        second, _, _ = await self.activate("second")
        panel, users = panel_fixture()
        a = await self.provision(first.id, panel)
        b = await self.provision(second.id, panel)
        assert a.panel_user_uuid != b.panel_user_uuid
        assert a.state == b.state == "pending"
        assert a.last_error is b.last_error is None
        assert a.attempted_at is not None
        assert {u["status"] for u in users.values()} == {"DISABLED"}
        for call in panel.create_panel_user.await_args_list:
            assert "email" not in call.kwargs and "telegram_id" not in call.kwargs
            assert call.kwargs["default_traffic_limit_bytes"] == 10_000
            assert call.kwargs["default_traffic_limit_strategy"] == "NO_RESET"
        await self.provision(first.id, panel)
        assert panel.create_panel_user.await_count == 2
        async with self.sessions() as session:
            user = await session.get(User, 1)
            assert user is not None and user.panel_user_uuid is None
        panel.update_user_status_on_panel.assert_not_awaited()

    async def test_lost_create_response_persists_uncertainty_then_recovers_by_service(self) -> None:
        service, _, _ = await self.activate()
        panel, users = panel_fixture()
        create = panel.create_panel_user.side_effect
        assert callable(create)

        async def uncertain_create(username: str, **kwargs: Any) -> None:
            # This read observes the marker committed before the external side effect.
            async with self.sessions() as session:
                record = await session.get(ServiceConnection, service.id)
                assert record is not None and record.state == "error"
            await create(username, **kwargs)
            raise TimeoutError("response lost")

        panel.create_panel_user.side_effect = uncertain_create
        pending = await self.provision(service.id, panel)
        assert pending.state == "error" and pending.panel_user_uuid is None
        assert len(users) == 1
        async with self.sessions() as session:
            with self.assertRaisesRegex(ServiceConflict, "service_connection_unconfirmed"):
                await deletion_connections(session, 1)
        recovered = await self.provision(service.id, panel)
        assert recovered.state == "pending" and recovered.panel_user_uuid == "1"
        panel.create_panel_user.assert_awaited_once()

    async def test_outage_and_simulated_create_never_claim_a_delivered_identity(self) -> None:
        for unknown in (True, False):
            with self.subTest(unknown=unknown):
                service, _, _ = await self.activate(str(unknown))
                panel, _ = panel_fixture()
                panel.get_users_by_filter.side_effect = None
                panel.get_users_by_filter.return_value = None if unknown else []
                panel.create_panel_user.side_effect = None
                panel.create_panel_user.return_value = {"response": {"uuid": "synthetic"}}
                connection = await self.provision(service.id, panel)
                assert connection.state == "error"
                assert connection.panel_user_uuid is None
                assert panel.create_panel_user.await_count == (0 if unknown else 1)

    async def test_recovered_identity_requires_confirmed_disabled_state(self) -> None:
        service, _, _ = await self.activate()
        panel, users = panel_fixture()
        await self.provision(service.id, panel)
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection is not None
            connection.state = "error"
        remote = users[f"svc_{service.id}"]
        remote["status"] = "ACTIVE"
        panel.update_user_status_on_panel.return_value = True
        uncertain = await self.provision(service.id, panel)
        assert uncertain.state == "error"
        panel.update_user_status_on_panel.assert_awaited_once_with("1", False)
        remote["status"] = "DISABLED"
        confirmed = await self.provision(service.id, panel)
        assert confirmed.state == "pending" and confirmed.last_error is None
        panel.create_panel_user.assert_awaited_once()

    async def test_ban_prevents_new_identity_without_changing_entitlements(self) -> None:
        service, _, _ = await self.activate()
        async with self.sessions.begin() as session:
            user = await session.get(User, 1)
            assert user is not None
            user.is_banned = True
        panel, _ = panel_fixture()
        connection = await self.provision(service.id, panel)
        assert connection.state == "pending" and connection.panel_user_uuid is None
        assert not panel.mock_calls
        async with self.sessions() as session:
            stored = await session.get(UserService, service.id)
            assert stored is not None and stored.used_bytes == 0 and stored.quota_bytes == 10_000

    async def test_dedicated_identity_waits_for_verified_allocation(self) -> None:
        squad = "00000000-0000-0000-0000-000000000002"
        async with self.sessions.begin() as session:
            plan = await save_plan(
                session,
                terms=sample_terms(resource_type="dedicated", squad_uuids=[], resource_pool="test"),
                enabled=True,
                actor_id=1,
            )
            resource = await create_exit(
                session,
                label="Test exit",
                ip_address="192.0.2.1",
                resource_pool="test",
                squad_uuid=squad,
            )
            service, _, _ = await activate_service(
                session,
                user_id=1,
                actor_id=1,
                plan_id=plan.id,
                expected_revision=1,
                idempotency_key="dedicated",
                exit_id=resource.id,
            )
        panel, users = panel_fixture()
        waiting = await self.provision(service.id, panel)
        assert waiting.state == "pending" and waiting.panel_user_uuid is None
        worker = ServiceProvisioningWorker(cast(sessionmaker, self.sessions), panel)
        await worker.tick()
        assert not panel.mock_calls
        async with self.sessions.begin() as session:
            allocation = await session.get(DedicatedExit, resource.id)
            assert allocation is not None
            allocation.verified_at = datetime.now(UTC)
        await worker.tick()
        async with self.sessions() as session:
            prepared = await session.get(ServiceConnection, service.id)
            assert prepared is not None
        assert prepared.panel_user_uuid == "1" and prepared.state == "pending"
        assert users[prepared.username]["activeInternalSquads"] == [{"uuid": squad}]

    async def test_name_collision_is_not_adopted_or_disabled(self) -> None:
        service, _, _ = await self.activate()
        panel, users = panel_fixture()
        users[f"svc_{service.id}"] = {
            "uuid": "42",
            "username": f"svc_{service.id}",
            "description": "another operator's user",
            "status": "ACTIVE",
        }
        connection = await self.provision(service.id, panel)
        assert connection.panel_user_uuid is None
        assert connection.last_error == "panel_identity_conflict"
        panel.create_panel_user.assert_not_awaited()
        panel.update_user_status_on_panel.assert_not_awaited()

    async def test_missing_bound_identity_is_not_recreated_and_terms_are_not_silently_replaced(
        self,
    ) -> None:
        service, _, _ = await self.activate()
        panel, users = panel_fixture()
        await self.provision(service.id, panel)
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, service.id)
            assert connection is not None
            connection.state = "error"
        users[f"svc_{service.id}"]["activeInternalSquads"] = [{"uuid": "wrong"}]
        mismatch = await self.provision(service.id, panel)
        assert mismatch.last_error == "panel_identity_terms_mismatch"
        assert mismatch.panel_user_uuid == "1"
        users.clear()
        missing = await self.provision(service.id, panel)
        assert missing.last_error == "panel_identity_missing"
        assert missing.panel_user_uuid == "1"
        panel.create_panel_user.assert_awaited_once()
        panel.update_user_details_on_panel.assert_not_awaited()

    async def test_ineligible_services_are_not_created_and_worker_keeps_progress(self) -> None:
        expired, _, _ = await self.activate("expired")
        paused, _, _ = await self.activate("paused")
        valid, _, _ = await self.activate("valid", user_id=2)
        async with self.sessions.begin() as session:
            row = await session.get(UserService, expired.id)
            assert row is not None
            row.starts_at = datetime.now(UTC) - timedelta(days=2)
            row.expires_at = datetime.now(UTC) - timedelta(days=1)
            row = await session.get(UserService, paused.id)
            assert row is not None
            row.desired_status = "paused"
        panel, users = panel_fixture()
        worker = ServiceProvisioningWorker(cast(sessionmaker, self.sessions), panel)
        await worker.tick()
        await worker.tick()
        assert list(users) == [f"svc_{valid.id}"]
        panel.create_panel_user.assert_awaited_once()
        async with self.sessions() as session:
            records = {c.service_id: c for c in await session.scalars(select(ServiceConnection))}
            assert records[valid.id].attempted_at is not None
            assert records[expired.id].attempted_at is records[paused.id].attempted_at is None


def test_worker_does_not_provision_in_dry_run() -> None:
    from main_worker import _core_worker_tasks

    from tests.unit.test_telegram_business_retirement import settings

    spec = next(task for task in _core_worker_tasks() if task.name == "ServiceProvisioning")
    assert spec.enabled is not None
    cfg = settings()
    cfg.PANEL_WRITE_MODE = "dry_run"
    assert spec.enabled(cfg) is False
    cfg.PANEL_WRITE_MODE = "live"
    assert spec.enabled(cfg) is True
