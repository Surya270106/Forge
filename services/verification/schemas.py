from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from packages.database.models.verification import DiagnosticType, VerificationStatus


class VerificationResultSchema(BaseModel):
    id: UUID
    diagnostic_type: DiagnosticType
    is_passed: bool
    output: str
    parsed_diagnostics: list[dict[str, Any]]

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
