"""Service-scoped credentials and auditable administrator resource operations."""

from aiohttp import web

from bot.app.web.admin_api_impl.auth import _require_admin_user_id
from bot.app.web.admin_api_impl.common import _error, _ok
from bot.app.web.context import get_panel_service, get_session_factory
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
from bot.app.web.service_delivery_schemas import (
    ExitAuditOut,
    ExitReclaimBody,
    ExitVerifyBody,
    ServiceDeliverBody,
    ServiceRevokeBody,
    ServiceSubscriptionOut,
)
from bot.app.web.service_routes import _pagination, _service_out
from bot.app.web.service_schemas import DedicatedExitOut, ServiceOrderOut, UserServiceOut
from bot.app.web.webapp.common import _require_user_id
from bot.services.service_delivery import service_subscription
from db.dal.service_delivery_dal import (
    list_exit_audit,
    record_exit_evidence,
    request_service_delivery,
    request_service_revocation,
)
from db.dal.user_services_dal import ServiceConflict


async def user_service_subscription_route(request: web.Request) -> web.Response:
    user_id = _require_user_id(request)
    service_id = request.match_info["service_id"]
    async with get_session_factory(request)() as session:
        try:
            url = await service_subscription(
                session, user_id=user_id, service_id=service_id, panel=get_panel_service(request)
            )
            response = _ok(
                {
                    "subscription": ServiceSubscriptionOut(
                        service_id=service_id, subscription_url=url
                    ).model_dump(mode="json")
                }
            )
        except ServiceConflict as exc:
            response = _error(exc.status, exc.code)
        # Retain fresh usage/anomalies even when they prevent credential delivery.
        await session.commit()
    response.headers.update(
        {
            "Cache-Control": "private, no-store",
            "Pragma": "no-cache",
            "Referrer-Policy": "no-referrer",
            "Vary": "Cookie, Authorization",
        }
    )
    return response


async def _exit_evidence(request: web.Request, action: str) -> web.Response:
    actor_id = _require_admin_user_id(request)
    body = await parse_body_or_400(
        request, ExitVerifyBody if action == "verify" else ExitReclaimBody
    )
    try:
        async with get_session_factory(request)() as session:
            resource, audit, duplicate = await record_exit_evidence(
                session,
                exit_id=request.match_info["exit_id"],
                actor_id=actor_id,
                action=action,
                command=body.model_dump(mode="json"),
            )
            response = _ok(
                {
                    "exit": DedicatedExitOut.from_orm_exit(resource).model_dump(mode="json"),
                    "audit": ExitAuditOut.from_orm_audit(audit).model_dump(mode="json"),
                    "duplicate": duplicate,
                }
            )
            await session.commit()
            return response
    except ServiceConflict as exc:
        return _error(exc.status, exc.code)


async def admin_exit_verify_route(request: web.Request) -> web.Response:
    return await _exit_evidence(request, "verify")


async def admin_exit_reclaim_route(request: web.Request) -> web.Response:
    return await _exit_evidence(request, "reclaim")


async def admin_exit_audit_route(request: web.Request) -> web.Response:
    _require_admin_user_id(request)
    limit, offset = _pagination(request)
    async with get_session_factory(request)() as session:
        rows, total = await list_exit_audit(
            session, request.match_info["exit_id"], limit=limit, offset=offset
        )
        return _ok(
            {
                "audit": [ExitAuditOut.from_orm_audit(row).model_dump(mode="json") for row in rows],
                "total": total,
            }
        )


async def admin_service_revoke_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    body = await parse_body_or_400(request, ServiceRevokeBody)
    try:
        async with get_session_factory(request)() as session:
            service, order, duplicate = await request_service_revocation(
                session,
                service_id=request.match_info["service_id"],
                actor_id=actor_id,
                **body.model_dump(),
            )
            response = _ok(
                {
                    "service": (await _service_out(session, service)).model_dump(mode="json"),
                    "order": ServiceOrderOut.from_orm_order(order).model_dump(mode="json"),
                    "duplicate": duplicate,
                }
            )
            await session.commit()
            return response
    except ServiceConflict as exc:
        return _error(exc.status, exc.code)


async def admin_service_deliver_route(request: web.Request) -> web.Response:
    actor_id = _require_admin_user_id(request)
    body = await parse_body_or_400(request, ServiceDeliverBody)
    try:
        async with get_session_factory(request)() as session:
            service, order, duplicate = await request_service_delivery(
                session,
                service_id=request.match_info["service_id"],
                actor_id=actor_id,
                **body.model_dump(),
            )
            response = _ok(
                {
                    "service": (await _service_out(session, service)).model_dump(mode="json"),
                    "order": ServiceOrderOut.from_orm_order(order).model_dump(mode="json"),
                    "duplicate": duplicate,
                }
            )
            await session.commit()
            return response
    except ServiceConflict as exc:
        return _error(exc.status, exc.code)


def setup_service_delivery_admin_routes(app: web.Application) -> None:
    for name, body in (
        ("admin_exit_verify_route", ExitVerifyBody),
        ("admin_exit_reclaim_route", ExitReclaimBody),
    ):
        register_contract(
            name,
            RouteContract(
                request_model=body,
                response_schema=ok_envelope_for(
                    DedicatedExitOut,
                    key="exit",
                    extra={"audit": schema_ref(ExitAuditOut), "duplicate": BOOLEAN_SCHEMA},
                ),
                models=(DedicatedExitOut, ExitAuditOut),
                security=ADMIN_SECURITY,
            ),
        )
    register_contract(
        "admin_exit_audit_route",
        RouteContract(
            response_schema=ok_envelope_for(
                ExitAuditOut, key="audit", many=True, extra={"total": INTEGER_SCHEMA}
            ),
            models=(ExitAuditOut,),
            security=ADMIN_SECURITY,
        ),
    )
    register_contract(
        "admin_service_revoke_route",
        RouteContract(
            request_model=ServiceRevokeBody,
            response_schema=ok_envelope_for(
                UserServiceOut,
                key="service",
                extra={"order": schema_ref(ServiceOrderOut), "duplicate": BOOLEAN_SCHEMA},
            ),
            models=(UserServiceOut, ServiceOrderOut),
            security=ADMIN_SECURITY,
        ),
    )
    app.router.add_post("/api/admin/dedicated-exits/{exit_id}/verify", admin_exit_verify_route)
    app.router.add_post("/api/admin/dedicated-exits/{exit_id}/reclaim", admin_exit_reclaim_route)
    app.router.add_get("/api/admin/dedicated-exits/{exit_id}/audit", admin_exit_audit_route)
    register_contract(
        "admin_service_deliver_route",
        RouteContract(
            request_model=ServiceDeliverBody,
            response_schema=ok_envelope_for(
                UserServiceOut,
                key="service",
                extra={"order": schema_ref(ServiceOrderOut), "duplicate": BOOLEAN_SCHEMA},
            ),
            models=(UserServiceOut, ServiceOrderOut),
            security=ADMIN_SECURITY,
        ),
    )
    app.router.add_post("/api/admin/services/{service_id}/deliver", admin_service_deliver_route)
    app.router.add_post("/api/admin/services/{service_id}/revoke", admin_service_revoke_route)


def setup_service_delivery_user_routes(app: web.Application) -> None:
    register_contract(
        "user_service_subscription_route",
        RouteContract(
            response_schema=ok_envelope_for(ServiceSubscriptionOut, key="subscription"),
            models=(ServiceSubscriptionOut,),
            security=USER_SECURITY,
        ),
    )
    app.router.add_get("/api/services/{service_id}/subscription", user_service_subscription_route)
