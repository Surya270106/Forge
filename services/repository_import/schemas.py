from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ImportRepositoryRequest(BaseModel):
    clone_url: str = Field(..., description="Git clone URL of the repository")
    owner: str = Field(..., description="Repository owner/organization")
    name: str = Field(..., description="Repository name")
    branch: str = Field(default="main", description="Branch to import")
    is_private: bool = Field(default=False, description="Whether the repository is private")


class ImportRepositoryResponse(BaseModel):
    repository_id: UUID
    import_job_id: UUID
    status: str
    message: str


class RepositoryResponse(BaseModel):
    id: UUID
    organization_id: UUID
    owner: str
    name: str
    full_name: str
    clone_url: str
    default_branch: str
    status: str
    primary_language: str | None
    total_files: int
    total_size_bytes: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ImportJobResponse(BaseModel):
    id: UUID
    repository_id: UUID
    organization_id: UUID
    status: str
    branch: str
    started_at: datetime | None
    finished_at: datetime | None

    class Config:
        from_attributes = True
