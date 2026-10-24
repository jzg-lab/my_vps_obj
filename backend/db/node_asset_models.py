"""Manual inventory only; these records never confer control of a remote node."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class NodeAsset(Base):
    __tablename__ = "node_assets"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_node_asset_name"),
        CheckConstraint("length(trim(address)) > 0", name="ck_node_asset_address"),
        Index("ix_node_assets_created", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    address: Mapped[str] = mapped_column(String(253), nullable=False)
    notes: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
