from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from packages.database.models.planning import PlanStatus


class CreatePlanRequest(BaseModel):
    intent: str = Field(..., description="The natural language intent or goal")
    memory_version_id: UUID | None = Field(None, description="The specific repository memory version to use")


class TaskNodeSchema(BaseModel):
    id: UUID
    action_type: str
    target: str
    parameters: dict[str, Any]

    class Config:
        from_attributes = True


class TaskEdgeSchema(BaseModel):
    id: UUID
    from_node_id: UUID
    to_node_id: UUID
    condition: str | None

    class Config:
        from_attributes = True


class PlanResponse(BaseModel):
    id: UUID
    organization_id: UUID
    repository_id: UUID
    memory_version_id: UUID | None
    status: PlanStatus
    intent: str
    nodes: list[TaskNodeSchema] = []
    edges: list[TaskEdgeSchema] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ApprovePlanRequest(BaseModel):
    pass
