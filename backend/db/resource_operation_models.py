"""Durable resource intents; remote inventory remains owned by Remnawave."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class ResourceOperation(Base):
    __tablename__ = "resource_operations"
    __table_args__ = (
        UniqueConstraint("actor_id", "idempotency_key", name="uq_resource_operation_request"),
        CheckConstraint(
            "status IN ('pending','unknown','failed','succeeded','superseded')",
            name="ck_resource_operation_status",
        ),
        CheckConstraint("version > 0 AND attempt_count >= 0", name="ck_resource_operation_counts"),
        CheckConstraint(
            "(status IN ('pending','unknown') AND gate_key IS NOT NULL) OR "
            "(status IN ('failed','succeeded','superseded') AND gate_key IS NULL)",
            name="ck_resource_operation_gate",
        ),
        Index("ix_resource_operation_history", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    actor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(36))
    recovery_of: Mapped[str | None] = mapped_column(String(32))
    request: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    preview: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    baseline_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # Only this row owns the panel gate. Uncertainty never expires with a lease.
    gate_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    observation: Mapped[dict[str, object] | None] = mapped_column(JSON)
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
