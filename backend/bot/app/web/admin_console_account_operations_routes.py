"""Account audit reads; the integration owner wires this module into the application."""

import re
from datetime import UTC, datetime

from aiohttp import web

from bot.app.web.admin_api_impl.auth import _require_admin_user_id
from bot.app.web.admin_api_impl.common import _error, _ok
from bot.app.web.admin_console_account_operations_schemas import (
    ConsoleAccountOperationOut,
    ConsoleAccountOperationsOut,
    ConsoleAccountOperationsQuery,
)
from bot.app.web.context import get_session_factory
from bot.app.web.route_contracts import (
    ADMIN_SECURITY,
    RouteContract,
    ok_envelope_for,
    register_contract,
)
from db.dal.account_operation_reads_dal import get_account_operation, list_account_operations


async def admin_console_account_operations_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    try:
        if len(request.query) != len(set(request.query)):
            raise ValueError("duplicate_query_parameter")
        query = ConsoleAccountOperationsQuery.model_validate(dict(request.query))
    except ValueError:
        response = _error(400, "invalid_account_operations_query")
    else:
        async with get_session_factory(request)() as session:
            rows, total = await list_account_operations(
                session, query.filters(), page=query.page, page_size=query.page_size
            )
            result = ConsoleAccountOperationsOut(
                operations=[ConsoleAccountOperationOut.from_row(row) for row in rows],
                total=total,
                page=query.page,
                page_size=query.page_size,
                observed_at=datetime.now(UTC),
            )
        response = _ok(result.model_dump(mode="json"))
    response.headers["Cache-Control"] = "private, no-store"
    return response


async def admin_console_account_operation_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    operation_id = request.match_info["operation_id"]
    if re.fullmatch(r"[0-9a-f]{32}", operation_id) is None:
        response = _error(400, "invalid_account_operation_id")
    else:
        async with get_session_factory(request)() as session:
            row = await get_account_operation(session, operation_id)
            response = (
                _ok({"operation": ConsoleAccountOperationOut.from_row(row).model_dump(mode="json")})
                if row
                else _error(404, "account_operation_not_found")
            )
    response.headers["Cache-Control"] = "private, no-store"
    return response


def setup_admin_console_account_operations_routes(app: web.Application) -> None:
    register_contract(
        admin_console_account_operations_route.__name__,
        RouteContract(
            response_schema=ok_envelope_for(ConsoleAccountOperationsOut),
            models=(ConsoleAccountOperationsOut,),
            security=ADMIN_SECURITY,
        ),
    )
    register_contract(
        admin_console_account_operation_route.__name__,
        RouteContract(
            response_schema=ok_envelope_for(ConsoleAccountOperationOut, key="operation"),
            models=(ConsoleAccountOperationOut,),
            security=ADMIN_SECURITY,
        ),
    )
    path = "/api/admin/console/account-operations"
    app.router.add_get(path, admin_console_account_operations_route)
    app.router.add_get(path + "/{operation_id}", admin_console_account_operation_route)
