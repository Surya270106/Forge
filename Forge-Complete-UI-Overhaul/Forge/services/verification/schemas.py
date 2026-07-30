from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from packages.database.models.verification import VerificationStatus


class VerificationResultSchema(BaseModel):
    id: UUID
    verifier: str
    status: VerificationStatus
    exit_code: int | None
    duration_ms: int | None
    stdout: str | None
    stderr: str | None
    stdout_truncated: bool
    stderr_truncated: bool
    blocking: bool
    attempt: int
    diagnostics: list[dict[str, Any]]
    started_at: datetime | None
    finished_at: datetime | None

    class Config:
        from_attributes = True


class VerificationJobResponse(BaseModel):
    id: UUID
    organization_id: UUID
    repository_id: UUID
    execution_job_id: UUID
    status: VerificationStatus
    started_at: datetime | None
    finished_at: datetime | None
    results: list[VerificationResultSchema] = []

    class Config:
        from_attributes = True


class TriggerVerificationRequest(BaseModel):
    pass
