from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, IdMixin


class OutboxEventModel(IdMixin, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_published", "published"),
        Index("ix_outbox_occurred", "occurred_at"),
    )

    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(36), nullable=False)
    aggregate_version: Mapped[int] = mapped_column(Integer, default=1)
    correlation_id: Mapped[str | None] = mapped_column(String(36))
    causation_id: Mapped[str | None] = mapped_column(String(36))
    schema_version: Mapped[str] = mapped_column(String(10), default="1.0")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
