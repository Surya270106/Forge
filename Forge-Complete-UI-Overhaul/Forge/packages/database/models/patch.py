from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from packages.database.base import Base, IdMixin, TimestampMixin


class PatchStatus(StrEnum):
    GENERATED = "GENERATED"
    UNDER_REVIEW = "UNDER_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    APPLIED_TO_BRANCH = "APPLIED_TO_BRANCH"
    COMMITTED = "COMMITTED"
    PULL_REQUEST_CREATED = "PULL_REQUEST_CREATED"
    FAILED = "FAILED"


class PatchModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "patches"
    __table_args__ = (
        Index("ix_patches_repo_org", "repository_id", "organization_id"),
        Index("ix_patches_exec", "execution_job_id"),
        Index("ix_patches_status", "status"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)

    # The execution that generated this patch
    execution_job_id: Mapped[UUID] = mapped_column(ForeignKey("execution_jobs.id"), nullable=False)
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)

    status: Mapped[PatchStatus] = mapped_column(
        SAEnum(PatchStatus, name="patch_status"),
        nullable=False,
        default=PatchStatus.GENERATED
    )

    # Summaries of the patch
    total_additions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_deletions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_changed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Optional metadata if a PR is created from this patch
    pull_request_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pull_request_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    branch_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # When it was reviewed
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
