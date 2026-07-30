from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.outbox_event import OutboxEventModel
from packages.shared.events import EventEnvelope, EventPublisher


class OutboxEventPublisher(EventPublisher):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def publish(self, event: EventEnvelope) -> None:
        outbox_event = OutboxEventModel(
            id=event.event_id,
            event_type=event.event_type,
            organization_id=event.organization_id,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            aggregate_version=event.aggregate_version,
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            schema_version=event.schema_version,
            payload=event.payload,
            occurred_at=event.occurred_at,
        )
        self.session.add(outbox_event)
        # Flush to ensure it's written in the current transaction, but not committed yet
        await self.session.flush()


def create_indexing_requested_event(org_id: UUID, repo_id: UUID, job_id: UUID) -> EventEnvelope:
    return EventEnvelope(
        event_type="repository.memory.indexing_requested",
        aggregate_type="repository",
        aggregate_id=str(repo_id),
        organization_id=str(org_id),
        payload={"organization_id": str(org_id), "job_id": str(job_id)},
    )


def create_indexing_started_event(org_id: UUID, repo_id: UUID, job_id: UUID, commit_sha: str) -> EventEnvelope:
    return EventEnvelope(
        event_type="repository.memory.indexing_started",
        aggregate_type="repository",
        aggregate_id=str(repo_id),
        organization_id=str(org_id),
        payload={"organization_id": str(org_id), "job_id": str(job_id), "commit_sha": commit_sha},
    )


def create_file_parsed_event(org_id: UUID, repo_id: UUID, file_path: str, symbols_count: int) -> EventEnvelope:
    return EventEnvelope(
        event_type="repository.memory.file_parsed",
        aggregate_type="repository",
        aggregate_id=str(repo_id),
        organization_id=str(org_id),
        payload={
            "organization_id": str(org_id),
            "file_path": file_path,
            "symbols_extracted": symbols_count,
        },
    )


def create_indexing_completed_event(org_id: UUID, repo_id: UUID, job_id: UUID, version_id: UUID) -> EventEnvelope:
    return EventEnvelope(
        event_type="repository.memory.indexing_completed",
        aggregate_type="repository",
        aggregate_id=str(repo_id),
        organization_id=str(org_id),
        payload={
            "organization_id": str(org_id),
            "job_id": str(job_id),
            "memory_version_id": str(version_id),
        },
    )


def create_indexing_failed_event(org_id: UUID, repo_id: UUID, job_id: UUID, error: str) -> EventEnvelope:
    return EventEnvelope(
        event_type="repository.memory.indexing_failed",
        aggregate_type="repository",
        aggregate_id=str(repo_id),
        organization_id=str(org_id),
        payload={"organization_id": str(org_id), "job_id": str(job_id), "error": error},
    )


def create_version_created_event(org_id: UUID, repo_id: UUID, version_id: UUID, version_number: int) -> EventEnvelope:
    return EventEnvelope(
        event_type="repository.memory.version_created",
        aggregate_type="repository",
        aggregate_id=str(repo_id),
        organization_id=str(org_id),
        payload={
            "organization_id": str(org_id),
            "version_id": str(version_id),
            "version": version_number,
        },
    )
