from datetime import datetime

from sqlalchemy import DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, IdMixin


class ProcessedEventModel(IdMixin, Base):
    __tablename__ = "processed_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "consumer_name", "event_id", name="uq_processed_event"),
        Index("ix_processed_event_org", "organization_id"),
    )

    organization_id: Mapped[str] = mapped_column(String(36), nullable=False)
    consumer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result: Mapped[str] = mapped_column(String(50), nullable=False)
