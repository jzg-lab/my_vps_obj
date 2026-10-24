"""Execution evidence is separate from immutable business orders and current rights."""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.service_operation_errors import CONFIRMED_SERVICE_FAILURES, safe_service_error
from config.service_exit_replacement import ReplacementProgress
from config.service_periods import as_utc
from db.dal.user_dal import lock_user_by_id
from db.dal.user_services_dal import ServiceConflict
from db.models import User
from db.service_models import (
    ServiceConnection,
    ServiceOperationExecution,
    ServiceOrder,
    UserService,
)

OPEN_STATUSES = ("pending", "unknown", "failed")


async def supersede_executions(session: AsyncSession, service: UserService) -> None:
    rows = await session.scalars(
        select(ServiceOperationExecution).where(
            ServiceOperationExecution.service_id == service.id,
            ServiceOperationExecution.status.in_(OPEN_STATUSES),
            ServiceOperationExecution.phase != "exit_replace",
            or_(
                ServiceOperationExecution.target_revision != service.revision,
                ServiceOperationExecution.request_owner_id != service.user_id,
            ),
        )
    )
    for row in rows:
        row.status = "superseded"
        row.completed_at = datetime.now(UTC)
        row.error_code = row.error_code or (
            "service_revision_changed"
            if row.target_revision != service.revision
            else "idempotency_owner_changed"
        )


async def enqueue_execution(
    session: AsyncSession,
    service: UserService,
    phase: str,
    *,
    order: ServiceOrder | None = None,
    source: str = "worker",
) -> ServiceOperationExecution:
    if phase == "exit_replace":
        raise ServiceConflict("exit_replacement_in_progress")
    assert service.user_id is not None
    if order is not None:
        # Scalar foreign keys do not order pending ORM inserts without relationships.
        await session.flush()
    await supersede_executions(session, service)
    row = ServiceOperationExecution(
        id=uuid4().hex,
        service_id=service.id,
        order_id=order.id if order else None,
        request_owner_id=service.user_id,
        phase=phase,
        target_revision=service.revision,
        source=source,
        actor_id=order.actor_id if order else None,
        status="pending",
        attempt_count=0,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    await session.flush()
    return row


async def _open_executions(
    session: AsyncSession, service: UserService, phase: str
) -> list[ServiceOperationExecution]:
    if phase == "exit_replace":
        raise ServiceConflict("exit_replacement_in_progress")
    await supersede_executions(session, service)
    return list(
        await session.scalars(
            select(ServiceOperationExecution).where(
                ServiceOperationExecution.service_id == service.id,
                ServiceOperationExecution.target_revision == service.revision,
                ServiceOperationExecution.request_owner_id == service.user_id,
                ServiceOperationExecution.phase == phase,
                ServiceOperationExecution.status.in_(OPEN_STATUSES),
            )
        )
    )


async def begin_execution(
    session: AsyncSession, service: UserService, phase: str, *, create: bool = False
) -> None:
    """Run after local guards; commit before remote calls and reacquire the account lock."""
    rows = await _open_executions(session, service, phase)
    if not rows and create:
        rows = [await enqueue_execution(session, service, phase)]
    for row in rows:
        row.status = "unknown"
        row.attempted_at = datetime.now(UTC)
        row.attempt_count += 1


async def finish_execution(
    session: AsyncSession,
    service: UserService,
    phase: str,
    *,
    success: bool,
    error: str | None = None,
    enabling_error: str | None = None,
    capture_failure: bool = True,
    attempted_at: datetime | None = None,
) -> None:
    """New automatic faults use the call's start time; local guards never invent a call."""
    rows = await _open_executions(session, service, phase)
    if not rows and not success and error is not None and capture_failure:
        rows = [await enqueue_execution(session, service, phase)]
    for row in rows:
        now = datetime.now(UTC)
        if row.attempted_at is None and attempted_at is not None:
            row.attempted_at = attempted_at
            row.attempt_count += 1
        row_error = (
            enabling_error
            if row.source == "administrator" and enabling_error and (success or error is None)
            else error
        )
        row_success = success and not (row.source == "administrator" and enabling_error)
        row.error_code = None if row_success else safe_service_error(row_error)
        if row_success:
            row.status = "succeeded"
            row.completed_at = now
        elif row_error in CONFIRMED_SERVICE_FAILURES:
            row.status = "failed"
            if row.first_failed_at is None:
                row.first_failed_at = now
        else:
            row.status = "unknown" if row.attempted_at is not None else "pending"


def retry_block_reason(
    service: UserService,
    connection: ServiceConnection | None,
    user: User | None,
    operation: ServiceOperationExecution,
) -> str | None:
    if operation.phase == "exit_replace":
        try:
            progress = ReplacementProgress.model_validate(operation.replacement_progress)
        except ValidationError:
            return "exit_replacement_state_invalid"
        if progress.pending_action is not None:
            return "exit_replacement_write_unknown"
        if (
            connection is None
            or connection.replacement_order_id != operation.order_id
            or progress.stage in {"completed", "closed"}
        ):
            return "operation_not_retryable"
        return None
    if connection is not None and connection.replacement_order_id is not None:
        return "exit_replacement_in_progress"
    if (
        service.user_id is None
        or user is None
        or connection is None
        or connection.state == "revoked"
    ):
        return "service_not_editable"
    if operation.request_owner_id != service.user_id:
        return "idempotency_owner_changed"
    if operation.target_revision != service.revision:
        return "service_revision_changed"
    if operation.status not in OPEN_STATUSES:
        return "operation_not_retryable"
    if connection.usage_error in {"panel_usage_reset", "panel_usage_regressed"}:
        return "usage_reconciliation_required"
    enabling = operation.phase in {"prepare", "delivery"} or (
        operation.phase == "entitlement" and service.desired_status == "active"
    )
    if enabling:
        if user.is_banned:
            return "account_banned"
        if as_utc(service.expires_at) <= datetime.now(UTC):
            return "service_expired"
        if service.used_bytes >= service.quota_bytes:
            return "service_exhausted"
        if service.desired_status != "active" or connection.revoke_requested_at is not None:
            return "service_not_editable"
    if operation.phase == "prepare":
        return (
            None
            if connection.state in {"pending", "error"} and connection.revoke_requested_at is None
            else "operation_not_retryable"
        )
    if operation.phase == "delivery":
        return (
            None
            if connection.state == "pending"
            or (connection.state == "ready" and connection.sync_pending)
            else "operation_not_retryable"
        )
    if operation.phase == "revocation":
        return (
            None
            if service.desired_status == "cancelled" and connection.revoke_requested_at is not None
            else "operation_not_retryable"
        )
    if operation.phase == "entitlement":
        return (
            None
            if connection.panel_user_uuid
            and service.desired_status != "cancelled"
            and connection.sync_pending
            else "operation_not_retryable"
        )
    return (
        None if connection.panel_user_uuid and connection.usage_error else "operation_not_retryable"
    )


async def retry_execution(
    session: AsyncSession,
    *,
    service_id: str,
    operation_id: str,
    user_id: int,
    actor_id: int,
    expected_revision: int,
    idempotency_key: str,
) -> tuple[ServiceOperationExecution, ServiceOrder, bool]:
    from db.dal.resource_operations_dal import coordinate_resources

    await coordinate_resources(session)
    user = await lock_user_by_id(session, user_id)
    service = await session.get(UserService, service_id, populate_existing=True)
    if user is None or service is None or service.user_id != user_id:
        raise ServiceConflict("service_not_found", 404)
    operation = await session.get(ServiceOperationExecution, operation_id, populate_existing=True)
    if operation is None or operation.service_id != service_id:
        raise ServiceConflict("operation_not_found", 404)
    command: dict[str, object] = {
        "service_id": service_id,
        "operation_id": operation_id,
        "expected_revision": expected_revision,
    }
    previous = await session.scalar(
        select(ServiceOrder).where(
            ServiceOrder.request_owner_id == user_id,
            ServiceOrder.idempotency_key == idempotency_key,
        )
    )
    if previous is not None:
        if previous.kind != "retry" or previous.request != command:
            raise ServiceConflict("idempotency_conflict")
        if operation.request_owner_id != user_id:
            raise ServiceConflict("idempotency_owner_changed")
        return operation, previous, True
    if service.revision != expected_revision:
        raise ServiceConflict("service_revision_changed")
    if operation.phase == "exit_replace":
        from db.dal.service_exit_replacement_completion_dal import retry_replacement
        from db.dal.service_exit_replacement_dal import lock_replacement

        state = await lock_replacement(
            session, service_id=service_id, user_id=user_id, operation_id=operation_id
        )
        order, duplicate = await retry_replacement(
            session,
            state,
            actor_id=actor_id,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
        )
        return state.execution, order, duplicate
    connection = await session.get(ServiceConnection, service_id, populate_existing=True)
    blocked = retry_block_reason(service, connection, user, operation)
    if blocked:
        raise ServiceConflict(blocked)
    assert connection is not None
    if operation.phase == "delivery" and not await session.scalar(
        select(ServiceOrder.id)
        .where(
            ServiceOrder.service_id == service_id,
            ServiceOrder.kind == "deliver",
        )
        .limit(1)
    ):
        raise ServiceConflict("operation_not_retryable")
    if operation.phase in {"entitlement", "delivery", "revocation"}:
        connection.sync_pending = True
    if operation.status != "unknown":
        operation.status = "pending"
    order = ServiceOrder(
        id=uuid4().hex,
        user_id=user_id,
        request_owner_id=user_id,
        service_id=service_id,
        actor_id=actor_id,
        kind="retry",
        idempotency_key=idempotency_key,
        request=command,
        snapshot={
            "operation_id": operation_id,
            "phase": operation.phase,
            "revision": service.revision,
        },
        created_at=datetime.now(UTC),
    )
    session.add(order)
    await session.flush()
    return operation, order, False


async def list_operation_records(
    session: AsyncSession,
    service_id: str,
    *,
    limit: int,
    offset: int,
) -> tuple[list[tuple[ServiceOrder | None, ServiceOperationExecution | None]], int]:
    executions = select(
        ServiceOperationExecution.id.label("id"),
        ServiceOperationExecution.created_at.label("created_at"),
        literal("execution").label("record_type"),
    ).where(ServiceOperationExecution.service_id == service_id)
    legacy = select(
        ServiceOrder.id.label("id"),
        ServiceOrder.created_at.label("created_at"),
        literal("order").label("record_type"),
    ).where(
        ServiceOrder.service_id == service_id,
        ServiceOrder.kind != "retry",
        ~select(ServiceOperationExecution.id)
        .where(ServiceOperationExecution.order_id == ServiceOrder.id)
        .exists(),
    )
    records = union_all(executions, legacy).subquery()
    total = int(await session.scalar(select(func.count()).select_from(records)) or 0)
    page = (
        await session.execute(
            select(records)
            .order_by(records.c.created_at.desc(), records.c.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    if not page:
        return [], total
    rows = list(
        await session.scalars(
            select(ServiceOperationExecution).where(
                ServiceOperationExecution.id.in_(
                    [row.id for row in page if row.record_type == "execution"]
                )
            )
        )
    )
    by_id = {row.id: row for row in rows}
    orders = list(
        await session.scalars(
            select(ServiceOrder).where(
                ServiceOrder.id.in_(
                    [row.id for row in page if row.record_type == "order"]
                    + [row.order_id for row in rows if row.order_id]
                )
            )
        )
    )
    by_order = {row.id: row for row in orders}
    result = []
    for item in page:
        execution = by_id.get(item.id) if item.record_type == "execution" else None
        order = (
            by_order.get(execution.order_id)
            if execution and execution.order_id
            else by_order.get(item.id)
        )
        result.append((order, execution))
    return result, total
