import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, IdMixin, TimestampMixin


class ImportJobStatus(str, enum.Enum):
    PENDING = "PENDING"
    AUTHENTICATING = "AUTHENTICATING"
    CLONING = "CLONING"
    SCANNING = "SCANNING"
    DETECTING = "DETECTING"
    BUILDING_MANIFEST = "BUILDING_MANIFEST"
    PERSISTING = "PERSISTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Valid state transitions
IMPORT_TRANSITIONS: dict[ImportJobStatus, set[ImportJobStatus]] = {
    ImportJobStatus.PENDING: {
        ImportJobStatus.AUTHENTICATING,
        ImportJobStatus.FAILED,
        ImportJobStatus.CANCELLED,
    },
    ImportJobStatus.AUTHENTICATING: {ImportJobStatus.CLONING, ImportJobStatus.FAILED},
    ImportJobStatus.CLONING: {ImportJobStatus.SCANNING, ImportJobStatus.FAILED},
    ImportJobStatus.SCANNING: {ImportJobStatus.DETECTING, ImportJobStatus.FAILED},
    ImportJobStatus.DETECTING: {ImportJobStatus.BUILDING_MANIFEST, ImportJobStatus.FAILED},
    ImportJobStatus.BUILDING_MANIFEST: {ImportJobStatus.PERSISTING, ImportJobStatus.FAILED},
    ImportJobStatus.PERSISTING: {ImportJobStatus.COMPLETED, ImportJobStatus.FAILED},
    ImportJobStatus.COMPLETED: set(),
    ImportJobStatus.FAILED: {ImportJobStatus.PENDING},  # retry
    ImportJobStatus.CANCELLED: set(),
}


class ImportJobModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "import_jobs"
    __table_args__ = (
        Index("ix_import_jobs_repository_id", "repository_id"),
        Index("ix_import_jobs_status", "status"),
        Index("ix_import_jobs_org", "organization_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)

    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    status: Mapped[ImportJobStatus] = mapped_column(
        SAEnum(ImportJobStatus, name="import_job_status"),
        default=ImportJobStatus.PENDING,
        nullable=False,
    )
    worker_id: Mapped[str | None] = mapped_column(String(255))
    branch: Mapped[str] = mapped_column(String(255), default="main")
    commit_sha: Mapped[str | None] = mapped_column(String(40))
    retries: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
