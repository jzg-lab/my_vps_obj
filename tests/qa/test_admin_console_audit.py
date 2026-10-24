"""Local HTTP audit: read checks and exact-ID-owned asset CRUD, without fixture seeding."""

import re
from datetime import UTC, datetime, time, timedelta
from time import sleep
from urllib.parse import urlencode
from uuid import uuid4

import httpx
import pytest
from pydantic import BaseModel

from bot.app.web.admin_api_impl.panel_links import build_panel_maintenance_url
from bot.app.web.admin_console_account_operations_schemas import (
    ConsoleAccountOperationOut,
    ConsoleAccountOperationsOut,
)
from bot.app.web.admin_console_maintenance_schemas import ConsoleMaintenanceOut
from bot.app.web.admin_console_node_assets_schemas import (
    ConsoleNodeAssetDeletedOut,
    ConsoleNodeAssetOut,
    ConsoleNodeAssetsListOut,
)
from bot.app.web.admin_console_nodes_schemas import ConsoleNodesListOut
from bot.app.web.admin_console_services_schemas import ConsoleServiceListOut
from tests.qa.test_admin_console import _csrf_headers, _login_console, _read
from tests.qa.test_admin_console import console_client as console_client

ACCOUNT_PATH = "/api/admin/console/account-operations"
ASSET_PATH = "/api/admin/console/node-assets"


class _AccountDetail(BaseModel):
    operation: ConsoleAccountOperationOut


def _check(condition: bool, message: str) -> None:
    # Never let assertion introspection print a destination, token or response payload.
    if not condition:
        pytest.fail(message + " (payload withheld)", pytrace=False)


def _audit_read[T: BaseModel](client: httpx.Client, path: str, model: type[T]) -> T:
    try:
        return _read(client, path, model)
    except (AssertionError, httpx.HTTPError, KeyError, TypeError, ValueError):
        pytest.fail(
            "Console audit read failed HTTP/cache/schema checks (payload withheld)", pytrace=False
        )


def _matches(operation: ConsoleAccountOperationOut, filters: dict[str, str]) -> bool:
    return (
        ("user_id" not in filters or operation.target_id == int(filters["user_id"]))
        and ("actor_id" not in filters or operation.actor_id == int(filters["actor_id"]))
        and (filters.get("status", "all") in {"all", operation.status})
        and (filters.get("source", "all") in {"all", operation.source})
        and (filters.get("archived", "all") != "only" or operation.archived)
        and (filters.get("archived", "all") != "exclude" or not operation.archived)
        and (filters.get("needs_attention") != "true" or operation.needs_attention)
    )


def test_live_account_audit_filters_pages_and_existing_details(
    console_client: httpx.Client,
) -> None:
    first = _audit_read(
        console_client, ACCOUNT_PATH + "?page_size=200", ConsoleAccountOperationsOut
    )
    history: list[ConsoleAccountOperationOut] = []
    for page in range(max(1, (first.total + 199) // 200)):
        current = (
            first
            if page == 0
            else _audit_read(
                console_client,
                ACCOUNT_PATH + f"?page={page}&page_size=200",
                ConsoleAccountOperationsOut,
            )
        )
        _check(current.total == first.total, "Account history changed during read-only audit")
        _check(current.page == page and current.page_size == 200, "Account page metadata mismatch")
        _check(current.observed_at.utcoffset() == timedelta(0), "Account observation is not UTC")
        _check(
            len(current.operations) == min(200, first.total - len(history)),
            "Account history page length mismatch",
        )
        history.extend(current.operations)
    _check(
        len({row.id for row in history}) == first.total, "Account pages duplicate or omit records"
    )
    order = [(row.created_at, row.id) for row in history]
    _check(order == sorted(order, reverse=True), "Account history order is not stable")

    filters: list[dict[str, str]] = [{}]
    for field, values in (
        ("status", ("all", "pending", "unknown", "failed", "succeeded", "superseded")),
        ("source", ("all", "administrator", "worker")),
        ("archived", ("all", "only", "exclude")),
        ("needs_attention", ("false", "true")),
    ):
        filters.extend({field: value} for value in values)
    for field, identities in (
        ("user_id", {row.target_id for row in history}),
        ("actor_id", {row.actor_id for row in history if row.actor_id is not None}),
    ):
        absent = next(value for value in range(len(identities) + 1) if value not in identities)
        samples = [absent, *sorted(identities)[:1]]
        filters.extend({field: str(value)} for value in samples)
    archived = next((row for row in history if row.archived), None)
    if archived is not None:
        filters.append({"user_id": str(archived.target_id), "archived": "only"})
    if history:
        row = history[0]
        combined = {
            "user_id": str(row.target_id),
            "status": row.status,
            "source": row.source,
            "archived": "only" if row.archived else "exclude",
            "needs_attention": "true" if row.needs_attention else "false",
        }
        if row.actor_id is not None:
            combined["actor_id"] = str(row.actor_id)
        filters.append(combined)

    for selected in filters:
        expected = [row for row in history if _matches(row, selected)]
        for page in {0, 1, len(expected)}:
            query = urlencode({**selected, "page": page, "page_size": 1})
            actual = _audit_read(
                console_client, ACCOUNT_PATH + "?" + query, ConsoleAccountOperationsOut
            )
            _check(actual.total == len(expected), "Filtered account total mismatch")
            _check(
                actual.page == page and actual.page_size == 1,
                "Filtered account pagination mismatch",
            )
            _check(
                [row.id for row in actual.operations]
                == [row.id for row in expected[page : page + 1]],
                "Filtered account page or beyond-end result mismatch",
            )
            _check(
                all(_matches(row, selected) for row in actual.operations), "Account filter ignored"
            )

    # Empty history is valid; this read-only check never creates records to exercise detail.
    for row in history[:3]:
        detail = _audit_read(console_client, ACCOUNT_PATH + "/" + row.id, _AccountDetail).operation
        _check(detail == row, "Account operation detail differs from its list record")
        _check(detail.archived == (detail.user_id is None), "Account archive identity mismatch")
        _check(detail.created_at.utcoffset() == timedelta(0), "Account record time is not UTC")


def test_live_account_audit_rejects_invalid_filters(console_client: httpx.Client) -> None:
    for query in (
        "user_id=1.0",
        "actor_id=1e3",
        "status=invalid",
        "source=invalid",
        "archived=invalid",
        "needs_attention=1",
        "page=-1",
        "page=1000001",
        "page_size=0",
        "page_size=201",
        "page=0&page=1",
        "unexpected=1",
    ):
        try:
            response = console_client.get(ACCOUNT_PATH + "?" + query)
            body = response.json()
        except (httpx.HTTPError, ValueError):
            pytest.fail(
                "Invalid-filter audit could not read a JSON response (payload withheld)",
                pytrace=False,
            )
        _check(response.status_code == 400, "Invalid account filter was not rejected")
        _check(
            response.headers.get("Cache-Control") == "private, no-store",
            "Invalid-filter response is cacheable",
        )
        _check(
            body
            == {
                "ok": False,
                "error": "invalid_account_operations_query",
                "message": "invalid_account_operations_query",
            },
            "Invalid account filter error contract mismatch",
        )


def test_live_maintenance_destination_is_explicit_safe_or_null(
    console_client: httpx.Client,
) -> None:
    result = _audit_read(console_client, "/api/admin/console/maintenance", ConsoleMaintenanceOut)
    _check(
        result.destination is None
        or build_panel_maintenance_url(result.destination) == result.destination,
        "Maintenance destination violates the public URL policy",
    )


def test_live_node_http_windows_preserve_inventory_totals_and_order(
    console_client: httpx.Client,
) -> None:
    baseline_ids: list[str] | None = None
    baseline_total: int | None = None
    for preset, days in (("today", 1), ("7d", 7), ("30d", 30)):
        before = datetime.now(UTC).date()
        path = f"/api/admin/console/nodes?traffic_window={preset}"
        result = _audit_read(console_client, path + "&page_size=200", ConsoleNodesListOut)
        after = datetime.now(UTC).date()
        if result.total is None or result.traffic is None:
            pytest.fail(
                "Node inventory total or traffic metadata unavailable (payload withheld)",
                pytrace=False,
            )
        traffic = result.traffic
        _check(
            {
                "preset",
                "timezone",
                "boundaries",
                "start_date",
                "end_date",
                "start_at",
                "end_at",
                "source",
                "unit",
                "direction",
                "history_completeness",
            }
            <= traffic.model_fields_set,
            "UTC traffic metadata was defaulted instead of returned explicitly",
        )
        _check(
            traffic.preset == preset and traffic.timezone == "UTC",
            "Traffic window identity mismatch",
        )
        _check(
            traffic.end_date in {before, after},
            "Traffic window does not end on the current UTC day",
        )
        _check(
            traffic.start_date == traffic.end_date - timedelta(days=days - 1),
            "Traffic calendar-day range mismatch",
        )
        _check(
            traffic.start_at == datetime.combine(traffic.start_date, time.min, UTC)
            and traffic.end_at == datetime.combine(traffic.end_date, time(23, 59, 59, 999000), UTC)
            and traffic.start_at.utcoffset() == traffic.end_at.utcoffset() == timedelta(0),
            "Traffic UTC boundaries mismatch",
        )
        _check(
            traffic.boundaries == "inclusive_start_and_end"
            and traffic.source == "remnawave_bandwidth_stats_nodes_series"
            and traffic.unit == "bytes"
            and traffic.direction == "outbound_upload_plus_download_unmultiplied"
            and traffic.history_completeness == "unknown_not_service_billing",
            "Traffic accounting/source metadata mismatch",
        )
        _check(traffic.inventory_nodes == result.total, "Traffic ranking changed inventory total")
        _check(0 <= traffic.matched_nodes <= result.total, "Traffic match count exceeds inventory")
        nodes = list(result.nodes)
        for page in range(1, (result.total + 199) // 200):
            extra = _audit_read(
                console_client, path + f"&page={page}&page_size=200", ConsoleNodesListOut
            )
            _check(extra.total == result.total, "Node inventory changed during pagination")
            nodes.extend(extra.nodes)
        ids = [node.id for node in nodes]
        _check(
            len(ids) == len(set(ids)) == result.total,
            "Node pagination omits or duplicates inventory",
        )
        _check(
            ids
            == [
                node.id for node in sorted(nodes, key=lambda node: (node.name.casefold(), node.id))
            ],
            "Traffic ranking replaced inventory ordering",
        )
        if baseline_ids is None:
            baseline_ids, baseline_total = ids, result.total
        _check(
            ids == baseline_ids and result.total == baseline_total,
            "Traffic window changed inventory membership or total",
        )
        for page in {0, result.total}:
            limited = _audit_read(
                console_client, path + f"&page={page}&page_size=1", ConsoleNodesListOut
            )
            _check(limited.total == result.total, "Node total depends on pagination size")
            _check(limited.page == page and limited.page_size == 1, "Node page metadata mismatch")
            _check(
                [node.id for node in limited.nodes] == ids[page : page + 1],
                "Node limited/beyond-end page mismatch",
            )


@pytest.mark.parametrize("console_client", ["runes.active@example.com"], indirect=True)
def test_live_audit_routes_reject_regular_and_anonymous_accounts(
    console_client: httpx.Client,
) -> None:
    paths = [
        ACCOUNT_PATH,
        ACCOUNT_PATH + "/" + "a" * 32,
        "/api/admin/console/maintenance",
        *[f"/api/admin/console/nodes?traffic_window={preset}" for preset in ("today", "7d", "30d")],
    ]
    for status, error in ((403, "forbidden"), (401, "unauthorized")):
        if status == 401:
            console_client.cookies.clear()
            console_client.headers.pop("Cookie", None)
            console_client.headers.pop("Authorization", None)
        for path in paths:
            try:
                response = console_client.get(path)
                body = response.json()
            except (httpx.HTTPError, ValueError):
                pytest.fail(
                    "Authorization audit response unavailable (payload withheld)", pytrace=False
                )
            _check(
                response.status_code == status, "Console audit route did not enforce authorization"
            )
            _check(
                "no-store" in response.headers.get("Cache-Control", ""),
                "Authorization error is cacheable",
            )
            _check(body == {"ok": False, "error": error}, "Authorization error contract mismatch")


def _asset_inventory(client: httpx.Client) -> tuple[int, list[ConsoleNodeAssetOut]]:
    first = _audit_read(client, ASSET_PATH + "?page_size=100", ConsoleNodeAssetsListOut)
    rows = list(first.items)
    for page in range(1, (first.total + 99) // 100):
        result = _audit_read(
            client, ASSET_PATH + f"?page={page}&page_size=100", ConsoleNodeAssetsListOut
        )
        _check(result.total == first.total, "Asset inventory changed during pagination")
        rows.extend(result.items)
    _check(
        len(rows) == len({row.id for row in rows}) == first.total, "Asset real COUNT/page mismatch"
    )
    return first.total, rows


def _asset_count(client: httpx.Client) -> int:
    result: ConsoleNodeAssetsListOut = _audit_read(
        client, ASSET_PATH + "?page_size=1", ConsoleNodeAssetsListOut
    )
    total = result.total
    if not isinstance(total, int) or isinstance(total, bool):
        pytest.fail("Asset COUNT is not an integer (payload withheld)", pytrace=False)
    return total


def _managed_counts(client: httpx.Client) -> tuple[int, int]:
    nodes = _audit_read(client, "/api/admin/console/nodes?page_size=1", ConsoleNodesListOut)
    services = _audit_read(client, "/api/admin/console/services?page_size=1", ConsoleServiceListOut)
    if nodes.total is None:
        pytest.fail("Managed-node count unavailable for asset isolation check", pytrace=False)
    return nodes.total, services.total


def _asset_body[T: BaseModel](response: httpx.Response, model: type[T]) -> T:
    _check(response.status_code == 200, "Asset write did not return success")
    _check(
        response.headers.get("Cache-Control") == "private, no-store", "Asset response is cacheable"
    )
    try:
        body = response.json()
        _check(
            isinstance(body, dict) and body.get("ok") is True, "Asset response envelope mismatch"
        )
        return model.model_validate(body)
    except (KeyError, TypeError, ValueError):
        pytest.fail("Asset response violates its schema (payload withheld)", pytrace=False)


def _asset_request(
    client: httpx.Client,
    method: str,
    path: str,
    headers: dict[str, str],
    body: dict[str, str] | None = None,
) -> httpx.Response:
    try:
        return client.request(method, path, headers=headers, json=body)
    except httpx.HTTPError:
        # POST has no idempotency contract: the caller must discover, never replay it.
        pytest.fail(
            "Asset request outcome unavailable; exact-owned cleanup will run", pytrace=False
        )


def _asset_login(client: httpx.Client, email: str) -> dict[str, str]:
    try:
        _login_console(client, email)
        return _csrf_headers(client)
    except (AssertionError, httpx.HTTPError, KeyError, TypeError, ValueError):
        pytest.fail("Asset QA session setup failed (credentials withheld)", pytrace=False)


def _cleanup_asset_ids(
    client: httpx.Client,
    headers: dict[str, str],
    owned_ids: set[str],
    baseline_ids: set[str],
    attempted_names: dict[str, tuple[str, str]],
) -> None:
    candidates = set(owned_ids)
    incomplete = False
    try:
        _, rows = _asset_inventory(client)
        for row in rows:
            expected = attempted_names.get(row.name)
            if (
                expected == (row.address, row.notes)
                and row.id not in baseline_ids
                and row.management_state == "unmanaged"
            ):
                candidates.add(row.id)
    except pytest.fail.Exception:
        incomplete = True
    for asset_id in sorted(candidates):
        if asset_id in baseline_ids or re.fullmatch(r"[0-9a-f]{32}", asset_id) is None:
            incomplete = True
            continue
        try:
            response = _asset_request(client, "DELETE", ASSET_PATH + "/" + asset_id, headers)
            if response.status_code == 404:
                _check(
                    "no-store" in response.headers.get("Cache-Control", ""),
                    "Asset 404 is cacheable",
                )
                _check(
                    response.json().get("error") == "node_asset_not_found", "Unexpected cleanup 404"
                )
                continue
            deleted = _asset_body(response, ConsoleNodeAssetDeletedOut)
            _check(
                deleted.id == asset_id and deleted.deleted, "Cleanup deleted-ID receipt mismatch"
            )
        except (pytest.fail.Exception, AttributeError, TypeError, ValueError):
            incomplete = True
    _check(not incomplete, "Exact-owned asset cleanup incomplete; inspect the isolated stand")


def test_live_node_assets_crud_persists_and_never_changes_managed_counts(
    console_client: httpx.Client,
) -> None:
    # Reserve a fresh 120-request/minute budget before writes and exact-ID cleanup.
    sleep(60)
    baseline_count, baseline_rows = _asset_inventory(console_client)
    baseline_ids = {row.id for row in baseline_rows}
    managed_before = _managed_counts(console_client)
    prefix = "qa-audit-assets-" + uuid4().hex
    address = "192.0.2.199"
    notes = prefix + " local-only record"
    owned_ids: set[str] = set()
    attempted_names: dict[str, tuple[str, str]] = {}
    created: list[ConsoleNodeAssetOut] = []
    try:
        headers = _csrf_headers(console_client)
    except (AssertionError, KeyError, TypeError, ValueError):
        pytest.fail("Asset QA CSRF setup failed (credentials withheld)", pytrace=False)
    _check("Authorization" not in console_client.headers, "Asset CSRF audit must use cookie auth")
    _check("X-CSRF-Token" not in console_client.headers, "Asset CSRF header must be request-local")
    try:
        for suffix in ("first", "second"):
            name = prefix + "-" + suffix
            attempted_names[name] = (address, notes)
            response = _asset_request(
                console_client,
                "POST",
                ASSET_PATH,
                headers,
                {"name": name, "address": address, "notes": notes},
            )
            item = _asset_body(response, ConsoleNodeAssetOut)
            _check(
                re.fullmatch(r"[0-9a-f]{32}", item.id) is not None
                and item.id not in baseline_ids
                and item.name == name
                and item.address == address
                and item.notes == notes,
                "Created asset identity does not match this test's exact intention",
            )
            owned_ids.add(item.id)
            created.append(item)
            _check(item.management_state == "unmanaged", "Local asset was unexpectedly managed")
            _check(
                item.created_at.utcoffset() == item.updated_at.utcoffset() == timedelta(0),
                "Asset timestamps are not UTC",
            )
        first, second = created
        _check(
            first.id != second.id and first.address == second.address,
            "Duplicate-address assets were merged",
        )
        _check(
            _asset_count(console_client) == baseline_count + 2,
            "Asset COUNT did not increase by two",
        )
        _check(
            _managed_counts(console_client) == managed_before,
            "Local registration changed managed counts",
        )

        edited_body = {
            "name": prefix + "-edited",
            "address": "2001:db8::199",
            "notes": notes + " edited",
        }
        edited = _asset_body(
            _asset_request(
                console_client, "PUT", ASSET_PATH + "/" + first.id, headers, edited_body
            ),
            ConsoleNodeAssetOut,
        )
        _check(
            edited.id == first.id
            and edited.created_at == first.created_at
            and edited.updated_at > first.updated_at
            and (edited.name, edited.address, edited.notes)
            == (edited_body["name"], edited_body["address"], edited_body["notes"]),
            "Asset replacement did not persist editable fields and timestamps",
        )
        # Omitted notes is the frozen PUT clear contract, not patch semantics.
        cleared = _asset_body(
            _asset_request(
                console_client,
                "PUT",
                ASSET_PATH + "/" + first.id,
                headers,
                {"name": edited.name, "address": edited.address},
            ),
            ConsoleNodeAssetOut,
        )
        _check(
            cleared.id == first.id
            and cleared.created_at == first.created_at
            and cleared.updated_at > edited.updated_at
            and cleared.notes == ""
            and (cleared.name, cleared.address) == (edited.name, edited.address),
            "Asset notes clear or preserved fields mismatch",
        )
        with httpx.Client(base_url=console_client.base_url, timeout=30, trust_env=False) as fresh:
            _asset_login(fresh, "runes.admin@example.com")
            reread = _audit_read(fresh, ASSET_PATH + "/" + first.id, ConsoleNodeAssetOut)
            untouched = _audit_read(fresh, ASSET_PATH + "/" + second.id, ConsoleNodeAssetOut)
            _check(
                reread == cleared and untouched == second,
                "New HTTP session did not observe committed assets",
            )

        with httpx.Client(
            base_url=console_client.base_url, timeout=30, trust_env=False
        ) as restricted:
            regular_headers = _asset_login(restricted, "runes.active@example.com")
            for label, client, denied_headers, status, error in (
                ("no-csrf", console_client, {}, 403, "csrf_failed"),
                ("regular", restricted, regular_headers, 403, "forbidden"),
                ("anonymous", restricted, {}, 401, "unauthorized"),
            ):
                if label == "anonymous":
                    restricted.cookies.clear()
                    restricted.headers.pop("Cookie", None)
                    restricted.headers.pop("Authorization", None)
                denied_name = prefix + "-denied-" + label
                attempted_names[denied_name] = (address, notes)
                for method, target, payload in (
                    ("POST", ASSET_PATH, {"name": denied_name, "address": address, "notes": notes}),
                    (
                        "PUT",
                        ASSET_PATH + "/" + first.id,
                        {
                            "name": cleared.name,
                            "address": cleared.address,
                            "notes": "must-not-change",
                        },
                    ),
                    ("DELETE", ASSET_PATH + "/" + second.id, None),
                ):
                    denied = _asset_request(client, method, target, denied_headers, payload)
                    _check(
                        denied.status_code == status, "Asset write authorization was not enforced"
                    )
                    _check(
                        "no-store" in denied.headers.get("Cache-Control", ""),
                        "Denied asset write is cacheable",
                    )
                    try:
                        rejected = denied.json()
                    except ValueError:
                        pytest.fail(
                            "Denied asset write returned non-JSON (payload withheld)", pytrace=False
                        )
                    _check(
                        isinstance(rejected, dict)
                        and rejected.get("ok") is False
                        and rejected.get("error") == error,
                        "Denied asset write error contract mismatch",
                    )
                _check(
                    _asset_count(console_client) == baseline_count + 2,
                    "Denied write changed asset COUNT",
                )
                _check(
                    _audit_read(console_client, ASSET_PATH + "/" + first.id, ConsoleNodeAssetOut)
                    == cleared,
                    "Denied PUT changed an asset",
                )
                _check(
                    _audit_read(console_client, ASSET_PATH + "/" + second.id, ConsoleNodeAssetOut)
                    == second,
                    "Denied DELETE removed or changed an asset",
                )

        for item, expected_count in ((first, baseline_count + 1), (second, baseline_count)):
            deleted = _asset_body(
                _asset_request(console_client, "DELETE", ASSET_PATH + "/" + item.id, headers),
                ConsoleNodeAssetDeletedOut,
            )
            _check(
                deleted.id == item.id and deleted.deleted, "Asset DELETE exact-ID receipt mismatch"
            )
            _check(_asset_count(console_client) == expected_count, "Asset COUNT decrement mismatch")
        _check(
            _managed_counts(console_client) == managed_before,
            "Asset CRUD changed managed-node/service counts",
        )
    finally:
        _cleanup_asset_ids(console_client, headers, owned_ids, baseline_ids, attempted_names)
        remaining_count, remaining = _asset_inventory(console_client)
        _check(
            remaining_count == baseline_count and {row.id for row in remaining} == baseline_ids,
            "Asset baseline COUNT or existing identities were not restored",
        )
        _check(
            {row.id: row for row in remaining} == {row.id: row for row in baseline_rows},
            "Existing asset records changed during the isolated test",
        )
        _check(
            _managed_counts(console_client) == managed_before,
            "Asset cleanup changed managed counts",
        )
