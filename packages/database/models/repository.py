import enum
from uuid import UUID

from sqlalchemy import BigInteger, Index, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, IdMixin, TimestampMixin


class RepositoryStatus(str, enum.Enum):
    PENDING = "PENDING"
    IMPORTING = "IMPORTING"
    READY = "READY"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class RepositoryModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "repositories"
    __table_args__ = (
        Index("ix_repositories_owner_name", "owner", "name", unique=True),
        Index("ix_repositories_status", "status"),
        Index("ix_repositories_org", "organization_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(512), nullable=False)
    clone_url: Mapped[str] = mapped_column(Text, nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), default="main")
    status: Mapped[RepositoryStatus] = mapped_column(
        SAEnum(RepositoryStatus, name="repository_status"),
        default=RepositoryStatus.PENDING,
        nullable=False,
    )
    commit_sha: Mapped[str | None] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(Text)
    primary_language: Mapped[str | None] = mapped_column(String(50))
    frameworks: Mapped[dict | None] = mapped_column(JSONB)
    total_files: Mapped[int] = mapped_column(Integer, default=0)
    total_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    is_private: Mapped[bool] = mapped_column(default=False)
