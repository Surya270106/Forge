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

        # 5. Invoke LLM (Real Implementation)

        import httpx

        from packages.database.models.auth import OrganizationModel

        org = await self.session.get(OrganizationModel, self.organization_id)
        provider_config = org.provider_config or {} if org else {}
        api_key = provider_config.get("api_key")
        provider = provider_config.get("provider", "openai").lower()
        model_name = provider_config.get("model", "gpt-4o")

        response_text = ""
        tool_calls = []

        if not api_key:
            # Fallback to mock for local testing without key
            response_text = (
                '{"nodes": [{"id": "install", "type": "command", "target": "workspace", "parameters": {"command": "echo mock"}}], "edges": []}'
            )
        else:
            async with httpx.AsyncClient() as client:
                if provider == "openai":
                    resp = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json={
                            "model": model_name,
                            "messages": [{"role": "user", "content": rendered_prompt}],
                            "response_format": {"type": "json_object"},
                        },
                        timeout=60.0,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        response_text = data["choices"][0]["message"]["content"]
                    else:
                        raise Exception(f"OpenAI error: {resp.text}")
                elif provider == "anthropic":
                    resp = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                        json={"model": model_name, "max_tokens": 4000, "messages": [{"role": "user", "content": rendered_prompt}]},
                        timeout=60.0,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        response_text = data["content"][0]["text"]
                    else:
                        raise Exception(f"Anthropic error: {resp.text}")
                else:
                    raise Exception(f"Unsupported provider: {provider}")

        # 6. Save Interaction
        interaction = AgentInteractionModel(
            id=generate_id(),
            organization_id=self.organization_id,
            repository_id=repository_id,
            context_snapshot_id=snapshot.id,
            provider=provider,
            model=model_name,
            response_text=response_text,
            tool_calls=tool_calls,
            prompt_tokens=snapshot.tokens_estimated,
            completion_tokens=len(response_text) // 4,
            latency_ms=1500,
        )
        self.session.add(interaction)
        await self.session.flush()

        await self.publisher.publish(create_agent_invoked_event(self.organization_id, repository_id, interaction.id))
        await self.session.commit()

        return interaction
