from datetime import datetime
from enum import Enum as PyEnum
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from packages.database.base import Base, IdMixin, TimestampMixin


class VerificationStatus(str, PyEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"


class DiagnosticType(str, PyEnum):
    LINT = "LINT"
    TYPE_CHECK = "TYPE_CHECK"
    UNIT_TEST = "UNIT_TEST"
    BUILD = "BUILD"
    SECURITY = "SECURITY"


class VerificationJobModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "verification_jobs"
    __table_args__ = (
        Index("ix_verif_jobs_repo_org", "repository_id", "organization_id"),
        Index("ix_verif_jobs_exec", "execution_job_id"),
        Index("ix_verif_jobs_status", "status"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    execution_job_id: Mapped[UUID] = mapped_column(ForeignKey("execution_jobs.id"), nullable=False)

    status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus, name="verification_status"),
        default=VerificationStatus.PENDING,
        nullable=False,
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VerificationResultModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "verification_results"
    __table_args__ = (
        Index("ix_verif_res_job", "verification_job_id"),
        Index("ix_verif_res_type", "diagnostic_type"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    verification_job_id: Mapped[UUID] = mapped_column(ForeignKey("verification_jobs.id"), nullable=False)

    diagnostic_type: Mapped[DiagnosticType] = mapped_column(SAEnum(DiagnosticType, name="diagnostic_type"), nullable=False)
    is_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    output: Mapped[str] = mapped_column(Text, nullable=False)

    # Store parsed diagnostics like line numbers, error codes, file paths
    parsed_diagnostics: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)


class RepairAttemptModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "repair_attempts"
    __table_args__ = (
        Index("ix_repair_repo_org", "repository_id", "organization_id"),
        Index("ix_repair_verif", "verification_job_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    verification_job_id: Mapped[UUID] = mapped_column(ForeignKey("verification_jobs.id"), nullable=False)

    # Links back to the execution job that was spawned to fix this
    repair_execution_id: Mapped[UUID] = mapped_column(ForeignKey("execution_jobs.id"), nullable=False)

    prompt_used: Mapped[str] = mapped_column(Text, nullable=False)
    is_successful: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
