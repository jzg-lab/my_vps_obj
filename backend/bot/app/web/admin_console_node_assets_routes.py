"""Admin-only local inventory CRUD, independent of Remnawave and provisioning."""

import re
from collections.abc import Awaitable, Callable
from functools import wraps

from aiohttp import web
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from bot.app.web.admin_api_impl.auth import _require_admin_user_id
from bot.app.web.admin_api_impl.common import _error, _ok
from bot.app.web.admin_console_node_assets_schemas import (
    ConsoleNodeAssetBody,
    ConsoleNodeAssetDeletedOut,
    ConsoleNodeAssetOut,
    ConsoleNodeAssetsListOut,
    ConsoleNodeAssetsQuery,
)
from bot.app.web.context import get_session_factory
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import (
    ADMIN_SECURITY,
    RouteContract,
    ok_envelope_for,
    register_contract,
)
from db.dal import node_assets_dal


def _asset_private(
    handler: Callable[[web.Request], Awaitable[web.Response]],
) -> Callable[[web.Request], Awaitable[web.Response]]:
    @wraps(handler)
    async def guarded(request: web.Request) -> web.Response:
        try:
            _require_admin_user_id(request)
            asset_id = request.match_info.get("asset_id")
            if asset_id is not None and re.fullmatch(r"[a-f0-9]{32}", asset_id) is None:
                response = _error(400, "invalid_node_asset_id")
            elif request.query and (asset_id is not None or request.method not in {"GET", "HEAD"}):
                response = _error(400, "invalid_node_asset_query")
            else:
                response = await handler(request)
        except web.HTTPException as exc:
            exc.headers["Cache-Control"] = "private, no-store"
            raise
        except SQLAlchemyError:
            response = _error(503, "node_assets_unavailable")
        response.headers["Cache-Control"] = "private, no-store"
        return response

    return guarded


@_asset_private
async def admin_console_node_assets_route(request: web.Request) -> web.Response:
    if any(len(request.query.getall(key)) != 1 for key in request.query):
        return _error(400, "invalid_node_asset_query")
    try:
        query = ConsoleNodeAssetsQuery.model_validate(dict(request.query))
    except ValidationError:
        return _error(400, "invalid_node_asset_query")
    async with get_session_factory(request)() as session:
        rows, total = await node_assets_dal.list_assets(
            session, page=query.page, page_size=query.page_size
        )
        result = ConsoleNodeAssetsListOut(
            items=[ConsoleNodeAssetOut.from_orm_asset(row) for row in rows],
            total=total,
            page=query.page,
            page_size=query.page_size,
        )
    return _ok(result.model_dump(mode="json"))


@_asset_private
async def admin_console_node_asset_route(request: web.Request) -> web.Response:
    async with get_session_factory(request)() as session:
        row = await node_assets_dal.get_asset(session, request.match_info["asset_id"])
        if row is None:
            return _error(404, "node_asset_not_found")
        result = ConsoleNodeAssetOut.from_orm_asset(row)
    return _ok(result.model_dump(mode="json"))


@_asset_private
async def admin_console_node_asset_create_route(request: web.Request) -> web.Response:
    body = await parse_body_or_400(
        request,
        ConsoleNodeAssetBody,
        validation_error_response_factory=lambda _: _error(400, "invalid_node_asset_request"),
    )
    async with get_session_factory(request)() as session:
        row = await node_assets_dal.create_asset(
            session, name=body.name, address=body.address, notes=body.notes
        )
        result = ConsoleNodeAssetOut.from_orm_asset(row)
        await session.commit()
    return _ok(result.model_dump(mode="json"))


@_asset_private
async def admin_console_node_asset_update_route(request: web.Request) -> web.Response:
    body = await parse_body_or_400(
        request,
        ConsoleNodeAssetBody,
        validation_error_response_factory=lambda _: _error(400, "invalid_node_asset_request"),
    )
    async with get_session_factory(request)() as session:
        row = await node_assets_dal.update_asset(
            session,
            request.match_info["asset_id"],
            name=body.name,
            address=body.address,
            notes=body.notes,
        )
        if row is None:
            return _error(404, "node_asset_not_found")
        result = ConsoleNodeAssetOut.from_orm_asset(row)
        await session.commit()
    return _ok(result.model_dump(mode="json"))


@_asset_private
async def admin_console_node_asset_delete_route(request: web.Request) -> web.Response:
    asset_id = request.match_info["asset_id"]
    async with get_session_factory(request)() as session:
        if not await node_assets_dal.delete_asset(session, asset_id):
            return _error(404, "node_asset_not_found")
        await session.commit()
    return _ok(ConsoleNodeAssetDeletedOut(id=asset_id, deleted=True).model_dump(mode="json"))


def setup_admin_console_node_assets_routes(app: web.Application) -> None:
    # Global admin-auth, CSRF and no-store middleware remain the application boundary.
    for handler, response_model, request_model in (
        (admin_console_node_assets_route, ConsoleNodeAssetsListOut, None),
        (admin_console_node_asset_route, ConsoleNodeAssetOut, None),
        (admin_console_node_asset_create_route, ConsoleNodeAssetOut, ConsoleNodeAssetBody),
        (admin_console_node_asset_update_route, ConsoleNodeAssetOut, ConsoleNodeAssetBody),
        (admin_console_node_asset_delete_route, ConsoleNodeAssetDeletedOut, None),
    ):
        register_contract(
            handler.__name__,
            RouteContract(
                request_model=request_model,
                response_schema=ok_envelope_for(response_model),
                models=(response_model,),
                security=ADMIN_SECURITY,
            ),
        )
    app.router.add_get("/api/admin/console/node-assets", admin_console_node_assets_route)
    app.router.add_post("/api/admin/console/node-assets", admin_console_node_asset_create_route)
    app.router.add_get("/api/admin/console/node-assets/{asset_id}", admin_console_node_asset_route)
    app.router.add_put(
        "/api/admin/console/node-assets/{asset_id}", admin_console_node_asset_update_route
    )
    app.router.add_delete(
        "/api/admin/console/node-assets/{asset_id}", admin_console_node_asset_delete_route
    )
