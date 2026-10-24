"""Filtered account history and page totals from one database snapshot."""

from dataclasses import dataclass

from sqlalchemy import and_, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from db.account_operation_models import AccountOperation
from db.dal.account_operations_dal import OPEN_STATUSES
from db.service_models import AccountAccessSync


@dataclass(frozen=True)
class AccountOperationFilters:
    user_id: int | None = None
    actor_id: int | None = None
    status: str = "all"
    source: str = "all"
    archived: str = "all"
    needs_attention: bool = False


@dataclass(frozen=True)
class AccountOperationRow:
    operation: AccountOperation
    needs_attention: bool


def attention_condition() -> ColumnElement[bool]:
    return and_(
        AccountOperation.user_id.is_not(None),
        AccountOperation.status.in_(OPEN_STATUSES),
        select(AccountAccessSync.user_id)
        .where(
            AccountAccessSync.user_id == AccountOperation.user_id,
            AccountAccessSync.operation_id == AccountOperation.id,
            AccountAccessSync.pending.is_(True),
        )
        .exists(),
    )


async def list_account_operations(
    session: AsyncSession,
    filters: AccountOperationFilters,
    *,
    page: int = 0,
    page_size: int = 25,
) -> tuple[list[AccountOperationRow], int]:
    statement = select(AccountOperation.id, AccountOperation.created_at)
    if filters.user_id is not None:
        statement = statement.where(AccountOperation.target_id == filters.user_id)
    if filters.actor_id is not None:
        statement = statement.where(AccountOperation.actor_id == filters.actor_id)
    if filters.status != "all":
        statement = statement.where(AccountOperation.status == filters.status)
    if filters.source != "all":
        statement = statement.where(AccountOperation.source == filters.source)
    if filters.archived != "all":
        statement = statement.where(
            AccountOperation.user_id.is_(None)
            if filters.archived == "only"
            else AccountOperation.user_id.is_not(None)
        )
    if filters.needs_attention:
        statement = statement.where(attention_condition())
    filtered = statement.cte("filtered_account_operations")
    totals = select(func.count().label("total")).select_from(filtered).cte("account_total")
    selected = (
        select(filtered.c.id, filtered.c.created_at)
        .order_by(filtered.c.created_at.desc(), filtered.c.id.desc())
        .offset(page * page_size)
        .limit(page_size)
        .cte("account_page")
    )
    rows = (
        await session.execute(
            select(AccountOperation, totals.c.total, attention_condition())
            .select_from(totals)
            .outerjoin(selected, true())
            .outerjoin(AccountOperation, AccountOperation.id == selected.c.id)
            .order_by(selected.c.created_at.desc(), selected.c.id.desc())
        )
    ).all()
    return (
        [AccountOperationRow(row[0], bool(row[2])) for row in rows if row[0] is not None],
        int(rows[0][1]),
    )


async def get_account_operation(
    session: AsyncSession, operation_id: str
) -> AccountOperationRow | None:
    row = (
        await session.execute(
            select(AccountOperation, attention_condition()).where(
                AccountOperation.id == operation_id
            )
        )
    ).one_or_none()
    return AccountOperationRow(row[0], bool(row[1])) if row is not None else None
