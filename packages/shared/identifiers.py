from typing import NewType
from uuid import UUID

try:
    from uuid_extensions import uuid7
except ImportError:
    import uuid as _uuid_mod

    uuid7 = _uuid_mod.uuid4  # fallback

RepositoryId = NewType("RepositoryId", UUID)
ImportId = NewType("ImportId", UUID)
WorkspaceId = NewType("WorkspaceId", UUID)
OrganizationId = NewType("OrganizationId", UUID)
PlanId = NewType("PlanId", UUID)
ExecutionId = NewType("ExecutionId", UUID)
VerificationId = NewType("VerificationId", UUID)
CorrelationId = NewType("CorrelationId", str)
EventId = NewType("EventId", UUID)
JobId = NewType("JobId", UUID)
MemoryVersionId = NewType("MemoryVersionId", UUID)


def generate_id() -> UUID:
    return uuid7()


def generate_correlation_id() -> CorrelationId:
    return CorrelationId(str(uuid7()))
