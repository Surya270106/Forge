from datetime import datetime
from enum import Enum as PyEnum
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from packages.database.base import Base, IdMixin, TimestampMixin


class VerificationStatus(str, PyEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    WARNING = "WARNING"
    SKIPPED = "SKIPPED"
    BLOCKED = "BLOCKED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


class VerificationJobModel(IdMixin, TimestampMixin, Base):
    """
    Groups a set of verification results for a given execution attempt.
    """

    __tablename__ = "verification_jobs"
    __table_args__ = (
        Index("ix_verif_jobs_repo_org", "repository_id", "organization_id"),
        Index("ix_verif_jobs_exec", "execution_job_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    execution_job_id: Mapped[UUID] = mapped_column(ForeignKey("execution_jobs.id"), nullable=False)

    status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus, name="verification_status"), nullable=False, default=VerificationStatus.PENDING
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VerificationResultModel(IdMixin, TimestampMixin, Base):
    """
    A normalized verification result for a single verifier run (e.g. format, lint, typecheck).
    """

    __tablename__ = "verification_results"
    __table_args__ = (
        Index("ix_verif_res_job", "verification_job_id"),
        Index("ix_verif_res_status", "status"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    verification_job_id: Mapped[UUID] = mapped_column(ForeignKey("verification_jobs.id"), nullable=False)
    execution_id: Mapped[UUID] = mapped_column(ForeignKey("execution_jobs.id"), nullable=False)

    verifier: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus, name="verification_result_status"),
        nullable=False,
    )
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    stdout: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr: Mapped[str | None] = mapped_column(Text, nullable=True)
    stdout_truncated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stderr_truncated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    diagnostics: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)

    blocking: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class RepairAttemptStatus(str, PyEnum):
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    ELIGIBLE = "ELIGIBLE"
    QUEUED = "QUEUED"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    REVERIFYING = "REVERIFYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    EXHAUSTED = "EXHAUSTED"
    CANCELLED = "CANCELLED"


class RepairAttemptModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "repair_attempts"
    __table_args__ = (
        Index("ix_repair_repo_org", "repository_id", "organization_id"),
        Index("ix_repair_verif", "verification_job_id"),
        Index("ix_repair_status", "status"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    verification_job_id: Mapped[UUID] = mapped_column(ForeignKey("verification_jobs.id"), nullable=False)

    repair_execution_id: Mapped[UUID | None] = mapped_column(ForeignKey("execution_jobs.id"), nullable=True)

    status: Mapped[RepairAttemptStatus] = mapped_column(
        SAEnum(RepairAttemptStatus, name="repair_attempt_status"), nullable=False, default=RepairAttemptStatus.QUEUED
    )

    prompt_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
