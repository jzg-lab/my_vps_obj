"""Administrator-only maintenance discovery, without contacting the execution layer."""

from aiohttp import web

from bot.app.web.admin_api_impl.auth import _require_admin_user_id
from bot.app.web.admin_api_impl.common import _error, _ok
from bot.app.web.admin_api_impl.panel_links import build_panel_maintenance_url
from bot.app.web.admin_console_maintenance_schemas import ConsoleMaintenanceOut
from bot.app.web.context import get_settings
from bot.app.web.route_contracts import (
    ADMIN_SECURITY,
    RouteContract,
    ok_envelope_for,
    register_contract,
)


async def admin_console_maintenance_route(request: web.Request) -> web.Response:
    try:
        _require_admin_user_id(request)
    except web.HTTPException as exc:
        exc.headers["Cache-Control"] = "private, no-store"
        raise
    if request.query:
        response = _error(400, "invalid_maintenance_query")
    else:
        result = ConsoleMaintenanceOut(
            destination=build_panel_maintenance_url(get_settings(request).PANEL_PUBLIC_URL)
        )
        response = _ok(result.model_dump(mode="json"))
    response.headers["Cache-Control"] = "private, no-store"
    return response


def setup_admin_console_maintenance_routes(app: web.Application) -> None:
    register_contract(
        admin_console_maintenance_route.__name__,
        RouteContract(
            response_schema=ok_envelope_for(ConsoleMaintenanceOut),
            models=(ConsoleMaintenanceOut,),
            security=ADMIN_SECURITY,
        ),
    )
    app.router.add_get("/api/admin/console/maintenance", admin_console_maintenance_route)
