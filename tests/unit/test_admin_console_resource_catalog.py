"""Resource catalog supplies safe drafts, never cached confirmation or mutations."""

from typing import cast
from unittest import IsolatedAsyncioTestCase

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy import delete

from bot.app.web.admin_api_impl.auth import admin_auth_middleware
from bot.app.web.admin_console_resource_routes import setup_admin_console_resource_routes
from bot.app.web.admin_console_resource_schemas import (
    ConsoleResourceCatalogOut,
    ConsoleResourcePreviewBody,
)
from bot.app.web.context import PANEL_SERVICE, SESSION_FACTORY, SETTINGS
from bot.app.web.route_contracts import ADMIN_SECURITY, get_contracts, ok_envelope_for
from bot.app.web.webapp_auth import create_webapp_session_token
from bot.services.resource_preview_catalog import build_resource_catalog
from bot.services.resource_preview_panel import digest, read_preview_inventory
from config.settings import Settings
from db.auth_models import AccountRole
from tests.unit.test_admin_console_resource_preview import (
    H1,
    I1,
    I2,
    I3,
    N1,
    N2,
    P1,
    P2,
    SECRET,
    build_resource_preview,
    group_change,
    inventory_fixture,
    panel_fixture,
    uid,
)
from tests.unit.test_user_services import ServiceDatabaseTestCase


def profile_rows(payloads: dict[str, object]) -> list[dict[str, object]]:
    return cast(
        list[dict[str, object]],
        cast(dict[str, object], payloads["/config-profiles"])["configProfiles"],
    )


def group_rows(payloads: dict[str, object]) -> list[dict[str, object]]:
    return cast(
        list[dict[str, object]],
        cast(dict[str, object], payloads["/internal-squads"])["internalSquads"],
    )


class ResourceCatalogTests(IsolatedAsyncioTestCase):
    async def test_full_sets_stable_ids_and_current_values_match_preview(self) -> None:
        payloads = inventory_fixture()
        group_rows(payloads)[0]["inbounds"] = [{"uuid": I2}, {"uuid": I1}]
        panel, request = panel_fixture(payloads)
        inventory = await read_preview_inventory(panel)
        result = build_resource_catalog(inventory)
        assert result.coverage == "complete" and result.draft_available
        assert not result.blockers and not result.execution_available
        assert result.reviewed_panel_version == result.observed_panel_version == "3.4.5"
        assert {item.source for item in result.sources} == {
            "metadata",
            "groups",
            "profiles",
            "nodes",
            "hosts",
        }
        assert all(item.availability == "available" for item in result.sources)
        assert result.groups[0].inbound_ids == [I1, I2]
        assert result.groups[0].name == result.groups[1].name
        assert result.groups[0].id != result.groups[1].id
        assert result.profiles[0].id == P1
        assert result.profiles[0].node_ids == [N1, N2]
        assert [item.id for item in result.profiles[0].inbounds] == [I1, I2]
        assert all(item.profile_id == P1 for item in result.profiles[0].inbounds)
        assert result.profiles[0].inbounds[0].tag == "Same inbound tag"
        assert result.nodes[0].profile_id == P1
        assert result.nodes[0].inbound_ids == [I1, I2]
        host = result.hosts[0]
        assert host.id == H1 and host.profile_id == P1 and host.inbound_ids == [I1]
        assert host.node_ids == [N1] and host.group_mode == "EXCLUDE" and host.group_ids == []
        assert host.address == "192.0.2.1" and host.port == 443
        assert host.is_disabled is False and host.is_hidden is False
        for change, current in (
            (group_change(), result.groups[0]),
            ({"operation": "node_disable", "target_id": N1}, result.nodes[0]),
            ({"operation": "host_update", "target_id": H1, "patch": {"port": 8443}}, host),
        ):
            preview = build_resource_preview(
                ConsoleResourcePreviewBody.model_validate({"change": change}).change,
                inventory,
                [],
            )
            assert preview.current == current
        assert request.await_count == 5
        assert SECRET not in result.model_dump_json()

    async def test_only_allowlisted_fields_and_config_digest_leave_inventory(self) -> None:
        payloads = inventory_fixture()
        profile = profile_rows(payloads)[0]
        config = {"privateKey": SECRET, "password": SECRET, "apiToken": SECRET}
        profile["config"] = config
        profile["password"] = SECRET
        inbounds = cast(list[dict[str, object]], profile["inbounds"])
        inbounds[0].update({"name": SECRET, "rawInbound": config, "tag": "Verified tag"})
        panel, _ = panel_fixture(payloads)
        result = build_resource_catalog(await read_preview_inventory(panel))
        assert result.profiles[0].config_digest == digest(config)
        assert result.profiles[0].inbounds[0].tag == "Verified tag"
        assert set(result.profiles[0].model_dump()) == {
            "id",
            "name",
            "inbounds",
            "node_ids",
            "config_digest",
        }
        assert set(result.profiles[0].inbounds[0].model_dump()) == {"id", "profile_id", "tag"}
        assert SECRET not in result.model_dump_json()
        profile["config"] = {"privateKey": SECRET + "CHANGED"}
        after = build_resource_catalog(await read_preview_inventory(panel))
        assert after.profiles[0].config_digest != result.profiles[0].config_digest
        assert SECRET not in after.model_dump_json()

    async def test_unavailable_or_malformed_sources_never_enable_drafting(self) -> None:
        for endpoint, source in (
            ("/system/metadata", "metadata"),
            ("/nodes", "nodes"),
            ("/hosts", "hosts"),
            ("/internal-squads", "groups"),
            ("/config-profiles", "profiles"),
        ):
            for invalid in (RuntimeError(SECRET), {"unexpected": SECRET}):
                with self.subTest(endpoint=endpoint, invalid=type(invalid).__name__):
                    payloads = inventory_fixture()
                    payloads[endpoint] = invalid
                    panel, _ = panel_fixture(payloads)
                    with self.assertNoLogs(level="DEBUG"):
                        result = build_resource_catalog(await read_preview_inventory(panel))
                    assert result.coverage == "partial" and not result.draft_available
                    assert any(item.startswith(source + "_") for item in result.blockers)
                    assert not result.execution_available
                    assert SECRET not in result.model_dump_json()

    async def test_partial_totals_duplicates_and_missing_labels_fail_closed(self) -> None:
        for issue in ("total", "duplicate", "missing_tag", "invalid_tag", "missing_name"):
            with self.subTest(issue=issue):
                payloads = inventory_fixture()
                profiles = cast(dict[str, object], payloads["/config-profiles"])
                rows = profile_rows(payloads)
                if issue == "total":
                    profiles["total"] = 3
                elif issue == "duplicate":
                    rows[1] = rows[0]
                elif issue == "missing_name":
                    rows[0].pop("name")
                else:
                    inbound = cast(list[dict[str, object]], rows[0]["inbounds"])[0]
                    inbound.pop("tag")
                    inbound["name"] = SECRET
                    if issue == "invalid_tag":
                        inbound["tag"] = {"secret": SECRET}
                panel, _ = panel_fixture(payloads)
                result = build_resource_catalog(await read_preview_inventory(panel))
                assert result.coverage == "partial" and not result.draft_available
                assert result.profiles == [] and "profiles_invalid" in result.blockers
                assert SECRET not in result.model_dump_json()

    async def test_unsupported_version_and_absent_panel_cannot_enable_drafting(self) -> None:
        for version in ("3.4.6", SECRET, None):
            with self.subTest(version=version):
                payloads = inventory_fixture()
                payloads["/system/metadata"] = {"version": version}
                panel, _ = panel_fixture(payloads)
                result = build_resource_catalog(await read_preview_inventory(panel))
                assert result.coverage == "partial" and not result.draft_available
                assert result.observed_panel_version is None
                assert SECRET not in result.model_dump_json()
        result = build_resource_catalog(await read_preview_inventory(None))
        assert not result.draft_available and result.coverage == "partial"
        assert result.groups == result.profiles == result.nodes == result.hosts == []
        assert all(source.availability == "unavailable" for source in result.sources)

    async def test_inconsistent_references_block_catalog_like_preview(self) -> None:
        for issue in ("profile", "node", "group", "host"):
            with self.subTest(issue=issue):
                payloads = inventory_fixture()
                if issue == "profile":
                    inbound = cast(list[dict[str, object]], profile_rows(payloads)[0]["inbounds"])[
                        0
                    ]
                    inbound["profileUuid"] = P2
                elif issue == "node":
                    profile_rows(payloads)[0]["nodes"] = []
                elif issue == "group":
                    group_rows(payloads)[0]["inbounds"] = [{"uuid": uid(999)}]
                else:
                    cast(list[dict[str, object]], payloads["/hosts"])[0]["nodes"] = [uid(999)]
                panel, _ = panel_fixture(payloads)
                inventory = await read_preview_inventory(panel)
                result = build_resource_catalog(inventory)
                assert not result.draft_available and result.coverage == "partial"
                assert all(source.availability == "available" for source in result.sources)
                preview = build_resource_preview(
                    ConsoleResourcePreviewBody.model_validate({"change": group_change()}).change,
                    inventory,
                    [],
                )
                assert set(result.blockers) <= set(preview.blockers)

    async def test_credential_address_is_redacted_and_blocks_drafting(self) -> None:
        payloads = inventory_fixture()
        cast(list[dict[str, object]], payloads["/hosts"])[0]["address"] = (
            f"https://user:{SECRET}@example.test/"
        )
        panel, _ = panel_fixture(payloads)
        result = build_resource_catalog(await read_preview_inventory(panel))
        assert result.hosts[0].address is None
        assert not result.draft_available and result.coverage == "partial"
        assert "unsupported_host_address" in result.blockers
        assert SECRET not in result.model_dump_json()

    async def test_complete_empty_inventory_is_distinct_from_failure(self) -> None:
        payloads: dict[str, object] = {
            "/system/metadata": {"version": "v3.4.5"},
            "/nodes": [],
            "/hosts": [],
            "/internal-squads": {"total": 0, "internalSquads": []},
            "/config-profiles": {"total": 0, "configProfiles": []},
        }
        panel, _ = panel_fixture(payloads)
        result = build_resource_catalog(await read_preview_inventory(panel))
        assert result.draft_available and result.coverage == "complete" and not result.blockers
        assert result.groups == result.profiles == result.nodes == result.hosts == []

    async def test_disabled_unconfigured_node_is_not_given_invented_associations(self) -> None:
        payloads = inventory_fixture()
        cast(list[dict[str, object]], payloads["/nodes"]).append(
            {
                "uuid": uid(104),
                "name": "Unconfigured",
                "isDisabled": True,
                "configProfile": {"activeConfigProfileUuid": None, "activeInbounds": []},
                "secretKey": SECRET,
            }
        )
        panel, _ = panel_fixture(payloads)
        result = build_resource_catalog(await read_preview_inventory(panel))
        node = result.nodes[-1]
        assert node.is_disabled is True and node.profile_id is None and node.inbound_ids == []
        assert result.coverage == "complete" and result.draft_available
        assert SECRET not in result.model_dump_json()


@pytest.mark.filterwarnings(
    "ignore:It is recommended to use web.RequestKey: aiohttp.web_exceptions.NotAppKeyWarning"
)
class ResourceCatalogRouteTests(ServiceDatabaseTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.payloads = inventory_fixture()
        self.panel, self.panel_request = panel_fixture(self.payloads)
        settings = Settings(
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            BOT_TOKEN="1234567890:AA_test_token_value",
            _env_file=None,
        )
        app = web.Application(middlewares=[admin_auth_middleware])
        app[SETTINGS], app[SESSION_FACTORY], app[PANEL_SERVICE] = (
            settings,
            self.sessions,
            self.panel,
        )
        setup_admin_console_resource_routes(app)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.headers = {
            user: {"Authorization": "Bearer " + create_webapp_session_token(settings, user)}
            for user in (1, 2, 3)
        }

    async def test_permissions_checked_before_inventory_and_after_role_revocation(self) -> None:
        path = "/api/admin/console/resources/catalog"
        for headers, status in (({}, 401), (self.headers[2], 403), (self.headers[3], 403)):
            response = await self.client.get(path, headers=headers)
            assert response.status == status
        self.panel_request.assert_not_awaited()
        response = await self.client.get(path, headers=self.headers[1])
        assert response.status == 200 and self.panel_request.await_count == 5
        assert response.headers["Cache-Control"] == "private, no-store"
        body = await response.json()
        assert body["ok"] and body["draft_available"] and not body["execution_available"]
        assert "fingerprint" not in body and "remote_authorization_verified" not in body
        assert SECRET not in str(body)
        async with self.sessions.begin() as session:
            await session.execute(delete(AccountRole).where(AccountRole.user_id == 1))
        response = await self.client.get(path, headers=self.headers[1])
        assert response.status == 403 and self.panel_request.await_count == 5
        assert response.headers["Cache-Control"] == "private, no-store"

    async def test_contract_query_rejection_and_no_execute(self) -> None:
        response = await self.client.get(
            "/api/admin/console/resources/catalog",
            params={"unexpected": SECRET},
            headers=self.headers[1],
        )
        assert response.status == 400 and SECRET not in await response.text()
        assert response.headers["Cache-Control"] == "private, no-store"
        self.panel_request.assert_not_awaited()
        response = await self.client.post(
            "/api/admin/console/resources/catalog", headers=self.headers[1]
        )
        assert response.status == 405
        response = await self.client.post(
            "/api/admin/console/resources/execute", headers=self.headers[1]
        )
        assert response.status == 404
        contract = get_contracts()["admin_console_resource_catalog_route"]
        assert contract.request_model is None and contract.security == ADMIN_SECURITY
        assert contract.response_schema == ok_envelope_for(ConsoleResourceCatalogOut)
        assert contract.models == (ConsoleResourceCatalogOut,)

    async def test_catalog_refresh_and_preview_revalidation_never_reuse_drafts(self) -> None:
        path = "/api/admin/console/resources/"
        response = await self.client.get(path + "catalog", headers=self.headers[1])
        before = await response.json()
        assert before["groups"][0]["inbound_ids"] == [I1]
        group_rows(self.payloads)[0]["inbounds"] = [{"uuid": I2}]
        response = await self.client.get(path + "catalog", headers=self.headers[1])
        assert (await response.json())["groups"][0]["inbound_ids"] == [I2]
        assert self.panel_request.await_count == 10
        group_rows(self.payloads)[0]["inbounds"] = [{"uuid": I1}, {"uuid": I2}]
        response = await self.client.post(
            path + "preview", json={"change": group_change()}, headers=self.headers[1]
        )
        preview = await response.json()
        assert preview["current"]["inbound_ids"] == [I1, I2] and preview["fingerprint"]
        assert self.panel_request.await_count == 20
        group_rows(self.payloads)[1]["inbounds"] = [{"uuid": I3}]
        response = await self.client.post(
            path + "revalidate",
            json={"change": group_change(), "expected_fingerprint": preview["fingerprint"]},
            headers=self.headers[1],
        )
        revalidated = await response.json()
        assert not revalidated["valid"] and revalidated["reason"] == "changed"
        assert self.panel_request.await_count == 30
        assert revalidated["preview"]["coverage"] == "complete"

    async def test_partial_failure_stays_no_store_and_does_not_reflect_exception(self) -> None:
        self.payloads["/config-profiles"] = RuntimeError(SECRET)
        response = await self.client.get(
            "/api/admin/console/resources/catalog", headers=self.headers[1]
        )
        assert response.status == 200
        assert response.headers["Cache-Control"] == "private, no-store"
        body = await response.json()
        assert body["coverage"] == "partial" and not body["draft_available"]
        assert body["profiles"] == [] and body["groups"]
        assert "profiles_unavailable" in body["blockers"]
        assert SECRET not in str(body)

    async def test_config_digest_is_not_a_preview_confirmation(self) -> None:
        response = await self.client.get(
            "/api/admin/console/resources/catalog", headers=self.headers[1]
        )
        catalog = ConsoleResourceCatalogOut.model_validate(await response.json())
        response = await self.client.post(
            "/api/admin/console/resources/revalidate",
            json={
                "change": group_change(),
                "expected_fingerprint": catalog.profiles[0].config_digest,
            },
            headers=self.headers[1],
        )
        assert response.status == 200
        body = await response.json()
        assert body["valid"] is False and body["reason"] == "changed"
        assert body["preview"]["execution_available"] is False
        assert self.panel_request.await_count == 15
