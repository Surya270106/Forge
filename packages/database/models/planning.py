from enum import StrEnum
from uuid import UUID

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from packages.database.base import Base, IdMixin, TimestampMixin


class PlanStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SUPERSEDED = "SUPERSEDED"


class PlanModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "plans"
    __table_args__ = (
        Index("ix_plans_repo_org", "repository_id", "organization_id"),
        Index("ix_plans_status", "status"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    memory_version_id: Mapped[UUID | None] = mapped_column(ForeignKey("repository_memory_versions.id"), nullable=True)

    status: Mapped[PlanStatus] = mapped_column(
        SAEnum(PlanStatus, name="plan_status"),
        default=PlanStatus.DRAFT,
        nullable=False,
    )
    intent: Mapped[str] = mapped_column(Text, nullable=False)
    context_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    
    parent_plan_id: Mapped[UUID | None] = mapped_column(ForeignKey("plans.id"), nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    nodes: Mapped[list["TaskNodeModel"]] = relationship("TaskNodeModel", back_populates="plan", cascade="all, delete-orphan")


class TaskNodeModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "task_nodes"
    __table_args__ = (Index("ix_task_nodes_plan_org", "plan_id", "organization_id"),)

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    plan_id: Mapped[UUID] = mapped_column(ForeignKey("plans.id"), nullable=False)

    action_type: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g., 'edit_file', 'run_command'
    target: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    plan: Mapped["PlanModel"] = relationship("PlanModel", back_populates="nodes")


class TaskEdgeModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "task_edges"
    __table_args__ = (
        Index("ix_task_edges_plan_org", "plan_id", "organization_id"),
        Index("ix_task_edges_from", "from_node_id"),
        Index("ix_task_edges_to", "to_node_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    plan_id: Mapped[UUID] = mapped_column(ForeignKey("plans.id"), nullable=False)

    from_node_id: Mapped[UUID] = mapped_column(ForeignKey("task_nodes.id"), nullable=False)
    to_node_id: Mapped[UUID] = mapped_column(ForeignKey("task_nodes.id"), nullable=False)

    condition: Mapped[str | None] = mapped_column(String(255), nullable=True)  # e.g. "on_success", "on_failure"
