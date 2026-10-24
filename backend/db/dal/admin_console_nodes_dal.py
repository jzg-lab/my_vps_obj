"""Read service scope without provisioning identities or changing entitlements."""

from contextlib import suppress
from dataclasses import dataclass, field
from typing import cast
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import and_, false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from config.service_exit_replacement import ReplacementRequest
from config.service_plans import ServicePlanTerms
from db.models import User
from db.service_models import (
    DedicatedExit,
    ServiceConnection,
    ServiceOperationExecution,
    ServiceOrder,
    UserService,
)

type ServiceResourceRow = tuple[UserService, ServiceConnection | None, DedicatedExit | None, User]


@dataclass
class ReplacementImpact:
    """Potential resource impact, never a grant of customer authorization."""

    service_id: str | None
    customer_id: int | None
    group_ids: set[str] = field(default_factory=set)
    blockers: set[str] = field(default_factory=set)
    unknown_scope: bool = False

    def affects(self, group_ids: set[str]) -> bool:
        return self.unknown_scope or bool(self.group_ids & group_ids)


class ServiceResourceRows(list[ServiceResourceRow]):
    """Keep the current-binding rows while carrying separate replacement impacts."""

    def __init__(
        self, rows: list[ServiceResourceRow], replacement_impacts: list[ReplacementImpact]
    ) -> None:
        super().__init__(rows)
        self.replacement_impacts = replacement_impacts


def replacement_impacts(rows: list[ServiceResourceRow]) -> list[ReplacementImpact]:
    if isinstance(rows, ServiceResourceRows):
        return rows.replacement_impacts
    # A caller supplying only current bindings has not resolved an active gate.
    return [
        ReplacementImpact(
            service.id,
            cast(int, user.user_id),
            blockers={"replacement_scope_unconfirmed"},
            unknown_scope=True,
        )
        for service, connection, _, user in rows
        if connection is not None and connection.replacement_order_id is not None
    ]


def service_group_ids(service: UserService, resource: DedicatedExit | None) -> set[str]:
    terms = ServicePlanTerms.model_validate(service.terms)
    if terms.resource_type == "shared":
        return {str(value) for value in terms.squad_uuids}
    if (
        resource is not None
        and resource.service_id == service.id
        and resource.hold_order_id is None
        and resource.enabled
        and resource.verified_at is not None
        and resource.resource_pool == terms.resource_pool
    ):
        return {resource.squad_uuid.lower()}
    return set()


def _add_exit_scope(impact: ReplacementImpact, resource: DedicatedExit | None) -> None:
    try:
        if resource is None or not isinstance(resource.squad_uuid, str):
            raise ValueError("missing_exit")
        impact.group_ids.add(str(UUID(resource.squad_uuid)))
    except ValueError:
        impact.unknown_scope = True
        impact.blockers.add("replacement_scope_unconfirmed")


async def _read_replacement_impacts(
    session: AsyncSession,
    services: dict[str, tuple[UserService, ServiceConnection | None, User | None]],
    *,
    service_id: str | None,
) -> list[ReplacementImpact]:
    # Three batch reads in total, independent of service/hold count; no ORM lazy loads.
    gates = {
        identity: connection.replacement_order_id
        for identity, (_, connection, _) in services.items()
        if connection is not None and connection.replacement_order_id is not None
    }
    held_orders = select(DedicatedExit.hold_order_id).where(
        DedicatedExit.hold_order_id.is_not(None)
    )
    if service_id is not None:
        held_orders = held_orders.join(
            ServiceOrder, ServiceOrder.id == DedicatedExit.hold_order_id
        ).where(ServiceOrder.service_id == service_id)
    query = (
        select(ServiceOrder, ServiceOperationExecution)
        .outerjoin(
            ServiceOperationExecution,
            ServiceOperationExecution.order_id == ServiceOrder.id,
            full=True,
        )
        .where(
            or_(
                ServiceOrder.id.in_(gates.values()),
                ServiceOrder.id.in_(held_orders),
                and_(
                    ServiceOperationExecution.phase == "exit_replace",
                    ServiceOperationExecution.status.in_(("pending", "unknown", "failed")),
                ),
            )
        )
    )
    if service_id is not None:
        query = query.where(
            or_(
                ServiceOrder.service_id == service_id,
                ServiceOperationExecution.service_id == service_id,
                ServiceOrder.id.in_(gates.values()),
            )
        )
    records = list(await session.execute(query))
    orders = {order.id: (order, execution) for order, execution in records if order is not None}
    requests: dict[str, ReplacementRequest] = {}
    for order_id, (order, _) in orders.items():
        with suppress(ValidationError):
            requests[order_id] = ReplacementRequest.model_validate(
                order.request.get("replacement") if isinstance(order.request, dict) else None
            )
    referenced_exits = {
        exit_id
        for request in requests.values()
        for exit_id in (request.old_exit_id, request.new_exit_id)
    }
    exit_query = select(DedicatedExit).where(
        or_(
            DedicatedExit.hold_order_id.is_not(None)
            if service_id is None
            else DedicatedExit.hold_order_id.in_(orders),
            DedicatedExit.id.in_(referenced_exits),
            DedicatedExit.service_id == service_id if service_id is not None else false(),
        )
    )
    exits = {resource.id: resource for resource in await session.scalars(exit_query)}
    held = [resource for resource in exits.values() if resource.hold_order_id is not None]
    impacts: list[ReplacementImpact] = []

    def impact_for(service_id: str | None) -> ReplacementImpact:
        entry = services.get(service_id) if service_id is not None else None
        user = entry[2] if entry else None
        impact = ReplacementImpact(
            service_id if entry else None, cast(int, user.user_id) if user else None
        )
        if entry is None:
            impact.blockers.add("replacement_service_unconfirmed")
        elif user is None:
            impact.blockers.add("replacement_customer_unavailable")
        return impact

    for resource in held:
        record = orders.get(resource.hold_order_id)
        order, execution = record if record else (None, None)
        impact = impact_for(order.service_id if order else resource.service_id)
        impact.blockers.add("replacement_resource_held")
        _add_exit_scope(impact, resource)
        if (
            order is None
            or order.kind != "replace_exit"
            or execution is None
            or execution.phase != "exit_replace"
            or execution.service_id != order.service_id
            or resource.service_id is not None
        ):
            impact.blockers.add("replacement_state_invalid")
        else:
            request = requests.get(order.id)
            if request is None or resource.id not in (request.old_exit_id, request.new_exit_id):
                impact.blockers.add("replacement_state_invalid")
        impacts.append(impact)
        if resource.service_id is not None and resource.service_id != impact.service_id:
            bound = impact_for(resource.service_id)
            bound.group_ids.update(impact.group_ids)
            bound.unknown_scope = impact.unknown_scope
            bound.blockers = impact.blockers | {"replacement_state_invalid"}
            impacts.append(bound)

    active = set(gates.items())
    active.update(
        (execution.service_id, order.id)
        for order, execution in orders.values()
        if execution is not None
        and execution.phase == "exit_replace"
        and execution.status in {"pending", "unknown", "failed"}
    )
    for service_id, order_id in sorted(active):
        impact = impact_for(service_id)
        impact.blockers.add("exit_replacement_in_progress")
        entry = services.get(service_id)
        if entry is None or gates.get(service_id) != order_id:
            impact.blockers.add("replacement_state_invalid")
        record = orders.get(order_id)
        order, execution = record if record else (None, None)
        if (
            order is None
            or order.service_id != service_id
            or order.kind != "replace_exit"
            or execution is None
            or execution.service_id != service_id
            or execution.phase != "exit_replace"
        ):
            impact.unknown_scope = True
            impact.blockers.add("replacement_state_invalid")
        else:
            request = requests.get(order.id)
            if request is not None:
                for exit_id in (request.old_exit_id, request.new_exit_id):
                    _add_exit_scope(impact, exits.get(exit_id))
            else:
                impact.unknown_scope = True
                impact.blockers.add("replacement_scope_unconfirmed")
        impacts.append(impact)
    for order, execution in records:
        if order is None and execution is not None:
            impact = impact_for(execution.service_id)
            impact.unknown_scope = True
            impact.blockers.add("replacement_state_invalid")
            impacts.append(impact)
    return impacts


async def read_service_resources(
    session: AsyncSession,
    *,
    service_id: str | None = None,
    group_ids: set[str] | None = None,
) -> ServiceResourceRows:
    query = (
        select(UserService, ServiceConnection, DedicatedExit, User)
        .outerjoin(User, User.user_id == UserService.user_id)
        .outerjoin(ServiceConnection, ServiceConnection.service_id == UserService.id)
        .outerjoin(DedicatedExit, DedicatedExit.service_id == UserService.id)
        .order_by(UserService.created_at.desc(), UserService.id)
    )
    if service_id is not None:
        query = query.where(UserService.id == service_id)
    rows = list(await session.execute(query))
    impacts = await _read_replacement_impacts(
        session,
        {service.id: (service, connection, user) for service, connection, _, user in rows},
        service_id=service_id,
    )
    if service_id is not None:
        impacts = [impact for impact in impacts if impact.service_id == service_id]
    if group_ids is not None:
        impacts = [impact for impact in impacts if impact.affects(group_ids)]
    replacement_ids = {impact.service_id for impact in impacts}
    # shortcut: scope lives in JSON; index relations when service volume makes scans costly.
    matched = [
        (service, connection, resource, user)
        for service, connection, resource, user in rows
        if user is not None
        and (service_id is None or service.id == service_id)
        and (
            group_ids is None
            or service.id in replacement_ids
            or (
                (connection is None or connection.state != "revoked")
                and service_group_ids(service, resource) & group_ids
            )
        )
    ]
    return ServiceResourceRows(matched, impacts)
