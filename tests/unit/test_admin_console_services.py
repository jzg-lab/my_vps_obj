"""Real SQL and HTTP checks for cross-customer console reads."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import delete

from bot.app.web.admin_api_impl.auth import admin_auth_middleware
from bot.app.web.admin_console_services_routes import setup_admin_console_services_routes
from bot.app.web.admin_console_services_schemas import ConsoleSummaryOut
from bot.app.web.context import SESSION_FACTORY, SETTINGS
from bot.app.web.webapp_auth import create_webapp_session_token
from bot.services.user_service_access import service_status
from config.settings import Settings
from db.auth_models import AccountRole
from db.dal.admin_console_services_dal import business_status, list_services, service_query
from db.dal.admin_console_summary_dal import read_console_summary
from db.models import User
from db.service_models import AccountAccessSync, DedicatedExit, ServiceConnection, UserService
from tests.unit.test_user_services import ServiceDatabaseTestCase


class ConsoleServicesTests(ServiceDatabaseTestCase):
    @pytest.mark.filterwarnings(
        "ignore:It is recommended to use web.RequestKey: aiohttp.web_exceptions.NotAppKeyWarning"
    )
    async def test_archived_audit_detail_preserves_history_without_operational_counts(self) -> None:
        current, _, _ = await self.activate("current", user_id=2)
        archived, _, _ = await self.activate("archived", user_id=2)
        async with self.sessions.begin() as session:
            service = await session.get(UserService, archived.id)
            connection = await session.get(ServiceConnection, archived.id)
            assert service and connection
            service.user_id = None
            service.desired_status = "cancelled"
            service.used_bytes = 123
            connection.state = "revoked"
        settings = Settings(
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            BOT_TOKEN="1234567890:AA_test_token_value",
            _env_file=None,
        )
        app = web.Application(middlewares=[admin_auth_middleware])
        app[SETTINGS] = settings
        app[SESSION_FACTORY] = self.sessions
        setup_admin_console_services_routes(app)
        admin = {"Authorization": "Bearer " + create_webapp_session_token(settings, 1)}
        ordinary = {"Authorization": "Bearer " + create_webapp_session_token(settings, 2)}
        path = "/api/admin/console/services/" + archived.id
        async with TestClient(TestServer(app)) as client:
            before = await (await client.get("/api/admin/console/summary", headers=admin)).json()
            assert (await client.get(path)).status == 401
            assert (await client.get(path, headers=ordinary)).status == 403
            response = await client.get(path, headers=admin)
            assert response.status == 200, await response.text()
            assert response.headers["Cache-Control"] == "private, no-store"
            detail = await response.json()
            assert detail["customer"] == {
                "user_id": None,
                "minishop_id": None,
                "username": None,
                "email": None,
                "first_name": None,
                "last_name": None,
                "is_banned": None,
            }
            assert detail["service"]["id"] == archived.id
            assert detail["service"]["user_id"] is None
            assert detail["service"]["status"] == "cancelled"
            assert detail["service"]["used_bytes"] == 123
            assert detail["service"]["quota_bytes"] == archived.quota_bytes
            assert detail["terms"] == archived.terms
            assert detail["connection"] is not None
            for suffix in ("", "?user_id=2", "?page_size=1"):
                listing = await (
                    await client.get("/api/admin/console/services" + suffix, headers=admin)
                ).json()
                assert listing["total"] == 1
                assert [row["service"]["id"] for row in listing["services"]] == [current.id]
                assert listing["services"][0]["customer"]["user_id"] == 2
                assert isinstance(listing["services"][0]["customer"]["minishop_id"], str)
                assert listing["services"][0]["customer"]["is_banned"] is False
            searched = await (
                await client.get("/api/admin/console/services?q=" + archived.id, headers=admin)
            ).json()
            assert searched["total"] == 0 and searched["services"] == []
            after = await (await client.get("/api/admin/console/summary", headers=admin)).json()
            assert before["services"] == after["services"]
            assert after["services"]["total"] == 1 and after["services"]["archived"] == 1
            assert before["customers"] == after["customers"]

    async def summary(self) -> ConsoleSummaryOut:
        async with self.sessions() as session:
            return ConsoleSummaryOut.model_validate(
                await read_console_summary(session, now=datetime.now(UTC))
            )

    async def test_customers_are_distinct_and_archives_are_separate(self) -> None:
        first, _, _ = await self.activate("first", user_id=2)
        second, _, _ = await self.activate("second", user_id=2)
        archived, _, _ = await self.activate("archived")
        async with self.sessions.begin() as session:
            row = await session.get(UserService, archived.id)
            assert row
            row.user_id = None
            row.desired_status = "cancelled"
        result = await self.summary()
        assert result.customers.total == 3
        assert result.customers.with_services == 1
        assert result.customers.banned == 1
        assert result.services.total == 2
        assert result.services.archived == 1
        assert result.services.by_status == {"pending": 2}
        assert result.services.entitlement_valid == 2
        assert result.services.delivery_ready == 0
        async with self.sessions() as session:
            rows, total = await list_services(
                session, now=datetime.now(UTC), user_id=2, page_size=1
            )
            assert total == 2 and len(rows) == 1
            assert rows[0][0].id in {first.id, second.id}
            assert rows[0][3].user_id == 2

    async def test_known_zero_unknown_and_partial_usage(self) -> None:
        empty = await self.summary()
        assert empty.usage.confirmed_used_bytes == 0
        assert empty.usage.availability == "available"
        first, _, _ = await self.activate()
        second, _, _ = await self.activate("second")
        unknown = await self.summary()
        assert unknown.usage.confirmed_used_bytes is None
        assert unknown.usage.availability == "unknown"
        past = datetime.now(UTC) - timedelta(days=3)
        async with self.sessions.begin() as session:
            service = await session.get(UserService, first.id)
            connection = await session.get(ServiceConnection, first.id)
            assert service and connection
            service.last_usage_sync_at = past
            connection.usage_total_bytes = 0
        partial = await self.summary()
        assert partial.usage.confirmed_used_bytes == 0
        assert partial.usage.availability == "partial"
        assert partial.usage.services_sampled == 1
        assert partial.usage.oldest_sample_at == past
        async with self.sessions.begin() as session:
            service = await session.get(UserService, second.id)
            connection = await session.get(ServiceConnection, second.id)
            assert service and connection
            service.last_usage_sync_at = past
            service.used_bytes = 27
            connection.usage_error = "panel_usage_unavailable"
        failed = await self.summary()
        assert failed.usage.confirmed_used_bytes == 27
        assert failed.usage.services_with_errors == 1
        assert failed.usage.availability == "partial"

    async def test_usage_summary_preserves_mixed_periods_and_sample_coverage(self) -> None:
        monthly, _, _ = await self.activate("monthly", user_id=2)
        total, _, _ = await self.activate("total", user_id=2)
        unobserved, _, _ = await self.activate("unobserved", user_id=2)
        archived, _, _ = await self.activate("archived")
        oldest = datetime(2026, 10, 20, tzinfo=UTC)
        latest = datetime(2026, 10, 23, tzinfo=UTC)
        async with self.sessions.begin() as session:
            for identity, used, sampled in (
                (monthly.id, 100, oldest),
                (total.id, 200, latest),
                (unobserved.id, 300, None),
                (archived.id, 400, latest),
            ):
                service = await session.get(UserService, identity)
                assert service
                service.used_bytes = used
                service.last_usage_sync_at = sampled
                if identity == monthly.id:
                    service.terms = {**service.terms, "traffic_rule": "monthly"}
                    service.cycle_started_at = datetime(2026, 10, 3, tzinfo=UTC)
                    service.cycle_ends_at = datetime(2026, 11, 3, tzinfo=UTC)
                elif identity == archived.id:
                    service.user_id = None
                    service.desired_status = "cancelled"
        result = await self.summary()
        assert result.services.total == 3 and result.services.archived == 1
        assert result.customers.with_services == 1
        assert result.usage.confirmed_used_bytes == 300
        assert result.usage.services_total == 3 and result.usage.services_sampled == 2
        assert result.usage.oldest_sample_at == oldest
        assert result.usage.latest_sample_at == latest
        assert result.usage.availability == "partial"
        assert result.usage.scope == "current_period_upload_plus_download_business_payload"
        assert (await self.summary()).usage == result.usage

    async def test_sql_status_matches_existing_business_rules(self) -> None:
        now = datetime.now(UTC)
        for index in range(10):
            service, _, _ = await self.activate(str(index), user_id=2 if index != 9 else 1)
            async with self.sessions.begin() as session:
                row = await session.get(UserService, service.id)
                connection = await session.get(ServiceConnection, service.id)
                assert row and connection
                connection.state = "ready"
                row.starts_at = now - timedelta(days=1)
                if index == 0:
                    row.desired_status = "paused"
                elif index == 1:
                    row.desired_status = "cancelled"
                elif index == 2:
                    row.expires_at = now - timedelta(seconds=1)
                    row.starts_at = now - timedelta(days=1)
                elif index == 3:
                    row.used_bytes = row.quota_bytes
                elif index == 4:
                    connection.state = "pending"
                elif index == 5:
                    row.starts_at = now + timedelta(days=1)
                elif index == 6:
                    await session.delete(connection)
                elif index == 7:
                    row.terms = {
                        **row.terms,
                        "resource_type": "dedicated",
                        "resource_pool": "private",
                        "squad_uuids": [],
                    }
        async with self.sessions.begin() as session:
            user = await session.get(User, 1)
            assert user
            user.is_banned = True
        async with self.sessions() as session:
            rows, total = await list_services(session, now=now, page_size=200)
            assert total == 10
            result = await session.execute(
                service_query().with_only_columns(UserService.id, business_status(now))
            )
            sql: dict[str, str] = dict(result.tuples().all())
            for service, connection, resource, user in rows:
                assert sql[service.id] == service_status(
                    service, connection, resource, banned=bool(user.is_banned), now=now
                )
                selected, count = await list_services(
                    session, now=now, status=sql[service.id], page_size=200
                )
                assert count == len(selected)
                assert service.id in {row[0].id for row in selected}

    async def test_literal_search_total_sort_and_unconfirmed_filters(self) -> None:
        first, _, _ = await self.activate("first")
        second, _, _ = await self.activate("second", user_id=2)
        async with self.sessions.begin() as session:
            one = await session.get(UserService, first.id)
            two = await session.get(UserService, second.id)
            connection = await session.get(ServiceConnection, first.id)
            assert one and two and connection
            one.terms = {**one.terms, "name": "Literal %_\\ plan"}
            one.used_bytes = 7
            connection.sync_error = "panel_change_unconfirmed"
            connection.sync_pending = True
            two.expires_at = datetime.now(UTC) + timedelta(days=2)
        async with self.sessions() as session:
            rows, total = await list_services(session, now=datetime.now(UTC), q="%_\\")
            assert total == 1 and rows[0][0].id == first.id
            rows, total = await list_services(
                session, now=datetime.now(UTC), sort="usage_desc", page_size=1
            )
            assert total == 2 and rows[0][0].id == first.id
            rows, total = await list_services(
                session, now=datetime.now(UTC), sort="usage_desc", page_size=1, page=1
            )
            assert total == 2 and rows[0][0].id == second.id
            for state in ("sync_error", "sync_pending"):
                rows, total = await list_services(session, now=datetime.now(UTC), status=state)
                assert total == 1 and rows[0][0].id == first.id
            rows, total = await list_services(session, now=datetime.now(UTC), status="expiring")
            assert total == 1 and rows[0][0].id == second.id
            _, total = await list_services(
                session, now=datetime.now(UTC), status="expiring", expiring_within_days=1
            )
            assert total == 0

    async def test_health_includes_archives_and_never_invents_success_time(self) -> None:
        service, _, _ = await self.activate()
        attempted = datetime.now(UTC) - timedelta(hours=1)
        async with self.sessions.begin() as session:
            row = await session.get(UserService, service.id)
            connection = await session.get(ServiceConnection, service.id)
            assert row and connection
            row.user_id = None
            row.desired_status = "cancelled"
            connection.state = "error"
            connection.last_error = "panel_identity_unconfirmed"
            connection.sync_pending = True
            connection.sync_error = "service_revoke_pending"
            connection.sync_attempted_at = attempted
            session.add(
                AccountAccessSync(
                    user_id=2,
                    pending=True,
                    last_error="panel_access_unconfirmed",
                    attempted_at=attempted,
                )
            )
        result = await self.summary()
        assert result.services.total == 0 and result.services.archived == 1
        assert result.health.delivery_failed == 1
        assert result.health.sync_pending == 1
        assert result.health.account_sync_pending == 1
        assert result.health.account_sync_failed == 1
        assert result.health.latest_success_at is None
        assert result.health.latest_attempt_at == attempted
        assert result.health.oldest_pending_since is None

    async def test_expired_exit_is_occupied_until_reclaimed(self) -> None:
        service, _, _ = await self.activate()
        now = datetime.now(UTC)
        async with self.sessions.begin() as session:
            row = await session.get(UserService, service.id)
            assert row
            row.desired_status = "cancelled"
            for index in range(4):
                session.add(
                    DedicatedExit(
                        id=f"{index:032x}",
                        label="Exit",
                        ip_address=f"192.0.2.{index + 1}",
                        resource_pool="pool",
                        squad_uuid=str(UUID(int=index + 1)),
                        service_id=service.id if index == 0 else None,
                        verified_at=now if index < 2 else None,
                        enabled=index != 3,
                        created_at=now,
                    )
                )
        result = await self.summary()
        assert result.exits.total == 4
        assert result.exits.occupied == 1 and result.exits.pending_reclaim == 1
        assert result.exits.available == 1
        assert result.exits.pending_verification == 1
        assert result.exits.disabled == 1 and result.exits.unverified_total == 2

    async def test_delivery_readiness_and_cycle_pending_use_persisted_evidence(self) -> None:
        first, _, _ = await self.activate()
        second, _, _ = await self.activate("second")
        now = datetime.now(UTC)
        async with self.sessions.begin() as session:
            for service_id in (first.id, second.id):
                connection = await session.get(ServiceConnection, service_id)
                assert connection
                connection.state = "ready"
            connection = await session.get(ServiceConnection, first.id)
            service = await session.get(UserService, first.id)
            other = await session.get(UserService, second.id)
            assert connection and service and other
            connection.panel_user_uuid = str(UUID(int=555))
            connection.usage_total_bytes = 0
            service.last_usage_sync_at = now
            service.terms = {**service.terms, "traffic_rule": "monthly"}
            service.cycle_started_at = now - timedelta(days=31)
            service.cycle_ends_at = now - timedelta(days=1)
        result = await self.summary()
        assert result.services.by_status == {"active": 2}
        assert result.services.delivery_ready == 1
        assert result.health.cycle_pending == 1
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, first.id)
            assert connection
            connection.usage_error = "panel_usage_unavailable"
        result = await self.summary()
        assert result.services.delivery_ready == 0

    @pytest.mark.filterwarnings(
        "ignore:It is recommended to use web.RequestKey: aiohttp.web_exceptions.NotAppKeyWarning"
    )
    async def test_http_permissions_validation_and_no_credentials(self) -> None:
        service, _, _ = await self.activate(user_id=2)
        settings = Settings(
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            BOT_TOKEN="1234567890:AA_secret_bot_token_value",
            _env_file=None,
        )
        app = web.Application(middlewares=[admin_auth_middleware])
        app[SETTINGS] = settings
        app[SESSION_FACTORY] = self.sessions
        setup_admin_console_services_routes(app)
        admin = {"Authorization": "Bearer " + create_webapp_session_token(settings, 1)}
        ordinary = {"Authorization": "Bearer " + create_webapp_session_token(settings, 2)}
        paths = [
            "/api/admin/console/services",
            "/api/admin/console/services/" + service.id,
            "/api/admin/console/summary",
        ]
        async with TestClient(TestServer(app)) as client:
            for path in paths:
                assert (await client.get(path)).status == 401
                assert (await client.get(path, headers=ordinary)).status == 403
                response = await client.get(path, headers=admin)
                assert response.status == 200, await response.text()
                assert response.headers["Cache-Control"] == "private, no-store"
                body = await response.text()
                assert "subscription_url" not in body
                if path != paths[1]:
                    assert "panel_user_uuid" not in body
            payload = await (
                await client.get(paths[0] + "?user_id=2&page_size=1", headers=admin)
            ).json()
            assert payload["total"] == 1 and payload["services"][0]["customer"]["user_id"] == 2
            assert payload["services"][0]["service"]["id"] == service.id
            for query in (
                "page=-1",
                "page_size=201",
                "sort=bad",
                "status=bad",
                "user_id=1.2",
                "q=" + "x" * 201,
                "expiring_within_days=0",
            ):
                assert (await client.get(paths[0] + "?" + query, headers=admin)).status == 400
            assert (await client.get(paths[0] + "/bad", headers=admin)).status == 400
            assert (await client.get(paths[0] + "/" + "0" * 32, headers=admin)).status == 404
            async with self.sessions.begin() as session:
                await session.execute(delete(AccountRole).where(AccountRole.user_id == 1))
            for path in paths:
                assert (await client.get(path, headers=admin)).status == 403
