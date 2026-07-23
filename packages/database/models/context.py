from enum import Enum as PyEnum
from uuid import UUID

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from packages.database.base import Base, IdMixin, TimestampMixin


class ModelProvider(str, PyEnum):
    ANTHROPIC = "ANTHROPIC"
    OPENAI = "OPENAI"
    GOOGLE = "GOOGLE"
    LOCAL = "LOCAL"


class PromptTemplateModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "prompt_templates"
    __table_args__ = (Index("ix_prompt_name", "name", unique=True),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_text: Mapped[str] = mapped_column(Text, nullable=False)  # Jinja2 template
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_provider: Mapped[ModelProvider] = mapped_column(
        SAEnum(ModelProvider, name="model_provider"),
        default=ModelProvider.ANTHROPIC,
        nullable=False,
    )
    default_model: Mapped[str] = mapped_column(String(255), nullable=False)


class ContextSnapshotModel(IdMixin, TimestampMixin, Base):
    """Stores the fully assembled context injected into an LLM call for trace/debug."""

    __tablename__ = "context_snapshots"
    __table_args__ = (
        Index("ix_context_repo_org", "repository_id", "organization_id"),
        Index("ix_context_plan", "plan_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    plan_id: Mapped[UUID | None] = mapped_column(ForeignKey("plans.id"), nullable=True)

    assembled_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    context_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    tokens_estimated: Mapped[int] = mapped_column(default=0, nullable=False)


class AgentInteractionModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "agent_interactions"
    __table_args__ = (
        Index("ix_agent_repo_org", "repository_id", "organization_id"),
        Index("ix_agent_snapshot", "context_snapshot_id"),
    )

    organization_id: Mapped[UUID] = mapped_column(nullable=False)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    context_snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("context_snapshots.id"), nullable=False)

    provider: Mapped[ModelProvider] = mapped_column(SAEnum(ModelProvider, name="model_provider"), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)

    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)

    prompt_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(default=0, nullable=False)
