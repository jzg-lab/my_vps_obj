"""Administrator visibility and explicit retry for durable account connection changes."""

from aiohttp import web

from bot.app.web.admin_api_impl.auth import _require_admin_user_id
from bot.app.web.admin_api_impl.common import _error, _ok
from bot.app.web.context import (
    get_optional_subscription_service,
    get_panel_service,
    get_session_factory,
)
from bot.app.web.route_contracts import (
    ADMIN_SECURITY,
    RouteContract,
    ok_envelope_for,
    register_contract,
)
from bot.app.web.service_schemas import AccountAccessSyncOut
from bot.services.account_access_sync import synchronize_account_access
from db.dal import user_dal
from db.service_models import AccountAccessSync


async def admin_account_access_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    user_id = int(request.match_info["user_id"])
    panel = get_panel_service(request)
    if panel is None:
        service = get_optional_subscription_service(request)
        panel = getattr(service, "panel_service", None)
    async with get_session_factory(request)() as session:
        if await user_dal.get_user_by_id(session, user_id) is None:
            return _error(404, "not_found")
        if request.method == "POST":
            await synchronize_account_access(session, user_id, panel)
        job = await session.get(AccountAccessSync, user_id)
        result = AccountAccessSyncOut.from_job(job)
    return _ok({"access_sync": result.model_dump(mode="json")})


def setup_account_access_routes(app: web.Application) -> None:
    register_contract(
        "admin_account_access_route",
        RouteContract(
            response_schema=ok_envelope_for(AccountAccessSyncOut, key="access_sync"),
            models=(AccountAccessSyncOut,),
            security=ADMIN_SECURITY,
        ),
    )
    path = "/api/admin/users/{user_id:-?\\d+}/access-sync"
    app.router.add_get(path, admin_account_access_route)
    app.router.add_post(path, admin_account_access_route)
