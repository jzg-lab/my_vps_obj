"""Optional isolated database + real local panel preparation, without a Node."""

import os
from datetime import datetime, timedelta
from typing import cast
from urllib.parse import urlsplit

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker

from bot.services.panel_api_contracts import PanelApiOperation
from bot.services.panel_api_service import PanelApiService
from bot.services.service_change_sync import synchronize_service_change
from bot.services.service_delivery import deliver_service_identity, service_subscription
from bot.services.service_provisioning import provision_service_identity
from bot.services.service_revocation import revoke_service_identity
from bot.services.service_usage_sync import synchronize_service_usage
from config.service_changes import ServiceChange
from config.service_periods import as_utc
from db.dal.service_changes_dal import change_service
from db.dal.service_delivery_dal import request_service_delivery, request_service_revocation
from db.dal.user_services_dal import ServiceConflict, activate_service, save_plan
from db.service_models import ServiceConnection, UserService
from tests.integration.test_user_services_postgres import DATABASE_URL, scenario
from tests.qa.test_remnawave_panel_contract import _panel_service
from tests.unit.test_user_services import sample_terms

pytestmark = pytest.mark.skipif(
    os.environ.get("QA_SERVICE_PROVISIONING") != "1" or not DATABASE_URL,
    reason="Requires explicitly configured isolated PostgreSQL and panel",
)


async def _require_node_free_local_panel(panel: PanelApiService) -> None:
    if urlsplit(panel.base_url or "").hostname not in {"127.0.0.1", "::1", "localhost"}:
        pytest.fail("This lifecycle test requires an explicitly configured loopback panel")
    response = await panel._request(
        "GET",
        "/nodes",
        operation=PanelApiOperation.NODES_LIST,
        params={"start": 0, "size": 1},
        log_full_response=False,
    )
    if not isinstance(response, dict) or response.get("error"):
        pytest.fail("Cannot confirm that the isolated panel contains no Nodes")
    payload = response.get("response")
    if isinstance(payload, list):
        nodes = payload
    elif isinstance(payload, dict) and isinstance(payload.get("nodes"), list):
        nodes = payload["nodes"]
        if payload.get("total", 0) != 0:
            pytest.fail("Lifecycle enablement is forbidden while any Node is registered")
    else:
        pytest.fail("Unknown Node listing shape; refusing lifecycle enablement")
    if nodes:
        pytest.fail("Lifecycle enablement is forbidden while any Node is registered")


def test_real_panel_keeps_two_services_disabled_separate_and_idempotent() -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        panel = _panel_service()
        names: list[str] = []
        try:
            await _require_node_free_local_panel(panel)
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
                await synchronize_service_usage(cast(sessionmaker, factory), service.id, panel)
                await synchronize_service_usage(cast(sessionmaker, factory), service.id, panel)
                async with factory() as session:
                    connection = await session.get(ServiceConnection, service.id)
                    saved = await session.get(UserService, service.id)
                    assert connection and saved
                    assert connection.usage_error is None, connection.usage_error
                    assert connection.usage_total_bytes == saved.used_bytes == 0
                    assert saved.last_usage_sync_at is not None
                    assert connection.state == "pending"
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


def test_real_panel_delivery_pause_and_revocation_remain_service_scoped() -> None:
    async def run(factory: async_sessionmaker[AsyncSession]) -> None:
        panel = _panel_service()
        names: list[str] = []

        async def status(reference: str) -> tuple[str, int, str, int, int]:
            lookup = await panel.get_user_by_uuid_lookup(reference)
            remote = lookup.get("user") if lookup.get("ok") is True else None
            if not isinstance(remote, dict):
                pytest.fail("Expected isolated test identity is unavailable")
            traffic = remote.get("userTraffic")
            if not isinstance(traffic, dict):
                pytest.fail("Expected panel metering sample is unavailable")
            # A credential-free projection makes assertion failures safe to report.
            return (
                str(remote["status"]),
                int(remote["trafficLimitBytes"]),
                str(remote["expireAt"]),
                int(traffic["usedTrafficBytes"]),
                int(traffic["lifetimeUsedTrafficBytes"]),
            )

        try:
            await _require_node_free_local_panel(panel)
            squads = await panel.get_internal_squads()
            assert squads, "An isolated internal squad is required"
            async with factory.begin() as session:
                plan = await save_plan(
                    session,
                    terms=sample_terms(squad_uuids=[squads[0]["uuid"]]),
                    enabled=True,
                    actor_id=1,
                )
                services = []
                for key in ("deliver-one", "deliver-two"):
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
            references: list[str] = []
            for service in services:
                await provision_service_identity(cast(sessionmaker, factory), service.id, panel)
                await synchronize_service_usage(cast(sessionmaker, factory), service.id, panel)
                async with factory.begin() as session:
                    connection = await session.get(ServiceConnection, service.id)
                    assert (
                        connection and connection.state == "pending" and connection.panel_user_uuid
                    )
                    references.append(connection.panel_user_uuid)
                    _, order, duplicate = await request_service_delivery(
                        session,
                        service_id=service.id,
                        user_id=1,
                        actor_id=1,
                        expected_revision=1,
                        idempotency_key=f"deliver:{service.id}",
                    )
                    assert not duplicate and connection.sync_pending
                await _require_node_free_local_panel(panel)
                await deliver_service_identity(cast(sessionmaker, factory), service.id, panel)
                await synchronize_service_change(cast(sessionmaker, factory), service.id, panel)
                async with factory.begin() as session:
                    saved, replay, duplicate = await request_service_delivery(
                        session,
                        service_id=service.id,
                        user_id=1,
                        actor_id=1,
                        expected_revision=1,
                        idempotency_key=f"deliver:{service.id}",
                    )
                    connection = await session.get(ServiceConnection, service.id)
                    assert duplicate and replay.id == order.id and saved.revision == 2
                    assert saved.used_bytes == 0 and connection and connection.state == "ready"
                    assert not connection.sync_pending and connection.sync_confirmed_at
                    lookup = await panel.get_user_by_uuid_lookup(connection.panel_user_uuid)
                    remote_url = lookup["user"].get("subscriptionUrl", "")
                    if urlsplit(remote_url).scheme == "https":
                        url = await service_subscription(
                            session, user_id=1, service_id=service.id, panel=panel
                        )
                        if url != remote_url:
                            pytest.fail("Subscription response did not match the selected identity")
                    else:
                        # Local HTTP remains rejected; never change global panel settings.
                        with pytest.raises(ServiceConflict, match="service_delivery_unconfirmed"):
                            await service_subscription(
                                session, user_id=1, service_id=service.id, panel=panel
                            )
                assert (await status(references[-1]))[0] == "ACTIVE"
            assert len(set(references)) == 2
            untouched = await status(references[1])
            assert untouched[0] == "ACTIVE" and untouched[1] == 10_000 and untouched[3:] == (0, 0)
            first = services[0]
            async with factory.begin() as session:
                await change_service(
                    session,
                    service_id=first.id,
                    user_id=1,
                    actor_id=1,
                    expected_revision=2,
                    idempotency_key="pause-delivered",
                    change=ServiceChange(action="pause"),
                )
            await synchronize_service_change(cast(sessionmaker, factory), first.id, panel)
            assert (await status(references[0]))[0] == "DISABLED"
            assert await status(references[1]) == untouched
            async with factory.begin() as session:
                await request_service_revocation(
                    session,
                    service_id=first.id,
                    user_id=1,
                    actor_id=1,
                    expected_revision=3,
                    idempotency_key="revoke-delivered",
                    reason="Isolated panel lifecycle test",
                )
            await revoke_service_identity(cast(sessionmaker, factory), first.id, panel)
            await revoke_service_identity(cast(sessionmaker, factory), first.id, panel)
            lookup = await panel.get_user_by_uuid_lookup(references[0])
            assert lookup.get("not_found") is True
            assert await status(references[1]) == untouched
            async with factory() as session:
                connection = await session.get(ServiceConnection, first.id)
                saved = await session.get(UserService, first.id)
                assert connection and connection.state == "revoked" and connection.revoked_at
                assert saved and saved.desired_status == "cancelled" and saved.used_bytes == 0
        finally:
            try:
                for name in names:
                    users = await panel.get_users_by_filter(username=name)
                    assert users is not None, "Could not verify isolated identity cleanup"
                    for remote in users:
                        if (
                            remote.get("username") != name
                            or remote.get("description") != f"my_vps_obj:service:{name[4:]}"
                        ):
                            pytest.fail("Cleanup identity ownership mismatch")
                        reference = str(remote["uuid"])
                        assert await panel.update_user_status_on_panel(reference, False)
                        assert await panel.delete_user_from_panel(reference)
                        assert (await panel.get_user_by_uuid_lookup(reference)).get(
                            "not_found"
                        ) is True
            finally:
                await panel.close_session()

    scenario(run)
