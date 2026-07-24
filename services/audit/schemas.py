from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: UUID
    organization_id: UUID
    repository_id: UUID | None = None
    actor_id: UUID | None = None
    actor_type: str
    action: str
    resource_type: str
    resource_id: UUID | None = None
    metadata_payload: dict
    timestamp: datetime
