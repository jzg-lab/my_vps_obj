"""Read-only console checks against the isolated, source-built project stack."""

import os
import re
from collections.abc import Iterator
from http.cookies import SimpleCookie
from urllib.parse import urlsplit

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from bot.app.web.admin_console_customers_schemas import ConsoleCustomerServicesOut
from bot.app.web.admin_console_exit_replacement_schemas import ConsoleExitReplacementStateOut
from bot.app.web.admin_console_global_operations_schemas import (
    ConsoleGlobalOperationOut,
    ConsoleGlobalOperationsOut,
)
from bot.app.web.admin_console_nodes_schemas import (
    ConsoleNodeDetailOut,
    ConsoleNodesListOut,
    ConsoleServiceResourcesOut,
)
from bot.app.web.admin_console_operations_schemas import (
    ConsoleServiceDiagnosticsOut,
    ConsoleServiceOperationsOut,
    ConsoleServicePreflightOut,
)
from bot.app.web.admin_console_resource_operation_schemas import (
    ConsoleResourceOperationListOut,
    ConsoleResourceOperationOut,
)
from bot.app.web.admin_console_resource_schemas import (
    ConsoleResourceCatalogOut,
    ConsoleResourcePreviewOut,
    ConsoleResourceRevalidateOut,
)
from bot.app.web.admin_console_services_schemas import (
    ConsoleServiceDetailOut,
    ConsoleServiceListOut,
    ConsoleSummaryOut,
)
from bot.app.web.service_schemas import ServicePlanOut
from bot.services.service_operation_errors import SAFE_SERVICE_ERRORS


def _login_console(client: httpx.Client, email: str) -> None:
    client.cookies.clear()
    client.headers.pop("Cookie", None)
    response = client.post(
        "/api/auth/email/password",
        json={"email": email, "password": "Minishop-Dev-2026!"},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    # httpx does not send Secure cookies over loopback HTTP like the browser does.
    client.headers["Cookie"] = "; ".join(
        f"{name}={value}"
        for name, value in response.cookies.items()
        if name in {"rw_webapp_session", "rw_webapp_csrf"}
    )
    assert client.headers["Cookie"]


@pytest.fixture
def console_client(request: pytest.FixtureRequest) -> Iterator[httpx.Client]:
    base_url = os.getenv("QA_FRONTEND_URL", "http://127.0.0.1:18082")
    assert urlsplit(base_url).hostname in {"127.0.0.1", "localhost", "::1"}, (
        "Console QA is restricted to the isolated loopback development stack."
    )
    with httpx.Client(
        base_url=base_url,
        timeout=30,
        trust_env=False,
    ) as client:
        _login_console(client, str(getattr(request, "param", "runes.admin@example.com")))
        yield client


def _read[T: BaseModel](client: httpx.Client, path: str, model: type[T]) -> T:
    response = client.get(path)
    assert response.status_code == 200, f"{path}: HTTP {response.status_code}"
    assert response.headers.get("Cache-Control") == "private, no-store"
    body = response.json()
    assert body["ok"] is True
    return model.model_validate(body)


def test_live_console_services_and_metrics_agree(console_client: httpx.Client) -> None:
    summary = _read(console_client, "/api/admin/console/summary", ConsoleSummaryOut)
    services = _read(
        console_client, "/api/admin/console/services?page_size=1", ConsoleServiceListOut
    )
    assert summary.services.total == services.total
    assert sum(summary.services.by_status.values()) == services.total
    assert summary.customers.with_services <= summary.customers.total
    assert services.services, "This read-only QA requires an existing local service fixture."
    for status, expected in summary.services.by_status.items():
        filtered = _read(
            console_client,
            f"/api/admin/console/services?status={status}&page_size=1",
            ConsoleServiceListOut,
        )
        assert filtered.total == expected
        assert all(item.service.status == status for item in filtered.services)
    for row in services.services:
        path = f"/api/admin/console/services/{row.service.id}"
        detail = _read(console_client, path, ConsoleServiceDetailOut)
        assert detail.customer.user_id == row.customer.user_id
        assert detail.service.id == row.service.id
        resources = _read(console_client, path + "/resources", ConsoleServiceResourcesOut)
        assert resources.service_id == row.service.id
        assert resources.remote_authorization_verified is False
        diagnostics = _read(console_client, path + "/diagnostics", ConsoleServiceDiagnosticsOut)
        assert diagnostics.service_id == row.service.id
        assert diagnostics.user_id == row.customer.user_id
        assert diagnostics.service_revision == detail.service.revision
        assert diagnostics.data_plane_verified is False
        operations = _read(
            console_client, path + "/operations?limit=1", ConsoleServiceOperationsOut
        )
        assert operations.service_id == row.service.id
        assert operations.service_revision == detail.service.revision
        assert len(operations.operations) <= operations.total
        assert len(operations.operations) <= 1
        assert all(item.service_id == row.service.id for item in operations.operations)
        beyond = _read(
            console_client,
            path + f"/operations?limit=1&offset={operations.total}",
            ConsoleServiceOperationsOut,
        )
        assert beyond.total == operations.total
        assert beyond.operations == []
        response = console_client.get(
            "/api/admin/users", params={"q": row.customer.minishop_id, "page_size": 1}
        )
        assert response.status_code == 200
        customers = response.json()
        assert customers["ok"] is True and customers["total"] == 1
        customer = customers["users"][0]
        assert customer["user_id"] == row.customer.user_id
        customer_summary = ConsoleCustomerServicesOut.model_validate(
            customer["independent_services"]
        )
        owned = _read(
            console_client,
            f"/api/admin/console/services?user_id={row.customer.user_id}&page_size=1",
            ConsoleServiceListOut,
        )
        assert customer_summary.total == owned.total
        assert sum(customer_summary.by_status.values()) == owned.total
        assert customer_summary.activity == "not_collected"


def test_live_console_node_inventory_and_anonymous_denial(console_client: httpx.Client) -> None:
    catalog = _read(
        console_client, "/api/admin/console/resources/catalog", ConsoleResourceCatalogOut
    )
    assert catalog.execution_available is False
    assert catalog.draft_available == (catalog.coverage == "complete" and not catalog.blockers)
    assert {source.source for source in catalog.sources} == {
        "metadata",
        "nodes",
        "hosts",
        "groups",
        "profiles",
    }
    nodes = _read(console_client, "/api/admin/console/nodes?page_size=1", ConsoleNodesListOut)
    assert {source.source for source in nodes.sources} == {"nodes", "hosts", "internal_squads"}
    assert all(source.availability == "available" for source in nodes.sources)
    assert nodes.total is not None
    totals = []
    for status in ("online", "offline", "unknown"):
        filtered = _read(
            console_client,
            f"/api/admin/console/nodes?status={status}&page_size=1",
            ConsoleNodesListOut,
        )
        assert filtered.total is not None
        totals.append(filtered.total)
        assert all(node.status == status for node in filtered.nodes)
    assert sum(totals) == nodes.total
    for node in nodes.nodes:
        detail = _read(console_client, f"/api/admin/console/nodes/{node.id}", ConsoleNodeDetailOut)
        assert detail.node.id == node.id
        assert detail.current_connections is None
    console_client.cookies.clear()
    del console_client.headers["Cookie"]
    for path in (
        "summary",
        "services",
        "services/" + "a" * 32 + "/diagnostics",
        "services/" + "a" * 32 + "/operations",
        "services/" + "a" * 32 + "/exit-replacement",
        "resources/catalog",
        "resources/operations",
        "resources/operations/" + "a" * 32,
        "nodes",
        "nodes/00000000-0000-0000-0000-000000000001",
    ):
        assert console_client.get(f"/api/admin/console/{path}").status_code == 401


@pytest.mark.parametrize("console_client", ["runes.active@example.com"], indirect=True)
def test_live_console_rejects_regular_account(console_client: httpx.Client) -> None:
    for path in (
        "summary",
        "services",
        "services/" + "a" * 32,
        "services/" + "a" * 32 + "/resources",
        "services/" + "a" * 32 + "/diagnostics",
        "services/" + "a" * 32 + "/operations",
        "services/" + "a" * 32 + "/exit-replacement",
        "resources/catalog",
        "resources/operations",
        "resources/operations/" + "a" * 32,
        "nodes",
        "nodes/00000000-0000-0000-0000-000000000001",
    ):
        assert console_client.get(f"/api/admin/console/{path}").status_code == 403


def _assert_no_credentials(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z]", "", str(key).lower())
            if normalized in {
                "config",
                "rawconfig",
                "privatekey",
                "secretkey",
                "secret",
                "password",
                "token",
                "apitoken",
                "apikey",
                "panelapikey",
                "panelapicookie",
                "cookie",
                "authorization",
                "subscriptionurl",
                "subscriptiontoken",
                "subscriptionuuid",
                "shortuuid",
                "csrftoken",
            }:
                pytest.fail("Credential/configuration field in console response", pytrace=False)
            _assert_no_credentials(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_credentials(child)
    elif isinstance(value, str) and re.search(
        r"(?i)(?:https?|vless|vmess|trojan|ss)://|-----BEGIN .*PRIVATE KEY|"
        r"\bBearer\s|(?:password|private[_-]?key|api[_-]?key|token)\s*[:=]",
        value,
    ):
        pytest.fail("Credential/URL material in console response", pytrace=False)


def _assert_contract_fields(raw: object, projected: object) -> None:
    # Response models ignore extras; inspect the wire payload before they can hide leaks.
    if isinstance(raw, dict) and isinstance(projected, dict):
        if raw.keys() != projected.keys():
            pytest.fail("Missing or undeclared console response field", pytrace=False)
        for key, value in raw.items():
            _assert_contract_fields(value, projected[key])
    elif isinstance(raw, list) and isinstance(projected, list):
        for value, expected in zip(raw, projected, strict=True):
            _assert_contract_fields(value, expected)


def _checkpoint_response[T: BaseModel](response: httpx.Response, model: type[T]) -> T:
    assert response.status_code == 200, f"Console checkpoint: HTTP {response.status_code}"
    assert response.headers.get("Cache-Control") == "private, no-store"
    body = response.json()
    _assert_no_credentials(body)
    assert body.pop("ok") is True
    try:
        result = model.model_validate(body)
    except ValidationError:
        pytest.fail("Console response violates its schema (payload withheld)", pytrace=False)
    _assert_contract_fields(body, result.model_dump(mode="json"))
    return result


def _csrf_headers(client: httpx.Client) -> dict[str, str]:
    cookies = SimpleCookie()
    cookies.load(client.headers["Cookie"])
    assert "rw_webapp_csrf" in cookies
    return {"X-CSRF-Token": cookies["rw_webapp_csrf"].value}


def test_live_console_resource_history_read_only(console_client: httpx.Client) -> None:
    path = "/api/admin/console/resources/operations"
    history = _checkpoint_response(
        console_client.get(path + "?limit=1"), ConsoleResourceOperationListOut
    )
    assert len(history.items) == min(history.total, 1)
    for item in history.items:
        detail = _checkpoint_response(
            console_client.get(path + "/" + item.id), ConsoleResourceOperationOut
        )
        assert detail == item
        assert detail.gate_active == (detail.status in {"pending", "unknown"})
        if detail.observation is not None:
            assert detail.observation.runtime == "unverified"
    beyond = _checkpoint_response(
        console_client.get(path + f"?offset={history.total}&limit=1"),
        ConsoleResourceOperationListOut,
    )
    assert beyond.total == history.total and beyond.items == []
    catalog = _checkpoint_response(
        console_client.get("/api/admin/console/resources/catalog"), ConsoleResourceCatalogOut
    )
    assert catalog.execution_available is False, "The default local dry-run must stay enabled."


def test_live_console_operations_checkpoint_read_only(console_client: httpx.Client) -> None:
    """UC-04/05/06 first checkpoint; requires the existing no-Node Local QA stand."""
    services = _read(
        console_client,
        "/api/admin/console/services?q=Local%20QA&page_size=200",
        ConsoleServiceListOut,
    )
    row = next(
        (
            item
            for item in services.services
            if item.service.name.startswith("Local QA") and item.service.resource_type == "shared"
        ),
        None,
    )
    assert row is not None, "Existing Local QA shared service required; QA never creates it."
    path = f"/api/admin/console/services/{row.service.id}"
    before = _read(console_client, path, ConsoleServiceDetailOut)
    assert before.customer.user_id is not None
    assert before.connection is None or before.connection.panel_user_uuid is None, (
        "This checkpoint requires an unprepared Local QA service, not a live identity."
    )
    response = console_client.get("/api/admin/service-plans?limit=200")
    assert response.status_code == 200
    plan_body = response.json()
    assert plan_body["ok"] is True
    plans = [ServicePlanOut.model_validate(item) for item in plan_body["plans"]]
    plan = next((item for item in plans if item.id == before.service.plan_id), None)
    assert plan is not None, "The existing Local QA plan must be present in the local catalog."
    assert plan.terms.name.startswith("Local QA") and plan.terms.resource_type == "shared"
    preflight_body = {
        "user_id": before.customer.user_id,
        "plan_id": plan.id,
        "expected_revision": plan.revision,
    }
    headers = _csrf_headers(console_client)
    history = _checkpoint_response(
        console_client.get(path + "/operations?limit=200"), ConsoleServiceOperationsOut
    )
    assert history.service_id == row.service.id
    assert history.service_revision == before.service.revision
    replacement = _checkpoint_response(
        console_client.get(path + "/exit-replacement"), ConsoleExitReplacementStateOut
    )
    assert replacement.service_id == row.service.id
    assert replacement.service_revision == before.service.revision
    assert replacement.observed_at.tzinfo is not None
    assert replacement.draft is None and replacement.replacement is None
    assert history.total > 0 and history.operations, "Existing activation history must not vanish."
    assert len(history.operations) == min(history.total, 200)
    safe_errors = SAFE_SERVICE_ERRORS | {"unclassified_service_error", None}
    for operation in history.operations:
        assert operation.service_id == row.service.id
        assert operation.error_code in safe_errors
        if operation.source == "unknown":
            assert operation.status == "unknown" and not operation.retryable
            assert operation.attempt_count is None
            assert operation.attempted_at is None and operation.first_failed_at is None
            assert operation.completed_at is None
    global_path = "/api/admin/console/operations"
    global_params = {"service_id": row.service.id, "limit": "1"}
    global_page = _checkpoint_response(
        console_client.get(global_path, params=global_params), ConsoleGlobalOperationsOut
    )
    global_operations: list[ConsoleGlobalOperationOut] = []
    cursors: set[str] = set()
    while True:
        assert global_page.total == history.total
        assert global_page.limit == int(global_params["limit"])
        assert global_page.observed_at.tzinfo is not None
        assert len(global_page.operations) == min(
            global_page.limit, history.total - len(global_operations)
        )
        global_operations.extend(global_page.operations)
        assert (global_page.next_cursor is not None) == (len(global_operations) < history.total)
        if global_page.next_cursor is None:
            break
        assert global_page.next_cursor not in cursors, "Global history cursor must advance."
        cursors.add(global_page.next_cursor)
        global_params.update(limit="200", cursor=global_page.next_cursor)
        global_page = _checkpoint_response(
            console_client.get(global_path, params=global_params), ConsoleGlobalOperationsOut
        )
    assert len(global_operations) == history.total
    by_record = {(item.record_type, item.id): item for item in global_operations}
    assert len(by_record) == history.total, "Global history pages must not duplicate records."
    for operation in history.operations:
        record_type = "order" if operation.phase is None else "execution"
        actual = by_record[(record_type, operation.id)]
        assert (
            actual.model_dump(include=set(type(operation).model_fields)) == operation.model_dump()
        )
    for operation in global_operations:
        assert operation.service_id == row.service.id
        assert operation.service_revision == before.service.revision
        assert operation.service_name == before.service.name
        assert operation.archived is False and operation.customer == before.customer
        assert operation.error_code in safe_errors
        assert operation.needs_attention == (
            operation.record_type == "execution"
            and (
                operation.status in {"failed", "unknown"}
                or (operation.status == "pending" and operation.error_code is not None)
            )
        )
        if operation.record_type == "order":
            assert operation.status == "unknown" and not operation.needs_attention
            assert operation.retry_block_reason == "historical_result_unknown"
    attention = _checkpoint_response(
        console_client.get(
            global_path,
            params={"service_id": row.service.id, "needs_attention": "true", "limit": "200"},
        ),
        ConsoleGlobalOperationsOut,
    )
    assert attention.total == sum(item.needs_attention for item in global_operations)
    assert len(attention.operations) == min(attention.total, attention.limit)
    for operation in attention.operations:
        assert operation.record_type == "execution" and operation.needs_attention
        assert operation == by_record[(operation.record_type, operation.id)]
    for archived, expected_total in (("exclude", history.total), ("only", 0)):
        filtered = _checkpoint_response(
            console_client.get(
                global_path,
                params={"service_id": row.service.id, "archived": archived, "limit": "1"},
            ),
            ConsoleGlobalOperationsOut,
        )
        assert filtered.total == expected_total
        assert len(filtered.operations) == min(expected_total, 1)
        assert all(
            not item.archived and item.customer == before.customer for item in filtered.operations
        )
    # Existing archived rows may be absent; never manufacture a deleted customer for QA.
    archived_history = _checkpoint_response(
        console_client.get(global_path, params={"archived": "only", "limit": "200"}),
        ConsoleGlobalOperationsOut,
    )
    assert len(archived_history.operations) == min(archived_history.total, archived_history.limit)
    for operation in archived_history.operations:
        assert operation.archived is True
        assert all(value is None for value in operation.customer.model_dump().values())
    diagnostics = _checkpoint_response(
        console_client.get(path + "/diagnostics"), ConsoleServiceDiagnosticsOut
    )
    assert diagnostics.service_id == row.service.id
    assert diagnostics.user_id == before.customer.user_id
    assert diagnostics.service_revision == before.service.revision
    assert diagnostics.status == before.service.status
    assert diagnostics.data_plane_verified is False
    assert diagnostics.local_observed_at.tzinfo is not None
    assert diagnostics.remote.availability in {"not_prepared", "unconfirmed"}
    assert diagnostics.remote.observed_at is None
    assert diagnostics.remote.raw_used_bytes is None
    assert diagnostics.remote.usage_readable is None
    assert diagnostics.remote.identity_matches is None
    assert diagnostics.remote.terms_match is None
    assert diagnostics.remote.error in safe_errors
    assert all(error in safe_errors for error in diagnostics.errors.values())
    preflight = _checkpoint_response(
        console_client.post(
            "/api/admin/console/service-preflight", json=preflight_body, headers=headers
        ),
        ConsoleServicePreflightOut,
    )
    assert (preflight.user_id, preflight.plan_id, preflight.plan_revision) == (
        before.customer.user_id,
        plan.id,
        plan.revision,
    )
    assert preflight.terms == plan.terms
    assert preflight.configured_group_ids == sorted(str(value) for value in plan.terms.squad_uuids)
    assert preflight.ready_for_delivery is False
    assert preflight.nodes == [] and preflight.hosts == []
    assert preflight.resource_readiness in {"blocked", "unknown"}
    checks = {check.code: check for check in preflight.checks}
    assert checks["subscription_path"].status in {"blocked", "unknown"}
    assert checks["subscription_path"].reason == "subscription_path_unconfirmed"
    assert checks["identity_and_metering"].status == "unknown"
    assert {source.source for source in preflight.sources} == {"nodes", "hosts", "internal_squads"}
    if all(source.availability == "available" for source in preflight.sources):
        assert checks["resource_sources"].status == "passed"
        assert checks["subscription_path"].status == "blocked"
    else:
        assert checks["resource_sources"].status == "unknown"
        assert checks["subscription_path"].status == "unknown"
    assert preflight.allow_pending_creation == all(
        checks[code].status == "passed" for code in ("account", "plan", "plan_revision", "exit")
    )
    catalog = _checkpoint_response(
        console_client.get("/api/admin/console/resources/catalog"), ConsoleResourceCatalogOut
    )
    assert catalog.nodes == [] and catalog.hosts == [], "Default no-Node/Host stand required."
    sources = {source.source: source.availability for source in catalog.sources}
    assert sources["nodes"] == sources["hosts"] == "available"
    assert catalog.execution_available is False
    assert (catalog.coverage == "partial") == bool(catalog.blockers)
    assert catalog.draft_available == (catalog.coverage == "complete" and not catalog.blockers)
    for source, availability in sources.items():
        if availability != "available":
            assert f"{source}_{availability}" in catalog.blockers
            assert catalog.coverage == "partial" and not catalog.draft_available
    # A nonexistent target is a read-only proposal, never a request to restart a Node.
    change = {"operation": "node_restart", "target_id": "00000000-0000-0000-0000-000000000001"}
    preview_body = {"change": change}
    revalidate_body = {**preview_body, "expected_fingerprint": "0" * 64}
    preview = _checkpoint_response(
        console_client.post(
            "/api/admin/console/resources/preview", json=preview_body, headers=headers
        ),
        ConsoleResourcePreviewOut,
    )
    revalidated = _checkpoint_response(
        console_client.post(
            "/api/admin/console/resources/revalidate", json=revalidate_body, headers=headers
        ),
        ConsoleResourceRevalidateOut,
    )
    for result in (preview, revalidated.preview):
        assert str(result.change.target_id) == change["target_id"]
        assert result.change.operation == change["operation"]
        assert "target_not_found" in result.blockers
        assert result.coverage == "partial" and result.fingerprint is None
        assert result.current is None and result.proposed is None
        assert result.execution_available is False
        for source in result.sources:
            if source.availability != "available":
                blocker = (
                    "archived_resource_scope_unconfirmed"
                    if source.source == "services" and source.availability == "invalid"
                    else f"{source.source}_{source.availability}"
                )
                assert blocker in result.blockers
    assert revalidated.valid is False and revalidated.reason == "incomplete"
    after = _read(console_client, path, ConsoleServiceDetailOut)
    assert after.service == before.service and after.terms == before.terms
    after_history = _checkpoint_response(
        console_client.get(path + "/operations?limit=200"), ConsoleServiceOperationsOut
    )
    assert after_history == history
    remaining = _checkpoint_response(
        console_client.get(path + f"/operations?limit=1&offset={history.total}"),
        ConsoleServiceOperationsOut,
    )
    assert remaining.total == history.total and remaining.operations == []

    requests: tuple[tuple[str, str, object], ...] = (
        ("POST", "/api/admin/console/service-preflight", preflight_body),
        ("GET", path + "/diagnostics", None),
        ("GET", path + "/operations", None),
        ("GET", path + "/exit-replacement", None),
        ("POST", path + "/exit-replacement", {}),
        ("POST", path + "/exit-replacement/confirm", {}),
        ("POST", path + "/exit-replacement/evidence", {}),
        ("GET", global_path + f"?service_id={row.service.id}&limit=1", None),
        ("GET", "/api/admin/console/resources/catalog", None),
        ("POST", "/api/admin/console/resources/preview", preview_body),
        ("POST", "/api/admin/console/resources/revalidate", revalidate_body),
        ("GET", "/api/admin/console/resources/operations", None),
        ("GET", "/api/admin/console/resources/operations/" + "a" * 32, None),
        ("POST", "/api/admin/console/resources/operations", {}),
        ("POST", "/api/admin/console/resources/operations/" + "a" * 32 + "/retry", {}),
        ("POST", "/api/admin/console/resources/operations/" + "a" * 32 + "/reconcile", {}),
        ("POST", "/api/admin/console/resources/operations/" + "a" * 32 + "/evidence", {}),
        ("POST", "/api/admin/console/nodes/onboarding/deployment", {"management_port": 2222}),
    )
    _login_console(console_client, "runes.active@example.com")
    headers = _csrf_headers(console_client)
    for status, error in ((403, "forbidden"), (401, "unauthorized")):
        if status == 401:
            console_client.cookies.clear()
            del console_client.headers["Cookie"]
            headers = {}
        for method, endpoint, body in requests:
            denied = console_client.request(method, endpoint, json=body, headers=headers)
            assert denied.status_code == status, f"{method} {endpoint}: HTTP {denied.status_code}"
            _assert_no_credentials(denied.json())
            assert denied.json() == {"ok": False, "error": error}
