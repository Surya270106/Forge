from typing import Any
from uuid import UUID

from pydantic import BaseModel

from packages.database.models.context import ModelProvider


class ContextSnapshotResponse(BaseModel):
    id: UUID
    organization_id: UUID
    repository_id: UUID
    plan_id: UUID | None
    assembled_prompt: str
    tokens_estimated: int

    class Config:
        from_attributes = True


class AgentInteractionResponse(BaseModel):
    id: UUID
    organization_id: UUID
    repository_id: UUID
    context_snapshot_id: UUID
    provider: ModelProvider
    model: str
    response_text: str
    tool_calls: list[dict[str, Any]]
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int

    class Config:
        from_attributes = True
