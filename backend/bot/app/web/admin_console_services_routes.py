"""Read-only cross-customer services and local business metrics."""

import re
from datetime import UTC, datetime

from aiohttp import web
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from bot.app.web.admin_api_impl.auth import _require_admin_user_id
from bot.app.web.admin_api_impl.common import _error, _ok
from bot.app.web.admin_console_services_schemas import (
    ConsoleConnectionOut,
    ConsoleServiceDetailOut,
    ConsoleServiceListOut,
    ConsoleServiceOut,
    ConsoleSummaryOut,
)
from bot.app.web.context import get_session_factory
from bot.app.web.route_contracts import (
    ADMIN_SECURITY,
    RouteContract,
    ok_envelope_for,
    register_contract,
)
from config.service_plans import ServicePlanTerms
from db.dal import admin_console_services_dal
from db.dal.admin_console_services_dal import ConsoleSort, ConsoleStatus
from db.dal.admin_console_summary_dal import read_console_summary


class ConsoleServicesQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    q: str = Field(default="", max_length=200)
    status: ConsoleStatus = "all"
    user_id: int | None = Field(default=None, ge=-(2**53 - 1), le=2**53 - 1)
    sort: ConsoleSort = "created_desc"
    page: int = Field(default=0, ge=0, le=1_000_000)
    page_size: int = Field(default=25, ge=1, le=200)
    expiring_within_days: int = Field(default=7, ge=1, le=365)


async def admin_console_services_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    try:
        query = ConsoleServicesQuery.model_validate(dict(request.query))
    except ValidationError:
        return _error(400, "invalid_console_services_query")
    now = datetime.now(UTC)
    async with get_session_factory(request)() as session:
        rows, total = await admin_console_services_dal.list_services(
            session, now=now, **query.model_dump()
        )
        result = ConsoleServiceListOut(
            services=[ConsoleServiceOut.from_row(row) for row in rows],
            total=total,
            page=query.page,
            page_size=query.page_size,
            observed_at=now,
            expiring_within_days=query.expiring_within_days,
        )
    response = _ok(result.model_dump(mode="json"))
    response.headers["Cache-Control"] = "private, no-store"
    return response


async def admin_console_service_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    service_id = request.match_info["service_id"]
    if re.fullmatch(r"[0-9a-f]{32}", service_id) is None:
        return _error(400, "invalid_service_id")
    async with get_session_factory(request)() as session:
        row = await admin_console_services_dal.get_service(session, service_id)
        if row is None:
            return _error(404, "service_not_found")
        base = ConsoleServiceOut.from_row(row)
        result = ConsoleServiceDetailOut(
            service=base.service,
            customer=base.customer,
            connection=ConsoleConnectionOut.from_connection(row[1]) if row[1] else None,
            terms=ServicePlanTerms.model_validate(row[0].terms),
        )
    response = _ok(result.model_dump(mode="json"))
    response.headers["Cache-Control"] = "private, no-store"
    return response


async def admin_console_summary_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    async with get_session_factory(request)() as session:
        result = ConsoleSummaryOut.model_validate(
            await read_console_summary(session, now=datetime.now(UTC))
        )
    response = _ok(result.model_dump(mode="json"))
    response.headers["Cache-Control"] = "private, no-store"
    return response


def setup_admin_console_services_routes(app: web.Application) -> None:
    for handler, model in (
        (admin_console_services_route, ConsoleServiceListOut),
        (admin_console_service_route, ConsoleServiceDetailOut),
        (admin_console_summary_route, ConsoleSummaryOut),
    ):
        register_contract(
            handler.__name__,
            RouteContract(
                response_schema=ok_envelope_for(model),
                models=(model,),
                security=ADMIN_SECURITY,
            ),
        )
    app.router.add_get("/api/admin/console/services", admin_console_services_route)
    app.router.add_get("/api/admin/console/services/{service_id}", admin_console_service_route)
    app.router.add_get("/api/admin/console/summary", admin_console_summary_route)
