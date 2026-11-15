from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from packages.database.models.execution import ExecutionStatus


class ExecutionJobResponse(BaseModel):
    id: UUID
    organization_id: UUID
    repository_id: UUID
    plan_id: UUID
    status: ExecutionStatus
    commit_sha_before: str
    commit_sha_after: str | None
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    cancellation_requested_at: datetime | None = None
    cancellation_requested_by: UUID | None = None

    class Config:
        from_attributes = True


class CancelExecutionResponse(BaseModel):
    id: UUID
    status: ExecutionStatus
    cancellation_status: str
    cancellation_requested_at: datetime | None

class ExecutionLogResponse(BaseModel):
    id: UUID
    task_node_id: UUID | None
    level: str
    message: str
    stream: str
    created_at: datetime

    class Config:
        from_attributes = True


class StartExecutionRequest(BaseModel):
    pass
