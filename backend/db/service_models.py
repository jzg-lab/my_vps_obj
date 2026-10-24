"""Independent user services; never reuse the account's legacy subscription identity."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class AccountAccessSync(Base):
    __tablename__ = "account_access_sync"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    last_error: Mapped[str | None] = mapped_column(String(64))
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    operation_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("account_operations.id", ondelete="RESTRICT")
    )


class ServicePlan(Base):
    __tablename__ = "service_plans"
    __table_args__ = (CheckConstraint("revision > 0", name="ck_service_plan_revision"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    terms: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[int] = mapped_column(BigInteger, nullable=False)


class UserService(Base):
    __tablename__ = "user_services"
    __table_args__ = (
        CheckConstraint("quota_bytes > 0", name="ck_user_service_quota"),
        CheckConstraint("used_bytes >= 0", name="ck_user_service_used"),
        CheckConstraint("expires_at > starts_at", name="ck_user_service_dates"),
        CheckConstraint(
            "desired_status IN ('active', 'paused', 'cancelled')",
            name="ck_user_service_desired_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="RESTRICT"), index=True
    )
    plan_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("service_plans.id", ondelete="RESTRICT")
    )
    plan_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    quota_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    terms: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    quota_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    used_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    desired_status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    last_usage_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cycle_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cycle_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ServiceOrder(Base):
    __tablename__ = "service_orders"
    __table_args__ = (
        UniqueConstraint(
            "request_owner_id", "idempotency_key", name="uq_service_order_request_key"
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="RESTRICT"), index=True
    )
    # Original request scope survives ownership transfers and account deletion.
    request_owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    service_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("user_services.id", ondelete="RESTRICT"), index=True
    )
    actor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ServiceConnection(Base):
    __tablename__ = "service_connections"
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending', 'ready', 'error', 'revoked')",
            name="ck_service_connection_state",
        ),
    )

    service_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("user_services.id", ondelete="RESTRICT"), primary_key=True
    )
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    panel_user_uuid: Mapped[str | None] = mapped_column(String(36), unique=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    last_error: Mapped[str | None] = mapped_column(String(128))
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sync_pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sync_error: Mapped[str | None] = mapped_column(String(128))
    sync_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replacement_order_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("service_orders.id", ondelete="RESTRICT"), unique=True
    )

    usage_total_bytes: Mapped[int | None] = mapped_column(BigInteger)
    usage_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    usage_error: Mapped[str | None] = mapped_column(String(128))
    cycle_cutover_bytes: Mapped[int | None] = mapped_column(BigInteger)
    usage_raw_bytes: Mapped[int | None] = mapped_column(BigInteger)
    usage_lifetime_offset: Mapped[int | None] = mapped_column(BigInteger)

    revoke_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_delete_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ServiceOperationExecution(Base):
    __tablename__ = "service_operation_executions"
    __table_args__ = (
        CheckConstraint(
            "phase IN ('prepare','delivery','entitlement','revocation','usage','exit_replace')",
            name="ck_service_execution_phase",
        ),
        CheckConstraint(
            "status IN ('pending','unknown','failed','succeeded','superseded')",
            name="ck_service_execution_status",
        ),
        CheckConstraint("source IN ('administrator','worker')", name="ck_service_execution_source"),
        CheckConstraint(
            "target_revision > 0 AND attempt_count >= 0", name="ck_service_execution_counts"
        ),
        Index("ix_service_executions_history", "service_id", "created_at", "id"),
        CheckConstraint(
            "(phase = 'exit_replace' AND replacement_progress IS NOT NULL) OR "
            "(phase != 'exit_replace' AND replacement_progress IS NULL)",
            name="ck_service_execution_replacement",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    service_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("user_services.id", ondelete="RESTRICT")
    )
    order_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("service_orders.id", ondelete="RESTRICT"), unique=True
    )
    # Ownership at enqueue time must survive merges and account deletion.
    request_owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    target_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    replacement_progress: Mapped[dict[str, object] | None] = mapped_column(JSON(none_as_null=True))


class ServiceUsagePeriod(Base):
    __tablename__ = "service_usage_periods"

    service_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("user_services.id", ondelete="RESTRICT"), primary_key=True
    )
    cycle_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    cycle_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quota_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cutover_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    next_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DedicatedExit(Base):
    __tablename__ = "dedicated_exits"
    __table_args__ = (
        CheckConstraint(
            "service_id IS NULL OR hold_order_id IS NULL", name="ck_dedicated_exit_binding_hold"
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False, unique=True)
    resource_pool: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    squad_uuid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    service_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user_services.id", ondelete="RESTRICT"), unique=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hold_order_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("service_orders.id", ondelete="RESTRICT"), index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DedicatedExitAudit(Base):
    __tablename__ = "dedicated_exit_audit"
    __table_args__ = (UniqueConstraint("exit_id", "idempotency_key", name="uq_exit_audit_request"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    exit_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("dedicated_exits.id", ondelete="RESTRICT"), index=True
    )
    service_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user_services.id", ondelete="RESTRICT")
    )
    actor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ServicePlanQuotaChange(Base):
    __tablename__ = "service_plan_quota_changes"

    plan_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("service_plans.id", ondelete="RESTRICT"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    quota_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    actor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
