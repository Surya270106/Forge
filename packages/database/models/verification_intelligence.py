"""Immutable verifier selection bound to a prepared patch."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from packages.database.base import Base, IdMixin


class VerificationPlanModel(IdMixin, Base):
    __tablename__ = "verification_plans"
    __table_args__ = (
        UniqueConstraint("verification_job_id", name="uq_verification_plan_job"),
        ForeignKeyConstraint(["change_set_id", "organization_id", "repository_id"],
                             ["context_change_sets.id", "context_change_sets.organization_id",
                              "context_change_sets.repository_id"], name="fk_verification_plan_change_scope"),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    execution_job_id: Mapped[UUID] = mapped_column(ForeignKey("execution_jobs.id"), nullable=False)
    verification_job_id: Mapped[UUID] = mapped_column(ForeignKey("verification_jobs.id"), nullable=False)
    change_set_id: Mapped[UUID] = mapped_column(nullable=False)
    base_commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    patch_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    decision: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
