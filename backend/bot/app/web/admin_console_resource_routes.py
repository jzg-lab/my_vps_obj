"""UC-06 draft inventory, preview and revalidation; no panel mutation endpoint."""

import hmac

from aiohttp import web

from bot.app.web.admin_api_impl.auth import _require_admin_user_id
from bot.app.web.admin_api_impl.common import _error, _ok
from bot.app.web.admin_console_resource_schemas import (
    ConsoleResourceCatalogOut,
    ConsoleResourcePreviewBody,
    ConsoleResourcePreviewOut,
    ConsoleResourceRevalidateBody,
    ConsoleResourceRevalidateOut,
    ResourceChange,
)
from bot.app.web.context import get_panel_service, get_session_factory
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import (
    ADMIN_SECURITY,
    RouteContract,
    ok_envelope_for,
    register_contract,
)
from bot.services.resource_operation_panel import resource_writes_enabled
from bot.services.resource_preview import build_resource_preview
from bot.services.resource_preview_authorizations import read_preview_authorizations
from bot.services.resource_preview_catalog import build_resource_catalog
from bot.services.resource_preview_panel import read_preview_inventory
from bot.services.resource_preview_read import unconfirmed_resource_archive
from db.dal.admin_console_nodes_dal import ServiceResourceRow, read_service_resources


async def _read_services(request: web.Request) -> tuple[list[ServiceResourceRow], bool]:
    async with get_session_factory(request)() as session:
        rows = await read_service_resources(session)
        return rows, await unconfirmed_resource_archive(session)


async def _read_preview(request: web.Request, change: ResourceChange) -> ConsoleResourcePreviewOut:
    inventory = await read_preview_inventory(get_panel_service(request))
    local_available = True
    archived_scope_unconfirmed = False
    try:
        rows, archived_scope_unconfirmed = await _read_services(request)
    except Exception:
        rows = []
        local_available = False
    authorizations = await read_preview_authorizations(get_panel_service(request), rows)
    result = build_resource_preview(
        change,
        inventory,
        rows,
        local_available=local_available,
        archived_scope_unconfirmed=archived_scope_unconfirmed,
        authorizations=authorizations,
    )
    result.execution_available = result.coverage == "complete" and resource_writes_enabled(
        get_panel_service(request)
    )
    return result


async def _stable_preview(
    request: web.Request, change: ResourceChange
) -> ConsoleResourcePreviewOut:
    first = await _read_preview(request, change)
    if first.fingerprint is None:
        return first
    second = await _read_preview(request, change)
    if second.fingerprint is not None and first.fingerprint != second.fingerprint:
        second.fingerprint = None
        second.coverage = "partial"
        second.execution_available = False
        second.blockers = sorted(set(second.blockers) | {"sources_changed_during_read"})
    return second


async def admin_console_resource_catalog_route(request: web.Request) -> web.Response:
    try:
        _require_admin_user_id(request)
    except web.HTTPException as exc:
        exc.headers["Cache-Control"] = "private, no-store"
        raise
    if request.query:
        response = _error(400, "invalid_resource_catalog_query")
    else:
        inventory = await read_preview_inventory(get_panel_service(request))
        result = build_resource_catalog(inventory)
        result.execution_available = result.coverage == "complete" and resource_writes_enabled(
            get_panel_service(request)
        )
        response = _ok(result.model_dump(mode="json"))
    response.headers["Cache-Control"] = "private, no-store"
    return response


async def admin_console_resource_preview_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    body = await parse_body_or_400(
        request,
        ConsoleResourcePreviewBody,
        validation_error_response_factory=lambda _: _error(400, "invalid_resource_change"),
    )
    result = await _stable_preview(request, body.change)
    response = _ok(result.model_dump(mode="json"))
    response.headers["Cache-Control"] = "private, no-store"
    return response


async def admin_console_resource_revalidate_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    body = await parse_body_or_400(
        request,
        ConsoleResourceRevalidateBody,
        validation_error_response_factory=lambda _: _error(400, "invalid_resource_change"),
    )
    preview = await _stable_preview(request, body.change)
    valid = preview.fingerprint is not None and hmac.compare_digest(
        preview.fingerprint, body.expected_fingerprint
    )
    result = ConsoleResourceRevalidateOut(
        valid=valid,
        reason="unchanged" if valid else "incomplete" if preview.fingerprint is None else "changed",
        preview=preview,
    )
    response = _ok(result.model_dump(mode="json"))
    response.headers["Cache-Control"] = "private, no-store"
    return response


def setup_admin_console_resource_routes(app: web.Application) -> None:
    register_contract(
        admin_console_resource_catalog_route.__name__,
        RouteContract(
            response_schema=ok_envelope_for(ConsoleResourceCatalogOut),
            models=(ConsoleResourceCatalogOut,),
            security=ADMIN_SECURITY,
        ),
    )
    app.router.add_get("/api/admin/console/resources/catalog", admin_console_resource_catalog_route)
    for handler, body, response in (
        (
            admin_console_resource_preview_route,
            ConsoleResourcePreviewBody,
            ConsoleResourcePreviewOut,
        ),
        (
            admin_console_resource_revalidate_route,
            ConsoleResourceRevalidateBody,
            ConsoleResourceRevalidateOut,
        ),
    ):
        register_contract(
            handler.__name__,
            RouteContract(
                request_model=body,
                response_schema=ok_envelope_for(response),
                models=(body, response),
                security=ADMIN_SECURITY,
            ),
        )
    app.router.add_post(
        "/api/admin/console/resources/preview", admin_console_resource_preview_route
    )
    app.router.add_post(
        "/api/admin/console/resources/revalidate", admin_console_resource_revalidate_route
    )
