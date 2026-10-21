"""One pending reconciliation per account; callers serialize using the user row."""

from sqlalchemy.ext.asyncio import AsyncSession

from db.service_models import AccountAccessSync


async def enqueue_access_sync(session: AsyncSession, user_id: int) -> AccountAccessSync:
    job = await session.get(AccountAccessSync, user_id, populate_existing=True)
    if job is None:
        job = AccountAccessSync(user_id=user_id, pending=True)
        session.add(job)
    job.pending = True
    job.last_error = None
    await session.flush()
    return job
