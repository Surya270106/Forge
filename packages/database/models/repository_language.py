from uuid import UUID

from sqlalchemy import Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, IdMixin, TimestampMixin


class RepositoryLanguageModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "repository_languages"
    __table_args__ = (Index("ix_repo_lang_repo_id", "repository_id"),)

    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    language: Mapped[str] = mapped_column(String(50), nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    byte_count: Mapped[int] = mapped_column(Integer, default=0)
    percentage: Mapped[float] = mapped_column(Float, default=0.0)
    is_primary: Mapped[bool] = mapped_column(default=False)
