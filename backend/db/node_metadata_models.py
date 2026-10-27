"""Administrator-maintained labels for Remnawave nodes."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class NodeMetadata(Base):
    __tablename__ = "node_metadata"
    __table_args__ = (
        CheckConstraint(
            "display_name IS NULL OR length(trim(display_name)) > 0",
            name="ck_node_metadata_display_name",
        ),
        CheckConstraint(
            "region IS NULL OR length(trim(region)) > 0", name="ck_node_metadata_region"
        ),
        CheckConstraint(
            "provider IS NULL OR length(trim(provider)) > 0", name="ck_node_metadata_provider"
        ),
    )

    node_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    region: Mapped[str | None] = mapped_column(String(120))
    provider: Mapped[str | None] = mapped_column(String(120))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
