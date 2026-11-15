from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
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
        UniqueConstraint("id", "organization_id", "repository_id", name="uq_execution_job_capsule_scope"),
        Index("ix_exec_jobs_repo_org", "repository_id", "organization_id"),
        Index("ix_exec_jobs_plan", "plan_id"),
        Index("ix_exec_jobs_status", "status"),
        Index("ix_exec_jobs_lease", "status", "lease_expires_at"),
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
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_requested_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    safety_policy_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


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


class ExecutionEventModel(IdMixin, Base):
    __tablename__ = "execution_events"
    __table_args__ = (
        UniqueConstraint("execution_job_id", "sequence", name="uq_execution_event_sequence"),
        UniqueConstraint("execution_job_id", "idempotency_key", name="uq_execution_event_idempotency"),
        Index("ix_execution_events_timeline", "organization_id", "execution_job_id", "sequence"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    execution_job_id: Mapped[UUID] = mapped_column(ForeignKey("execution_jobs.id"), nullable=False)
    task_node_id: Mapped[UUID | None] = mapped_column(ForeignKey("task_nodes.id"), nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    summary: Mapped[str] = mapped_column(String(160), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    causation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
