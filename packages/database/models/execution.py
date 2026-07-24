from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from packages.database.base import Base, IdMixin, TimestampMixin


class ExecutionStatus(StrEnum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ROLLBACK = "ROLLBACK"


class ExecutionJobModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "execution_jobs"
    __table_args__ = (
        Index("ix_exec_jobs_repo_org", "repository_id", "organization_id"),
        Index("ix_exec_jobs_plan", "plan_id"),
        Index("ix_exec_jobs_status", "status"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    plan_id: Mapped[UUID] = mapped_column(ForeignKey("plans.id"), nullable=False)

    status: Mapped[ExecutionStatus] = mapped_column(
        SAEnum(ExecutionStatus, name="execution_status"),
        default=ExecutionStatus.PENDING,
        nullable=False,
    )

    commit_sha_before: Mapped[str] = mapped_column(String(40), nullable=False)
    commit_sha_after: Mapped[str | None] = mapped_column(String(40), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExecutionLogModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "execution_logs"
    __table_args__ = (
        Index("ix_exec_logs_job", "execution_job_id"),
        Index("ix_exec_logs_node", "task_node_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    execution_job_id: Mapped[UUID] = mapped_column(ForeignKey("execution_jobs.id"), nullable=False)
    task_node_id: Mapped[UUID | None] = mapped_column(ForeignKey("task_nodes.id"), nullable=True)

    level: Mapped[str] = mapped_column(String(20), nullable=False, default="INFO")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    stream: Mapped[str] = mapped_column(String(20), nullable=False, default="stdout")  # stdout or stderr


class MutationModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "mutations"
    __table_args__ = (
        Index("ix_mutations_repo_org", "repository_id", "organization_id"),
        Index("ix_mutations_job", "execution_job_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    execution_job_id: Mapped[UUID] = mapped_column(ForeignKey("execution_jobs.id"), nullable=False)
    task_node_id: Mapped[UUID] = mapped_column(ForeignKey("task_nodes.id"), nullable=False)

    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    mutation_type: Mapped[str] = mapped_column(String(50), nullable=False)  # CREATE, UPDATE, DELETE
    diff_hunk: Mapped[str] = mapped_column(Text, nullable=False)
    is_reverted: Mapped[bool] = mapped_column(Boolean, default=False)
