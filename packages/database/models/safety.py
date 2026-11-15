"""Versioned organization safety restrictions."""

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from packages.database.base import Base, IdMixin, TimestampMixin


class SafetyPolicyModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "safety_policies"
    __table_args__ = (UniqueConstraint("organization_id", "version", name="uq_safety_policy_version"),)

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    denied: Mapped[list] = mapped_column(JSONB, nullable=False)
    repository_denies: Mapped[dict] = mapped_column(JSONB, nullable=False)
    stopped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
