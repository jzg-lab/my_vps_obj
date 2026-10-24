"""Read-only service queries for the unified console; archives stay in history."""

from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import String, and_, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Select

from db.models import User
from db.service_models import DedicatedExit, ServiceConnection, UserService

ConsoleStatus = Literal[
    "all",
    "active",
    "pending",
    "paused",
    "cancelled",
    "expired",
    "exhausted",
    "account_banned",
    "sync_error",
    "sync_pending",
    "usage_unconfirmed",
    "expiring",
]
ConsoleSort = Literal["created_desc", "created_asc", "expires_asc", "expires_desc", "usage_desc"]
ServiceRow = tuple[UserService, ServiceConnection | None, DedicatedExit | None, User]
ServiceDetailRow = tuple[UserService, ServiceConnection | None, DedicatedExit | None, User | None]


def business_status(now: datetime) -> ColumnElement[str]:
    """SQL equivalent of user_service_access.service_status, tested against that source."""
    dedicated = UserService.terms["resource_type"].as_string() == "dedicated"
    resource_missing = or_(
        DedicatedExit.id.is_(None),
        DedicatedExit.verified_at.is_(None),
        DedicatedExit.enabled.is_(False),
        DedicatedExit.resource_pool != UserService.terms["resource_pool"].as_string(),
    )
    return case(
        (User.is_banned.is_(True), "account_banned"),
        (UserService.user_id.is_(None), "cancelled"),
        (UserService.desired_status != "active", UserService.desired_status),
        (UserService.expires_at <= now, "expired"),
        (UserService.used_bytes >= UserService.quota_bytes, "exhausted"),
        (
            or_(
                UserService.starts_at > now,
                ServiceConnection.service_id.is_(None),
                ServiceConnection.replacement_order_id.is_not(None),
                ServiceConnection.state != "ready",
                and_(dedicated, resource_missing),
            ),
            "pending",
        ),
        else_="active",
    )


def service_query() -> Select[tuple[UserService, ServiceConnection, DedicatedExit, User]]:
    return (
        select(UserService, ServiceConnection, DedicatedExit, User)
        .join(User, User.user_id == UserService.user_id)
        .outerjoin(ServiceConnection, ServiceConnection.service_id == UserService.id)
        .outerjoin(DedicatedExit, DedicatedExit.service_id == UserService.id)
    )


def cycle_pending(now: datetime) -> ColumnElement[bool]:
    return or_(
        ServiceConnection.cycle_cutover_bytes.is_not(None),
        and_(
            UserService.terms["traffic_rule"].as_string() == "monthly",
            UserService.cycle_ends_at <= now,
            UserService.expires_at > now,
            UserService.desired_status != "cancelled",
        ),
    )


def sync_error() -> ColumnElement[bool]:
    return or_(
        ServiceConnection.last_error.is_not(None),
        ServiceConnection.sync_error.is_not(None),
        ServiceConnection.usage_error.is_not(None),
        ServiceConnection.state == "error",
    )


async def list_services(
    session: AsyncSession,
    *,
    now: datetime,
    q: str = "",
    status: ConsoleStatus = "all",
    user_id: int | None = None,
    sort: ConsoleSort = "created_desc",
    page: int = 0,
    page_size: int = 25,
    expiring_within_days: int = 7,
) -> tuple[list[ServiceRow], int]:
    statement = service_query()
    if user_id is not None:
        statement = statement.where(UserService.user_id == user_id)
    if q:
        # Literal substring search: SQL wildcard characters are ordinary user input.
        fields = [
            UserService.id,
            UserService.terms["name"].as_string(),
            cast(User.user_id, String),
            User.minishop_id,
            User.username,
            User.email,
            User.first_name,
            User.last_name,
        ]
        statement = statement.where(or_(*(field.icontains(q, autoescape=True) for field in fields)))
    state = business_status(now)
    if status == "sync_error":
        statement = statement.where(sync_error())
    elif status == "sync_pending":
        statement = statement.where(ServiceConnection.sync_pending.is_(True))
    elif status == "usage_unconfirmed":
        statement = statement.where(
            or_(
                UserService.last_usage_sync_at.is_(None), ServiceConnection.usage_error.is_not(None)
            )
        )
    elif status == "expiring":
        statement = statement.where(
            UserService.expires_at > now,
            UserService.expires_at <= now + timedelta(days=expiring_within_days),
            UserService.desired_status != "cancelled",
        )
    elif status != "all":
        statement = statement.where(state == status)
    total = (
        await session.execute(select(func.count()).select_from(statement.subquery()))
    ).scalar_one()
    order = {
        "created_desc": UserService.created_at.desc(),
        "created_asc": UserService.created_at.asc(),
        "expires_asc": UserService.expires_at.asc(),
        "expires_desc": UserService.expires_at.desc(),
        "usage_desc": UserService.used_bytes.desc(),
    }[sort]
    rows = await session.execute(
        statement.order_by(order, UserService.id).limit(page_size).offset(page * page_size)
    )
    return [
        (service, connection, resource, user) for service, connection, resource, user in rows
    ], int(total)


async def get_service(session: AsyncSession, service_id: str) -> ServiceDetailRow | None:
    # Audit links retain archived services; operational lists keep their inner join.
    statement = (
        select(UserService, ServiceConnection, DedicatedExit, User)
        .outerjoin(User, User.user_id == UserService.user_id)
        .outerjoin(ServiceConnection, ServiceConnection.service_id == UserService.id)
        .outerjoin(DedicatedExit, DedicatedExit.service_id == UserService.id)
        .where(UserService.id == service_id)
    )
    row = (await session.execute(statement)).one_or_none()
    return (row[0], row[1], row[2], row[3]) if row is not None else None
