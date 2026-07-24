from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from packages.database.models.patch import PatchStatus


class PatchResponse(BaseModel):
    id: UUID
    organization_id: UUID
    repository_id: UUID
    execution_job_id: UUID
    task_id: UUID | None
    status: PatchStatus
    total_additions: int
    total_deletions: int
    files_changed: int
    pull_request_url: str | None
    pull_request_number: int | None
    branch_name: str | None
    commit_sha: str | None
    reviewed_at: datetime | None
    reviewed_by: UUID | None

    class Config:
        from_attributes = True


class AcceptPatchRequest(BaseModel):
    pass


class RejectPatchRequest(BaseModel):
    pass


class RevisePatchRequest(BaseModel):
    feedback: str
