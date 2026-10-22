"""Independent services retain commercial terms and ownership under retries."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest import IsolatedAsyncioTestCase
from uuid import UUID, uuid4

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from pydantic import ValidationError
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.app.web.admin_api_impl.auth import admin_auth_middleware
from bot.app.web.context import SESSION_FACTORY, SETTINGS
from bot.app.web.service_routes import setup_service_admin_routes, setup_service_user_routes
from bot.app.web.service_schemas import DedicatedExitBody, UserServiceOut
from bot.app.web.webapp_auth import create_webapp_session_token
from config.service_periods import SERVICE_TIMEZONE, month_boundary, monthly_period
from config.service_plans import ServicePlanTerms
from config.settings import Settings
from db.auth_models import AccountRole
from db.dal.user_services_dal import ServiceConflict, activate_service, save_plan
from db.models import Base, User
from db.service_models import (
    DedicatedExit,
    ServiceConnection,
    ServiceOrder,
    UserService,
)


def sample_terms(**changes: object) -> ServicePlanTerms:
    return ServicePlanTerms.model_validate(
        {
            "name": "Configured plan",
            "resource_type": "shared",
            "traffic_rule": "total",
            "quota_bytes": 10_000,
            "validity_days": 90,
            "price": "12.30",
            "currency": "CNY",
            "squad_uuids": [str(UUID(int=1))],
            **changes,
        }
    )


def test_monthly_period_keeps_original_day_and_beijing_wall_time() -> None:
    anchor = datetime(2024, 1, 31, 0, 30, tzinfo=SERVICE_TIMEZONE)
    february = month_boundary(anchor, 1)
    march = month_boundary(anchor, 2)
    assert february.astimezone(SERVICE_TIMEZONE) == datetime(
        2024, 2, 29, 0, 30, tzinfo=SERVICE_TIMEZONE
    )
    assert march.astimezone(SERVICE_TIMEZONE) == datetime(
        2024, 3, 31, 0, 30, tzinfo=SERVICE_TIMEZONE
    )
    assert monthly_period(anchor, february) == (february, march)
    assert monthly_period(anchor, datetime(2024, 2, 28, 15, 59, tzinfo=UTC))[0] == anchor
    assert month_boundary(anchor, 13).astimezone(SERVICE_TIMEZONE).day == 28


def test_ipv4_mapped_exit_cannot_claim_a_second_address() -> None:
    body = DedicatedExitBody.model_validate(
        {
            "label": "Test",
            "ip_address": "::ffff:192.0.2.1",
            "resource_pool": "private",
            "squad_uuid": str(UUID(int=1)),
        }
    )
    assert str(body.ip_address) == "192.0.2.1"


@pytest.mark.parametrize(
    "changes",
    [
        {"quota_bytes": 0},
        {"quota_bytes": True},
        {"quota_bytes": 1.1},
        {"validity_days": 0},
        {"price": "-1"},
        {"price": "1.001"},
        {"price": "NaN"},
        {"squad_uuids": []},
        {"squad_uuids": [str(UUID(int=1)), str(UUID(int=1))]},
        {"resource_type": "dedicated"},
        {"resource_pool": "private"},
    ],
)
def test_plan_terms_reject_ambiguous_or_invalid_entitlements(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        sample_terms(**changes)


class ServiceDatabaseTestCase(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite://")

        @event.listens_for(self.engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False, autoflush=False)
        async with self.sessions.begin() as session:
            session.add_all([User(user_id=1), User(user_id=2), User(user_id=3, is_banned=True)])
            await session.flush()
            session.add(AccountRole(user_id=1, role="owner"))
            self.plan = await save_plan(session, terms=sample_terms(), enabled=True, actor_id=1)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def activate(self, key: str = "open", user_id: int = 1):
        async with self.sessions.begin() as session:
            return await activate_service(
                session,
                user_id=user_id,
                actor_id=1,
                plan_id=self.plan.id,
                expected_revision=1,
                idempotency_key=key,
            )


class UserServicesTests(ServiceDatabaseTestCase):
    async def test_replay_and_separate_instances_preserve_original_price(self) -> None:
        first, order, _ = await self.activate()
        replay, same_order, duplicate = await self.activate()
        second, _, _ = await self.activate("another")
        assert replay.id == first.id and same_order.id == order.id and duplicate
        assert second.id != first.id
        async with self.sessions.begin() as session:
            await save_plan(
                session,
                plan_id=self.plan.id,
                expected_revision=1,
                terms=sample_terms(name="Edited", quota_bytes=777, price="55"),
                quota_change_reason="Verified quota adjustment",
                enabled=True,
                actor_id=1,
            )
        replay, _, duplicate = await self.activate()
        assert duplicate and replay.terms["name"] == "Configured plan"
        async with self.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(UserService)) == 2
            assert await session.scalar(select(func.count()).select_from(ServiceOrder)) == 2
            connections = (await session.scalars(select(ServiceConnection))).all()
            assert len({item.username for item in connections}) == 2
            assert all(
                item.state == "pending" and item.panel_user_uuid is None for item in connections
            )
            saved = await session.get(ServiceOrder, order.id)
            assert saved is not None
            assert saved.snapshot["terms"] == sample_terms().model_dump(mode="json")
            assert Decimal(str(first.terms["price"])) == Decimal("12.30")

    async def test_revision_conflict_does_not_create_service(self) -> None:
        async with self.sessions.begin() as session:
            await save_plan(
                session,
                plan_id=self.plan.id,
                expected_revision=1,
                terms=sample_terms(),
                enabled=True,
                actor_id=1,
            )
        with pytest.raises(ServiceConflict, match="plan_revision_changed"):
            await self.activate()
        async with self.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(UserService)) == 0

    async def test_reused_key_cannot_grant_changed_terms(self) -> None:
        await self.activate()
        async with self.sessions.begin() as session:
            with pytest.raises(ServiceConflict, match="idempotency_conflict"):
                await activate_service(
                    session,
                    user_id=1,
                    actor_id=1,
                    plan_id=self.plan.id,
                    expected_revision=2,
                    idempotency_key="open",
                )

    async def test_banned_user_and_disabled_template_cannot_open(self) -> None:
        with pytest.raises(ServiceConflict, match="account_banned"):
            await self.activate(user_id=3)
        async with self.sessions.begin() as session:
            await save_plan(
                session,
                plan_id=self.plan.id,
                expected_revision=1,
                terms=sample_terms(),
                enabled=False,
                actor_id=1,
            )
        with pytest.raises(ServiceConflict, match="plan_disabled"):
            await self.activate()

    async def test_monthly_activation_has_distinct_period_and_expiry(self) -> None:
        anchor = datetime(2024, 1, 31, 0, 30, tzinfo=SERVICE_TIMEZONE)
        async with self.sessions.begin() as session:
            plan = await save_plan(
                session, terms=sample_terms(traffic_rule="monthly"), enabled=True, actor_id=1
            )
            service, _, _ = await activate_service(
                session,
                user_id=1,
                actor_id=1,
                plan_id=plan.id,
                expected_revision=1,
                idempotency_key="monthly",
                now=anchor,
            )
            assert service.cycle_ends_at == month_boundary(anchor, 1)
            assert service.starts_at.tzinfo == UTC
            assert service.cycle_ends_at < service.expires_at
            assert service.quota_bytes == 10000

    async def test_dedicated_exit_is_exclusive_and_stays_pending_until_verified(self) -> None:
        resource_id = uuid4().hex
        async with self.sessions.begin() as session:
            plan = await save_plan(
                session,
                terms=sample_terms(
                    resource_type="dedicated", squad_uuids=[], resource_pool="private"
                ),
                enabled=True,
                actor_id=1,
            )
            session.add(
                DedicatedExit(
                    id=resource_id,
                    label="Test",
                    ip_address="192.0.2.1",
                    resource_pool="private",
                    squad_uuid=str(UUID(int=2)),
                    enabled=True,
                    created_at=datetime.now(UTC),
                )
            )
        async with self.sessions.begin() as session:
            first, _, _ = await activate_service(
                session,
                user_id=1,
                actor_id=1,
                plan_id=plan.id,
                expected_revision=1,
                idempotency_key="ip",
                exit_id=resource_id,
            )
        async with self.sessions.begin() as session:
            with pytest.raises(ServiceConflict, match="exit_unavailable"):
                await activate_service(
                    session,
                    user_id=2,
                    actor_id=1,
                    plan_id=plan.id,
                    expected_revision=1,
                    idempotency_key="ip",
                    exit_id=resource_id,
                )
            connection = await session.get(ServiceConnection, first.id)
            resource = await session.get(DedicatedExit, resource_id)
            out = UserServiceOut.from_orm_service(first, connection, resource)
            assert out.status == "pending" and not out.exit_verified
            assert out.exit_ip == "192.0.2.1"

    async def test_rollback_discards_order_connection_and_service_together(self) -> None:
        async with self.sessions() as session:
            await activate_service(
                session,
                user_id=1,
                actor_id=1,
                plan_id=self.plan.id,
                expected_revision=1,
                idempotency_key="rollback",
            )
            await session.rollback()
        async with self.sessions() as session:
            for model in (ServiceOrder, ServiceConnection, UserService):
                assert await session.scalar(select(func.count()).select_from(model)) == 0

    @pytest.mark.filterwarnings(
        "ignore:It is recommended to use web.RequestKey: aiohttp.web_exceptions.NotAppKeyWarning"
    )
    async def test_http_auth_ownership_validation_and_activation(self) -> None:
        settings = Settings(
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            BOT_TOKEN="1234567890:AA_secret_bot_token_value",
            _env_file=None,
        )
        app = web.Application(middlewares=[admin_auth_middleware])
        app[SETTINGS] = settings
        app[SESSION_FACTORY] = self.sessions
        setup_service_admin_routes(app)
        setup_service_user_routes(app)
        admin_headers = {"Authorization": "Bearer " + create_webapp_session_token(settings, 1)}
        user_headers = {"Authorization": "Bearer " + create_webapp_session_token(settings, 2)}
        async with TestClient(TestServer(app)) as client:
            assert (await client.get("/api/services")).status == 401
            assert (await client.get("/api/service-catalog")).status == 401
            async with self.sessions.begin() as session:
                await save_plan(
                    session, terms=sample_terms(name="Hidden"), enabled=False, actor_id=1
                )
            response = await client.get("/api/service-catalog?limit=1", headers=user_headers)
            catalog = await response.json()
            assert response.status == 200 and catalog["total"] == 1
            assert catalog["plans"][0] == {
                "id": self.plan.id,
                "name": "Configured plan",
                "description": "",
                "resource_type": "shared",
                "traffic_rule": "total",
                "quota_bytes": 10_000,
                "validity_days": 90,
                "price": "12.30",
                "currency": "CNY",
            }
            response = await client.get("/api/service-catalog?offset=1", headers=user_headers)
            assert (await response.json())["plans"] == []
            assert (
                await client.get("/api/service-catalog?limit=0", headers=user_headers)
            ).status == 400
            banned_headers = {"Authorization": "Bearer " + create_webapp_session_token(settings, 3)}
            assert (await client.get("/api/service-catalog", headers=banned_headers)).status == 403
            assert (
                await client.post("/api/service-catalog", json={}, headers=user_headers)
            ).status == 405

            assert (
                await client.get("/api/admin/service-plans", headers=user_headers)
            ).status == 403
            payload = {
                "user_id": 1,
                "plan_id": self.plan.id,
                "expected_revision": 1,
                "idempotency_key": "http",
            }
            response = await client.post("/api/admin/services", json=payload, headers=admin_headers)
            assert response.status == 200, await response.text()
            body = await response.json()
            assert body["ok"] and body["service"]["status"] == "pending"
            service_id = body["service"]["id"]
            change = {
                "user_id": 1,
                "expected_revision": 1,
                "idempotency_key": "pause-http",
                "change": {"action": "pause"},
            }
            change_path = f"/api/admin/services/{service_id}/changes"
            assert (await client.post(change_path, json=change)).status == 401
            assert (await client.post(change_path, json=change, headers=user_headers)).status == 403
            response = await client.post(change_path, json=change, headers=admin_headers)
            assert response.status == 200
            changed = await response.json()
            assert changed["service"]["desired_status"] == "paused"
            assert changed["service"]["sync_pending"] and changed["service"]["revision"] == 2
            response = await client.post(change_path, json=change, headers=admin_headers)
            assert (await response.json())["duplicate"] is True
            assert (
                await client.post(
                    change_path, json={**change, "force": True}, headers=admin_headers
                )
            ).status == 400
            assert (
                await client.post(
                    change_path, json={**change, "idempotency_key": "stale"}, headers=admin_headers
                )
            ).status == 409
            assert (
                await client.get(f"/api/services/{service_id}", headers=user_headers)
            ).status == 404
            response = await client.get("/api/services?user_id=1", headers=user_headers)
            assert (await response.json())["services"] == []
            response = await client.get("/api/services", headers=admin_headers)
            assert (await response.json())["total"] == 1
            assert (await client.get("/api/services?limit=0", headers=admin_headers)).status == 400
            assert (
                await client.post(
                    "/api/admin/services", json={**payload, "force": True}, headers=admin_headers
                )
            ).status == 400
            assert (
                await client.post(
                    "/api/admin/service-plans",
                    json={"terms": sample_terms().model_dump(mode="json"), "enabled": "false"},
                    headers=admin_headers,
                )
            ).status == 400
