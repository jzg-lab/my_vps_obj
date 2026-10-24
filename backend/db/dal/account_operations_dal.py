"""Account-row-locked audit updates; retries keep the original actor and intent."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from db.account_operation_models import AccountOperation
from db.models import User
from db.service_models import AccountAccessSync

OPEN_STATUSES = ("pending", "unknown", "failed")
BLOCKED_ERRORS = frozenset(
    {
        "panel_service_unavailable",
        "service_connection_unconfirmed",
        "service_change_pending",
        "exit_replacement_in_progress",
        "resource_operation_in_progress",
    }
)
SAFE_ERRORS = BLOCKED_ERRORS | {"panel_access_unconfirmed", "account_sync_unconfirmed"}


def safe_account_error(error: str | None) -> str | None:
    return error if error is None or error in SAFE_ERRORS else "account_sync_unconfirmed"


async def record_account_intent(
    session: AsyncSession,
    user: User,
    job: AccountAccessSync,
    *,
    actor_id: int | None = None,
    before_banned: bool | None = None,
) -> AccountOperation:
    """Caller holds the account lock and commits this with the business intent."""
    current = await session.get(AccountOperation, job.operation_id) if job.operation_id else None
    desired = bool(user.is_banned)
    if current and current.user_id == user.user_id and current.status in OPEN_STATUSES:
        if current.desired_banned == desired and (
            actor_id is None
            or (
                current.source == "administrator"
                and current.actor_id == actor_id
                and before_banned == desired
            )
        ):
            return current
        current.status = "superseded"
        current.completed_at = datetime.now(UTC)
    operation = AccountOperation(
        id=uuid4().hex,
        user_id=user.user_id,
        target_id=user.user_id,
        actor_id=actor_id,
        before_banned=before_banned,
        desired_banned=desired,
        source="administrator" if actor_id is not None else "worker",
        status="pending",
        attempt_count=0,
        created_at=datetime.now(UTC),
    )
    session.add(operation)
    await session.flush()
    job.operation_id = operation.id
    await session.flush()
    return operation


async def begin_account_attempt(
    session: AsyncSession, user: User, job: AccountAccessSync
) -> tuple[str, int]:
    operation = await record_account_intent(session, user, job)
    operation.status = "unknown"
    operation.attempt_count += 1
    operation.attempted_at = datetime.now(UTC)
    await session.flush()
    return operation.id, operation.attempt_count


async def current_account_attempt(
    session: AsyncSession,
    user: User,
    job: AccountAccessSync,
    attempt: tuple[str, int],
) -> AccountOperation | None:
    operation_id, count = attempt
    if not job.pending or job.operation_id != operation_id:
        return None
    operation = await session.get(AccountOperation, operation_id, populate_existing=True)
    if (
        operation is None
        or operation.user_id != user.user_id
        or operation.desired_banned != bool(user.is_banned)
        or operation.status not in OPEN_STATUSES
        or operation.attempt_count != count
    ):
        return None
    return operation


async def finish_account_attempt(
    session: AsyncSession,
    user: User,
    job: AccountAccessSync,
    attempt: tuple[str, int],
    *,
    error: str | None,
) -> bool:
    """Call under the reacquired account lock; never relabel a newer attempt."""
    operation = await current_account_attempt(session, user, job, attempt)
    if operation is None:
        return False
    now = datetime.now(UTC)
    code = safe_account_error(error)
    operation.error_code = code
    if code is None:
        operation.status = "succeeded"
        operation.completed_at = now
    elif code in BLOCKED_ERRORS:
        operation.status = "failed"
        if operation.first_failed_at is None:
            operation.first_failed_at = now
    else:
        operation.status = "unknown"
    job.pending = code is not None
    job.last_error = code
    job.attempted_at = operation.attempted_at
    await session.flush()
    return True
