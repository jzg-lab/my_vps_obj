"""管理员单服务操作；公共路由接线由整合窗口负责。"""

import re

from aiohttp import web
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select

from bot.app.web.admin_api_impl.auth import _require_admin_user_id
from bot.app.web.admin_api_impl.common import _error, _ok
from bot.app.web.admin_console_nodes_panel import NodeInventoryReader
from bot.app.web.admin_console_operations_schemas import (
    ConsoleServiceDiagnosticsOut,
    ConsoleServiceOperationOut,
    ConsoleServiceOperationsOut,
    ConsoleServicePreflightBody,
    ConsoleServicePreflightOut,
    ConsoleServiceRetryBody,
    ConsoleServiceRetryOut,
)
from bot.app.web.context import get_panel_service, get_session_factory
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import (
    ADMIN_SECURITY,
    RouteContract,
    ok_envelope_for,
    register_contract,
)
from bot.services.service_diagnostics import service_diagnostics
from bot.services.service_preflight import service_preflight
from db.dal.service_operations_dal import (
    list_operation_records,
    retry_block_reason,
    retry_execution,
)
from db.dal.user_services_dal import ServiceConflict
from db.models import User
from db.service_models import DedicatedExit, ServiceConnection, ServiceOrder, UserService

_PREFLIGHT_READER = web.AppKey("console_preflight_inventory", NodeInventoryReader)


class ConsoleServiceOperationsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=25, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=1_000_000)


def _private(response: web.Response) -> web.Response:
    response.headers["Cache-Control"] = "private, no-store"
    return response


async def admin_console_service_preflight_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    body = await parse_body_or_400(request, ConsoleServicePreflightBody)
    inventory = await request.app[_PREFLIGHT_READER].read(get_panel_service(request), ttl_seconds=0)
    async with get_session_factory(request)() as session:
        result = await service_preflight(session, body, inventory)
    return _private(_ok(result.model_dump(mode="json")))


async def admin_console_service_diagnostics_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    service_id = request.match_info["service_id"]
    if re.fullmatch(r"[0-9a-f]{32}", service_id) is None or request.query:
        return _private(_error(400, "invalid_service_diagnostics_query"))
    async with get_session_factory(request)() as session:
        service = await session.get(UserService, service_id)
        if service is None:
            return _private(_error(404, "service_not_found"))
        connection = await session.get(ServiceConnection, service_id)
        resource = await session.scalar(
            select(DedicatedExit).where(DedicatedExit.service_id == service_id)
        )
        user = await session.get(User, service.user_id) if service.user_id is not None else None
        result = await service_diagnostics(
            service, connection, resource, user, get_panel_service(request)
        )
    return _private(_ok(result.model_dump(mode="json")))


async def admin_console_service_operations_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    service_id = request.match_info["service_id"]
    try:
        query = ConsoleServiceOperationsQuery.model_validate(dict(request.query))
        if re.fullmatch(r"[0-9a-f]{32}", service_id) is None:
            raise ValueError
    except (ValueError, ValidationError):
        return _private(_error(400, "invalid_service_operations_query"))
    async with get_session_factory(request)() as session:
        service = await session.get(UserService, service_id)
        if service is None:
            return _private(_error(404, "service_not_found"))
        connection = await session.get(ServiceConnection, service_id)
        user = await session.get(User, service.user_id) if service.user_id is not None else None
        rows, total = await list_operation_records(
            session, service_id, limit=query.limit, offset=query.offset
        )
        result = ConsoleServiceOperationsOut(
            service_id=service_id,
            service_revision=service.revision,
            operations=[
                ConsoleServiceOperationOut.from_record(
                    order,
                    execution,
                    blocked=retry_block_reason(service, connection, user, execution)
                    if execution
                    else "historical_result_unknown",
                )
                for order, execution in rows
            ],
            total=total,
            limit=query.limit,
            offset=query.offset,
        )
    return _private(_ok(result.model_dump(mode="json")))


async def admin_console_service_retry_route(request: web.Request) -> web.Response:
    actor = _require_admin_user_id(request)
    service_id = request.match_info["service_id"]
    operation_id = request.match_info["operation_id"]
    if (
        any(re.fullmatch(r"[0-9a-f]{32}", value) is None for value in (service_id, operation_id))
        or request.query
    ):
        return _private(_error(400, "invalid_service_retry_query"))
    body = await parse_body_or_400(request, ConsoleServiceRetryBody)
    try:
        async with get_session_factory(request)() as session:
            execution, order, duplicate = await retry_execution(
                session,
                service_id=service_id,
                operation_id=operation_id,
                actor_id=actor,
                **body.model_dump(),
            )
            service = await session.get(UserService, service_id)
            user = await session.get(User, body.user_id)
            connection = await session.get(ServiceConnection, service_id)
            assert service is not None
            original = (
                await session.get(ServiceOrder, execution.order_id) if execution.order_id else None
            )
            result = ConsoleServiceRetryOut(
                operation=ConsoleServiceOperationOut.from_record(
                    original,
                    execution,
                    blocked=retry_block_reason(service, connection, user, execution),
                ),
                retry_order_id=order.id,
                duplicate=duplicate,
            )
            await session.commit()
    except ServiceConflict as exc:
        return _private(_error(exc.status, exc.code))
    return _private(_ok(result.model_dump(mode="json")))


def setup_admin_console_operations_routes(app: web.Application) -> None:
    app[_PREFLIGHT_READER] = NodeInventoryReader()
    for handler, model, body in (
        (
            admin_console_service_preflight_route,
            ConsoleServicePreflightOut,
            ConsoleServicePreflightBody,
        ),
        (admin_console_service_diagnostics_route, ConsoleServiceDiagnosticsOut, None),
        (admin_console_service_operations_route, ConsoleServiceOperationsOut, None),
        (admin_console_service_retry_route, ConsoleServiceRetryOut, ConsoleServiceRetryBody),
    ):
        register_contract(
            handler.__name__,
            RouteContract(
                request_model=body,
                response_schema=ok_envelope_for(model),
                models=(model,),
                security=ADMIN_SECURITY,
            ),
        )
    app.router.add_post(
        "/api/admin/console/service-preflight", admin_console_service_preflight_route
    )
    app.router.add_get(
        "/api/admin/console/services/{service_id}/diagnostics",
        admin_console_service_diagnostics_route,
    )
    app.router.add_get(
        "/api/admin/console/services/{service_id}/operations",
        admin_console_service_operations_route,
    )
    app.router.add_post(
        "/api/admin/console/services/{service_id}/operations/{operation_id}/retry",
        admin_console_service_retry_route,
    )
