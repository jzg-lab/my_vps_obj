"""Transactional plan editing and manual activation; panel delivery is separate work."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config.service_periods import as_utc, monthly_period
from config.service_plans import ServicePlanTerms
from db.service_models import (
    DedicatedExit,
    ServiceConnection,
    ServiceOrder,
    ServicePlan,
    UserService,
)


class ServiceConflict(ValueError):
    code: str
    status: int

    def __init__(self, code: str, status: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


async def save_plan(
    session: AsyncSession,
    *,
    terms: ServicePlanTerms,
    enabled: bool,
    actor_id: int,
    plan_id: str | None = None,
    expected_revision: int | None = None,
) -> ServicePlan:
    now = datetime.now(UTC)
    if plan_id is None:
        plan = ServicePlan(id=uuid4().hex, revision=1, created_at=now)
        session.add(plan)
    else:
        found = await session.scalar(
            select(ServicePlan).where(ServicePlan.id == plan_id).with_for_update()
        )
        if found is None:
            raise ServiceConflict("plan_not_found", 404)
        plan = found
        if expected_revision != plan.revision:
            raise ServiceConflict("plan_revision_changed")
        plan.revision += 1
    plan.terms = terms.model_dump(mode="json")
    plan.enabled = enabled
    plan.updated_by = actor_id
    plan.updated_at = now
    await session.flush()
    return plan


async def activate_service(
    session: AsyncSession,
    *,
    user_id: int,
    actor_id: int,
    plan_id: str,
    expected_revision: int,
    idempotency_key: str,
    exit_id: str | None = None,
    now: datetime | None = None,
) -> tuple[UserService, ServiceOrder, bool]:
    now = as_utc(now or datetime.now(UTC))
    from .user_dal import lock_user_by_id

    # Serialize activation/replays with bans and account merges on the same owner row.
    user = await lock_user_by_id(session, user_id)
    if user is None:
        raise ServiceConflict("user_not_found", 404)
    if user.is_banned:
        raise ServiceConflict("account_banned", 403)
    command: dict[str, object] = {
        "plan_id": plan_id,
        "expected_revision": expected_revision,
        "exit_id": exit_id,
    }
    previous = await session.scalar(
        select(ServiceOrder).where(
            ServiceOrder.request_owner_id == user_id,
            ServiceOrder.idempotency_key == idempotency_key,
        )
    )
    if previous is not None:
        if previous.kind != "activate" or previous.request != command:
            raise ServiceConflict("idempotency_conflict")
        service = await session.get(UserService, previous.service_id)
        if service is None or service.user_id != user_id:
            raise ServiceConflict("idempotency_owner_changed")
        return service, previous, True
    plan = await session.scalar(
        select(ServicePlan).where(ServicePlan.id == plan_id).with_for_update()
    )
    if plan is None:
        raise ServiceConflict("plan_not_found", 404)
    if not plan.enabled:
        raise ServiceConflict("plan_disabled")
    if plan.revision != expected_revision:
        raise ServiceConflict("plan_revision_changed")
    terms = ServicePlanTerms.model_validate(plan.terms)
    resource: DedicatedExit | None = None
    if terms.resource_type == "dedicated":
        if exit_id is None:
            raise ServiceConflict("dedicated_exit_required", 400)
        resource = await session.scalar(
            select(DedicatedExit).where(DedicatedExit.id == exit_id).with_for_update()
        )
        if resource is None:
            raise ServiceConflict("exit_not_found", 404)
        if (
            not resource.enabled
            or resource.service_id is not None
            or resource.resource_pool != terms.resource_pool
        ):
            raise ServiceConflict("exit_unavailable")
    elif exit_id is not None:
        raise ServiceConflict("shared_plan_cannot_bind_exit", 400)
    period = monthly_period(now, now) if terms.traffic_rule == "monthly" else None
    service = UserService(
        id=uuid4().hex,
        user_id=user_id,
        plan_id=plan.id,
        plan_revision=plan.revision,
        terms=terms.model_dump(mode="json"),
        quota_bytes=terms.quota_bytes,
        used_bytes=0,
        starts_at=now,
        expires_at=now + timedelta(days=terms.validity_days),
        cycle_started_at=period[0] if period else None,
        cycle_ends_at=period[1] if period else None,
        desired_status="active",
        created_at=now,
    )
    session.add(service)
    await session.flush()
    if resource is not None:
        resource.service_id = service.id
    session.add(
        ServiceConnection(service_id=service.id, username=f"svc_{service.id}", state="pending")
    )
    order = ServiceOrder(
        id=uuid4().hex,
        user_id=user_id,
        request_owner_id=user_id,
        service_id=service.id,
        actor_id=actor_id,
        kind="activate",
        idempotency_key=idempotency_key,
        request=command,
        snapshot={
            "terms": terms.model_dump(mode="json"),
            "plan_id": plan.id,
            "plan_revision": plan.revision,
            "starts_at": service.starts_at.isoformat(),
            "expires_at": service.expires_at.isoformat(),
            "exit_id": exit_id,
            "fulfillment": "manual",
        },
        created_at=now,
    )
    session.add(order)
    await session.flush()
    return service, order, False


async def list_plans(
    session: AsyncSession, *, limit: int, offset: int, enabled_only: bool = False
) -> tuple[list[ServicePlan], int]:
    filters = [ServicePlan.enabled.is_(True)] if enabled_only else []
    total = int(
        await session.scalar(select(func.count()).select_from(ServicePlan).where(*filters)) or 0
    )
    rows = await session.scalars(
        select(ServicePlan)
        .where(*filters)
        .order_by(ServicePlan.created_at.desc(), ServicePlan.id)
        .limit(limit)
        .offset(offset)
    )
    return list(rows), total


async def list_services(
    session: AsyncSession, *, user_id: int | None, limit: int, offset: int
) -> tuple[list[tuple[UserService, ServiceConnection | None, DedicatedExit | None]], int]:
    total = int(
        await session.scalar(
            select(func.count()).select_from(UserService).where(UserService.user_id == user_id)
        )
        or 0
    )
    rows = await session.execute(
        select(UserService, ServiceConnection, DedicatedExit)
        .outerjoin(ServiceConnection, ServiceConnection.service_id == UserService.id)
        .outerjoin(DedicatedExit, DedicatedExit.service_id == UserService.id)
        .where(UserService.user_id == user_id)
        .order_by(UserService.created_at.desc(), UserService.id)
        .limit(limit)
        .offset(offset)
    )
    return [(service, connection, resource) for service, connection, resource in rows], total


async def get_service(
    session: AsyncSession, service_id: str, *, user_id: int
) -> UserService | None:
    return await session.scalar(
        select(UserService).where(UserService.id == service_id, UserService.user_id == user_id)
    )


async def get_service_resource(
    session: AsyncSession, service_id: str
) -> tuple[ServiceConnection | None, DedicatedExit | None]:
    connection = await session.get(ServiceConnection, service_id)
    resource = await session.scalar(
        select(DedicatedExit).where(DedicatedExit.service_id == service_id)
    )
    return connection, resource


async def list_orders(
    session: AsyncSession, *, user_id: int | None, limit: int, offset: int
) -> tuple[list[ServiceOrder], int]:
    total = int(
        await session.scalar(
            select(func.count()).select_from(ServiceOrder).where(ServiceOrder.user_id == user_id)
        )
        or 0
    )
    rows = await session.scalars(
        select(ServiceOrder)
        .where(ServiceOrder.user_id == user_id)
        .order_by(ServiceOrder.created_at.desc(), ServiceOrder.id)
        .limit(limit)
        .offset(offset)
    )
    return list(rows), total


async def list_exits(
    session: AsyncSession, *, limit: int, offset: int
) -> tuple[list[DedicatedExit], int]:
    total = int(await session.scalar(select(func.count()).select_from(DedicatedExit)) or 0)
    rows = await session.scalars(
        select(DedicatedExit)
        .order_by(DedicatedExit.created_at, DedicatedExit.id)
        .limit(limit)
        .offset(offset)
    )
    return list(rows), total


async def create_exit(
    session: AsyncSession, *, label: str, ip_address: str, resource_pool: str, squad_uuid: str
) -> DedicatedExit:
    resource = DedicatedExit(
        id=uuid4().hex,
        label=label,
        ip_address=ip_address,
        resource_pool=resource_pool,
        squad_uuid=squad_uuid,
        enabled=True,
        created_at=datetime.now(UTC),
    )
    session.add(resource)
    await session.flush()
    return resource
