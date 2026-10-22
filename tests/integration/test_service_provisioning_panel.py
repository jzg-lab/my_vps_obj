"""Optional isolated database + real local panel preparation, without a Node."""

import os
from datetime import datetime, timedelta
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker

from bot.services.service_change_sync import synchronize_service_change
from bot.services.service_provisioning import provision_service_identity
from config.service_changes import ServiceChange
from config.service_periods import as_utc
from db.dal.service_changes_dal import change_service
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
            first = services[0]
            for revision, action in enumerate(("pause", "renew", "resume"), start=1):
                change = ServiceChange.model_validate(
                    {
                        "action": action,
                        **(
                            {"days": 31, "price": "6.90", "currency": "CNY"}
                            if action == "renew"
                            else {}
                        ),
                    }
                )
                async with factory.begin() as session:
                    updated, order, duplicate = await change_service(
                        session,
                        service_id=first.id,
                        user_id=1,
                        actor_id=1,
                        expected_revision=revision,
                        idempotency_key=action,
                        change=change,
                    )
                    assert not duplicate and updated.used_bytes == 0
                await synchronize_service_change(cast(sessionmaker, factory), first.id, panel)
                async with factory.begin() as session:
                    replay, same, duplicate = await change_service(
                        session,
                        service_id=first.id,
                        user_id=1,
                        actor_id=1,
                        expected_revision=revision,
                        idempotency_key=action,
                        change=change,
                    )
                    assert (
                        duplicate
                        and same.id == order.id
                        and replay.expires_at == updated.expires_at
                    )
                    connection = await session.get(ServiceConnection, first.id)
                    assert (
                        connection and not connection.sync_pending and connection.sync_confirmed_at
                    )
                    assert connection.state == "pending", (
                        "Resume must not deliver an unprepared service"
                    )
                lookup = await panel.get_user_by_uuid_lookup(references[0])
                assert lookup["ok"] and lookup["user"]["status"] == "DISABLED"
                assert lookup["user"]["trafficLimitBytes"] == 10_000
                expected = first.expires_at + (timedelta(days=31) if revision >= 2 else timedelta())
                actual = datetime.fromisoformat(lookup["user"]["expireAt"].replace("Z", "+00:00"))
                assert as_utc(actual).isoformat(timespec="milliseconds") == as_utc(
                    expected
                ).isoformat(timespec="milliseconds")
            untouched = await panel.get_user_by_uuid_lookup(references[1])
            assert untouched["user"]["status"] == "DISABLED"
            assert datetime.fromisoformat(
                untouched["user"]["expireAt"].replace("Z", "+00:00")
            ).isoformat(timespec="milliseconds") == services[1].expires_at.isoformat(
                timespec="milliseconds"
            )
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
