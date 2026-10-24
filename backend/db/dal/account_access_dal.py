"""One pending reconciliation per account; callers serialize using the user row."""

from sqlalchemy.ext.asyncio import AsyncSession

from db.dal.account_operations_dal import record_account_intent
from db.models import User
from db.service_models import AccountAccessSync


async def enqueue_access_sync(
    session: AsyncSession,
    user_id: int,
    *,
    actor_id: int | None = None,
    before_banned: bool | None = None,
) -> AccountAccessSync:
    job = await session.get(AccountAccessSync, user_id, populate_existing=True)
    if job is None:
        job = AccountAccessSync(user_id=user_id, pending=True)
        session.add(job)
    job.pending = True
    job.last_error = None
    user = await session.get(User, user_id)
    if user is None:
        raise ValueError("account_missing")
    await record_account_intent(session, user, job, actor_id=actor_id, before_banned=before_banned)
    await session.flush()
    return job
