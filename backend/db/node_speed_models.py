"""Short lived node speed observations for the operations charts."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class NodeSpeedSample(Base):
    __tablename__ = "node_speed_samples"
    __table_args__ = (
        UniqueConstraint("node_id", "sampled_at", name="uq_node_speed_sample"),
        Index("ix_node_speed_sampled_at", "sampled_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rx_bytes_per_second: Mapped[float | None] = mapped_column(Float, nullable=True)
    tx_bytes_per_second: Mapped[float | None] = mapped_column(Float, nullable=True)
