"""Tenant-scoped, immutable published Atlas graph snapshots."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from packages.database.base import Base, IdMixin, TimestampMixin


class AtlasJobModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "atlas_jobs"
    __table_args__ = (
        UniqueConstraint("organization_id", "repository_id", "idempotency_key", name="uq_atlas_job_request"),
        UniqueConstraint("id", "organization_id", "repository_id", name="uq_atlas_job_scope"),
        Index("ix_atlas_jobs_repo_status", "organization_id", "repository_id", "status"),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    requested_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    execution_id: Mapped[UUID | None] = mapped_column(ForeignKey("execution_jobs.id"))
    requested_revision: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="QUEUED")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(60))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AtlasSnapshotModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "atlas_snapshots"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_atlas_snapshot_job"),
        UniqueConstraint("id", "organization_id", "repository_id", name="uq_atlas_snapshot_scope"),
        ForeignKeyConstraint(["job_id", "organization_id", "repository_id"],
                             ["atlas_jobs.id", "atlas_jobs.organization_id", "atlas_jobs.repository_id"], name="fk_atlas_snapshot_job_scope"),
        Index("ix_atlas_snapshots_repo_published", "organization_id", "repository_id", "status", "completed_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    job_id: Mapped[UUID] = mapped_column(nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    tree_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    dirty: Mapped[bool] = mapped_column(Boolean, nullable=False)
    indexer_version: Mapped[str] = mapped_column(String(40), nullable=False)
    parser_versions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    config_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="BUILDING")
    stats: Mapped[dict] = mapped_column(JSONB, nullable=False)
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AtlasFileFactModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "atlas_file_facts"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "path", name="uq_atlas_fact_path"),
        ForeignKeyConstraint(["snapshot_id", "organization_id", "repository_id"],
                             ["atlas_snapshots.id", "atlas_snapshots.organization_id", "atlas_snapshots.repository_id"], name="fk_atlas_fact_scope"),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    fact: Mapped[dict] = mapped_column(JSONB, nullable=False)


class AtlasNodeModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "atlas_nodes"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "stable_key", name="uq_atlas_node_key"),
        UniqueConstraint("snapshot_id", "id", name="uq_atlas_node_snapshot_id"),
        ForeignKeyConstraint(["snapshot_id", "organization_id", "repository_id"],
                             ["atlas_snapshots.id", "atlas_snapshots.organization_id", "atlas_snapshots.repository_id"], name="fk_atlas_node_scope"),
        Index("ix_atlas_nodes_search", "organization_id", "repository_id", "snapshot_id", "name"),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(nullable=False)
    stable_key: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str | None] = mapped_column(Text)
    line_start: Mapped[int | None] = mapped_column(Integer)
    line_end: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str | None] = mapped_column(String(32))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    parser_version: Mapped[str | None] = mapped_column(String(40))


class AtlasEdgeModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "atlas_edges"
    __table_args__ = (
        ForeignKeyConstraint(["snapshot_id", "organization_id", "repository_id"],
                             ["atlas_snapshots.id", "atlas_snapshots.organization_id", "atlas_snapshots.repository_id"], name="fk_atlas_edge_scope"),
        ForeignKeyConstraint(["snapshot_id", "from_node_id"], ["atlas_nodes.snapshot_id", "atlas_nodes.id"], name="fk_atlas_edge_from_snapshot"),
        ForeignKeyConstraint(["snapshot_id", "to_node_id"], ["atlas_nodes.snapshot_id", "atlas_nodes.id"], name="fk_atlas_edge_to_snapshot"),
        Index("ix_atlas_edges_reverse", "snapshot_id", "to_node_id", "kind"),
        Index("ix_atlas_edges_source", "snapshot_id", "from_node_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(nullable=False)
    from_node_id: Mapped[UUID] = mapped_column(nullable=False)
    to_node_id: Mapped[UUID | None] = mapped_column(nullable=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    target_name: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_path: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_line: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution: Mapped[str] = mapped_column(String(24), nullable=False)
    confidence: Mapped[str] = mapped_column(String(12), nullable=False)
    method: Mapped[str] = mapped_column(String(50), nullable=False)
