from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from packages.database.models.memory import IndexingStatus


class IndexRepositoryRequest(BaseModel):
    branch: str | None = Field(default=None, description="Branch to index, defaults to repository default")
    force_reindex: bool = Field(default=False, description="Force reindexing of all files ignoring checksums")


class IndexingJobResponse(BaseModel):
    id: UUID
    repository_id: UUID
    organization_id: UUID
    status: IndexingStatus
    commit_sha: str
    branch: str
    started_at: datetime | None
    finished_at: datetime | None

    class Config:
        from_attributes = True


class SymbolResponse(BaseModel):
    id: UUID
    name: str
    qualname: str
    symbol_type: str
    line_start: int
    line_end: int
    snippet: str
    source_file_id: UUID

    class Config:
        from_attributes = True


class DependencyEdgeResponse(BaseModel):
    id: UUID
    from_file_id: UUID
    to_file_id: UUID | None
    import_statement: str
    is_external: bool

    class Config:
        from_attributes = True
