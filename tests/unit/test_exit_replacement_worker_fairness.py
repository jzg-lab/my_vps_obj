"""Offline SQLite scheduling regression; replacement writes remain unresolved."""

from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from bot.services.service_change_sync import ServiceChangeWorker
from bot.services.service_exit_replacement_topology import read_replacement_topology
from bot.services.service_usage_sync import record_service_usage
from config.service_exit_replacement import ReplacementRequest, ReplacementStopEvidence
from config.service_periods import as_utc
from db.dal.service_exit_replacement_dal import (
    accept_replacement_stop,
    begin_replacement_action,
    lock_replacement,
    reserve_exit_replacement,
)
from db.dal.user_services_dal import activate_service, save_plan
from db.service_models import DedicatedExit, ServiceConnection, ServiceOperationExecution
from tests.unit.test_admin_console_resource_preview import panel_fixture, uid
from tests.unit.test_service_changes import ServiceChangeTestCase
from tests.unit.test_user_services import sample_terms


def exit_inventory() -> dict[str, object]:
    # Separate profiles keep each replacement's scope independent of the other 49 holds.
    paths = range(1, 102)
    return {
        "/system/metadata": {"version": "3.4.5"},
        "/nodes": [
            {
                "uuid": uid(1000 + index),
                "name": f"Node {index}",
                "isDisabled": False,
                "configProfile": {
                    "activeConfigProfileUuid": uid(3000 + index),
                    "activeInbounds": [{"uuid": uid(2000 + index)}],
                },
            }
            for index in paths
        ],
        "/internal-squads": {
            "total": len(paths),
            "internalSquads": [
                {
                    "uuid": uid(index),
                    "name": f"Group {index}",
                    "inbounds": [{"uuid": uid(2000 + index)}],
                }
                for index in paths
            ],
        },
        "/hosts": [
            {
                "uuid": uid(4000 + index),
                "remark": f"Host {index}",
                "address": f"192.0.2.{index}",
                "port": 443,
                "inbound": {
                    "configProfileUuid": uid(3000 + index),
                    "configProfileInboundUuid": uid(2000 + index),
                },
                "nodes": [uid(1000 + index)],
                "isDisabled": False,
                "isHidden": False,
                "internalSquads": {"mode": "EXCLUDE", "squads": []},
            }
            for index in paths
        ],
        "/config-profiles": {
            "total": len(paths),
            "configProfiles": [
                {
                    "uuid": uid(3000 + index),
                    "name": f"Profile {index}",
                    "config": {},
                    "inbounds": [
                        {
                            "uuid": uid(2000 + index),
                            "profileUuid": uid(3000 + index),
                            "tag": f"inbound-{index}",
                        }
                    ],
                    "nodes": [{"uuid": uid(1000 + index)}],
                }
                for index in paths
            ],
        },
    }


class ExitReplacementWorkerFairnessTests(ServiceChangeTestCase):
    async def test_unknown_replacements_do_not_starve_ordinary_service(self) -> None:
        await self.check_fairness(unknown=True)

    async def test_manual_confirmation_wait_does_not_starve_ordinary_service(self) -> None:
        await self.check_fairness(unknown=False)

    async def check_fairness(self, *, unknown: bool) -> None:
        async with self.sessions.begin() as session:
            dedicated = await save_plan(
                session,
                terms=sample_terms(
                    resource_type="dedicated", squad_uuids=[], resource_pool="private"
                ),
                enabled=True,
                actor_id=1,
            )
            self.plan = await save_plan(
                session, terms=sample_terms(squad_uuids=[uid(101)]), enabled=True, actor_id=1
            )
            session.add_all(
                DedicatedExit(
                    id=f"{index:032x}",
                    label=f"Exit {index}",
                    ip_address=f"192.0.2.{index}",
                    resource_pool="private",
                    squad_uuid=uid(index),
                    enabled=True,
                    verified_at=datetime.now(UTC),
                    created_at=datetime.now(UTC),
                )
                for index in range(1, 101)
            )
        services = []
        for index in range(50):
            async with self.sessions.begin() as session:
                service, _, _ = await activate_service(
                    session,
                    user_id=1,
                    actor_id=1,
                    plan_id=dedicated.id,
                    expected_revision=1,
                    idempotency_key=f"replacement-service:{index}",
                    exit_id=f"{index * 2 + 1:032x}",
                )
            await self.prepare(service, ready=True)
            services.append(service)
        ordinary, _, _ = await self.activate("ordinary")
        _, ordinary_remote = await self.prepare(ordinary, ready=True)
        await self.change(ordinary, "pause", key="ordinary-pause")

        _, request = panel_fixture(exit_inventory())
        self.panel._request = request
        self.panel._get_all_panel_users_uncached.side_effect = lambda **_kwargs: list(
            self.remote_users.values()
        )

        async def lookup(reference: str, **_kwargs: object) -> dict[str, object]:
            remote = next(user for user in self.remote_users.values() if user["uuid"] == reference)
            return {"ok": True, "not_found": False, "user": remote}

        self.panel.get_user_by_uuid_lookup.side_effect = lookup
        for index, service in enumerate(services):
            async with self.sessions.begin() as session:
                old = await session.get(DedicatedExit, f"{index * 2 + 1:032x}")
                new = await session.get(DedicatedExit, f"{index * 2 + 2:032x}")
                assert old and new
                topology = await read_replacement_topology(
                    session, self.panel, old, new, service_id=service.id
                )
                assert topology.public.coverage == "complete", topology.public.block_reasons
                fingerprint = topology.public.resource_fingerprint
                assert fingerprint is not None
                operation, duplicate = await reserve_exit_replacement(
                    session,
                    service_id=service.id,
                    user_id=1,
                    actor_id=1,
                    idempotency_key=f"replacement:{index}",
                    request=ReplacementRequest(
                        expected_revision=service.revision,
                        old_exit_id=old.id,
                        new_exit_id=new.id,
                        expected_old_exit_revision=old.revision,
                        expected_new_exit_revision=new.revision,
                        resource_fingerprint=fingerprint,
                        reason="Offline scheduling regression",
                    ),
                )
                assert not duplicate
                state = await lock_replacement(
                    session, service_id=service.id, user_id=1, operation_id=operation.id
                )
                if unknown:
                    await begin_replacement_action(
                        session, state, action="stop_old", expected_version=state.progress.version
                    )
                else:
                    remote = self.remote_users[f"svc_{service.id}"]
                    remote.update(status="DISABLED", activeInternalSquads=[])
                    record_service_usage(state.service, state.connection, remote)
                    assert state.service.last_usage_sync_at is not None
                    observed = as_utc(state.service.last_usage_sync_at)
                    await accept_replacement_stop(
                        session,
                        state,
                        actor_id=1,
                        expected_version=state.progress.version,
                        idempotency_key="attest-stop",
                        evidence=ReplacementStopEvidence(
                            resource_fingerprint=fingerprint,
                            stopped_at=observed,
                            usage_observed_at=observed,
                            stop_provenance="administrator",
                            usage_provenance="administrator",
                            stop_report_digest="a" * 64,
                            usage_report_digest="b" * 64,
                            authorization_removed=True,
                            connections_stopped=True,
                            old_config_rejected=True,
                            usage_total_bytes=0,
                            usage_raw_bytes=0,
                            usage_lifetime_offset=0,
                        ),
                    )
                    assert state.progress.stage == "awaiting_confirmation"

        previous_check = datetime.now(UTC) - timedelta(days=1)
        operations = (
            select(ServiceOperationExecution.__table__)
            .where(ServiceOperationExecution.phase == "exit_replace")
            .order_by(ServiceOperationExecution.id)
        )
        bindings = select(
            DedicatedExit.id, DedicatedExit.service_id, DedicatedExit.hold_order_id
        ).order_by(DedicatedExit.id)
        async with self.sessions.begin() as session:
            connection = await session.get(ServiceConnection, ordinary.id)
            assert connection and connection.sync_pending
            connection.sync_attempted_at = previous_check
            before = [dict(row) for row in (await session.execute(operations)).mappings()]
            assert len(before) == 50
            assert all(row["attempt_count"] == (1 if unknown else 0) for row in before)
            assert all((row["attempted_at"] is not None) == unknown for row in before)
            held_before = (await session.execute(bindings)).all()
            waiting = list(
                await session.scalars(
                    select(ServiceConnection).where(
                        ServiceConnection.replacement_order_id.is_not(None)
                    )
                )
            )
            assert len(waiting) == 50 and all(row.sync_attempted_at is None for row in waiting)

        self.panel.reset_mock()
        worker = ServiceChangeWorker(cast(sessionmaker, self.sessions), self.panel)
        for tick in (1, 2):
            await worker.tick()
            async with self.sessions() as session:
                after = [dict(row) for row in (await session.execute(operations)).mappings()]
                assert after == before, "Scheduling must not retry or complete replacement writes"
                assert (await session.execute(bindings)).all() == held_before
                connection = await session.get(ServiceConnection, ordinary.id)
                assert connection is not None
                assert connection.sync_attempted_at is not None
                if tick == 1:
                    assert connection.sync_pending and connection.sync_confirmed_at is None
                    assert as_utc(connection.sync_attempted_at) == previous_check
                    self.panel.update_user_status_on_panel.assert_not_awaited()
                else:
                    assert not connection.sync_pending, "50 waiting replacements starved tick two"
                    assert connection.sync_confirmed_at is not None
                    assert as_utc(connection.sync_attempted_at) > previous_check
        assert ordinary_remote["status"] == "DISABLED"
        self.panel.update_user_status_on_panel.assert_awaited_once_with(
            ordinary_remote["uuid"], False
        )
        self.panel.update_user_details_on_panel.assert_not_awaited()
        self.panel.create_panel_user.assert_not_awaited()
        assert all(call.args[0] == "GET" for call in request.await_args_list)
