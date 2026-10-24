"""Account-only audit contracts; no panel payloads or account profile snapshots."""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from bot.app.web.http_contracts import HttpResponseModel
from config.service_periods import as_utc
from db.dal.account_operation_reads_dal import AccountOperationFilters, AccountOperationRow
from db.dal.account_operations_dal import safe_account_error

AccountOperationStatus = Literal["pending", "unknown", "failed", "succeeded", "superseded"]
AccountOperationSource = Literal["administrator", "worker"]


class ConsoleAccountOperationsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int | None = Field(default=None, ge=-(2**53 - 1), le=2**53 - 1)
    actor_id: int | None = Field(default=None, ge=-(2**53 - 1), le=2**53 - 1)
    status: Literal["all", "pending", "unknown", "failed", "succeeded", "superseded"] = "all"
    source: Literal["all", "administrator", "worker"] = "all"
    archived: Literal["all", "only", "exclude"] = "all"
    needs_attention: bool = False
    page: int = Field(default=0, ge=0, le=1_000_000)
    page_size: int = Field(default=25, ge=1, le=200)

    @field_validator("user_id", "actor_id", "page", "page_size", mode="before")
    @classmethod
    def integer_parameter(cls, value: object) -> object:
        if value is None or type(value) is int:
            return value
        if not isinstance(value, str) or re.fullmatch(r"-?(0|[1-9][0-9]*)", value) is None:
            raise ValueError("invalid_integer")
        return value

    @field_validator("needs_attention", mode="before")
    @classmethod
    def boolean_parameter(cls, value: object) -> bool:
        if type(value) is bool:
            return value
        if value not in ("true", "false"):
            raise ValueError("invalid_boolean")
        return value == "true"

    def filters(self) -> AccountOperationFilters:
        return AccountOperationFilters(**self.model_dump(exclude={"page", "page_size"}))


class ConsoleAccountOperationOut(HttpResponseModel):
    id: str
    actor_id: int | None
    target_id: int
    user_id: int | None
    before_banned: bool | None
    desired_banned: bool
    source: AccountOperationSource
    status: AccountOperationStatus
    attempt_count: int
    created_at: datetime
    attempted_at: datetime | None
    first_failed_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    archived: bool
    needs_attention: bool

    @classmethod
    def from_row(cls, row: AccountOperationRow) -> "ConsoleAccountOperationOut":
        operation = row.operation
        return cls.model_validate(
            {
                "id": operation.id,
                "actor_id": operation.actor_id,
                "target_id": operation.target_id,
                "user_id": operation.user_id,
                "before_banned": operation.before_banned,
                "desired_banned": operation.desired_banned,
                "source": operation.source,
                "status": operation.status,
                "attempt_count": operation.attempt_count,
                "created_at": as_utc(operation.created_at),
                "attempted_at": as_utc(operation.attempted_at) if operation.attempted_at else None,
                "first_failed_at": as_utc(operation.first_failed_at)
                if operation.first_failed_at
                else None,
                "completed_at": as_utc(operation.completed_at) if operation.completed_at else None,
                "error_code": safe_account_error(operation.error_code),
                "archived": operation.user_id is None,
                "needs_attention": row.needs_attention,
            }
        )


class ConsoleAccountOperationsOut(HttpResponseModel):
    operations: list[ConsoleAccountOperationOut]
    total: int
    page: int
    page_size: int
    observed_at: datetime
