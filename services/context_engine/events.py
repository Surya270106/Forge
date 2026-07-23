from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from packages.database.models.outbox_event import OutboxEventModel
from packages.shared.events import EventEnvelope, EventPublisher


class ContextEventPublisher(EventPublisher):
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


def create_context_assembled_event(org_id: UUID, repo_id: UUID, snapshot_id: UUID, plan_id: UUID = None) -> EventEnvelope:
    return EventEnvelope(
        event_type="context.assembled",
        aggregate_type="context_snapshot",
        aggregate_id=str(snapshot_id),
        organization_id=str(org_id),
        payload={
            "organization_id": str(org_id),
            "repository_id": str(repo_id),
            "plan_id": str(plan_id) if plan_id else None,
        },
    )


def create_agent_invoked_event(org_id: UUID, repo_id: UUID, interaction_id: UUID) -> EventEnvelope:
    return EventEnvelope(
        event_type="agent.invoked",
        aggregate_type="agent_interaction",
        aggregate_id=str(interaction_id),
        organization_id=str(org_id),
        payload={"organization_id": str(org_id), "repository_id": str(repo_id)},
    )
