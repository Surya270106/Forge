from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.context import (
    AgentInteractionModel,
    ContextSnapshotModel,
    ModelProvider,
    PromptTemplateModel,
)
from packages.database.models.memory import SymbolModel
from packages.shared.identifiers import generate_id

from .events import (
    ContextEventPublisher,
    create_agent_invoked_event,
    create_context_assembled_event,
)

logger = structlog.get_logger(__name__)


class ContextAssembler:
    """Gathers Repository Memory data to build the context."""

    def __init__(self, session: AsyncSession, organization_id: UUID):
        self.session = session
        self.organization_id = organization_id

    async def assemble_context(self, repository_id: UUID, query: str) -> dict[str, Any]:
        # In a real scenario, this would use semantic search or BM25 to rank symbols.
        # We'll pull a subset of symbols as mocked relevant context.
        stmt = (
            select(SymbolModel)
            .where(
                SymbolModel.organization_id == self.organization_id,
                SymbolModel.repository_id == repository_id,
            )
            .limit(10)
        )

        symbols = (await self.session.execute(stmt)).scalars().all()

        return {
            "query": query,
            "symbols": [{"name": s.name, "file_path": str(s.source_file_id), "kind": s.symbol_type} for s in symbols],
        }


from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment


class PromptManager:
    """Renders Jinja2 templates using assembled context in a secure sandbox."""

    @staticmethod
    def render(template_text: str, context: dict[str, Any]) -> str:
        # Use SandboxedEnvironment to prevent RCE from prompt injection
        env = SandboxedEnvironment(autoescape=True, undefined=StrictUndefined)
        template = env.from_string(template_text)
        rendered = template.render(**context)
        return rendered


class AgentOrchestrator:
    """Handles LLM invocations and records interactions."""

    def __init__(self, session: AsyncSession, organization_id: UUID):
        self.session = session
        self.organization_id = organization_id
        self.publisher = ContextEventPublisher(session)
        self.assembler = ContextAssembler(session, organization_id)

    async def invoke_agent(self, repository_id: UUID, query: str, template_name: str, plan_id: UUID | None = None) -> AgentInteractionModel:
        # 1. Fetch Template
        stmt_template = select(PromptTemplateModel).where(PromptTemplateModel.name == template_name)
        template = (await self.session.execute(stmt_template)).scalars().first()
        if not template:
            # Fallback mock template if none exist
            template = PromptTemplateModel(
                name=template_name,
                template_text="Please solve the user query.",
                default_provider=ModelProvider.LOCAL,
                default_model="mock-model",
            )

        # 2. Assemble Context
        context_data = await self.assembler.assemble_context(repository_id, query)

        # 3. Render Prompt
        rendered_prompt = PromptManager.render(template.template_text, context_data)

        # 4. Save Snapshot
        snapshot = ContextSnapshotModel(
            id=generate_id(),
            organization_id=self.organization_id,
            repository_id=repository_id,
            plan_id=plan_id,
            assembled_prompt=rendered_prompt,
            context_data=context_data,
            tokens_estimated=len(rendered_prompt) // 4,
        )
        self.session.add(snapshot)
        await self.session.flush()

        await self.publisher.publish(create_context_assembled_event(self.organization_id, repository_id, snapshot.id, plan_id))

        # 5. Invoke LLM (Mocked)
        mock_response = "Here is the plan to achieve your intent..."
        mock_tools = [{"type": "function", "name": "create_plan", "arguments": {}}]

        # 6. Save Interaction
        interaction = AgentInteractionModel(
            id=generate_id(),
            organization_id=self.organization_id,
            repository_id=repository_id,
            context_snapshot_id=snapshot.id,
            provider=template.default_provider,
            model=template.default_model,
            response_text=mock_response,
            tool_calls=mock_tools,
            prompt_tokens=snapshot.tokens_estimated,
            completion_tokens=len(mock_response) // 4,
            latency_ms=1500,
        )
        self.session.add(interaction)
        await self.session.flush()

        await self.publisher.publish(create_agent_invoked_event(self.organization_id, repository_id, interaction.id))
        await self.session.commit()

        return interaction
