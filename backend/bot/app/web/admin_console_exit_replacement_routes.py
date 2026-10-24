"""Service-scoped replacement intent, evidence and read-only progress."""

import re
from collections.abc import Awaitable, Callable
from functools import wraps

from aiohttp import web
from pydantic import ValidationError

from bot.app.web.admin_api_impl.auth import _require_admin_user_id
from bot.app.web.admin_api_impl.common import _error, _ok
from bot.app.web.admin_console_exit_replacement_schemas import (
    ConsoleExitReplacementAcceptedOut,
    ConsoleExitReplacementConfirmBody,
    ConsoleExitReplacementEvidenceBody,
    ConsoleExitReplacementQuery,
    ConsoleExitReplacementStartBody,
    ConsoleExitReplacementStateOut,
)
from bot.app.web.context import get_panel_service, get_session_factory
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import (
    ADMIN_SECURITY,
    RouteContract,
    ok_envelope_for,
    register_contract,
)
from bot.services.service_exit_replacement_commands import (
    accept_evidence,
    confirm_replacement,
    start_replacement,
)
from bot.services.service_exit_replacement_view import replacement_view
from db.dal.user_services_dal import ServiceConflict


def private_handler(
    handler: Callable[[web.Request], Awaitable[web.Response]],
) -> Callable[[web.Request], Awaitable[web.Response]]:
    @wraps(handler)
    async def guarded(request: web.Request) -> web.Response:
        try:
            _require_admin_user_id(request)
            if re.fullmatch(r"[0-9a-f]{32}", request.match_info.get("service_id", "")) is None:
                raise ServiceConflict("invalid_service_id", 400)
            if request.method != "GET" and request.query:
                raise ServiceConflict("invalid_replacement_query", 400)
            response = await handler(request)
        except web.HTTPException as exc:
            exc.headers["Cache-Control"] = "private, no-store"
            raise
        except ServiceConflict as exc:
            response = _error(exc.status, exc.code)
        except (ValidationError, ValueError):
            response = _error(400, "invalid_replacement_request")
        except Exception:
            # Do not expose transport errors, configuration or raw validation inputs.
            response = _error(503, "exit_replacement_sources_incomplete")
        response.headers["Cache-Control"] = "private, no-store"
        return response

    return guarded


@private_handler
async def admin_console_service_exit_replacement_route(request: web.Request) -> web.Response:
    query = ConsoleExitReplacementQuery.model_validate(dict(request.query))
    async with get_session_factory(request)() as session:
        result = await replacement_view(
            session, get_panel_service(request), request.match_info["service_id"], query
        )
    return _ok(result.model_dump(mode="json"))


@private_handler
async def admin_console_service_exit_replacement_start_route(request: web.Request) -> web.Response:
    body = await parse_body_or_400(
        request,
        ConsoleExitReplacementStartBody,
        validation_error_response_factory=lambda _: _error(400, "invalid_replacement_request"),
    )
    async with get_session_factory(request)() as session:
        result = await start_replacement(
            session,
            get_panel_service(request),
            service_id=request.match_info["service_id"],
            actor_id=_require_admin_user_id(request),
            body=body,
        )
        await session.commit()
    return _ok(result.model_dump(mode="json"))


@private_handler
async def admin_console_service_exit_replacement_confirm_route(
    request: web.Request,
) -> web.Response:
    body = await parse_body_or_400(
        request,
        ConsoleExitReplacementConfirmBody,
        validation_error_response_factory=lambda _: _error(400, "invalid_replacement_request"),
    )
    async with get_session_factory(request)() as session:
        result = await confirm_replacement(
            session,
            get_panel_service(request),
            service_id=request.match_info["service_id"],
            actor_id=_require_admin_user_id(request),
            body=body,
        )
        await session.commit()
    return _ok(result.model_dump(mode="json"))


@private_handler
async def admin_console_service_exit_replacement_evidence_route(
    request: web.Request,
) -> web.Response:
    body = await parse_body_or_400(
        request,
        ConsoleExitReplacementEvidenceBody,
        validation_error_response_factory=lambda _: _error(400, "invalid_replacement_request"),
    )
    async with get_session_factory(request)() as session:
        result = await accept_evidence(
            session,
            get_panel_service(request),
            service_id=request.match_info["service_id"],
            actor_id=_require_admin_user_id(request),
            body=body,
        )
        await session.commit()
    return _ok(result.model_dump(mode="json"))


async def _private_response(request: web.Request, response: web.StreamResponse) -> None:
    # Authentication and CSRF middleware can reject before a route handler runs.
    if request.match_info.route.handler.__name__.startswith(
        "admin_console_service_exit_replacement_"
    ):
        response.headers["Cache-Control"] = "private, no-store"


def setup_admin_console_exit_replacement_routes(app: web.Application) -> None:
    app.on_response_prepare.append(_private_response)
    path = "/api/admin/console/services/{service_id}/exit-replacement"
    for method, suffix, handler, body, output in (
        (
            "GET",
            "",
            admin_console_service_exit_replacement_route,
            None,
            ConsoleExitReplacementStateOut,
        ),
        (
            "POST",
            "",
            admin_console_service_exit_replacement_start_route,
            ConsoleExitReplacementStartBody,
            ConsoleExitReplacementAcceptedOut,
        ),
        (
            "POST",
            "/confirm",
            admin_console_service_exit_replacement_confirm_route,
            ConsoleExitReplacementConfirmBody,
            ConsoleExitReplacementAcceptedOut,
        ),
        (
            "POST",
            "/evidence",
            admin_console_service_exit_replacement_evidence_route,
            ConsoleExitReplacementEvidenceBody,
            ConsoleExitReplacementAcceptedOut,
        ),
    ):
        register_contract(
            handler.__name__,
            RouteContract(
                request_model=body,
                response_schema=ok_envelope_for(output),
                models=(output,),
                security=ADMIN_SECURITY,
            ),
        )
        app.router.add_route(method, path + suffix, handler)
