"""Account access history survives deletion without retaining customer credentials."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class AccountOperation(Base):
    __tablename__ = "account_operations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','unknown','failed','succeeded','superseded')",
            name="ck_account_operation_status",
        ),
        CheckConstraint("source IN ('administrator','worker')", name="ck_account_operation_source"),
        CheckConstraint("attempt_count >= 0", name="ck_account_operation_attempts"),
        Index("ix_account_operation_history", "created_at", "id"),
        Index("ix_account_operation_target", "target_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    # Historical IDs are not reassigned or erased when an account is deleted or merged.
    actor_id: Mapped[int | None] = mapped_column(BigInteger)
    target_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="SET NULL"), index=True
    )
    before_banned: Mapped[bool | None] = mapped_column(Boolean)
    desired_banned: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
