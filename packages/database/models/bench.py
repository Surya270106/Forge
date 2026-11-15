from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from packages.database.base import Base, IdMixin, TimestampMixin


class BenchmarkRunModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "benchmark_runs"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_benchmark_run_request"),
        Index("ix_benchmark_runs_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    suite_id: Mapped[str] = mapped_column(String(64), nullable=False)
    suite_version: Mapped[int] = mapped_column(Integer, nullable=False)
    dataset_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    baseline_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("benchmark_runs.id"), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BenchmarkTrialModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "benchmark_trials"
    __table_args__ = (
        UniqueConstraint("run_id", "task_id", "repetition", name="uq_benchmark_trial_slot"),
        UniqueConstraint("execution_id", name="uq_benchmark_trial_execution"),
        Index("ix_benchmark_trials_org_run", "organization_id", "run_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("benchmark_runs.id"), nullable=False)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False)
    task_version: Mapped[int] = mapped_column(Integer, nullable=False)
    repetition: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    execution_id: Mapped[UUID | None] = mapped_column(ForeignKey("execution_jobs.id"), nullable=True)
    plan_id: Mapped[UUID | None] = mapped_column(ForeignKey("plans.id"), nullable=True)
    base_commit: Mapped[str] = mapped_column(String(40), nullable=False)
    patch_digest: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[dict | None] = mapped_column(JSONB)
    failure_category: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
