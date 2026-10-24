"""Strict global-operation filters, keyset cursors and public scalar output."""

import base64
import hashlib
import json
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from bot.app.web.admin_console_operations_schemas import ConsoleServiceOperationOut
from bot.app.web.admin_console_services_schemas import ConsoleCustomerOut
from bot.app.web.http_contracts import HttpResponseModel
from config.service_periods import as_utc
from db.dal.global_service_operations_dal import (
    GlobalOperationRow,
    OperationFilters,
    OperationPosition,
)
from db.dal.service_operations_dal import retry_block_reason


class _OperationCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[1]
    filters: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: str
    record_type: Literal["execution", "order"]
    id: str = Field(pattern=r"^[0-9a-f]{32}$")

    @field_validator("created_at")
    @classmethod
    def canonical_utc(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or as_utc(parsed).isoformat() != value:
            raise ValueError("invalid_cursor_time")
        return value

    def encode(self) -> str:
        return base64.urlsafe_b64encode(self.model_dump_json().encode()).decode().rstrip("=")


class ConsoleGlobalOperationsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["all", "pending", "unknown", "failed", "succeeded", "superseded"] = "all"
    phase: Literal[
        "all", "prepare", "delivery", "entitlement", "revocation", "usage", "exit_replace"
    ] = "all"
    user_id: int | None = Field(default=None, ge=-(2**53 - 1), le=2**53 - 1)
    service_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    archived: Literal["all", "only", "exclude"] = "all"
    needs_attention: bool = False
    limit: int = Field(default=25, ge=1, le=200)
    cursor: str | None = Field(default=None, min_length=1, max_length=1024)

    @field_validator("limit", "user_id", mode="before")
    @classmethod
    def integer_parameter(cls, value: object) -> object:
        if type(value) is int or value is None:
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

    def filters(self) -> OperationFilters:
        return OperationFilters(
            status=self.status,
            phase=self.phase,
            user_id=self.user_id,
            service_id=self.service_id,
            archived=self.archived,
            needs_attention=self.needs_attention,
        )

    def _filter_digest(self) -> str:
        normalized = self.model_dump(exclude={"cursor", "limit"})
        return hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()

    def position(self) -> OperationPosition | None:
        if self.cursor is None:
            return None
        if re.fullmatch(r"[A-Za-z0-9_-]+", self.cursor) is None:
            raise ValueError("invalid_cursor_encoding")
        raw = base64.b64decode(
            self.cursor + "=" * (-len(self.cursor) % 4), altchars=b"-_", validate=True
        )
        cursor = _OperationCursor.model_validate_json(raw)
        # Canonical re-encoding also rejects duplicate JSON keys and alternate encodings.
        if cursor.encode() != self.cursor or cursor.filters != self._filter_digest():
            raise ValueError("invalid_cursor_filters")
        return OperationPosition(
            datetime.fromisoformat(cursor.created_at), cursor.record_type, cursor.id
        )

    def next_cursor(self, position: OperationPosition) -> str:
        return _OperationCursor(
            version=1,
            filters=self._filter_digest(),
            created_at=as_utc(position.created_at).isoformat(),
            record_type=position.record_type,
            id=position.id,
        ).encode()


class ConsoleGlobalOperationOut(ConsoleServiceOperationOut):
    record_type: Literal["execution", "order"]
    needs_attention: bool
    service_revision: int
    service_name: str
    archived: bool
    customer: ConsoleCustomerOut
    last_success_at: datetime | None

    @classmethod
    def from_row(cls, row: GlobalOperationRow) -> "ConsoleGlobalOperationOut":
        execution = row.execution
        blocked = (
            retry_block_reason(row.service, row.connection, row.user, execution)
            if execution
            else "historical_result_unknown"
        )
        if (
            execution
            and execution.phase == "delivery"
            and blocked is None
            and not row.has_delivery_order
        ):
            blocked = "operation_not_retryable"
        operation = ConsoleServiceOperationOut.from_record(row.order, execution, blocked=blocked)
        user = row.user if row.service.user_id is not None else None
        return cls(
            **operation.model_dump(),
            record_type=row.position.record_type,
            needs_attention=row.needs_attention,
            service_revision=row.service.revision,
            service_name=row.service_name,
            archived=row.service.user_id is None,
            customer=ConsoleCustomerOut(
                user_id=user.user_id if user else None,
                minishop_id=user.minishop_id if user else None,
                username=user.username if user else None,
                email=user.email if user else None,
                first_name=user.first_name if user else None,
                last_name=user.last_name if user else None,
                is_banned=bool(user.is_banned) if user else None,
            ),
            last_success_at=as_utc(row.last_success_at) if row.last_success_at else None,
        )


class ConsoleGlobalOperationsOut(HttpResponseModel):
    operations: list[ConsoleGlobalOperationOut]
    total: int
    limit: int
    next_cursor: str | None
    observed_at: datetime
