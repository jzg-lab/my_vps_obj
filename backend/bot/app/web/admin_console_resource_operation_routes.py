"""Admin-only resource intents, progress and scoped reconciliation."""

import re
from collections.abc import Awaitable, Callable
from functools import wraps

from aiohttp import web
from pydantic import ValidationError

from bot.app.web.admin_api_impl.auth import _require_admin_user_id
from bot.app.web.admin_api_impl.common import _error, _ok
from bot.app.web.admin_console_resource_operation_schemas import (
    ConsoleResourceOperationAcceptedOut,
    ConsoleResourceOperationEvidenceBody,
    ConsoleResourceOperationListOut,
    ConsoleResourceOperationOut,
    ConsoleResourceOperationQuery,
    ConsoleResourceOperationReconcileBody,
    ConsoleResourceOperationRetryBody,
    ConsoleResourceOperationStartBody,
)
from bot.app.web.context import get_panel_service, get_session_factory
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import (
    ADMIN_SECURITY,
    RouteContract,
    ok_envelope_for,
    register_contract,
)
from bot.services.resource_operation_errors import safe_resource_error
from bot.services.resource_operations import (
    list_resource_operations,
    operation_output,
    retry_resource_operation,
    start_resource_operation,
)
from db.dal.user_services_dal import ServiceConflict
from db.resource_operation_models import ResourceOperation


def resource_private(
    handler: Callable[[web.Request], Awaitable[web.Response]],
) -> Callable[[web.Request], Awaitable[web.Response]]:
    @wraps(handler)
    async def guarded(request: web.Request) -> web.Response:
        try:
            _require_admin_user_id(request)
            operation_id = request.match_info.get("operation_id")
            if operation_id is not None and re.fullmatch(r"[a-f0-9]{32}", operation_id) is None:
                raise ServiceConflict("invalid_resource_operation_request", 400)
            if request.method != "GET" and request.query:
                raise ServiceConflict("invalid_resource_operation_request", 400)
            response = await handler(request)
        except web.HTTPException as exc:
            exc.headers["Cache-Control"] = "private, no-store"
            raise
        except ServiceConflict as exc:
            response = _error(exc.status, safe_resource_error(exc.code))
        except (ValidationError, ValueError):
            response = _error(400, "invalid_resource_operation_request")
        except Exception:
            response = _error(503, "resource_sources_incomplete")
        response.headers["Cache-Control"] = "private, no-store"
        return response

    return guarded


@resource_private
async def admin_console_resource_operations_route(request: web.Request) -> web.Response:
    query = ConsoleResourceOperationQuery.model_validate(dict(request.query))
    async with get_session_factory(request)() as session:
        rows, total = await list_resource_operations(
            session, offset=query.offset, limit=query.limit
        )
    return _ok(ConsoleResourceOperationListOut(items=rows, total=total).model_dump(mode="json"))


@resource_private
async def admin_console_resource_operation_route(request: web.Request) -> web.Response:
    if request.query:
        raise ServiceConflict("invalid_resource_operation_request", 400)
    async with get_session_factory(request)() as session:
        row = await session.get(ResourceOperation, request.match_info["operation_id"])
        if row is None:
            raise ServiceConflict("resource_operation_not_found", 404)
        result = operation_output(row).operation
    return _ok(result.model_dump(mode="json"))


@resource_private
async def admin_console_resource_operation_start_route(request: web.Request) -> web.Response:
    body = await parse_body_or_400(
        request,
        ConsoleResourceOperationStartBody,
        validation_error_response_factory=lambda _: _error(
            400, "invalid_resource_operation_request"
        ),
    )
    async with get_session_factory(request)() as session:
        result = await start_resource_operation(
            session, get_panel_service(request), actor_id=_require_admin_user_id(request), body=body
        )
        await session.commit()
    return _ok(result.model_dump(mode="json"))


@resource_private
async def admin_console_resource_operation_retry_route(request: web.Request) -> web.Response:
    body = await parse_body_or_400(
        request,
        ConsoleResourceOperationRetryBody,
        validation_error_response_factory=lambda _: _error(
            400, "invalid_resource_operation_request"
        ),
    )
    async with get_session_factory(request)() as session:
        result = await retry_resource_operation(
            session, get_panel_service(request), request.match_info["operation_id"], body
        )
        await session.commit()
    return _ok(result.model_dump(mode="json"))


@resource_private
async def admin_console_resource_operation_reconcile_route(request: web.Request) -> web.Response:
    from bot.services.resource_operation_reconciliation import reconcile_resource_operation

    body = await parse_body_or_400(
        request,
        ConsoleResourceOperationReconcileBody,
        validation_error_response_factory=lambda _: _error(
            400, "invalid_resource_operation_request"
        ),
    )
    async with get_session_factory(request)() as session:
        result = await reconcile_resource_operation(
            session,
            get_panel_service(request),
            request.match_info["operation_id"],
            expected_version=body.expected_version,
        )
        await session.commit()
    return _ok(result.model_dump(mode="json"))


@resource_private
async def admin_console_resource_operation_evidence_route(request: web.Request) -> web.Response:
    from bot.services.resource_operation_reconciliation import accept_resource_evidence

    body = await parse_body_or_400(
        request,
        ConsoleResourceOperationEvidenceBody,
        validation_error_response_factory=lambda _: _error(
            400, "invalid_resource_operation_request"
        ),
    )
    async with get_session_factory(request)() as session:
        result = await accept_resource_evidence(
            session,
            get_panel_service(request),
            request.match_info["operation_id"],
            actor_id=_require_admin_user_id(request),
            body=body,
        )
        await session.commit()
    return _ok(result.model_dump(mode="json"))


async def resource_private_response(request: web.Request, response: web.StreamResponse) -> None:
    if request.match_info.route.handler.__name__.startswith(
        ("admin_console_resource_operation", "admin_console_node_onboarding_")
    ):
        response.headers["Cache-Control"] = "private, no-store"


def setup_admin_console_resource_operation_routes(app: web.Application) -> None:
    if resource_private_response not in app.on_response_prepare:
        app.on_response_prepare.append(resource_private_response)
    path = "/api/admin/console/resources/operations"
    for method, suffix, handler, body, output in (
        ("GET", "", admin_console_resource_operations_route, None, ConsoleResourceOperationListOut),
        (
            "GET",
            "/{operation_id}",
            admin_console_resource_operation_route,
            None,
            ConsoleResourceOperationOut,
        ),
        (
            "POST",
            "",
            admin_console_resource_operation_start_route,
            ConsoleResourceOperationStartBody,
            ConsoleResourceOperationAcceptedOut,
        ),
        (
            "POST",
            "/{operation_id}/retry",
            admin_console_resource_operation_retry_route,
            ConsoleResourceOperationRetryBody,
            ConsoleResourceOperationAcceptedOut,
        ),
        (
            "POST",
            "/{operation_id}/reconcile",
            admin_console_resource_operation_reconcile_route,
            ConsoleResourceOperationReconcileBody,
            ConsoleResourceOperationAcceptedOut,
        ),
        (
            "POST",
            "/{operation_id}/evidence",
            admin_console_resource_operation_evidence_route,
            ConsoleResourceOperationEvidenceBody,
            ConsoleResourceOperationAcceptedOut,
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
