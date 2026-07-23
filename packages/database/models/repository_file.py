from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, IdMixin, TimestampMixin


class RepositoryFileModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "repository_files"
    __table_args__ = (
        Index("ix_repo_files_repo_id", "repository_id"),
        Index("ix_repo_files_path", "repository_id", "relative_path", unique=True),
        Index("ix_repo_files_category", "category"),
    )

    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    extension: Mapped[str | None] = mapped_column(String(20))
    language: Mapped[str | None] = mapped_column(String(50))
    category: Mapped[str] = mapped_column(String(20), default="unknown")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    checksum: Mapped[str | None] = mapped_column(String(64))
