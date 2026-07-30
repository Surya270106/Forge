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
            .limit(20)
        )
        symbols = (await self.session.execute(stmt)).scalars().all()

        from packages.database.models.memory import SourceFileModel
        file_stmt = (
            select(SourceFileModel)
            .where(
                SourceFileModel.organization_id == self.organization_id,
                SourceFileModel.repository_id == repository_id,
            )
            .limit(50)
        )
        files = (await self.session.execute(file_stmt)).scalars().all()

        return {
            "query": query,
            "symbols": [{"name": s.name, "file_path": str(s.source_file_id), "kind": s.symbol_type} for s in symbols],
            "files": [{"path": f.file_path} for f in files],
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
                template_text="Please solve the user query.\n\nQuery: {{ query }}\n\nReturn the result in JSON format.",
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

        # 5. Invoke LLM (Real Implementation using LiteLLM)
        from litellm import acompletion
        from litellm.exceptions import APIError, APIConnectionError, RateLimitError
        from packages.database.models.auth import OrganizationModel
        from packages.shared.crypto import CryptoService

        org = await self.session.get(OrganizationModel, self.organization_id)
        provider_config = org.provider_config or {} if org else {}
        api_key = CryptoService.decrypt(provider_config.get("api_key", ""))
        # For litellm, model names often include the provider e.g. "groq/llama3-8b-8192" or "anthropic/claude-3-opus-20240229"
        # If the model name doesn't include the provider, we can format it.
        provider = provider_config.get("provider", "openai").lower()
        base_model_name = provider_config.get("model", "gpt-4o")
        
        # Format model string for litellm if it's not already prefixed
        if "/" not in base_model_name and provider != "openai":
            model_name = f"{provider}/{base_model_name}"
        else:
            model_name = base_model_name

        budget_usd = float(provider_config.get("budget_usd", 100.0))
        spend_usd = float(provider_config.get("spend_usd", 0.0))

        if spend_usd >= budget_usd:
            raise Exception(f"Budget exceeded. Spent ${spend_usd:.2f} of ${budget_usd:.2f} budget.")

        response_text = ""
        tool_calls = []

        if not api_key:
            # Fallback to mock for local testing without key
            response_text = (
                '{"nodes": [{"id": "install", "type": "command", "target": "workspace", "parameters": {"command": "echo mock"}}], "edges": []}'
            )
        else:
            try:
                # Set the API key dynamically for this request
                # LiteLLM automatically handles mapping the api key to the right header
                # We can pass `api_key` directly to acompletion
                response = await acompletion(
                    model=model_name,
                    messages=[{"role": "user", "content": rendered_prompt}],
                    api_key=api_key,
                    response_format={"type": "json_object"} if "openai" in provider or "groq" in provider else None,
                )
                response_text = response.choices[0].message.content or ""
            except (APIError, APIConnectionError, RateLimitError) as e:
                raise Exception(f"LLM API Error: {str(e)}")
            except Exception as e:
                raise Exception(f"Unexpected error calling litellm: {str(e)}")

        # 6. Save Interaction
        interaction = AgentInteractionModel(
            id=generate_id(),
            organization_id=self.organization_id,
            repository_id=repository_id,
            context_snapshot_id=snapshot.id,
            provider=ModelProvider(provider.upper()),
            model=model_name,
            response_text=response_text,
            tool_calls=tool_calls,
            prompt_tokens=snapshot.tokens_estimated,
            completion_tokens=len(response_text) // 4,
            latency_ms=1500,
        )
        self.session.add(interaction)

        # 7. Update Spend (simplified cost estimation)
        cost_per_1k_tokens = 0.01
        estimated_cost = ((snapshot.tokens_estimated + (len(response_text) // 4)) / 1000.0) * cost_per_1k_tokens
        if org and org.provider_config:
            new_config = dict(org.provider_config)
            new_config["spend_usd"] = new_config.get("spend_usd", 0.0) + estimated_cost
            org.provider_config = new_config

        await self.session.flush()

        await self.publisher.publish(create_agent_invoked_event(self.organization_id, repository_id, interaction.id))
        await self.session.commit()

        return interaction
