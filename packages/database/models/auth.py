from uuid import UUID

from sqlalchemy import JSON, Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from packages.database.base import Base, IdMixin, TimestampMixin


class OrganizationModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "organizations"
    __table_args__ = (Index("ix_orgs_name", "name", unique=True),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    billing_plan: Mapped[str] = mapped_column(String(50), nullable=False, default="FREE")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    provider_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class UserModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_email", "email", unique=True),)

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    github_token: Mapped[str | None] = mapped_column(String(255), nullable=True)


class RoleBindingModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "role_bindings"
    __table_args__ = (Index("ix_role_bindings_org_user", "organization_id", "user_id", unique=True),)

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. OWNER, ADMIN, VIEWER
