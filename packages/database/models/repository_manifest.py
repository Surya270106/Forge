from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, IdMixin, TimestampMixin


class RepositoryManifestModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "repository_manifests"
    __table_args__ = (
        Index("ix_manifests_repo_version", "repository_id", "version", unique=True),
        Index("ix_manifests_org", "organization_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)

    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
