"""Read-only UC-05 entry point; application wiring belongs to the integration owner."""

from datetime import UTC, datetime

from aiohttp import web

from bot.app.web.admin_api_impl.auth import _require_admin_user_id
from bot.app.web.admin_api_impl.common import _error, _ok
from bot.app.web.admin_console_global_operations_schemas import (
    ConsoleGlobalOperationOut,
    ConsoleGlobalOperationsOut,
    ConsoleGlobalOperationsQuery,
)
from bot.app.web.context import get_session_factory
from bot.app.web.route_contracts import (
    ADMIN_SECURITY,
    RouteContract,
    ok_envelope_for,
    register_contract,
)
from db.dal.global_service_operations_dal import list_global_operation_records


async def admin_console_global_operations_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    try:
        if len(request.query) != len(set(request.query)):
            raise ValueError("duplicate_query_parameter")
        query = ConsoleGlobalOperationsQuery.model_validate(dict(request.query))
        after = query.position()
    except (ValueError, OverflowError):
        response = _error(400, "invalid_global_operations_query")
    else:
        observed_at = datetime.now(UTC)
        async with get_session_factory(request)() as session:
            rows, total, has_more = await list_global_operation_records(
                session, query.filters(), limit=query.limit, after=after
            )
            result = ConsoleGlobalOperationsOut(
                operations=[ConsoleGlobalOperationOut.from_row(row) for row in rows],
                total=total,
                limit=query.limit,
                next_cursor=query.next_cursor(rows[-1].position) if has_more else None,
                observed_at=observed_at,
            )
        response = _ok(result.model_dump(mode="json"))
    response.headers["Cache-Control"] = "private, no-store"
    return response


def setup_admin_console_global_operations_routes(app: web.Application) -> None:
    register_contract(
        admin_console_global_operations_route.__name__,
        RouteContract(
            response_schema=ok_envelope_for(ConsoleGlobalOperationsOut),
            models=(ConsoleGlobalOperationsOut,),
            security=ADMIN_SECURITY,
        ),
    )
    app.router.add_get("/api/admin/console/operations", admin_console_global_operations_route)
