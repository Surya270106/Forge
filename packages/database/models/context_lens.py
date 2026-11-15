"""Immutable, content-free patch preparation evidence."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from packages.database.base import Base, IdMixin


class ContextChangeSetModel(IdMixin, Base):
    __tablename__ = "context_change_sets"
    __table_args__ = (
        UniqueConstraint("patch_id", name="uq_context_change_set_patch"),
        UniqueConstraint("id", "organization_id", "repository_id", name="uq_context_change_set_scope"),
        ForeignKeyConstraint(["base_snapshot_id", "organization_id", "repository_id"],
                             ["atlas_snapshots.id", "atlas_snapshots.organization_id", "atlas_snapshots.repository_id"],
                             name="fk_context_base_snapshot_scope"),
        Index("ix_context_change_sets_execution", "organization_id", "execution_job_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    execution_job_id: Mapped[UUID] = mapped_column(ForeignKey("execution_jobs.id"), nullable=False)
    patch_id: Mapped[UUID] = mapped_column(ForeignKey("patches.id"), nullable=False)
    base_snapshot_id: Mapped[UUID | None] = mapped_column()
    base_commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    review_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    file_changes: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
