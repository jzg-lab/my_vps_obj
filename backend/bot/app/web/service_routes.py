"""Core HTTP routes for administrator-managed independent services."""

from aiohttp import web
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.admin_api_impl.auth import _require_admin_user_id
from bot.app.web.admin_api_impl.common import _error, _ok
from bot.app.web.context import get_session_factory
from bot.app.web.request_parsing import parse_body_or_400
from bot.app.web.route_contracts import (
    ADMIN_SECURITY,
    BOOLEAN_SCHEMA,
    INTEGER_SCHEMA,
    USER_SECURITY,
    RouteContract,
    ok_envelope_for,
    register_contract,
    schema_ref,
)
from bot.app.web.service_schemas import (
    DedicatedExitBody,
    DedicatedExitOut,
    ServiceActivationBody,
    ServiceOrderOut,
    ServicePlanBody,
    ServicePlanOut,
    ServicePlanUpdateBody,
    UserServiceOut,
)
from bot.app.web.webapp.common import _require_user_id
from db.dal import user_dal, user_services_dal
from db.dal.user_services_dal import ServiceConflict, activate_service, save_plan
from db.service_models import (
    UserService,
)


def _register_contracts() -> None:
    for name, model, key, body, many, security in (
        ("admin_service_plans_route", ServicePlanOut, "plans", None, True, ADMIN_SECURITY),
        (
            "admin_service_plan_create_route",
            ServicePlanOut,
            "plan",
            ServicePlanBody,
            False,
            ADMIN_SECURITY,
        ),
        (
            "admin_service_plan_update_route",
            ServicePlanOut,
            "plan",
            ServicePlanUpdateBody,
            False,
            ADMIN_SECURITY,
        ),
        ("admin_services_route", UserServiceOut, "services", None, True, ADMIN_SECURITY),
        ("user_services_route", UserServiceOut, "services", None, True, USER_SECURITY),
        ("user_service_route", UserServiceOut, "service", None, False, USER_SECURITY),
        ("admin_service_orders_route", ServiceOrderOut, "orders", None, True, ADMIN_SECURITY),
        ("admin_dedicated_exits_route", DedicatedExitOut, "exits", None, True, ADMIN_SECURITY),
        (
            "admin_dedicated_exit_create_route",
            DedicatedExitOut,
            "exit",
            DedicatedExitBody,
            False,
            ADMIN_SECURITY,
        ),
    ):
        register_contract(
            name,
            RouteContract(
                request_model=body,
                response_schema=ok_envelope_for(
                    model, key=key, many=many, extra={"total": INTEGER_SCHEMA} if many else None
                ),
                models=(model,),
                security=security,
            ),
        )
    register_contract(
        "admin_service_activate_route",
        RouteContract(
            request_model=ServiceActivationBody,
            response_schema=ok_envelope_for(
                UserServiceOut,
                key="service",
                extra={"order": schema_ref(ServiceOrderOut), "duplicate": BOOLEAN_SCHEMA},
            ),
            models=(UserServiceOut, ServiceOrderOut),
            security=ADMIN_SECURITY,
        ),
    )


def _pagination(request: web.Request) -> tuple[int, int]:
    try:
        limit = int(request.query.get("limit", "100"))
        offset = int(request.query.get("offset", "0"))
        if not 1 <= limit <= 200 or not 0 <= offset <= 1_000_000:
            raise ValueError
    except ValueError:
        raise web.HTTPBadRequest(
            text='{"ok":false,"error":"invalid_pagination"}', content_type="application/json"
        ) from None
    return limit, offset


def _query_user(request: web.Request) -> int:
    try:
        user_id = int(request.query["user_id"])
        if not -(2**53 - 1) <= user_id <= 2**53 - 1 or user_id == 0:
            raise ValueError
        return user_id
    except (KeyError, ValueError):
        raise web.HTTPBadRequest(
            text='{"ok":false,"error":"user_id_required"}', content_type="application/json"
        ) from None


async def _service_out(session: AsyncSession, service: UserService) -> UserServiceOut:
    connection, resource = await user_services_dal.get_service_resource(session, service.id)
    user = await user_dal.get_user_by_id(session, service.user_id)
    return UserServiceOut.from_orm_service(
        service, connection, resource, banned=bool(user and user.is_banned)
    )


async def admin_service_plans_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    limit, offset = _pagination(request)
    async with get_session_factory(request)() as session:
        rows, total = await user_services_dal.list_plans(session, limit=limit, offset=offset)
        plans = [ServicePlanOut.from_orm_plan(row).model_dump(mode="json") for row in rows]
    return _ok({"plans": plans, "total": total})


async def admin_service_plan_create_route(request: web.Request) -> web.Response:
    actor = _require_admin_user_id(request)
    body = await parse_body_or_400(request, ServicePlanBody)
    async with get_session_factory(request)() as session:
        plan = await save_plan(session, terms=body.terms, enabled=body.enabled, actor_id=actor)
        result = ServicePlanOut.from_orm_plan(plan)
        await session.commit()
    return _ok({"plan": result.model_dump(mode="json")})


async def admin_service_plan_update_route(request: web.Request) -> web.Response:
    actor = _require_admin_user_id(request)
    body = await parse_body_or_400(request, ServicePlanUpdateBody)
    try:
        async with get_session_factory(request)() as session:
            plan = await save_plan(
                session,
                terms=body.terms,
                enabled=body.enabled,
                actor_id=actor,
                plan_id=request.match_info["plan_id"],
                expected_revision=body.expected_revision,
            )
            result = ServicePlanOut.from_orm_plan(plan)
            await session.commit()
    except ServiceConflict as exc:
        return _error(exc.status, exc.code)
    return _ok({"plan": result.model_dump(mode="json")})


async def admin_service_activate_route(request: web.Request) -> web.Response:
    actor = _require_admin_user_id(request)
    body = await parse_body_or_400(request, ServiceActivationBody)
    try:
        async with get_session_factory(request)() as session:
            service, order, duplicate = await activate_service(
                session, actor_id=actor, **body.model_dump()
            )
            result = await _service_out(session, service)
            order_result = ServiceOrderOut.from_orm_order(order)
            await session.commit()
    except ServiceConflict as exc:
        return _error(exc.status, exc.code)
    return _ok(
        {
            "service": result.model_dump(mode="json"),
            "order": order_result.model_dump(mode="json"),
            "duplicate": duplicate,
        }
    )


async def _list_services(request: web.Request, user_id: int, *, admin: bool) -> web.Response:
    limit, offset = _pagination(request)
    async with get_session_factory(request)() as session:
        user = await user_dal.get_user_by_id(session, user_id)
        if user is None:
            return _error(404, "user_not_found")
        if not admin and user.is_banned:
            return _error(403, "account_banned")
        rows, total = await user_services_dal.list_services(
            session, user_id=user_id, limit=limit, offset=offset
        )
        services = [
            UserServiceOut.from_orm_service(
                service, connection, resource, banned=bool(user.is_banned)
            ).model_dump(mode="json")
            for service, connection, resource in rows
        ]
    return _ok({"services": services, "total": total})


async def admin_services_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    return await _list_services(request, _query_user(request), admin=True)


async def user_services_route(request: web.Request) -> web.Response:
    return await _list_services(request, _require_user_id(request), admin=False)


async def user_service_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    async with get_session_factory(request)() as session:
        user = await user_dal.get_user_by_id(session, user_id)
        if user is None or user.is_banned:
            return _error(403, "account_banned")
        service = await user_services_dal.get_service(
            session, request.match_info["service_id"], user_id=user_id
        )
        if service is None:
            return _error(404, "service_not_found")
        result = await _service_out(session, service)
    return _ok({"service": result.model_dump(mode="json")})


async def admin_service_orders_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    user_id = _query_user(request)
    limit, offset = _pagination(request)
    async with get_session_factory(request)() as session:
        rows, total = await user_services_dal.list_orders(
            session, user_id=user_id, limit=limit, offset=offset
        )
        orders = [ServiceOrderOut.from_orm_order(row).model_dump(mode="json") for row in rows]
    return _ok({"orders": orders, "total": total})


async def admin_dedicated_exits_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    limit, offset = _pagination(request)
    async with get_session_factory(request)() as session:
        rows, total = await user_services_dal.list_exits(session, limit=limit, offset=offset)
        exits = [DedicatedExitOut.from_orm_exit(row).model_dump(mode="json") for row in rows]
    return _ok({"exits": exits, "total": total})


async def admin_dedicated_exit_create_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    body = await parse_body_or_400(request, DedicatedExitBody)
    try:
        async with get_session_factory(request)() as session:
            resource = await user_services_dal.create_exit(
                session,
                label=body.label,
                ip_address=str(body.ip_address),
                resource_pool=body.resource_pool,
                squad_uuid=str(body.squad_uuid),
            )
            result = DedicatedExitOut.from_orm_exit(resource)
            await session.commit()
    except IntegrityError:
        return _error(409, "exit_already_exists")
    return _ok({"exit": result.model_dump(mode="json")})


def setup_service_admin_routes(app: web.Application) -> None:
    _register_contracts()
    app.router.add_get("/api/admin/service-plans", admin_service_plans_route)
    app.router.add_post("/api/admin/service-plans", admin_service_plan_create_route)
    app.router.add_put("/api/admin/service-plans/{plan_id}", admin_service_plan_update_route)
    app.router.add_get("/api/admin/services", admin_services_route)
    app.router.add_post("/api/admin/services", admin_service_activate_route)
    app.router.add_get("/api/admin/service-orders", admin_service_orders_route)
    app.router.add_get("/api/admin/dedicated-exits", admin_dedicated_exits_route)
    app.router.add_post("/api/admin/dedicated-exits", admin_dedicated_exit_create_route)


def setup_service_user_routes(app: web.Application) -> None:
    _register_contracts()
    app.router.add_get("/api/services", user_services_route)
    app.router.add_get("/api/services/{service_id}", user_service_route)
