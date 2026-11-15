from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from packages.database.base import Base, IdMixin, TimestampMixin


class IssueWorkflowModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "issue_workflows"
    __table_args__ = (
        UniqueConstraint("organization_id", "repository_id", "idempotency_key", name="uq_issue_workflow_request"),
        UniqueConstraint("organization_id", "github_repository_id", "github_issue_id", "base_commit_sha", name="uq_issue_workflow_source"),
        UniqueConstraint("plan_id", name="uq_issue_workflow_plan"),
        Index("ix_issue_workflow_repo", "organization_id", "repository_id", "created_at"),
        Index("ix_issue_workflow_issue", "github_repository_id", "github_issue_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    github_repository_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    github_issue_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    issue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    base_commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    atlas_snapshot_id: Mapped[UUID | None] = mapped_column(ForeignKey("atlas_snapshots.id"), nullable=True)
    candidate_paths: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    pending_plan_id: Mapped[UUID | None] = mapped_column(nullable=True)
    plan_id: Mapped[UUID | None] = mapped_column(ForeignKey("plans.id"), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(80), nullable=True)
    planned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
