"""Immutable execution evidence snapshots and bounded structured artifacts."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from packages.database.base import Base, IdMixin


class RunCapsuleModel(IdMixin, Base):
    __tablename__ = "run_capsules"
    __table_args__ = (
        Index("ix_run_capsule_execution", "organization_id", "execution_job_id", "attempt", "created_at"),
        UniqueConstraint("event_id", name="uq_run_capsule_event"),
        UniqueConstraint("id", "organization_id", name="uq_run_capsule_scope"),
        CheckConstraint("state IN ('PARTIAL', 'FINAL')", name="ck_run_capsule_state"),
        ForeignKeyConstraint(
            ["execution_job_id", "organization_id", "repository_id"],
            ["execution_jobs.id", "execution_jobs.organization_id", "execution_jobs.repository_id"],
            name="fk_run_capsule_execution_scope",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    execution_job_id: Mapped[UUID] = mapped_column(nullable=False)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("execution_events.id"), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(12), nullable=False)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RunCapsuleArtifactModel(IdMixin, Base):
    __tablename__ = "run_capsule_artifacts"
    __table_args__ = (
        UniqueConstraint("capsule_id", "kind", name="uq_run_capsule_artifact_kind"),
        CheckConstraint("size_bytes BETWEEN 0 AND 16384", name="ck_run_capsule_artifact_size"),
        ForeignKeyConstraint(
            ["capsule_id", "organization_id"],
            ["run_capsules.id", "run_capsules.organization_id"],
            name="fk_run_capsule_artifact_scope",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    capsule_id: Mapped[UUID] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
