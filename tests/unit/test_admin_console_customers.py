"""Customer summaries use only an isolated in-memory database; no HTTP or remote reads."""

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.app.web.admin_api_impl import users_listing
from bot.app.web.admin_console_customers_schemas import ConsoleCustomerServicesOut
from bot.app.web.openapi import generate_openapi
from db.dal.admin_console_customers_dal import summaries_for_customers
from db.dal.admin_console_services_dal import list_services
from db.models import User
from db.service_models import ServiceConnection, UserService
from tests.unit.test_user_services import ServiceDatabaseTestCase


def test_existing_users_contract_requires_customer_summary() -> None:
    document = generate_openapi()
    response = document["paths"]["/api/admin/users"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    enrichment = response["properties"]["users"]["items"]["allOf"][1]
    assert "independent_services" in enrichment["required"]
    assert enrichment["properties"]["independent_services"] == {
        "$ref": "#/components/schemas/ConsoleCustomerServicesOut"
    }
    summary = document["components"]["schemas"]["ConsoleCustomerServicesOut"]
    assert "observed_at" in summary["required"]
    assert summary["properties"]["activity"]["const"] == "not_collected"


class ConsoleCustomerTests(ServiceDatabaseTestCase):
    async def summaries(self, *user_ids: int) -> dict[int, ConsoleCustomerServicesOut]:
        async with self.sessions() as session:
            result = await summaries_for_customers(session, list(user_ids), now=datetime.now(UTC))
        return {
            key: ConsoleCustomerServicesOut.model_validate(value) for key, value in result.items()
        }

    async def test_one_query_counts_instances_for_only_the_current_page(self) -> None:
        await self.activate("one")
        await self.activate("two")
        await self.activate("off-page", user_id=2)
        archived, _, _ = await self.activate("archived")
        async with self.sessions.begin() as session:
            service = await session.get(UserService, archived.id)
            connection = await session.get(ServiceConnection, archived.id)
            assert service and connection
            service.user_id = None
            service.desired_status = "cancelled"
            connection.sync_error = "archived_revoke_pending"
        async with self.sessions() as session:
            with patch.object(session, "execute", wraps=session.execute) as execute:
                rows = await summaries_for_customers(session, [1, 3, 1], now=datetime.now(UTC))
            execute.assert_awaited_once()
            assert execute.await_args
            sql = str(
                execute.await_args.args[0].compile(
                    dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
                )
            ).lower()
        assert "user_services.user_id in (1, 3)" in sql
        assert "group by user_services.user_id" in sql
        assert set(rows) == {1, 3}
        first = ConsoleCustomerServicesOut.model_validate(rows[1])
        empty = ConsoleCustomerServicesOut.model_validate(rows[3])
        assert first.total == 2 and first.by_status["pending"] == 2
        assert first.sync_error == 0
        assert empty.total == 0 and sum(empty.by_status.values()) == 0
        assert empty.sync_unobserved == empty.usage_unobserved == 0
        assert empty.latest_usage_sync_at is None
        assert empty.activity == "not_collected"

    async def test_empty_page_does_not_query_and_failure_is_not_zero(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        assert await summaries_for_customers(session, [], now=datetime.now(UTC)) == {}
        session.execute.assert_not_awaited()
        session.execute.side_effect = RuntimeError("database unavailable")
        with pytest.raises(RuntimeError, match="database unavailable"):
            await summaries_for_customers(session, [1], now=datetime.now(UTC))

    async def test_business_states_match_global_list_and_account_ban_is_separate(self) -> None:
        now = datetime.now(UTC)
        for state in (
            "active",
            "pending",
            "paused",
            "cancelled",
            "expired",
            "exhausted",
            "account_banned",
        ):
            service, _, _ = await self.activate(state)
            async with self.sessions.begin() as session:
                row = await session.get(UserService, service.id)
                connection = await session.get(ServiceConnection, service.id)
                assert row and connection
                row.starts_at = now - timedelta(days=2)
                connection.state = "ready"
                if state in {"paused", "cancelled"}:
                    row.desired_status = state
                elif state == "expired":
                    row.expires_at = now - timedelta(days=1)
                elif state == "exhausted":
                    row.used_bytes = row.quota_bytes
                elif state == "pending":
                    await session.delete(connection)
                elif state == "account_banned":
                    row.user_id = 3
        async with self.sessions() as session:
            result = await summaries_for_customers(session, [1, 3], now=now)
            for user_id in (1, 3):
                summary = ConsoleCustomerServicesOut.model_validate(result[user_id])
                for state, count in summary.by_status.items():
                    _, expected = await list_services(
                        session, now=now, user_id=user_id, status=state
                    )
                    assert count == expected
                assert sum(summary.by_status.values()) == summary.total
                assert summary.sync_error == 0
        banned = ConsoleCustomerServicesOut.model_validate(result[3])
        assert banned.total == banned.by_status["account_banned"] == 1
        assert banned.by_status["paused"] == 0

    async def test_unknown_partial_and_failed_observations_keep_success_times(self) -> None:
        first, _, _ = await self.activate("one")
        second, _, _ = await self.activate("two")
        unknown = (await self.summaries(1))[1]
        assert unknown.total == unknown.sync_unobserved == unknown.usage_unobserved == 2
        assert unknown.latest_sync_confirmed_at is None
        assert unknown.latest_usage_sync_at is None
        now = datetime.now(UTC)
        older = now - timedelta(days=3)
        newer = now - timedelta(days=1)
        async with self.sessions.begin() as session:
            service = await session.get(UserService, first.id)
            connection = await session.get(ServiceConnection, first.id)
            assert service and connection
            service.last_usage_sync_at = older
            connection.sync_confirmed_at = older
            connection.sync_pending = True
            connection.sync_error = "sensitive-error-is-not-returned"
            connection.usage_error = "usage_unavailable"
            connection.cycle_cutover_bytes = 0
            connection.sync_attempted_at = now
        partial = (await self.summaries(1))[1]
        assert partial.sync_error == partial.sync_pending == partial.cycle_pending == 1
        assert partial.sync_unobserved == partial.usage_unobserved == 1
        assert partial.oldest_sync_confirmed_at == partial.latest_sync_confirmed_at == older
        assert partial.oldest_usage_sync_at == partial.latest_usage_sync_at == older
        assert partial.activity == "not_collected"
        assert "sensitive-error" not in partial.model_dump_json()
        async with self.sessions.begin() as session:
            service = await session.get(UserService, second.id)
            connection = await session.get(ServiceConnection, second.id)
            assert service and connection
            service.last_usage_sync_at = newer
            connection.sync_confirmed_at = newer
        sampled = (await self.summaries(1))[1]
        assert sampled.sync_unobserved == sampled.usage_unobserved == 0
        assert sampled.sync_error == 1
        assert sampled.oldest_usage_sync_at == sampled.oldest_sync_confirmed_at == older
        assert sampled.latest_usage_sync_at == sampled.latest_sync_confirmed_at == newer
        assert sampled.observed_at >= now

    async def test_dedicated_resource_without_verified_delivery_is_pending(self) -> None:
        service, _, _ = await self.activate()
        async with self.sessions.begin() as session:
            row = await session.get(UserService, service.id)
            connection = await session.get(ServiceConnection, service.id)
            assert row and connection
            row.terms = {**row.terms, "resource_type": "dedicated", "resource_pool": "private"}
            connection.state = "ready"
        summary = (await self.summaries(1))[1]
        assert summary.by_status["pending"] == 1
        assert summary.by_status["active"] == 0

    async def test_list_search_pagination_and_legacy_fields_share_one_response(self) -> None:
        await self.activate("one")
        await self.activate("two")
        async with self.sessions.begin() as session:
            for user_id, name in ((1, "Alpha"), (2, "Beta"), (3, "Gamma")):
                user = await session.get(User, user_id)
                assert user
                user.first_name = name

        async def load(*, page: int = 0, query: str = "") -> dict:
            result = await users_listing._load_admin_users_list_payload_uncached(
                cast(sessionmaker, self.sessions),
                page=page,
                page_size=1,
                query=query,
                filter_value="all",
                panel_status="all",
                premium_traffic="all",
                sort_value="name_asc",
                valid_tariff_keys=set(),
                balance_enabled=False,
                partner_balance_enabled=False,
                balance_currency="CNY",
                balance_currency_scale=100,
            )
            assert isinstance(result, dict)
            return result

        with patch.object(
            users_listing.admin_console_customers_dal,
            "summaries_for_customers",
            wraps=summaries_for_customers,
        ) as aggregate:
            first = await load()
            assert aggregate.await_args
            assert aggregate.await_args.args[1] == [1]
            aggregate.assert_awaited_once()
        assert first["total"] == 3 and len(first["users"]) == 1
        assert first["users"][0]["independent_services"]["total"] == 2
        assert first["users"][0]["panel_status"] == "bot_only"
        assert "premium_traffic" in first["users"][0]
        assert "payments_count" in first["users"][0]
        second = await load(page=1)
        assert second["total"] == 3 and second["users"][0]["user_id"] == 2
        assert second["users"][0]["independent_services"]["total"] == 0
        searched = await load(query="Alpha")
        assert searched["total"] == 1
        assert searched["users"][0]["independent_services"]["total"] == 2
        assert (await load(page=10))["users"] == []
        assert (await load(query="not-a-customer"))["total"] == 0
