from datetime import datetime
from enum import Enum as PyEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
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
from sqlalchemy.orm import Mapped, mapped_column

from packages.database.base import Base, IdMixin, TimestampMixin


class IndexingStatus(str, PyEnum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    SCANNING = "SCANNING"
    PARSING = "PARSING"
    PERSISTING = "PERSISTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RepositoryMemoryVersionModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "repository_memory_versions"
    __table_args__ = (
        Index("ix_repo_mem_versions_repo_org", "repository_id", "organization_id"),
        Index("ix_repo_mem_versions_version", "repository_id", "version", unique=True),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    branch: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)


class SourceFileModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "source_files"
    __table_args__ = (
        Index("ix_source_files_repo_org", "repository_id", "organization_id"),
        Index("ix_source_files_path", "repository_id", "file_path"),
        Index("ix_source_files_checksum", "repository_id", "checksum"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    memory_version_id: Mapped[UUID] = mapped_column(ForeignKey("repository_memory_versions.id"), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[str] = mapped_column(String(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    lines: Mapped[int] = mapped_column(Integer, nullable=False)


class SymbolModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "symbols"
    __table_args__ = (
        Index("ix_symbols_repo_org", "repository_id", "organization_id"),
        Index("ix_symbols_file", "source_file_id"),
        Index("ix_symbols_name", "repository_id", "name"),
        Index("ix_symbols_type", "repository_id", "symbol_type"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    source_file_id: Mapped[UUID] = mapped_column(ForeignKey("source_files.id"), nullable=False)
    memory_version_id: Mapped[UUID] = mapped_column(ForeignKey("repository_memory_versions.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    qualname: Mapped[str] = mapped_column(Text, nullable=False)
    symbol_type: Mapped[str] = mapped_column(String(50), nullable=False)  # class, function, method, interface, etc.
    line_start: Mapped[int] = mapped_column(Integer, nullable=False)
    line_end: Mapped[int] = mapped_column(Integer, nullable=False)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)


class SymbolReferenceModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "symbol_references"
    __table_args__ = (
        Index("ix_sym_refs_repo_org", "repository_id", "organization_id"),
        Index("ix_sym_refs_symbol", "symbol_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    source_file_id: Mapped[UUID] = mapped_column(ForeignKey("source_files.id"), nullable=False)
    symbol_id: Mapped[UUID | None] = mapped_column(ForeignKey("symbols.id"), nullable=True)  # Resolved symbol if found

    reference_name: Mapped[str] = mapped_column(Text, nullable=False)
    line_start: Mapped[int] = mapped_column(Integer, nullable=False)


class DependencyEdgeModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "dependency_edges"
    __table_args__ = (
        Index("ix_deps_repo_org", "repository_id", "organization_id"),
        Index("ix_deps_from", "from_file_id"),
        Index("ix_deps_to", "to_file_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    from_file_id: Mapped[UUID] = mapped_column(ForeignKey("source_files.id"), nullable=False)
    to_file_id: Mapped[UUID | None] = mapped_column(ForeignKey("source_files.id"), nullable=True)

    import_statement: Mapped[str] = mapped_column(Text, nullable=False)
    is_external: Mapped[bool] = mapped_column(Boolean, default=False)


class CallEdgeModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "call_edges"
    __table_args__ = (
        Index("ix_calls_repo_org", "repository_id", "organization_id"),
        Index("ix_calls_caller", "caller_symbol_id"),
        Index("ix_calls_callee", "callee_symbol_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    caller_symbol_id: Mapped[UUID] = mapped_column(ForeignKey("symbols.id"), nullable=False)
    callee_symbol_id: Mapped[UUID | None] = mapped_column(ForeignKey("symbols.id"), nullable=True)

    call_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    line_start: Mapped[int] = mapped_column(Integer, nullable=False)


class ASTCacheEntryModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "ast_cache_entries"
    __table_args__ = (
        Index("ix_ast_cache_repo_org", "repository_id", "organization_id"),
        Index("ix_ast_cache_checksum", "repository_id", "checksum", unique=True),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[str] = mapped_column(String(50), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(50), nullable=False)
    ast_blob: Mapped[bytes] = mapped_column(nullable=False)


class IndexingJobModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "indexing_jobs"
    __table_args__ = (
        Index("ix_idx_jobs_repo_org", "repository_id", "organization_id"),
        Index("ix_idx_jobs_status", "status"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    status: Mapped[IndexingStatus] = mapped_column(
        SAEnum(IndexingStatus, name="indexing_status"),
        default=IndexingStatus.PENDING,
        nullable=False,
    )
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    branch: Mapped[str] = mapped_column(String(255), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IndexingFailureModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "indexing_failures"
    __table_args__ = (
        Index("ix_idx_fails_job", "indexing_job_id"),
        Index("ix_idx_fails_file", "file_path"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    indexing_job_id: Mapped[UUID] = mapped_column(ForeignKey("indexing_jobs.id"), nullable=False)

    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    traceback: Mapped[str | None] = mapped_column(Text)
