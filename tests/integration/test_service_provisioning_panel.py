"""Optional isolated database + real local panel preparation, without a Node."""

import os
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker

from bot.services.service_provisioning import provision_service_identity
from db.dal.user_services_dal import activate_service, save_plan
from db.service_models import ServiceConnection
from tests.integration.test_user_services_postgres import DATABASE_URL, scenario
from tests.qa.test_remnawave_panel_contract import _panel_service
from tests.unit.test_user_services import sample_terms

pytestmark = pytest.mark.skipif(
    os.environ.get("QA_SERVICE_PROVISIONING") != "1" or not DATABASE_URL,
    reason="Requires explicitly configured isolated PostgreSQL and panel",
)


def test_real_panel_keeps_two_services_disabled_separate_and_idempotent() -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        panel = _panel_service()
        names: list[str] = []
        try:
            squads = await panel.get_internal_squads()
            assert squads, "An internal squad is needed, but no live Node is required"
            async with factory.begin() as session:
                plan = await save_plan(
                    session,
                    terms=sample_terms(squad_uuids=[squads[0]["uuid"]]),
                    enabled=True,
                    actor_id=1,
                )
                services = []
                for key in ("one", "two"):
                    service, _, _ = await activate_service(
                        session,
                        user_id=1,
                        actor_id=1,
                        plan_id=plan.id,
                        expected_revision=1,
                        idempotency_key=key,
                    )
                    services.append(service)
                    names.append(f"svc_{service.id}")
            references = []
            for service in services:
                await provision_service_identity(cast(sessionmaker, factory), service.id, panel)
                await provision_service_identity(cast(sessionmaker, factory), service.id, panel)
                async with factory() as session:
                    connection = await session.get(ServiceConnection, service.id)
                    assert connection is not None
                    assert connection.last_error is None, connection.last_error
                    assert connection.state == "pending" and connection.panel_user_uuid
                    references.append(connection.panel_user_uuid)
                    lookup = await panel.get_user_by_uuid_lookup(connection.panel_user_uuid)
                    assert lookup["ok"] and lookup["user"]["status"] == "DISABLED"
                    assert lookup["user"]["trafficLimitBytes"] == 10_000
            assert len(set(references)) == 2
        finally:
            try:
                for name in names:
                    users = await panel.get_users_by_filter(username=name)
                    assert users is not None, "Could not verify test identity cleanup"
                    for remote in users:
                        assert await panel.delete_user_from_panel(str(remote["uuid"]))
                        lookup = await panel.get_user_by_uuid_lookup(str(remote["uuid"]))
                        assert lookup["not_found"] is True
            finally:
                await panel.close_session()

    scenario(run)
