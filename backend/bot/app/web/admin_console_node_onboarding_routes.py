"""Explicit, non-cacheable deployment credentials; never installs or persists a secret."""

from aiohttp import web

from bot.app.web.admin_api_impl.common import _error, _ok
from bot.app.web.admin_console_resource_operation_routes import (
    resource_private,
    resource_private_response,
)
from bot.app.web.admin_console_resource_operation_schemas import (
    ConsoleNodeDeploymentBody,
    ConsoleNodeDeploymentOut,
)
from bot.app.web.context import get_panel_service
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import (
    ADMIN_SECURITY,
    RouteContract,
    ok_envelope_for,
    register_contract,
)
from bot.services.panel_api_contracts import PanelApiOperation
from bot.services.resource_operation_panel import require_resource_panel
from db.dal.user_services_dal import ServiceConflict


@resource_private
async def admin_console_node_onboarding_deployment_route(request: web.Request) -> web.Response:
    body = await parse_body_or_400(
        request,
        ConsoleNodeDeploymentBody,
        validation_error_response_factory=lambda _: _error(
            400, "invalid_resource_operation_request"
        ),
    )
    panel = await require_resource_panel(get_panel_service(request))
    result = await panel._request_once(
        "GET",
        "/keygen",
        operation=PanelApiOperation.NODE_KEYGEN,
        log_full_response=False,
        preserve_http_status=True,
    )
    response: object = (
        result.get("response")
        if isinstance(result, dict) and result.get("status_code") == 200
        else None
    )
    secret: object = response.get("secretKey") if isinstance(response, dict) else None
    if not isinstance(secret, str) or not secret:
        raise ServiceConflict("resource_deployment_unavailable", 503)
    return _ok(
        ConsoleNodeDeploymentOut(
            management_port=body.management_port, secret_key=secret
        ).model_dump(mode="json")
    )


def setup_admin_console_node_onboarding_routes(app: web.Application) -> None:
    if resource_private_response not in app.on_response_prepare:
        app.on_response_prepare.append(resource_private_response)
    register_contract(
        admin_console_node_onboarding_deployment_route.__name__,
        RouteContract(
            request_model=ConsoleNodeDeploymentBody,
            response_schema=ok_envelope_for(ConsoleNodeDeploymentOut),
            models=(ConsoleNodeDeploymentOut,),
            security=ADMIN_SECURITY,
        ),
    )
    app.router.add_post(
        "/api/admin/console/nodes/onboarding/deployment",
        admin_console_node_onboarding_deployment_route,
    )
