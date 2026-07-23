from uuid import UUID

from packages.shared.events import EventEnvelope, EventPublisher
from packages.database.models.outbox_event import OutboxEventModel
from sqlalchemy.ext.asyncio import AsyncSession


class ImportEventPublisher(EventPublisher):
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
        await self.session.flush()


def create_import_started_event(org_id: UUID, repo_id: UUID, job_id: UUID) -> EventEnvelope:
    return EventEnvelope(
        event_type="repository.import_started",
        organization_id=str(org_id),
        aggregate_type="repository",
        aggregate_id=str(repo_id),
        payload={"job_id": str(job_id)},
    )
