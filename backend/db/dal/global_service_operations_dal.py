"""One-statement, current-owner view of execution evidence and legacy orders."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import (
    Select,
    String,
    and_,
    cast,
    func,
    literal,
    or_,
    select,
    true,
    union_all,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from db.models import User
from db.service_models import (
    ServiceConnection,
    ServiceOperationExecution,
    ServiceOrder,
    UserService,
)


@dataclass(frozen=True)
class OperationFilters:
    status: str = "all"
    phase: str = "all"
    user_id: int | None = None
    service_id: str | None = None
    archived: str = "all"
    needs_attention: bool = False


@dataclass(frozen=True)
class OperationPosition:
    created_at: datetime
    record_type: Literal["execution", "order"]
    id: str


@dataclass(frozen=True)
class GlobalOperationRow:
    position: OperationPosition
    service: UserService
    service_name: str
    connection: ServiceConnection | None
    user: User | None
    order: ServiceOrder | None
    execution: ServiceOperationExecution | None
    needs_attention: bool
    last_success_at: datetime | None
    has_delivery_order: bool


def global_operations_statement(
    filters: OperationFilters, *, limit: int, after: OperationPosition | None = None
) -> Select:
    execution = ServiceOperationExecution
    order = ServiceOrder
    attention = or_(
        execution.status.in_(("failed", "unknown")),
        and_(execution.status == "pending", execution.error_code.is_not(None)),
    )
    records = union_all(
        select(
            execution.id.label("id"),
            execution.service_id.label("service_id"),
            execution.order_id.label("order_id"),
            execution.created_at.label("created_at"),
            literal("execution").label("record_type"),
            execution.status.label("status"),
            execution.phase.label("phase"),
            attention.label("needs_attention"),
        ),
        select(
            order.id,
            order.service_id,
            order.id,
            order.created_at,
            literal("order"),
            literal("unknown"),
            cast(literal(None), String(16)),
            literal(False),
        ).where(
            order.kind != "retry",
            ~select(execution.id).where(execution.order_id == order.id).exists(),
        ),
    ).subquery("operation_records")
    filtered_query = select(records).join(UserService, UserService.id == records.c.service_id)
    if filters.status != "all":
        filtered_query = filtered_query.where(records.c.status == filters.status)
    if filters.phase != "all":
        filtered_query = filtered_query.where(records.c.phase == filters.phase)
    if filters.user_id is not None:
        filtered_query = filtered_query.where(UserService.user_id == filters.user_id)
    if filters.service_id is not None:
        filtered_query = filtered_query.where(records.c.service_id == filters.service_id)
    if filters.archived != "all":
        filtered_query = filtered_query.where(
            UserService.user_id.is_(None)
            if filters.archived == "only"
            else UserService.user_id.is_not(None)
        )
    if filters.needs_attention:
        filtered_query = filtered_query.where(records.c.needs_attention.is_(True))
    filtered = filtered_query.cte("filtered_operations")
    totals = select(func.count().label("total")).select_from(filtered).cte("operation_total")
    page_query = select(filtered)
    if after is not None:
        page_query = page_query.where(
            or_(
                filtered.c.created_at < after.created_at,
                and_(
                    filtered.c.created_at == after.created_at,
                    or_(
                        filtered.c.record_type > after.record_type,
                        and_(filtered.c.record_type == after.record_type, filtered.c.id > after.id),
                    ),
                ),
            )
        )
    page = (
        page_query.order_by(filtered.c.created_at.desc(), filtered.c.record_type, filtered.c.id)
        .limit(limit + 1)
        .cte("operation_page")
    )
    pairs = select(page.c.service_id, page.c.phase).distinct().cte("page_phases")
    successes = (
        select(
            execution.service_id,
            execution.phase,
            func.max(execution.completed_at).label("last_success_at"),
        )
        .join(
            pairs,
            and_(pairs.c.service_id == execution.service_id, pairs.c.phase == execution.phase),
        )
        .where(execution.status == "succeeded")
        .group_by(execution.service_id, execution.phase)
        .cte("phase_successes")
    )
    delivery_order = (
        select(order.id)
        .where(order.service_id == UserService.id, order.kind == "deliver")
        .correlate(UserService)
        .exists()
    )
    # The total anchors an empty page too; all enrichment shares the statement's snapshot.
    return (
        select(
            totals.c.total,
            page.c.id,
            page.c.created_at,
            page.c.record_type,
            page.c.needs_attention,
            UserService,
            UserService.terms["name"].as_string().label("service_name"),
            ServiceConnection,
            User,
            order,
            execution,
            successes.c.last_success_at,
            delivery_order.label("has_delivery_order"),
        )
        .select_from(totals)
        .outerjoin(page, true())
        .outerjoin(UserService, UserService.id == page.c.service_id)
        .outerjoin(ServiceConnection, ServiceConnection.service_id == UserService.id)
        .outerjoin(User, User.user_id == UserService.user_id)
        .outerjoin(order, order.id == page.c.order_id)
        .outerjoin(execution, and_(page.c.record_type == "execution", execution.id == page.c.id))
        .outerjoin(
            successes,
            and_(successes.c.service_id == page.c.service_id, successes.c.phase == page.c.phase),
        )
        .options(
            load_only(
                UserService.id,
                UserService.user_id,
                UserService.revision,
                UserService.expires_at,
                UserService.used_bytes,
                UserService.quota_bytes,
                UserService.desired_status,
                raiseload=True,
            ),
            load_only(
                ServiceConnection.service_id,
                ServiceConnection.state,
                ServiceConnection.usage_error,
                ServiceConnection.revoke_requested_at,
                ServiceConnection.panel_user_uuid,
                ServiceConnection.sync_pending,
                ServiceConnection.replacement_order_id,
                raiseload=True,
            ),
            load_only(
                User.user_id,
                User.minishop_id,
                User.username,
                User.email,
                User.first_name,
                User.last_name,
                User.is_banned,
                raiseload=True,
            ),
            load_only(
                order.id,
                order.service_id,
                order.kind,
                order.actor_id,
                order.created_at,
                raiseload=True,
            ),
        )
        .order_by(page.c.created_at.desc(), page.c.record_type, page.c.id)
        .execution_options(populate_existing=True)
    )


async def list_global_operation_records(
    session: AsyncSession,
    filters: OperationFilters,
    *,
    limit: int,
    after: OperationPosition | None = None,
) -> tuple[list[GlobalOperationRow], int, bool]:
    statement = global_operations_statement(filters, limit=limit, after=after)
    with session.no_autoflush:
        rows = (await session.execute(statement)).all()
    total = int(rows[0].total)
    records: list[GlobalOperationRow] = []
    for row in rows:
        if row.id is None:
            continue
        records.append(
            GlobalOperationRow(
                position=OperationPosition(row.created_at, row.record_type, row.id),
                service=row.UserService,
                service_name=row.service_name or "",
                connection=row.ServiceConnection,
                user=row.User,
                order=row.ServiceOrder,
                execution=row.ServiceOperationExecution,
                needs_attention=bool(row.needs_attention),
                last_success_at=row.last_success_at,
                has_delivery_order=bool(row.has_delivery_order),
            )
        )
    return records[:limit], total, len(records) > limit
